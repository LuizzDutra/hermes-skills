#!/usr/bin/env python3
"""Generate a failing test skeleton from an approved behaviour.

The skeleton is scaffolding, not a test: every line of arrange/act/assert is a
comment translated from the spec's scenarios, and the body raises. Refining it
into a real failing test is the TDD step.

Usage:
    python spec_tests.py spec.yaml --only BEH-003
    python spec_tests.py spec.yaml --all --out tests/test_export.py
    python spec_tests.py spec.yaml --missing        # every behaviour without tests
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, _as_list, load_spec  # noqa: E402


def slug(text: str, limit: int = 48) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return (text[:limit].rstrip("_")) or "behaviour"


def skeleton(beh: dict, framework: str) -> str:
    bid = str(beh["id"]).replace("-", "_")
    title = beh.get("title") or ""
    lines = [f"# {beh['id']} — {title}", f"# {beh.get('rule', '')}", ""]

    for sc in _as_list(beh.get("scenarios")):
        if not isinstance(sc, dict):
            continue
        lines.append(f"# {sc.get('id', '')}")
        if sc.get("given"):
            lines.append(f"#   given: {'; '.join(str(g) for g in _as_list(sc.get('given')))}")
        lines.append(f"#   when:  {sc.get('when', '')}")
        lines.append(f"#   then:  {'; '.join(str(t) for t in _as_list(sc.get('then')))}")
    refs = _as_list(beh.get("refs"))
    if refs:
        lines.append("# refs:")
        for ref in refs:
            if isinstance(ref, dict):
                lines.append(f"#   {ref.get('path')}" + (f" · {ref['symbol']}" if ref.get("symbol") else ""))
    lines.append("")

    name = f"test_{bid}_{slug(title)}"
    if framework == "pytest":
        given = "; ".join(str(g) for g in _as_list((_as_list(beh.get("scenarios")) or [{}])[0].get("given")))
        when = (_as_list(beh.get("scenarios")) or [{}])[0].get("when", "")
        then = "; ".join(str(t) for t in _as_list((_as_list(beh.get("scenarios")) or [{}])[0].get("then")))
        rule = str(beh.get("rule") or "").replace('"', "'")
        lines += [
            f"def {name}():",
            f'    """{rule}"""',
            f"    # arrange: {given or 'build the starting state'}",
            f"    # act:     {when or 'perform the trigger'}",
            f"    # assert:  {then or 'observe the outcome'}",
            '    raise AssertionError("not implemented")',
            "",
        ]
    elif framework == "vitest":
        lines += [
            f'it("{name}", () => {{',
            f"  // arrange: {(_as_list(beh.get('scenarios')) or [{}])[0].get('given')}",
            f"  // act:     {(_as_list(beh.get('scenarios')) or [{}])[0].get('when')}",
            f"  // assert:  {(_as_list(beh.get('scenarios')) or [{}])[0].get('then')}",
            '  throw new Error("not implemented");',
            "});",
            "",
        ]
    else:
        lines += [name, ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("--repo")
    parser.add_argument("--only", action="append", default=[], help="behaviour id (repeatable)")
    parser.add_argument("--all", action="store_true", help="every behaviour")
    parser.add_argument("--missing", action="store_true", help="only behaviours without tests")
    parser.add_argument("--framework", default="pytest", choices=["pytest", "vitest", "plain"])
    parser.add_argument("--out", help="file to write (default: stdout)")
    parser.add_argument("--force", action="store_true", help="overwrite --out if it exists")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    behaviours = [b for b in (spec.data.get("behaviours") or []) if isinstance(b, dict) and b.get("id")]
    if args.only:
        wanted = {b.upper() for b in args.only}
        chosen = [b for b in behaviours if str(b["id"]).upper() in wanted]
        unknown = wanted - {str(b["id"]).upper() for b in chosen}
        if unknown:
            print(f"✗ unknown behaviour id(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
    elif args.missing:
        chosen = [b for b in behaviours if not _as_list(b.get("tests"))]
    elif args.all:
        chosen = behaviours
    else:
        print("✗ choose --only BEH-NNN, --missing or --all", file=sys.stderr)
        return 2

    if not chosen:
        print("no behaviours selected", file=sys.stderr)
        return 1

    header = f'"""Tests generated from {spec.data.get("spec")} v{spec.data.get("version")} — refine before committing."""\n\n'
    body = "\n".join(skeleton(b, args.framework) for b in chosen)

    if args.out:
        out = Path(args.out)
        if out.exists() and not args.force:
            print(f"✗ {out} exists (use --force)", file=sys.stderr)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(header + body, encoding="utf-8")
        print(f"✓ {out} ({len(chosen)} behaviour(s))")
    else:
        print(header + body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
