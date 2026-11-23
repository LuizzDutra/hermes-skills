#!/usr/bin/env python3
"""Link collected tests to behaviours — without renaming a single test.

The repo keeps its own test names. The mapping lives in `spec.yaml` under each
behaviour's `tests:` list, and this command keeps it honest:

    python spec_link.py spec.yaml                # suggestions + unlinked tests
    python spec_link.py spec.yaml --check        # exit 1 if a declared id vanished
    python spec_link.py spec.yaml --apply        # show the links it would write
    python spec_link.py spec.yaml --apply --yes  # write them (leaves a .bak)

Collection uses `repo.commands.collect` when present, otherwise the test
command's interpreter with `-m pytest --collect-only -q`. Override with
`--collect "<command>"`.

Suggestions are weighted token overlap between the behaviour's title/rule and
the test's function name. They are suggestions: `--apply` merges them with the
links that still resolve, never silently replaces a working mapping.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from spec_model import SpecError, _as_list, load_spec, run_command  # noqa: E402

BEH_ID = re.compile(r"^  - id: (BEH-\d{3})\s*$")
STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "when", "then",
    "shall", "system", "if", "while", "where", "is", "are", "be", "it", "its", "this",
    "that", "as", "by", "not", "no", "from", "into", "after", "before", "at", "up", "out",
    "can", "cannot", "must", "may", "only", "same", "than", "each", "any", "all", "still",
    "one", "two", "more", "has", "have", "does", "do", "so", "also", "would", "should",
}
DEFAULT_THRESHOLD = 0.6


def stem(word: str) -> str:
    """Crude suffix stripping: cancellation→cancel, payment→pay, submitted→submit."""
    if word.endswith("ssion") and len(word) > 6:
        word = word[:-5] + "t"
    elif word.endswith("ation") and len(word) > 6:
        word = word[:-5]
    elif word.endswith("tion") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ment") and len(word) > 5:
        word = word[:-4]
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 4:
        word = word[:-2]
    elif word.endswith("s") and len(word) > 3 and not word.endswith("ss"):
        word = word[:-1]
    if len(word) > 4 and word.endswith("y"):
        word = word[:-1]
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiou":
        word = word[:-1]
    return word


def tokens(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", str(text).lower())
    return {stem(w) for w in words if w not in STOP and len(w) > 2}


def test_tokens(node_id: str) -> set[str]:
    tail = re.sub(r"\[.*?\]$", "", node_id.split("::")[-1])
    return tokens(tail.replace("_", " "))


def build_idf(tokens_by_test: dict[str, set[str]]) -> tuple[dict[str, float], float]:
    df: dict[str, int] = {}
    for toks in tokens_by_test.values():
        for token in toks:
            df[token] = df.get(token, 0) + 1
    count = len(tokens_by_test)
    idf = {token: math.log(1 + count / (1 + freq)) for token, freq in df.items()}
    return idf, math.log(1 + count)


def _weight(toks: set[str], idf: dict[str, float], unseen: float) -> float:
    return sum(idf.get(token, unseen) for token in toks)


def overlap(a: set[str], b: set[str], idf: dict[str, float], unseen: float) -> float:
    """How much of the smaller token set the two share, weighted by rarity."""
    common = a & b
    if not common or not a or not b:
        return 0.0
    denominator = min(_weight(a, idf, unseen), _weight(b, idf, unseen))
    return _weight(common, idf, unseen) / denominator if denominator else 0.0


def collect(args, spec) -> tuple[str, list[str]]:
    commands = (spec.data.get("repo") or {}).get("commands") or {}
    cmd = args.collect or commands.get("collect")
    if not cmd:
        test_cmd = str(commands.get("test") or "")
        exe = test_cmd.strip().split()[0] if test_cmd.strip() else "python"
        if "pytest" in test_cmd or not test_cmd:
            cmd = f"{exe} -m pytest --collect-only -q"
        else:
            raise SpecError(
                "cannot infer how to collect tests: set repo.commands.collect or pass --collect",
                path=str(spec.path),
            )
    code, out = run_command(cmd, spec.root, timeout=600)
    ids = [
        line.strip()
        for line in out.splitlines()
        if "::" in line and not line.strip().startswith(("=", "E ", "ERROR", "warning"))
    ]
    return cmd, ids


def declared_links(spec) -> dict[str, list[str]]:
    out = {}
    for beh in spec.data.get("behaviours") or []:
        if isinstance(beh, dict) and beh.get("id"):
            out[str(beh["id"])] = [str(t) for t in _as_list(beh.get("tests"))]
    return out


def suggestions_for(spec, ids: list[str], threshold: float, include_linked: bool, top: int):
    tokens_by_test = {tid: test_tokens(tid) for tid in ids}
    idf, unseen = build_idf(tokens_by_test)
    rows = {}
    for beh in spec.data.get("behaviours") or []:
        if not isinstance(beh, dict) or not beh.get("id"):
            continue
        bid = str(beh["id"])
        declared = [str(t) for t in _as_list(beh.get("tests"))]
        valid = [t for t in declared if t in tokens_by_test]
        if valid and not include_linked:
            continue
        beh_tokens = tokens(str(beh.get("title") or "")) | tokens(str(beh.get("rule") or ""))
        scored = sorted(
            ((overlap(beh_tokens, tokens_by_test[tid], idf, unseen), tid) for tid in ids),
            reverse=True,
        )
        picks = [(round(s, 2), t) for s, t in scored if s >= threshold][:top]
        if picks or valid:
            rows[bid] = {
                "title": beh.get("title") or "",
                "valid": valid,
                "stale": [t for t in declared if t not in tokens_by_test],
                "suggestions": picks,
            }
    return rows


def check(spec, ids: list[str]) -> tuple[list[dict], list[dict]]:
    known = set(ids)
    stale, moved = [], []
    for bid, links in declared_links(spec).items():
        for link in links:
            if link in known:
                continue
            func = link.split("::")[-1]
            other = next((tid for tid in ids if tid.split("::")[-1] == func), None)
            (moved if other else stale).append({"behaviour": bid, "declared": link, "found": other})
    return stale, moved


def render_block(links: list[str]) -> list[str]:
    return ["    tests:"] + [f"      - {t}" for t in links]


def apply_links(text: str, links: dict[str, list[str]]) -> str:
    lines = text.split("\n")
    starts = [i for i, line in enumerate(lines) if BEH_ID.match(line)]
    for start in reversed(starts):
        bid = BEH_ID.match(lines[start]).group(1)
        if bid not in links:
            continue
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if BEH_ID.match(lines[j]) or re.match(r"^[A-Za-z_][A-Za-z0-9_-]*:", lines[j]):
                end = j
                break
        block = render_block(links[bid])
        existing = next((j for j in range(start, end) if re.match(r"^    tests:", lines[j])), None)
        if existing is not None:
            stop = existing + 1
            while stop < end and re.match(r"^      - ", lines[stop]):
                stop += 1
            lines[existing:stop] = block
        else:
            insert_at = end
            while insert_at - 1 > start and lines[insert_at - 1].strip() == "":
                insert_at -= 1
            lines[insert_at:insert_at] = block
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("--repo")
    parser.add_argument("--collect", help="command that prints one test id per line")
    parser.add_argument("--apply", action="store_true", help="write suggested links into the spec")
    parser.add_argument("--yes", action="store_true", help="confirm writing (without it --apply prints a diff)")
    parser.add_argument("--check", action="store_true", help="fail if declared test ids no longer exist")
    parser.add_argument("--all", action="store_true", help="also suggest for behaviours that already have valid links")
    parser.add_argument("--top", type=int, default=1, help="suggestions written per behaviour (default 1)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        spec = load_spec(args.spec, args.repo)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2

    if str(spec.data.get("kind") or "behaviour") != "behaviour":
        print("✗ refactor plans link invariants, not tests; run spec_checks.py instead", file=sys.stderr)
        return 2

    try:
        cmd, ids = collect(args, spec)
    except SpecError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    if not ids:
        print(f"✗ no test ids collected with: {cmd}", file=sys.stderr)
        print('  pass --collect "pytest --collect-only -q" (or the repo equivalent)', file=sys.stderr)
        return 2

    stale, moved = check(spec, ids)
    linked_all = {link for links in declared_links(spec).values() for link in links}
    unlinked = [tid for tid in ids if tid not in linked_all]
    rows = suggestions_for(spec, ids, args.threshold, args.all, args.top)
    link_style = str(spec.data.get("link_style") or "explicit")

    if args.json:
        print(json.dumps({
            "collected": len(ids),
            "link_style": link_style,
            "suggestions": rows,
            "stale": stale,
            "moved": moved,
            "unlinked": unlinked,
        }, indent=2))
    else:
        print(f"{spec.data.get('spec', '?')} · link_style: {link_style} · {len(ids)} tests collected")
        for bid, row in rows.items():
            print(f"\n{bid}  {row['title']}")
            for link in row["valid"]:
                print(f"  keep  {link}")
            for s, tid in row["suggestions"]:
                print(f"  {s:.2f}  {tid}")
        if moved:
            print("\nmoved (same test name, new path):")
            for item in moved:
                print(f"  {item['behaviour']}  {item['declared']} → {item['found']}")
        if stale:
            print("\ndeclared but not collected:")
            for item in stale:
                print(f"  {item['behaviour']}  {item['declared']}")
        if unlinked:
            print(f"\nunlinked tests ({len(unlinked)}):")
            for tid in unlinked[:12]:
                print(f"  {tid}")
            if len(unlinked) > 12:
                print(f"  … {len(unlinked) - 12} more")

    if args.check:
        return 1 if stale else 0

    if args.apply:
        links: dict[str, list[str]] = {}
        for bid, row in rows.items():
            merged = list(row["valid"])
            for _score, tid in row["suggestions"]:
                if tid not in merged:
                    merged.append(tid)
            if merged:
                links[bid] = merged
        if not links:
            print("\nnothing to apply")
            return 0
        text = spec.path.read_text(encoding="utf-8")
        updated = apply_links(text, links)
        diff = list(
            difflib.unified_diff(
                text.splitlines(), updated.splitlines(),
                fromfile=str(spec.path), tofile=str(spec.path) + " (linked)", lineterm="", n=2,
            )
        )
        if not diff:
            print("\nno change")
            return 0
        print()
        print("\n".join(diff))
        if not args.yes:
            print("\n(dry run: re-run with --yes to write)")
            return 0
        backup = spec.path.with_suffix(spec.path.suffix + ".bak")
        backup.write_text(text, encoding="utf-8")
        spec.path.write_text(updated, encoding="utf-8")
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        print(f"\n✓ wrote {spec.path} ({stamp}); backup at {backup.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
