"""Optional audited CPU OCR adapter, own code. No weight downloads or CUDA.
CPU inference is process-isolated with a hard deadline. Models must be picklable.
CUDA/Windows models need a separate audited service, not this adapter.
"""
from dataclasses import dataclass
from pathlib import Path
import io
import multiprocessing as mp
import tempfile
from .doc_ingest import DocResult,MAX_DOC_BYTES,MAX_MARKDOWN_CHARS

@dataclass(frozen=True)
class OCRConfig:
    enabled:bool=False
    max_bytes:int=MAX_DOC_BYTES
    max_chars:int=MAX_MARKDOWN_CHARS
    max_pixels:int=16000000
    max_dimension:int=8192
    timeout_seconds:float=30
    max_tokens:int=4096
    def __post_init__(self):
        if not (1<=self.max_bytes<=MAX_DOC_BYTES and 1<=self.max_chars<=MAX_MARKDOWN_CHARS and
                1<=self.max_pixels<=16000000 and 1<=self.max_dimension<=8192 and
                0<self.timeout_seconds<=120 and 1<=self.max_tokens<=8192):
            raise ValueError('OCR limits invalid')

def _infer_child(pipe,model,tokenizer,image,folder,config):
    try:
        text=model.infer(tokenizer,prompt='<image>document parsing.',image_file=str(image),output_path=folder,
            base_size=1024,image_size=640,crop_mode=True,max_length=config.max_tokens,
            no_repeat_ngram_size=35,ngram_window=128,save_results=False)
        if not isinstance(text,str) or not text.strip():pipe.send((False,'model returned no readable text',False))
        else:
            text=text.strip();pipe.send((True,text[:config.max_chars],len(text)>config.max_chars))
    except Exception as exc:pipe.send((False,f'local model failed: {type(exc).__name__}',False))
    finally:pipe.close()

class LocalOCR:
    def __init__(self,model=None,tokenizer=None,config=None):
        self.model=model;self.tokenizer=tokenizer;self.config=config or OCRConfig()
    def read(self,data:bytes,filename:str)->DocResult:
        def fail(error):return DocResult(ok=False,engine='unlimited-ocr',error=error)
        if not self.config.enabled or self.model is None or self.tokenizer is None:
            return fail('local audited model/tokenizer not configured; no model downloaded')
        if not data or len(data)>self.config.max_bytes:return fail('empty image or byte limit exceeded')
        suffix=Path(filename).suffix.lower()
        formats={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP'}
        if suffix not in formats:return fail('supported images only; PDF conversion needs a bounded pipeline')
        if str(getattr(self.model,'device','cpu')).split(':')[0]!='cpu':return fail('only audited CPU models supported by this isolated adapter')
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as img:
                if img.format!=formats[suffix] or getattr(img,'n_frames',1)!=1:return fail('format mismatch or animated image unsupported')
                width,height=img.size
                if width<=0 or height<=0 or max(width,height)>self.config.max_dimension or width*height>self.config.max_pixels:
                    return fail('decoded image dimensions/pixels exceed limits')
                img.verify()
            # Force bounded decode before model execution; verify alone does not decode.
            with Image.open(io.BytesIO(data)) as img:img.load()
            with tempfile.TemporaryDirectory(prefix='noesek-ocr-') as folder:
                image=Path(folder)/('input'+suffix);image.write_bytes(data)
                ctx=mp.get_context('spawn');parent,child=ctx.Pipe(duplex=False)
                worker=ctx.Process(target=_infer_child,args=(child,self.model,self.tokenizer,image,folder,self.config))
                try:worker.start()
                except Exception:
                    parent.close();child.close();raise
                child.close()
                try:
                    if not parent.poll(self.config.timeout_seconds):return fail('local inference deadline exceeded')
                    ok,text,clipped=parent.recv()
                finally:
                    if worker.is_alive():worker.terminate()
                    worker.join(timeout=2)
                    if worker.is_alive():worker.kill();worker.join()
                    parent.close()
            if not ok:return fail(text)
            return DocResult(ok=True,engine='unlimited-ocr',markdown=text,truncated=clipped,
                warnings=['Untrusted OCR output; wrap with content_guard. Live model quality and GPU readiness not verified.'])
        except Exception as exc:return fail(f'local OCR failed: {type(exc).__name__}')
