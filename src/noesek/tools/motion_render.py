"""Own-code renderer for a motion_storyboard plan: PIL draws every frame, the ffmpeg binary encodes H.264.
No Remotion code, no paid generation, no network. Remotion's license limits companies above three
employees and bars reselling derivatives, so it is not bundled; this renderer is the default path.
Bounded: frames, size and encode time are capped. Output is checked by decoding it back.
"""
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from pydantic import BaseModel,Field
from .motion_storyboard import MotionStoryboardInput,motion_storyboard
from .. import filestore
MAX_FRAMES=1800
_FONTS=('DejaVuSans-Bold.ttf','DejaVuSans.ttf','NotoSans-Bold.ttf','LiberationSans-Bold.ttf','Arial.ttf')
class MotionRenderInput(BaseModel):
    storyboard:MotionStoryboardInput
    width:int=Field(default=1280,ge=320,le=1920)
    height:int=Field(default=720,ge=240,le=1080)
    reduced_motion:bool=False
    background:str=Field(default='#101418',pattern=r'^#[0-9a-fA-F]{6}$')
    foreground:str=Field(default='#F4F1EA',pattern=r'^#[0-9a-fA-F]{6}$')
    accent:str=Field(default='#F2B84B',pattern=r'^#[0-9a-fA-F]{6}$')
    output_name:str=Field(default='motion.mp4',pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,60}\.mp4$')

def _font(size):
    from PIL import ImageFont
    for name in _FONTS:
        try:return ImageFont.truetype(name,size)
        except OSError:continue
    return ImageFont.load_default(size)
def _ease(t):return 1-(1-min(max(t,0),1))**3
def _hex(c):return tuple(int(c[i:i+2],16) for i in (1,3,5))
def _wrap(draw,text,font,limit):
    lines=[];cur=''
    for word in text.split():
        trial=(cur+' '+word).strip()
        if cur and draw.textlength(trial,font=font)>limit:lines.append(cur);cur=word
        else:cur=trial
    return lines+([cur] if cur else [])

def frame_scene(scenes,frame):
    """Scene whose [start_frame,end_frame) holds this frame, else None (gaps stay blank by design)."""
    for s in scenes:
        if s['start_frame']<=frame<s['end_frame']:return s
    return None

def draw_frame(scene,frame,inp):
    from PIL import Image,ImageDraw
    w,h=inp.width,inp.height
    img=Image.new('RGB',(w,h),_hex(inp.background));d=ImageDraw.Draw(img)
    if scene is None:return img
    into=frame-scene['start_frame']
    k=1.0 if inp.reduced_motion else _ease(into/6)
    fg=tuple(round(b+(f-b)*k) for b,f in zip(_hex(inp.background),_hex(inp.foreground)))
    size=round(h*0.2*(1 if inp.reduced_motion else 0.9+0.1*k))
    font=_font(size);margin=round(w*0.08)
    word=scene['word']
    while d.textlength(word,font=font)>w-2*margin and size>16:size-=4;font=_font(size)
    tw=d.textlength(word,font=font)
    d.text(((w-tw)/2,h*0.36-size/2),word,font=font,fill=fg)
    if scene['visual']!='No extra graphic':
        cap=_font(round(h*0.05));y=h*0.62
        for line in _wrap(d,scene['visual'],cap,w-2*margin)[:4]:
            lw=d.textlength(line,font=cap);d.text(((w-lw)/2,y),line,font=cap,fill=_hex(inp.accent));y+=h*0.065
    return img

def render_to_path(inp,out_path):
    plan=motion_storyboard(inp.storyboard)
    if not plan['ok']:return plan
    total=plan['scenes'][-1]['end_frame']
    if total>MAX_FRAMES:return {'ok':False,'error':f'{total} frames exceeds the {MAX_FRAMES} frame cap; shorten or split the script'}
    ffmpeg=shutil.which('ffmpeg')
    if not ffmpeg:return {'ok':False,'error':'ffmpeg binary not installed; storyboard plan is still valid'}
    fps=plan['fps'];scenes=plan['scenes']
    with tempfile.TemporaryDirectory(prefix='noesek-motion-') as tmp:
        for f in range(total):draw_frame(frame_scene(scenes,f),f,inp).save(f'{tmp}/f{f:05d}.png')
        cmd=[ffmpeg,'-v','error','-y','-framerate',str(fps),'-i',f'{tmp}/f%05d.png','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(out_path)]
        try:proc=subprocess.run(cmd,capture_output=True,timeout=120)
        except subprocess.TimeoutExpired:return {'ok':False,'error':'ffmpeg encode exceeded 120 seconds'}
        if proc.returncode:return {'ok':False,'error':'ffmpeg failed: '+proc.stderr.decode('utf-8','replace')[:200]}
    probe=probe_video(out_path)
    if not probe['ok']:return probe
    return {'ok':True,'frames':total,'fps':fps,'seconds':round(total/fps,3),'width':inp.width,'height':inp.height,
            'probe':probe,'scenes':len(scenes),'reduced_motion':inp.reduced_motion,'rendered':True,
            'caveat':'Visuals are text on a plain background from the supplied storyboard; audio is not included, timing follows caller-supplied word times. Inspect frames before publishing.'}

def probe_video(path):
    probe=shutil.which('ffprobe')
    if not probe:return {'ok':False,'error':'ffprobe not installed; encode not verified'}
    out=subprocess.run([probe,'-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames,width,height,codec_name,pix_fmt,duration','-of','json',str(path)],capture_output=True,timeout=60)
    if out.returncode:return {'ok':False,'error':'ffprobe could not read the output'}
    s=json.loads(out.stdout)['streams'][0]
    return {'ok':True,'frames':int(s['nb_read_frames']),'codec':s['codec_name'],'pix_fmt':s['pix_fmt'],'width':s['width'],'height':s['height'],'duration':float(s.get('duration') or 0)}

def motion_render(inp):
    with tempfile.TemporaryDirectory(prefix='noesek-motion-out-') as tmp:
        path=Path(tmp)/inp.output_name
        res=render_to_path(inp,path)
        if not res['ok']:return res
        data=path.read_bytes()
    try:filestore.write_file(inp.output_name,data)
    except filestore.FileStoreError as exc:return {'ok':False,'error':str(exc)}
    return res|{'file':inp.output_name,'download':f'/files/{inp.output_name}','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


_REMOTION_ROOT='''import React from 'react';
import {AbsoluteFill, Composition, registerRoot, useCurrentFrame, interpolate, Easing} from 'remotion';
import scenes from './scenes.json';
const Scene: React.FC = () => {
  const frame = useCurrentFrame();
  const s = scenes.scenes.find((x) => frame >= x.start_frame && frame < x.end_frame);
  if (!s) return <AbsoluteFill style={{backgroundColor: scenes.background}} />;
  const t = scenes.reduced_motion ? 1 : interpolate(frame - s.start_frame, [0, 6], [0, 1], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{backgroundColor: scenes.background, alignItems: 'center', justifyContent: 'center', fontFamily: 'sans-serif', fontWeight: 700}}>
      <div style={{color: scenes.foreground, opacity: t, fontSize: scenes.height * 0.2, transform: `scale(${0.9 + 0.1 * t})`}}>{s.word}</div>
      {s.visual !== 'No extra graphic' ? <div style={{color: scenes.accent, fontSize: scenes.height * 0.05, marginTop: scenes.height * 0.08}}>{s.visual}</div> : null}
    </AbsoluteFill>
  );
};
const Root: React.FC = () => (
  <Composition id="Storyboard" component={Scene} durationInFrames={scenes.total_frames} fps={scenes.fps} width={scenes.width} height={scenes.height} />
);
registerRoot(Root);
'''

def export_remotion_project(inp):
    """Own-written Remotion project files (text) for the same storyboard. Remotion itself is NOT bundled:
    the owner installs it under their own license (free for individuals and up to three employees)."""
    plan=motion_storyboard(inp.storyboard)
    if not plan['ok']:return plan
    total=plan['scenes'][-1]['end_frame']
    data={'scenes':plan['scenes'],'fps':plan['fps'],'total_frames':total,'width':inp.width,'height':inp.height,
          'background':inp.background,'foreground':inp.foreground,'accent':inp.accent,'reduced_motion':inp.reduced_motion}
    pkg={'name':'noesek-motion','private':True,'scripts':{'render':'remotion render src/index.tsx Storyboard out.mp4'},
         'dependencies':{'remotion':'4.0.532','@remotion/cli':'4.0.532','react':'18.3.1','react-dom':'18.3.1'}}
    return {'ok':True,'files':{'package.json':json.dumps(pkg,indent=2),'src/index.tsx':_REMOTION_ROOT,
            'src/scenes.json':json.dumps(data,indent=1),'tsconfig.json':json.dumps({'compilerOptions':{'jsx':'react','resolveJsonModule':True,'esModuleInterop':True,'module':'commonjs','target':'es2020','strict':False,'skipLibCheck':True}},indent=2)},
            'license_note':'Remotion license: free for individuals, for-profit orgs up to 3 employees, non-profits; others need a company license. Check before use.',
            'caveat':'Generated source only. Not rendered or verified until run with Remotion installed.'}
