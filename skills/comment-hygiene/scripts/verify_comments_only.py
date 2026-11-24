#!/usr/bin/env python3
"""Prove that a git range changed only comments and docstrings.

Usage: python verify_comments_only.py BASE [HEAD]

For every .py file that differs between BASE and HEAD (default HEAD), parses
both blobs, strips module/class/function docstrings, and compares the
resulting AST dumps. All equal -> PASS (comment/docstring-only diff).

Docstrings are code contract in several frameworks (FastAPI/Pydantic publish
them into an OpenAPI schema): a PASS here does NOT mean the published contract
is unchanged — diff the generated schema file separately.

Stdlib only; needs the git binary for blob access.
"""
import ast
import subprocess
import sys


def strip_docstrings(tree):
    class Stripper(ast.NodeTransformer):
        def _strip(self, node):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = [ast.Pass()] if len(body) == 1 else body[1:]
            self.generic_visit(node)
            return node

        def visit_Module(self, node):
            return self._strip(node)

        def visit_ClassDef(self, node):
            return self._strip(node)

        def visit_FunctionDef(self, node):
            return self._strip(node)

        def visit_AsyncFunctionDef(self, node):
            return self._strip(node)

    return Stripper().visit(tree)


def git(*args, strict=False):
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout
    except subprocess.CalledProcessError as exc:
        if strict:
            detail = (exc.stderr or "").strip()
            print(f"ERROR: git {' '.join(args)} falhou (exit {exc.returncode})")
            if detail:
                print(detail)
            print("Dica: verifique se BASE existe (o primeiro commit do repo nao tem pai).")
            raise SystemExit(2)
        raise


def code_dump(source):
    return ast.dump(strip_docstrings(ast.parse(source)), include_attributes=False)


def main():
    argv = sys.argv[1:]
    if not argv:
        print("usage: verify_comments_only.py BASE [HEAD]")
        return 2
    base, head = argv[0], (argv[1] if len(argv) > 1 else "HEAD")
    names = git("diff", "--name-only", f"{base}..{head}", "--", "*.py", strict=True).split()
    if not names:
        print(f"PASS: no .py file changed between {base} and {head}")
        return 0
    bad = []
    for name in names:
        try:
            old = git("show", f"{base}:{name}")
        except subprocess.CalledProcessError:
            print(f"DIFF: {name} (added)")
            bad.append(name)
            continue
        try:
            new = git("show", f"{head}:{name}")
        except subprocess.CalledProcessError:
            print(f"DIFF: {name} (deleted)")
            bad.append(name)
            continue
        try:
            same = code_dump(old) == code_dump(new)
        except SyntaxError as exc:
            print(f"SKIP: {name} does not parse ({exc})")
            continue
        if same:
            print(f"OK:   {name}")
        else:
            print(f"DIFF: {name} — code or non-docstring literal changed")
            bad.append(name)
    if bad:
        print(f"\nFAIL: {len(bad)} file(s) changed beyond comments/docstrings")
        return 1
    print(f"\nPASS: {len(names)} file(s), code and non-docstring literals identical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
