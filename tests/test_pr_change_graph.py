from noesek.tools.pr_change_graph import PRChangeGraphInput,pr_change_graph

def test_all_statuses_and_changed_lines():
    diff='''diff --git a/a.py b/a.py
new file mode 100644
--- /dev/null
+++ b/a.py
@@ -0,0 +1,1 @@
+import x
diff --git a/b.py b/b.py
deleted file mode 100644
--- a/b.py
+++ /dev/null
@@ -1,1 +0,0 @@
-x
'''
    out=pr_change_graph(PRChangeGraphInput(diff=diff))
    assert [n['status'] for n in out['nodes']]==['added','deleted']
    assert out['nodes'][0]['added_lines']==[1] and not out['edges']
    assert out['model_generated'] is False

def test_diagram_labels_are_not_code():
    diff='diff --git a/bad\"<x>.py b/bad\"<x>.py\nnew file mode 100644\n'
    out=pr_change_graph(PRChangeGraphInput(diff=diff))
    assert '"<x>' not in out['mermaid']
    assert '&quot;&lt;x&gt;' in out['mermaid']

def test_graph_budget_never_drops_files():
    diff=''.join(f'diff --git a/{i}.py b/{i}.py\nnew file mode 100644\n' for i in range(101))
    assert not pr_change_graph(PRChangeGraphInput(diff=diff))['ok']
