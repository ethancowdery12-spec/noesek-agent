import json
from pathlib import Path
from noesek import cli_surface

def test_manifest_pin_and_scale():
 m=json.loads((Path(__file__).parents[1]/'compat/cli-manifest.json').read_text())
 assert m['upstream']['commit']=='d7b836ab1c0cddaafc109ed24c9a83b6191cdc88'
 assert len(m['commands']) >= 240
 assert sum(len(x['options']) for x in m['commands']) >= 500
 assert len(m['slash_commands']) == 102

def test_every_manifest_command_builds():
 p=cli_surface.build_parser()
 m=cli_surface._manifest()
 for row in m['commands']:
  if row['path']:
   # Parser construction itself covers every path; help is allowed to exit 0 even
   # when the command has required arguments.
   try: p.parse_args(row['path']+['--help'])
   except SystemExit as exc: assert exc.code == 0

def test_unsupported_is_explicit(capsys):
 assert cli_surface.main(['send'])==3
 assert 'did not run' in capsys.readouterr().err

def test_completion_contains_full_top_level():
 text=cli_surface._completion('bash')
 assert 'gateway' in text and 'sessions' in text and 'computer-use' in text

def test_setup_and_model_route_to_vendored(monkeypatch):
 calls=[]
 import noesek.upstream_boot as ub
 monkeypatch.setattr(ub,'run_vendored',lambda argv: calls.append(argv) or 0)
 import importlib, noesek.cli_surface as cs
 assert cs.main(['setup','--non-interactive'])==0
 assert cs.main(['model'])==0
 assert calls==[['setup','--non-interactive'],['model']]

def test_serve_dispatches_to_main_run(monkeypatch):
 import noesek.main as m
 called = {}
 monkeypatch.setattr(m, 'run', lambda: called.setdefault('ran', True))
 assert cli_surface.main(['serve']) == 0
 assert called.get('ran') is True
