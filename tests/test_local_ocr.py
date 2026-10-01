import io
import time
from pathlib import Path
from PIL import Image
import pytest
from noesek.core.local_ocr import LocalOCR,OCRConfig

def image_bytes(size=(8,8)):
    buf=io.BytesIO();Image.new('RGB',size).save(buf,format='PNG');return buf.getvalue()
class Model:
    def infer(self,tokenizer,**kwargs):return 'recognized text'

def test_disabled_backend_does_not_download_or_load():
    out=LocalOCR().read(image_bytes(),'image.png')
    assert not out.ok and 'configured' in out.error

class TracedModel:
    def __init__(self,path):self.path=str(path)
    def infer(self,tokenizer,**kw):
        Path(self.path).write_text(kw['image_file']);assert Path(kw['image_file']).read_bytes()==image_bytes()
        assert not kw['save_results'] and kw['max_length']==4096
        return 'words'
class SlowModel:
    def infer(self,*a,**kw):time.sleep(10);return 'late'
class EmptyModel:
    def infer(self,*a,**kw):return None

def test_injected_model_and_parent_cleanup(tmp_path):
    trace=tmp_path/'path.txt'
    out=LocalOCR(TracedModel(trace),object(),OCRConfig(enabled=True)).read(image_bytes(),'x.png')
    assert out.ok and out.markdown=='words' and not Path(trace.read_text()).exists()

def test_decoded_and_compressed_bounds():
    o=LocalOCR(Model(),object(),OCRConfig(enabled=True,max_pixels=10,max_dimension=10))
    assert not o.read(image_bytes(),'x.png').ok
    assert not o.read(b'not an image','x.png').ok
    assert not o.read(image_bytes((2,2)),'x.jpg').ok
    assert not o.read(b'x','x.exe').ok
    assert not LocalOCR(Model(),object(),OCRConfig(enabled=True,max_bytes=3)).read(image_bytes(),'x.png').ok

def test_deadline_and_no_empty_success():
    start=time.monotonic()
    out=LocalOCR(SlowModel(),object(),OCRConfig(enabled=True,timeout_seconds=.05)).read(image_bytes(),'x.png')
    assert not out.ok and 'deadline' in out.error and time.monotonic()-start<2
    assert not LocalOCR(EmptyModel(),object(),OCRConfig(enabled=True)).read(image_bytes(),'x.png').ok
