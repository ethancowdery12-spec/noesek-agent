import io
import shutil
import subprocess
import pytest
from PIL import Image,ImageChops
from noesek.tools.motion_render import MotionRenderInput,render_to_path,draw_frame,frame_scene,probe_video,motion_render,MAX_FRAMES
from noesek.tools.motion_storyboard import MotionStoryboardInput,WordBeat,motion_storyboard

needs_ffmpeg=pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='ffmpeg not installed')
def sb(fps=10):
    words=[WordBeat(text='one',start=0,end=0.5),WordBeat(text='two',start=0.5,end=1.0),WordBeat(text='money',start=1.2,end=2.0)]
    return MotionStoryboardInput(words=words,beats={2:'Show the saved amount'},fps=fps)
def req(**kw):return MotionRenderInput(**({'storyboard':sb(),'width':320,'height':240}|kw))

def test_frames_follow_word_times_and_gap_is_blank():
    inp=req();scenes=motion_storyboard(inp.storyboard)['scenes']
    assert frame_scene(scenes,0)['word']=='one' and frame_scene(scenes,5)['word']=='two'
    assert frame_scene(scenes,11) is None
    blank=draw_frame(None,11,inp);word=draw_frame(frame_scene(scenes,2),2,inp)
    assert ImageChops.difference(blank,word).getbbox() is not None
    assert blank.getcolors(10) and len(blank.getcolors(10))==1

def test_each_word_frame_differs_and_caption_only_where_beat_exists():
    inp=req();scenes=motion_storyboard(inp.storyboard)['scenes']
    a=draw_frame(scenes[0],4,inp);c=draw_frame(scenes[2],18,inp)
    assert ImageChops.difference(a,c).getbbox() is not None
    low=lambda img:img.crop((0,int(inp.height*0.6),inp.width,inp.height)).getcolors(1000)
    assert len(low(a))==1 and len(low(c))>1   # plain bottom area vs caption text

def test_reduced_motion_has_no_fade_in():
    on=req();off=req(reduced_motion=True);scenes=motion_storyboard(on.storyboard)['scenes']
    first=lambda i:draw_frame(scenes[0],0,i);settled=lambda i:draw_frame(scenes[0],8,i)
    assert ImageChops.difference(first(off),settled(off)).getbbox() is None
    assert ImageChops.difference(first(on),settled(on)).getbbox() is not None

@needs_ffmpeg
def test_real_encode_decodes_back_with_exact_frame_count(tmp_path):
    out=tmp_path/'m.mp4';res=render_to_path(req(),out)
    assert res['ok'] and res['frames']==20 and res['probe']['frames']==20
    assert res['probe']['codec']=='h264' and res['probe']['pix_fmt']=='yuv420p' and res['probe']['width']==320
    assert out.stat().st_size>1000

@needs_ffmpeg
def test_decoded_video_frame_shows_the_spoken_word(tmp_path):
    out=tmp_path/'m.mp4';assert render_to_path(req(reduced_motion=True),out)['ok']
    png=subprocess.run(['ffmpeg','-v','error','-i',str(out),'-vf','select=eq(n\\,15)','-vframes','1','-f','image2pipe','-vcodec','png','-'],capture_output=True).stdout
    got=Image.open(io.BytesIO(png)).convert('RGB');inp=req(reduced_motion=True)
    want=draw_frame(frame_scene(motion_storyboard(inp.storyboard)['scenes'],15),15,inp)
    diff=ImageChops.difference(got,want).convert('L')
    assert max(diff.getdata())<60 and sum(diff.getdata())/len(diff.getdata())<3   # lossy codec tolerance

def test_bad_timing_and_frame_cap_fail_cleanly(tmp_path):
    bad=MotionRenderInput(storyboard=MotionStoryboardInput(words=[WordBeat(text='a',start=1,end=0)]))
    assert not render_to_path(bad,tmp_path/'x.mp4')['ok']
    long=MotionRenderInput(storyboard=MotionStoryboardInput(words=[WordBeat(text='a',start=0,end=MAX_FRAMES/30+5)]))
    assert 'cap' in render_to_path(long,tmp_path/'x.mp4')['error']

def test_output_name_and_color_validation():
    for kw in ({'output_name':'../x.mp4'},{'output_name':'x.exe'},{'background':'red'},{'width':100}):
        with pytest.raises(ValueError):req(**kw)

@needs_ffmpeg
def test_tool_writes_file_with_hash(monkeypatch):
    saved={}
    import noesek.tools.motion_render as mod
    monkeypatch.setattr(mod.filestore,'write_file',lambda n,c:saved.update({n:c}) or {})
    res=motion_render(req(output_name='demo.mp4'))
    assert res['ok'] and res['file']=='demo.mp4' and len(saved['demo.mp4'])==res['bytes']
    import hashlib;assert hashlib.sha256(saved['demo.mp4']).hexdigest()==res['sha256']


def test_remotion_export_matches_plan_and_pins_version():
    import json
    from noesek.tools.motion_render import export_remotion_project
    inp=req();out=export_remotion_project(inp);plan=motion_storyboard(inp.storyboard)
    assert out['ok'] and set(out['files'])=={'package.json','src/index.tsx','src/scenes.json','tsconfig.json'}
    data=json.loads(out['files']['src/scenes.json'])
    assert data['scenes']==plan['scenes'] and data['total_frames']==plan['scenes'][-1]['end_frame'] and data['fps']==10
    pkg=json.loads(out['files']['package.json']);assert pkg['dependencies']['remotion']=='4.0.532'
    assert 'registerRoot' in out['files']['src/index.tsx'] and 'license' in out['license_note'].lower()
    assert not export_remotion_project(MotionRenderInput(storyboard=MotionStoryboardInput(words=[WordBeat(text='a',start=1,end=0)])))['ok']
