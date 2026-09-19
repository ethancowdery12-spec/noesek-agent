import json
from pathlib import Path
from noesek import cli_surface

def test_fallback_redacts_secret(monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_LLM_FALLBACKS','[{"base_url":"https://x","model":"m","api_key":"secret"}]')
 assert cli_surface.main(['fallback'])==0
 assert 'secret' not in capsys.readouterr().out

def test_skill_list_is_local(tmp_path,monkeypatch,capsys):
 home=tmp_path/'h';p=home/'skills'/'demo';p.mkdir(parents=True);(p/'SKILL.md').write_text('# Demo\n')
 monkeypatch.setenv('NOESEK_HOME',str(home));assert cli_surface.main(['skills','list'])==0
 assert 'demo' in capsys.readouterr().out

def test_config_get(capsys):
 assert cli_surface.main(['config','get','log_level'])==0
 assert 'INFO' in capsys.readouterr().out

def test_cron_lifecycle(tmp_path,monkeypatch,capsys):
 monkeypatch.setenv('NOESEK_HOME',str(tmp_path))
 assert cli_surface.main(['cron','create','every 1 hour','test prompt','--name','demo'])==0
 row=json.loads(capsys.readouterr().out);jid=row['id']
 assert cli_surface.main(['cron','pause',jid])==0;capsys.readouterr()
 assert cli_surface.main(['cron','resume',jid])==0;capsys.readouterr()
 assert cli_surface.main(['cron','remove',jid])==0
