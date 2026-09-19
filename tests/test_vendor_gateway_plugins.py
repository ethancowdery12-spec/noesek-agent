"""Vendored gateway channel directory + plugin loader behind Noesek adapters."""
from noesek.channels.directory import ChannelDirectory
from noesek.compat.plugins_real import PluginRegistry


def test_channel_directory_empty_and_resilient(tmp_path):
    d = ChannelDirectory(tmp_path)
    loaded = d.load()
    assert isinstance(loaded, dict)
    assert d.resolve("whatsapp", "nonexistent") is None
    assert isinstance(d.display(), str)

def test_plugin_discovery(tmp_path):
    reg = PluginRegistry(tmp_path)
    assert reg.discover() == []
    plug = reg.plugins_dir() / "echo"
    plug.mkdir()
    (plug / "__init__.py").write_text("")
    (plug / "plugin.yaml").write_text("description: echo plugin\n")
    found = reg.discover()
    assert [p["name"] for p in found] == ["echo"]
