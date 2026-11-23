#!/usr/bin/env python3
"""Validate a spec-graph YAML file: schema, ids, machine wiring, file refs.

Usage:
    python spec_lint.py .specs/order-lifecycle/spec.yaml
    python spec_lint.py spec.yaml --repo . --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, git_state, load_spec, validate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", help="path to spec.yaml")
    parser.add_argument("--repo", help="repository root (default: discovered from the spec path)")
    parser.add_argument("--no-refs", action="store_true", help="skip file/symbol existence checks")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        if args.json:
            print(json.dumps({"ok": False, "errors": [{"message": str(exc)}], "warnings": []}, indent=2))
        else:
            print(f"✗ {exc}", file=sys.stderr)
        return 2

    report = validate(spec.data, spec.root, check_refs=not args.no_refs)
    git = git_state(spec.path, spec.root)
    if git["repo"]:
        generated = []
        for name in ("graph.html", "results.json", "checks.json"):
            candidate = spec.path.parent / name
            if candidate.exists() and git_state(candidate, spec.root)["tracked"]:
                generated.append(name)
        if generated:
            report.add_warning(
                "generated file(s) tracked in git: " + ", ".join(generated)
                + " — only spec.yaml belongs in the repository",
                "git",
            )
    payload = report.as_dict()
    payload["git"] = git

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if report.ok else 1

    head = f"{spec.data.get('spec', '?')}  v{spec.data.get('version', '?')}  [{spec.data.get('status', '?')}]"
    print(head)
    print(f"  root     {spec.root}")
    print(f"  spec     {spec.path}")
    stats = report.stats
    if stats.get("kind") == "refactor":
        print(
            "  content  "
            f"{stats.get('steps', 0)} steps · {stats.get('done', 0)} done · "
            f"{stats.get('checks', 0)} checks · {stats.get('invariants', 0)} invariants"
        )
    else:
        print(
            "  content  "
            f"{stats.get('behaviours', 0)} behaviours · {stats.get('scenarios', 0)} scenarios · "
            f"{stats.get('states', 0)} states · {stats.get('transitions', 0)} transitions"
        )
    if git["repo"]:
        if git["tracked"]:
            print("  git      spec.yaml is tracked")
            if git["ignored"]:
                print(f"           also matches an ignore rule ({git['reason']}) — `git rm --cached` if that was intentional")
        elif git["ignored"]:
            print(f"  git      ignored — {git['reason'] or 'matched by an ignore rule'}")
            print("           this spec stays local; do not force-add it")
        else:
            print("  git      untracked — stage it with the code when ready")
    else:
        print("  git      not a git repository")
    print()
    for item in report.errors:
        where = f" ({item['path']})" if item.get("path") else ""
        print(f"  ✗ {item['message']}{where}")
    for item in report.warnings:
        where = f" ({item['path']})" if item.get("path") else ""
        print(f"  ! {item['message']}{where}")
    if report.ok and not report.warnings:
        print("  ✓ no problems found")
    print()
    print(f"RESULT: {'PASS' if report.ok else 'FAIL'} — {len(report.errors)} error(s), {len(report.warnings)} warning(s)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
