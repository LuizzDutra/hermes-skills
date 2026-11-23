#!/usr/bin/env python3
"""Run the repository's tests and map pass/fail back onto spec behaviours.

Usage:
    python spec_verify.py .hermes/specs/order-lifecycle/spec.yaml
    python spec_verify.py spec.yaml --no-run --junit reports/junit.xml
    python spec_verify.py spec.yaml --render          # verify, then redraw the graph

Matching rules, in order:
  1. exact test id declared in the behaviour (`tests:` entries)
  2. same test function name, different path
  3. a BEH-NNN token in the test name (test_BEH_004_paying_twice)

Writes `<spec dir>/results.json` and, with --render, refreshes `graph.html`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, _as_list, load_spec, run_command, validate  # noqa: E402

BEH_IN_NAME = re.compile(r"BEH[-_]?(\d{3})")


def junit_tests(path: Path) -> list[dict]:
    tree = ET.parse(path)
    root = tree.getroot()
    cases = []
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or ""
        failed = case.find("failure") is not None or case.find("error") is not None
        skipped = case.find("skipped") is not None
        cases.append(
            {
                "classname": classname,
                "name": name,
                "ok": not failed and not skipped,
                "skipped": skipped,
                "time": float(case.get("time") or 0),
                "message": ((case.find("failure") if case.find("failure") is not None else case.find("error")) or {})
                .get("message", "") if failed else "",
            }
        )
    return cases


def full_id(case: dict) -> str:
    """Best-effort pytest node id from a JUnit classname."""
    classname = case["classname"]
    name = case["name"]
    if not classname:
        return name
    parts = classname.split(".")
    # tests.test_order -> tests/test_order.py ; tests.test_order.TestX -> tests/test_order.py::TestX
    for idx in range(len(parts), 0, -1):
        candidate = "/".join(parts[:idx]) + ".py"
        rest = parts[idx:]
        if rest:
            return candidate + "::" + "::".join(rest) + "::" + name
        return candidate + "::" + name
    return name


def match(behaviour: dict, cases: list[dict], allow_name_tokens: bool = False) -> list[dict]:
    declared = [str(t) for t in _as_list(behaviour.get("tests"))]
    out = []
    for case in cases:
        fid = full_id(case)
        hit = False
        for want in declared:
            if fid == want or fid.endswith("::" + want.split("::")[-1]) or want.split("::")[-1] == case["name"]:
                hit = True
                break
        if not hit and allow_name_tokens:
            m = BEH_IN_NAME.search(case["name"]) or BEH_IN_NAME.search(fid)
            if m and f"BEH-{m.group(1)}" == behaviour.get("id"):
                hit = True
        if hit:
            out.append({"name": fid or case["name"], "ok": case["ok"], "skipped": case["skipped"], "time": case["time"]})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("--repo")
    parser.add_argument("--junit", help="JUnit XML path (default: repo.commands.junit or reports/junit.xml)")
    parser.add_argument("--no-run", action="store_true", help="do not execute tests; only parse existing JUnit XML")
    parser.add_argument("--out", help="results.json path (default: <spec dir>/results.json)")
    parser.add_argument("--render", action="store_true", help="re-render graph.html with the results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if str(spec.data.get("kind") or "behaviour") != "behaviour":
        print("✗ this is a refactor plan; run spec_checks.py, not spec_verify.py", file=sys.stderr)
        return 2

    report = validate(spec.data, spec.root, check_refs=False)
    commands = ((spec.data.get("repo") or {}).get("commands") or {})
    test_cmd = commands.get("test")
    junit_rel = args.junit or commands.get("junit") or "reports/junit.xml"
    junit_path = (spec.root / junit_rel).resolve()

    exit_code, output = 0, ""
    if not args.no_run:
        if not test_cmd:
            print("✗ repo.commands.test is missing in the spec; add it or pass --no-run", file=sys.stderr)
            return 2
        if junit_path.exists():
            junit_path.unlink()
        print(f"$ {test_cmd}")
        exit_code, output = run_command(str(test_cmd), spec.root)
        if exit_code not in (0, 1):
            print(output[-3000:], file=sys.stderr)
            print(f"✗ the test command failed with exit code {exit_code}", file=sys.stderr)
            return 2

    if not junit_path.exists():
        print(f"✗ no JUnit report at {junit_path}", file=sys.stderr)
        print("  Add `--junitxml=<path>` (pytest) or an equivalent reporter, and set repo.commands.junit.", file=sys.stderr)
        return 2

    cases = junit_tests(junit_path)
    link_style = str(spec.data.get("link_style") or "explicit")
    behaviours = [b for b in (spec.data.get("behaviours") or []) if isinstance(b, dict) and b.get("id")]
    table: dict[str, dict] = {}
    rows = []
    for beh in behaviours:
        hits = match(beh, cases, allow_name_tokens=(link_style == "name"))
        if hits and any(not h["ok"] and not h["skipped"] for h in hits):
            status = "fail"
        elif hits:
            status = "pass"
        elif _as_list(beh.get("tests")):
            status = "missing"
        else:
            status = ""
        table[str(beh["id"])] = {"status": status, "tests": hits}
        rows.append((str(beh["id"]), beh.get("title") or "", status, len(hits)))

    mapped = {h["name"] for b in table.values() for h in b["tests"]}
    unmapped = [full_id(c) for c in cases if full_id(c) not in mapped]
    totals = {
        "tests": len(cases),
        "passed": sum(1 for c in cases if c["ok"]),
        "failed": sum(1 for c in cases if not c["ok"] and not c["skipped"]),
        "skipped": sum(1 for c in cases if c["skipped"]),
    }
    results = {
        "generated": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "command": test_cmd if not args.no_run else None,
        "exit_code": exit_code,
        "junit": str(junit_path),
        "totals": totals,
        "behaviours": table,
        "unmapped": unmapped,
    }

    out = Path(args.out) if args.out else spec.path.parent / "results.json"
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print()
        for bid, title, status, n in rows:
            mark = {"pass": "✓", "fail": "✗", "missing": "?", "": "·"}[status]
            label = {"pass": "pass", "fail": "FAIL", "missing": "no match", "": "no tests"}[status]
            print(f"  {mark} {bid}  {label:<8} {n} test(s)  {title}")
        print()
        print(f"  {totals['tests']} tests · {totals['passed']} passed · {totals['failed']} failed · {totals['skipped']} skipped")
        if unmapped:
            print(f"  ! {len(unmapped)} test(s) not linked to any behaviour, e.g. {unmapped[0]}")
            print("    link them with: python spec_link.py <spec.yaml>")
        failed_behaviours = [bid for bid, _, s, _ in rows if s == "fail"]
        print(f"\n  results → {out}")
        if failed_behaviours:
            print(f"  failing behaviours: {', '.join(failed_behaviours)}")

    if args.render:
        from spec_render import main as render_main  # late import keeps scripts independent

        sys.argv = ["spec_render.py", str(spec.path), "--results", str(out), "--quiet"]
        render_main()
        print(f"  graph   → {spec.path.parent / 'graph.html'}")

    if report.errors:
        print(f"\n  ! {len(report.errors)} lint error(s) in the spec; run spec_lint.py", file=sys.stderr)
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
