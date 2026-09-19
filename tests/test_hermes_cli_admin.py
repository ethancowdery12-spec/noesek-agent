import json
from noesek import hermes_cli

def test_mcp_local_config_redacted(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path))
 assert hermes_cli.main(['mcp','add','demo','--url','https://mcp.test'])==0;capsys.readouterr()
 assert hermes_cli.main(['mcp','list'])==0;out=capsys.readouterr().out
 assert 'demo' in out and 'Authorization' not in out
 assert hermes_cli.main(['mcp','remove','demo'])==0

def test_hooks_test_never_executes(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));(tmp_path/'hooks.json').write_text('[{"event":"pre_tool_call","command":"/bin/false"}]')
 assert hermes_cli.main(['hooks','test','pre_tool_call'])==0
 row=json.loads(capsys.readouterr().out)[0];assert row['would_run'] is False and row['approval_required'] is True

def test_profile_local_lifecycle(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path))
 assert hermes_cli.main(['profile','create','work','--description','Work'])==0;capsys.readouterr()
 assert hermes_cli.main(['profile','use','work'])==0;capsys.readouterr()
 assert hermes_cli.main(['profile','list'])==0;rows=json.loads(capsys.readouterr().out);assert any(x['name']=='work' and x['active'] for x in rows)
 assert hermes_cli.main(['profile','delete','work','--yes'])==0

def test_secret_and_vault_status_are_references_only(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));(tmp_path/'secret-references.json').write_text('{"OPENAI":{"source":"vault","reference":"ref:abc","value":"never"}}')
 assert hermes_cli.main(['secrets'])==0;out=capsys.readouterr().out
 assert 'never' not in out and 'ref:abc' in out

def test_session_repair_is_idempotent(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path));monkeypatch.setenv('NOESEK_DATABASE_URL',f'sqlite+aiosqlite:///{tmp_path}/db.sqlite')
 assert hermes_cli.main(['sessions','repair'])==0
 assert json.loads(capsys.readouterr().out)['changes']==0
