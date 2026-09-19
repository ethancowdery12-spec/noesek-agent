import hashlib, hmac
from noesek.channels.whatsapp import valid_signature
from noesek.config import settings

def _sig(body, secret): return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def test_signature_accepts_valid():
    old = settings.meta_app_secret; settings.meta_app_secret = "secret"
    try:
        body = b"hello"
        assert valid_signature(body, _sig(body, "secret"))
    finally: settings.meta_app_secret = old

def test_signature_rejects_wrong_and_malformed():
    old = settings.meta_app_secret; settings.meta_app_secret = "secret"
    try:
        assert not valid_signature(b"hello", "sha256=no")
        assert not valid_signature(b"hello", "badprefix")
        assert not valid_signature(b"hello", None)
        assert not valid_signature(b"hello", _sig(b"tampered", "secret"))
    finally: settings.meta_app_secret = old

def test_empty_secret_is_dev_mode():
    old = settings.meta_app_secret; settings.meta_app_secret = ""
    try: assert valid_signature(b"anything", None)
    finally: settings.meta_app_secret = old
