"""Optional audited CPU OCR adapter, own code. No weight downloads or CUDA.
CPU inference is process-isolated with a hard deadline. Models must be picklable.
CUDA/Windows models need a separate audited service, not this adapter.
"""
from dataclasses import dataclass
from pathlib import Path
import io
import multiprocessing as mp
import tempfile
import time
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
    max_pages:int=20
    pdf_dpi:int=150
    pdf_deadline_seconds:float=300
    def __post_init__(self):
        if not (1<=self.max_bytes<=MAX_DOC_BYTES and 1<=self.max_chars<=MAX_MARKDOWN_CHARS and
                1<=self.max_pixels<=16000000 and 1<=self.max_dimension<=8192 and
                0<self.timeout_seconds<=120 and 1<=self.max_tokens<=8192 and
                1<=self.max_pages<=100 and 72<=self.pdf_dpi<=300 and 0<self.pdf_deadline_seconds<=1800):
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

def pdfium_pages(data,config):
    """Default renderer: yield (page_count, page_index, PIL image, note) using optional pypdfium2."""
    try:import pypdfium2 as pdfium
    except ImportError:raise RuntimeError('PDF rendering needs the optional pypdfium2 package')
    pdf=pdfium.PdfDocument(data)
    try:
        total=len(pdf)
        for index in range(min(total,config.max_pages)):
            page=pdf[index]
            try:
                width,height=page.get_size();scale=config.pdf_dpi/72;note=''
                if width*scale*height*scale>config.max_pixels or max(width,height)*scale>config.max_dimension:
                    scale=min((config.max_pixels/(width*height))**.5,config.max_dimension/max(width,height))
                    note=f'page {index+1} rendered at reduced scale to fit pixel limits'
                yield total,index,page.render(scale=scale).to_pil().convert('RGB'),note
            finally:page.close()
    finally:pdf.close()

class LocalOCR:
    def __init__(self,model=None,tokenizer=None,config=None,renderer=None):
        self.model=model;self.tokenizer=tokenizer;self.config=config or OCRConfig();self.renderer=renderer
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

    def read_pdf(self,data:bytes,filename:str='document.pdf')->DocResult:
        """Bounded PDF pipeline: render each page to PNG on CPU, OCR page by page, join as Markdown.
        Own code. Rendering uses the optional pypdfium2 package unless a renderer is injected.
        Page count, dpi, per-page deadline and total deadline are all capped by OCRConfig."""
        def fail(error):return DocResult(ok=False,engine='unlimited-ocr-pdf',error=error)
        cfg=self.config
        if not cfg.enabled or self.model is None or self.tokenizer is None:
            return fail('local audited model/tokenizer not configured; no model downloaded')
        if not data or len(data)>cfg.max_bytes:return fail('empty PDF or byte limit exceeded')
        if data.lstrip()[:5]!=b'%PDF-':return fail('not a PDF')
        start=time.monotonic();parts=[];warnings=[];clipped=False;total=0
        try:
            for total,index,image,note in (self.renderer or pdfium_pages)(data,cfg):
                if note:warnings.append(note)
                if time.monotonic()-start>cfg.pdf_deadline_seconds:
                    warnings.append(f'total PDF deadline reached after {index} pages');break
                buf=io.BytesIO();image.save(buf,format='PNG')
                result=self.read(buf.getvalue(),f'page-{index+1}.png')
                if not result.ok:warnings.append(f'page {index+1}: {result.error}');continue
                clipped=clipped or result.truncated
                parts.append(f'## Page {index+1}\n\n{result.markdown}')
        except RuntimeError as exc:return fail(str(exc))
        except Exception as exc:return fail(f'PDF pipeline failed: {type(exc).__name__}')
        if total<1:return fail('PDF has no pages')
        if total>cfg.max_pages:warnings.append(f'only first {cfg.max_pages} of {total} pages read (max_pages limit)')
        if not parts:return DocResult(ok=False,engine='unlimited-ocr-pdf',error='no page produced readable text',warnings=warnings)
        text='\n\n'.join(parts)
        warnings.append('Untrusted OCR output; wrap with content_guard. Live model quality and GPU readiness not verified.')
        return DocResult(ok=True,engine='unlimited-ocr-pdf',markdown=text[:cfg.max_chars],truncated=clipped or len(text)>cfg.max_chars,warnings=warnings)
