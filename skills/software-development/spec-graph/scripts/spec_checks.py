#!/usr/bin/env python3
"""Run the structural checks of a `kind: refactor` plan and write checks.json.

A check is a command that exits 0 when the structural property holds. `grep`
style checks usually need `expect_exit: 1` (no matches found).

Usage:
    python spec_checks.py .specs/split-money/spec.yaml
    python spec_checks.py spec.yaml --only CHK-1 --json
    python spec_checks.py spec.yaml --render     # checks, then redraw the plan
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, _as_list, load_spec, run_command  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("--repo")
    parser.add_argument("--only", action="append", default=[], help="check id (repeatable)")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", help="checks.json path (default: <spec dir>/checks.json)")
    parser.add_argument("--render", action="store_true", help="re-render the plan with the results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if str(spec.data.get("kind") or "behaviour") != "refactor":
        print("✗ not a refactor plan: set `kind: refactor` at the top of the spec", file=sys.stderr)
        return 2

    checks = [c for c in _as_list(spec.data.get("checks")) if isinstance(c, dict) and c.get("id")]
    wanted = {c.upper() for c in args.only}
    if wanted:
        checks = [c for c in checks if str(c["id"]).upper() in wanted]
        missing = wanted - {str(c["id"]).upper() for c in checks}
        if missing:
            print(f"✗ unknown check id(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    if not checks:
        print("✗ no checks declared", file=sys.stderr)
        return 2

    results: dict[str, dict] = {}
    for chk in checks:
        cid = str(chk["id"])
        run = str(chk.get("run") or "")
        expect = int(chk.get("expect_exit", 0))
        started = time.time()
        code, output = run_command(run, spec.root, timeout=args.timeout)
        duration = round(time.time() - started, 2)
        tail = "\n".join(output.strip().splitlines()[-40:])
        results[cid] = {
            "ok": code == expect,
            "exit": code,
            "expect": expect,
            "duration": duration,
            "output": tail[-4000:],
        }
        mark = "✓" if code == expect else "✗"
        print(f"{mark} {cid}  exit {code} (expected {expect})  {duration}s  {chk.get('title') or run}")

    payload = {
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "checks": results,
        "totals": {
            "checks": len(results),
            "passed": sum(1 for r in results.values() if r["ok"]),
            "failed": sum(1 for r in results.values() if not r["ok"]),
        },
    }

    out = Path(args.out) if args.out else spec.path.parent / "checks.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.json:
        print(f"\n  results → {out}")

    if args.render:
        from spec_render import main as render_main

        sys.argv = ["spec_render.py", str(spec.path), "--results", str(out), "--quiet"]
        render_main()
        print(f"  plan    → {spec.path.parent / 'graph.html'}")

    return 1 if payload["totals"]["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
