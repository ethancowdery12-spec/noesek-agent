from noesek.core.chunk import chunk_text

def test_short_text_single_chunk():
    assert chunk_text("hello", 100) == ["hello"]

def test_long_text_splits_within_limit():
    text = ("word " * 500).strip()
    chunks = chunk_text(text, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert " ".join(" ".join(chunks).split()) == " ".join(text.split())

def test_hard_split_for_unbroken_string():
    chunks = chunk_text("x" * 250, 100)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == "x" * 250

def test_paragraph_boundaries_preserved():
    chunks = chunk_text("para one.\n\npara two.", 100)
    assert chunks == ["para one.\n\npara two."]

def test_empty_text():
    assert chunk_text("", 100) == []
