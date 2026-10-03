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


def scanned_pdf(pages=3):
    imgs=[Image.new('RGB',(120,160),(255,255,255)) for _ in range(pages)]
    buf=io.BytesIO();imgs[0].save(buf,format='PDF',save_all=True,append_images=imgs[1:]);return buf.getvalue()

def fake_renderer(count):
    # Injected so tests do not depend on a PDF rendering package being installed.
    def render(data,config):
        for index in range(min(count,config.max_pages)):yield count,index,Image.new('RGB',(40,40),'white'),''
    return render
def ocr(model=None,renderer=None,**cfg):
    return LocalOCR(model or Model(),object(),OCRConfig(enabled=True,**cfg),renderer=renderer)

def test_pdf_pipeline_reads_each_page_in_order():
    out=ocr(renderer=fake_renderer(3)).read_pdf(scanned_pdf(3),'scan.pdf')
    assert out.ok and out.engine=='unlimited-ocr-pdf'
    assert out.markdown.count('recognized text')==3
    assert out.markdown.index('## Page 1')<out.markdown.index('## Page 2')<out.markdown.index('## Page 3')

def test_pdf_page_cap_warns_and_reads_only_cap():
    out=ocr(renderer=fake_renderer(5),max_pages=2).read_pdf(scanned_pdf(5),'scan.pdf')
    assert out.ok and out.markdown.count('## Page')==2
    assert any('first 2 of 5' in w for w in out.warnings)

def test_pdf_rejects_non_pdf_disabled_and_oversize():
    assert not LocalOCR().read_pdf(scanned_pdf(1),'a.pdf').ok
    assert not ocr(renderer=fake_renderer(1)).read_pdf(b'not a pdf at all','a.pdf').ok
    assert not ocr(renderer=fake_renderer(1),max_bytes=10).read_pdf(scanned_pdf(1),'a.pdf').ok
    assert not ocr(renderer=fake_renderer(0)).read_pdf(scanned_pdf(1),'a.pdf').ok

def test_pdf_page_failure_is_reported_not_hidden():
    out=ocr(EmptyModel(),fake_renderer(2)).read_pdf(scanned_pdf(2),'a.pdf')
    assert not out.ok and any('page 1' in w for w in out.warnings)

def test_pdf_renderer_crash_is_a_clean_failure():
    def boom(data,config):raise ValueError('bad')
    yield_nothing=ocr(renderer=boom).read_pdf(scanned_pdf(1),'a.pdf')
    assert not yield_nothing.ok and 'ValueError' in yield_nothing.error

def test_pdf_config_limits_validated():
    for bad in ({'max_pages':0},{'max_pages':101},{'pdf_dpi':10},{'pdf_dpi':400},{'pdf_deadline_seconds':0}):
        with pytest.raises(ValueError):OCRConfig(**bad)

def test_pdf_real_render_when_pdfium_present():
    pytest.importorskip('pypdfium2')
    out=ocr().read_pdf(scanned_pdf(2),'scan.pdf')
    assert out.ok and out.markdown.count('## Page')==2

def test_missing_renderer_package_reports_clearly(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules,'pypdfium2',None)
    out=ocr().read_pdf(scanned_pdf(1),'a.pdf')
    assert not out.ok and 'pypdfium2' in out.error

def test_doc_ingest_routes_scanned_pdf_to_ocr_but_text_pdf_stays_text(monkeypatch):
    from noesek.core import doc_ingest
    from noesek.core.doc_ingest import convert_to_markdown
    monkeypatch.setattr(doc_ingest,'_convert_markitdown',lambda data,name,_r=iter(['','Quarterly revenue grew twelve percent over the prior year.']):next(_r))
    engine=ocr(renderer=fake_renderer(2))
    out=convert_to_markdown(scanned_pdf(2),'scan.pdf',local_ocr=engine)
    assert out.ok and out.engine=='unlimited-ocr-pdf' and out.markdown.count('## Page')==2
    out=convert_to_markdown(scanned_pdf(1),'text.pdf',local_ocr=engine)
    assert out.ok and out.engine=='markitdown' and 'Quarterly revenue' in out.markdown
