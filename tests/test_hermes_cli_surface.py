import json
from pathlib import Path
from noesek import hermes_cli

def test_manifest_pin_and_scale():
 m=json.loads((Path(__file__).parents[1]/'compat/hermes-cli-manifest.json').read_text())
 assert m['upstream']['commit']=='d7b836ab1c0cddaafc109ed24c9a83b6191cdc88'
 assert len(m['commands']) >= 240
 assert sum(len(x['options']) for x in m['commands']) >= 500
 assert len(m['slash_commands']) == 102

def test_every_manifest_command_builds():
 p=hermes_cli.build_parser()
 m=hermes_cli._manifest()
 for row in m['commands']:
  if row['path']:
   # Parser construction itself covers every path; help is allowed to exit 0 even
   # when the command has required arguments.
   try: p.parse_args(row['path']+['--help'])
   except SystemExit as exc: assert exc.code == 0

def test_unsupported_is_explicit(capsys):
 assert hermes_cli.main(['send'])==3
 assert 'did not run' in capsys.readouterr().err

def test_completion_contains_full_top_level():
 text=hermes_cli._completion('bash')
 assert 'gateway' in text and 'sessions' in text and 'computer-use' in text
