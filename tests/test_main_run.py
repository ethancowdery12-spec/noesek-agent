"""main.run(): port comes from Render's PORT (or NOESEK_PORT override)."""
import noesek.main as m


def test_run_honors_port_env(monkeypatch):
    seen = {}
    monkeypatch.setattr(m.uvicorn, "run", lambda app, host, port: seen.update(app=app, host=host, port=port))
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.delenv("NOESEK_PORT", raising=False)
    m.run()
    assert seen["port"] == 10000 and seen["host"] == "0.0.0.0"


def test_run_noesek_port_overrides(monkeypatch):
    seen = {}
    monkeypatch.setattr(m.uvicorn, "run", lambda app, host, port: seen.update(port=port))
    monkeypatch.setenv("PORT", "10000")
    monkeypatch.setenv("NOESEK_PORT", "8001")
    m.run()
    assert seen["port"] == 8001
