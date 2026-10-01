import subprocess
from noesek.review.diffparse import parse_unified_diff
from noesek.tools.pr_change_graph import PRChangeGraphInput,pr_change_graph

def test_real_git_quoted_names_and_header_like_content(tmp_path):
    subprocess.run(['git','init',str(tmp_path)],check=True,capture_output=True)
    for name in ['café.txt','normal.txt']:
        (tmp_path/name).write_text('++ forged.txt\n-- fake.txt\n')
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True)
    diff=subprocess.check_output(['git','diff','--cached'],cwd=tmp_path,text=True)
    files=parse_unified_diff(diff)
    assert {f.path for f in files}=={'café.txt','normal.txt'}
    assert all(f.added_lines=={1,2} and f.churn==2 for f in files)
    out=pr_change_graph(PRChangeGraphInput(diff=diff))
    assert out['ok'] and len(out['nodes'])==2

def test_malformed_hunks_are_incomplete_not_graph_success():
    for body in ['@@ -0,0 +1,1 @@\n+a\n+b\n','@@ this is malformed\n+a\n']:
        out=pr_change_graph(PRChangeGraphInput(diff='diff --git a/x b/x\nnew file mode 100644\n'+body))
        assert not out['ok'] and out['status']=='invalid_diff'

def test_actual_header_count_budget_includes_quoted_files():
    diff=''.join(f'diff --git "a/caf\\303\\251{i}" "b/caf\\303\\251{i}"\nnew file mode 100644\n' for i in range(101))
    out=pr_change_graph(PRChangeGraphInput(diff=diff))
    assert not out['ok'] and out['file_count']==101

def test_non_newline_unicode_separators_are_content_not_headers():
    text='+hi\f diff --git a/evil b/evil\u2028text'
    diff='diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -0,0 +1,1 @@\n'+text+'\n'
    files=parse_unified_diff(diff)
    assert len(files)==1 and not files[0].errors and files[0].hunks[0].lines[0][1]==text[1:]
