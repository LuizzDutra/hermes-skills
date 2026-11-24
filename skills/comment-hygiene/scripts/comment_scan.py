#!/usr/bin/env python3
"""Inventory process-slop in Python comments and docstrings.

Finds two kinds of noise:

  * process markers — plan, step and check ids, e.g. `P<n>`, `S<n>`, `CHK<n>`,
    `INV<n>`, `OQ<n>`, `BEH<n>`, `SC<n>`
  * commit citations — a hex sha inside parentheses `(<sha>)` or right after
    `commit`/`hash`. Bare hex is NOT flagged: english words like `ed25519`
    would drown the list.

With `--style` it also reports prose that ages badly, in three families:
`addressed` (talking to whoever asked), `step` (numbered plan phases) and
`tense` (past/future narration: previously, used to, será implementado). Prose
has real false positives, so the families stay off unless asked for.

Each hit is classified as comment or docstring (module / class / function).
`contract_risk` is set only when the text is actually published by the
framework: a FastAPI route handler (decorator `@router.<verb>` / `@app.<verb>`)
or a Pydantic model class (a class whose bases include `BaseModel`). A module
docstring or a plain function docstring in a file that imports pydantic is NOT
contract — flagging those is the classic false positive.

Usage:
    python comment_scan.py [ROOT ...]            # inventory
    python comment_scan.py [ROOT ...] --json     # machine readable
    python comment_scan.py [ROOT ...] --style    # + prose families
    python comment_scan.py --staged              # added lines in the index
    python comment_scan.py --staged --fail       # exit 1 when the diff adds slop

`--staged` is advisory by default: it reads `git diff --cached -U0`, reports
markers on added lines and exits 0. `--fail` turns it into the low-noise gate
(added lines only, never the whole tree).

Stdlib only.
"""

import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize

MARKER = re.compile(
    r"\b(P\d+(?:\.\d+)?[a-z]?|S-\d+[a-z]?|CHK-\d+|INV-\d+|OQ-\d+|BEH-\d+|SC-\d+)\b"
)
HEX_CITATION = re.compile(
    r"\((?P<sha>[0-9a-f]{7,40})\)|(?:commit|hash)\s+(?P<sha2>[0-9a-f]{7,40})\b"
)
SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".tox", ".mypy_cache", ".pytest_cache",
}
ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "head", "options", "api_route"}

# Prose families behind `--style`. Each pattern is matched case-insensitively and
# reports its family as the token, so a reviewer can triage by kind rather than by word.
STYLE = {
    "addressed": re.compile(
        r"(?:\bas (?:you )?(?:asked|requested|suggested)\b|\bper your (?:request|ask)\b"
        r"|\byou asked\b|\bconforme (?:solicitado|pedido)\b|\bcomo (?:voc[eê] )?(?:pediu|solicitou)\b"
        r"|\ba (?:seu|teu) pedido\b|\ba pedido\b|\bcomo discutimos\b)",
        re.IGNORECASE,
    ),
    "step": re.compile(
        r"\b(?:step|phase|fase|etapa|passo|task|tarefa|milestone)\s*#?\d+\b",
        re.IGNORECASE,
    ),
    "tense": re.compile(
        r"(?:\bused to\b|\bpreviously\b|\bformerly\b|\banteriormente\b|\bantigamente\b"
        r"|\bantes era\b|\bera antes\b|\bmoved here\b|\brenamed from\b"
        r"|\bwas (?:renamed|moved|replaced|removed)\b"
        r"|\bwill be (?:implemented|added|replaced|removed)\b"
        r"|\bser[aá] (?:implementad|adicionad|substitu[ií]d|removid)[oa]s?\b"
        r"|\bno futuro\b|\bin a future\b|\bainda n[aã]o implementad[oa]\b"
        r"|\bnot implemented yet\b|\bto be implemented\b)",
        re.IGNORECASE,
    ),
}


def _is_contract_function(node):
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            dec = dec.func
        if isinstance(dec, ast.Attribute) and dec.attr in ROUTE_DECORATORS:
            return True
    return False


def _is_pydantic_model(node):
    for base in node.bases:
        name = base.attr if isinstance(base, ast.Attribute) else getattr(base, "id", "")
        if name == "BaseModel":
            return True
    return False


def docstring_spans(tree):
    """Map line -> (kind, contract_risk) for every docstring in the module."""
    spans = {}

    def register(node, kind, contract):
        body = getattr(node, "body", None)
        if not body:
            return
        first = body[0]
        if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            return
        for line in range(first.lineno, (first.end_lineno or first.lineno) + 1):
            spans.setdefault(line, (kind, contract))

    register(tree, "docstring-module", False)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            register(node, "docstring-class", _is_pydantic_model(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            register(node, "docstring-function", _is_contract_function(node))
    return spans


def _style_hits(line, kind, contract, path, lineno):
    return [
        {"path": path, "line": lineno, "kind": kind, "contract_risk": contract,
         "token": f"style:{family}", "text": line.strip()[:160]}
        for family, pattern in STYLE.items() if pattern.search(line)
    ]


def scan_source(text, path, style=False):
    try:
        tree = ast.parse(text)
        spans = docstring_spans(tree)
        comments = {
            tok.start[0]
            for tok in tokenize.generate_tokens(io.StringIO(text).readline)
            if tok.type == tokenize.COMMENT
        }
    except (SyntaxError, tokenize.TokenError):
        return []
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if lineno in spans:
            kind, contract = spans[lineno]
        elif lineno in comments:
            kind, contract = "comment", False
        else:
            continue
        for match in MARKER.finditer(line):
            hits.append({
                "path": path, "line": lineno, "kind": kind, "contract_risk": contract,
                "token": match.group(0), "text": line.strip()[:160],
            })
        for match in HEX_CITATION.finditer(line):
            sha = match.group("sha") or match.group("sha2")
            hits.append({
                "path": path, "line": lineno, "kind": kind, "contract_risk": contract,
                "token": sha + " (sha)", "text": line.strip()[:160],
            })
        if style:
            hits.extend(_style_hits(line, kind, contract, path, lineno))
    return hits


def py_files(roots):
    for root in roots:
        if os.path.isfile(root) and root.endswith(".py"):
            yield root
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


def staged_lines():
    """(path, line_text) for added lines in the index."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--", "*.py"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    path, added = None, []
    for raw in out.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
        elif raw.startswith("+") and not raw.startswith("+++"):
            added.append((path, raw[1:]))
    return added


def scan_staged(allow, style=False):
    hits = []
    for path, line in staged_lines():
        for match in MARKER.finditer(line):
            if allow and allow.search(match.group(0)):
                continue
            hits.append({
                "path": path, "line": 0, "kind": "staged", "contract_risk": False,
                "token": match.group(0), "text": line.strip()[:160],
            })
        for match in HEX_CITATION.finditer(line):
            sha = match.group("sha") or match.group("sha2")
            hits.append({
                "path": path, "line": 0, "kind": "staged", "contract_risk": False,
                "token": sha + " (sha)", "text": line.strip()[:160],
            })
        if style:
            hits.extend(_style_hits(line, "staged", False, path, 0))
    return hits


def report(hits, as_json):
    hits.sort(key=lambda h: (h["path"], h["line"]))
    if as_json:
        for hit in hits:
            print(json.dumps(hit))
        return
    for hit in hits:
        where = f"{hit['path']}:{hit['line']}" if hit["line"] else hit["path"]
        flag = " [CONTRACT]" if hit["contract_risk"] else ""
        print(f"{where} [{hit['kind']}{flag}] {hit['token']} — {hit['text']}")
    counts = {}
    for hit in hits:
        key = hit["kind"] + ("+contract" if hit["contract_risk"] else "")
        counts[key] = counts.get(key, 0) + 1
    print(f"\n{len(hits)} hit(s): " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("roots", nargs="*", default=None, help="files or directories to scan")
    parser.add_argument("--json", action="store_true", help="emit JSON lines")
    parser.add_argument("--style", action="store_true",
                        help="also report prose families: addressed, step, tense")
    parser.add_argument("--staged", action="store_true", help="scan added lines in the git index")
    parser.add_argument("--fail", action="store_true", help="exit 1 when something is found (with --staged)")
    parser.add_argument("--allow", default=r"ADR-\d+", help="regex of tokens to ignore (default: ADR ids)")
    args = parser.parse_args()

    allow = re.compile(args.allow) if args.allow else None
    if args.staged:
        hits = scan_staged(allow, style=args.style)
        report(hits, args.json)
        return 1 if (args.fail and hits) else 0

    roots = args.roots or ["."]
    hits = []
    for path in py_files(roots):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            continue  # unreadable file (perms, broken link) is out of scope, not a crash
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        hits.extend(scan_source(text, path, style=args.style))
    if allow:
        hits = [h for h in hits if not allow.search(h["token"])]
    report(hits, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
