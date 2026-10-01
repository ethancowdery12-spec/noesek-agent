"""Unified-diff parsing for the review pipeline.

Own implementation: builds the file/hunk model the pipeline needs and the
set of added line numbers per file, so review comments can be anchored to
lines that actually changed (comments on unchanged or deleted lines are a
known failure mode of diff review).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_HEADER_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)  # (tag, text); tag in + - ' '


@dataclass
class FileDiff:
    path: str
    old_path: str = ""
    status: str = "modified"  # added | modified | deleted | renamed
    errors: list[str] = field(default_factory=list)
    is_binary: bool = False
    hunks: list[Hunk] = field(default_factory=list)

    @property
    def added_lines(self) -> set[int]:
        """New-file line numbers introduced or modified by this diff."""
        out: set[int] = set()
        for h in self.hunks:
            new_no = h.new_start
            for tag, _ in h.lines:
                if tag == "+":
                    out.add(new_no)
                    new_no += 1
                elif tag == " ":
                    new_no += 1
        return out

    @property
    def churn(self) -> int:
        return sum(1 for h in self.hunks for tag, _ in h.lines if tag in "+-")


def _decode_path(p: str) -> str:
    p=p.strip()
    if p.startswith('"'):
        if not p.endswith('"'): raise ValueError('unterminated quoted path')
        p=p[1:-1]; out=bytearray(); i=0
        escapes={'n':'\n','r':'\r','t':'\t','b':'\b','f':'\f','v':'\v','a':'\a','"':'"','\\':'\\'}
        while i<len(p):
            if p[i]=='\\':
                i+=1
                if i>=len(p):raise ValueError('trailing path escape')
                m=re.match(r'[0-7]{1,3}',p[i:])
                if m: out.append(int(m.group(),8));i+=len(m.group());continue
                if p[i] not in escapes:raise ValueError('unknown path escape')
                out.extend(escapes[p[i]].encode());i+=1
            else:out.extend(p[i].encode());i+=1
        p=out.decode('utf-8',errors='strict')
    return p

def _strip_prefix(p: str) -> str:
    p=_decode_path(p)
    return p[2:] if p.startswith(('a/','b/')) else p

def _header_paths(raw):
    tail=raw[len('diff --git '):]
    # Git's C-quoted paths, or its unquoted a/... b/... form (spaces allowed).
    if tail.startswith('"'):
        m=re.fullmatch(r'("(?:[^"\\]|\\.)*") ("(?:[^"\\]|\\.)*"|b/.*)',tail)
    else:
        m=re.fullmatch(r'(a/.*?) (b/.*|"(?:[^"\\]|\\.)*")',tail)
    if not m:raise ValueError('unrecognized git file header')
    return _strip_prefix(m.group(1)),_strip_prefix(m.group(2))

def parse_unified_diff(text: str) -> list[FileDiff]:
    files=[];cur=None;hunk=None;old_used=new_used=0
    def finish_hunk():
        if hunk is not None and (old_used!=hunk.old_count or new_used!=hunk.new_count):
            cur.errors.append('hunk line counts do not match header')
    for raw in text.split("\n"):
        raw=raw.removesuffix("\r")
        if raw.startswith('diff --git '):
            finish_hunk();hunk=None
            try:old,path=_header_paths(raw);cur=FileDiff(path=path,old_path=old)
            except (ValueError,UnicodeError) as exc:cur=FileDiff(path='unparsed-file-'+str(len(files)),errors=[str(exc)])
            files.append(cur);continue
        if cur is None:continue
        if raw.startswith('@@'):
            finish_hunk();hunk=None
            m=_HUNK_RE.match(raw)
            if not m:cur.errors.append('malformed hunk header');continue
            hunk=Hunk(int(m[1]),int(m[2] or 1),int(m[3]),int(m[4] or 1));cur.hunks.append(hunk)
            old_used=new_used=0;continue
        if hunk is not None:
            if raw.startswith('\\ No newline at end of file'):continue
            if raw[:1] in ('+','-',' '):
                hunk.lines.append((raw[0],raw[1:]));old_used+=raw[0] in ('-',' ');new_used+=raw[0] in ('+',' ')
                if old_used>hunk.old_count or new_used>hunk.new_count:cur.errors.append('hunk exceeds declared line counts')
                continue
            finish_hunk();hunk=None
        try:
            if raw.startswith('new file mode'):cur.status='added'
            elif raw.startswith('deleted file mode'):cur.status='deleted'
            elif raw.startswith('rename from '):cur.old_path=_decode_path(raw[12:]);cur.status='renamed'
            elif raw.startswith('rename to '):cur.path=_decode_path(raw[10:])
            elif raw.startswith(('Binary files ','GIT binary patch')):cur.is_binary=True
            elif raw.startswith(('--- ','+++ ')):
                p=_strip_prefix(raw[4:])
                if p!='/dev/null':
                    if raw.startswith('--- '):cur.old_path=p
                    else:cur.path=p
        except (ValueError,UnicodeError) as exc:cur.errors.append(str(exc))
    finish_hunk()
    return files


def render_file_diff(fd: FileDiff, max_lines: int = 400) -> str:
    """Compact unified-diff rendering of one file for prompts."""
    out = [f"--- a/{fd.old_path or fd.path}", f"+++ b/{fd.path}"]
    n = 0
    truncated = False
    for h in fd.hunks:
        out.append(f"@@ -{h.old_start},{h.old_count} +{h.new_start},{h.new_count} @@")
        for tag, text in h.lines:
            n += 1
            if n > max_lines:
                truncated = True
                break
            out.append(f"{tag}{text}")
        if truncated:
            out.append("... [diff truncated]")
            break
    return "\n".join(out)
