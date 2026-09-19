import json
from pathlib import Path
import pytest
from noesek import hermes_cli
from noesek.compat import local_admin as a

def test_vault_add_emits_nonsecret_request(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));assert hermes_cli.main(['vault','add','--kind','login'])==0
 r=json.loads(capsys.readouterr().out);p=Path(r['path']);d=json.loads(p.read_text());assert d['approved'] is False and d['payload']['accepts_secret_on_cli'] is False and a.verify_signed(d)

def test_password_managers_are_dry_interfaces(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));assert hermes_cli.main(['secrets','onepassword'])==0
 d=json.loads(capsys.readouterr().out);assert d['dry_run'] and not d['values_exposed']

def test_profile_signed_roundtrip_and_tamper(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));hermes_cli.main(['profile','create','a']);capsys.readouterr()
 out=tmp_path/'p.json';assert hermes_cli.main(['profile','export','a','--output',str(out)])==0;capsys.readouterr()
 assert hermes_cli.main(['profile','import',str(out),'--name','b'])==0;capsys.readouterr()
 d=json.loads(out.read_text());d['profile']['description']='tampered';out.write_text(json.dumps(d))
 with pytest.raises(PermissionError):hermes_cli.main(['profile','import',str(out),'--name','c'])

def test_update_and_service_commands_only_make_signed_plans(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path))
 for argv in (['update','--plan'],['uninstall','--dry-run'],['gateway','install']):
  assert hermes_cli.main(argv)==0;r=json.loads(capsys.readouterr().out);d=json.loads(Path(r['path']).read_text());assert not r['executed'] and a.verify_signed(d)
