from noesek.tools.web import extract_text

def test_extract_text_strips_scripts_and_gets_title():
    html = """<html><head><title>My Page</title><style>body{}</style></head>
    <body><h1>Hello</h1><script>alert('evil')</script><p>World</p></body></html>"""
    title, text = extract_text(html)
    assert title == "My Page"
    assert "Hello" in text and "World" in text
    assert "alert" not in text and "body{}" not in text

def test_extract_text_handles_empty():
    title, text = extract_text("")
    assert title == "" and text == ""
