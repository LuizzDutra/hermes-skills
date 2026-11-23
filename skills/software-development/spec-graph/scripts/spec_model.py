"""spec_model.py — load, validate and index a spec-graph YAML file.

Standard library only. Ships a small YAML *subset* parser so the skill works
on a bare Python install; the supported subset is documented in
references/format.md and is deliberately close enough to real YAML that files
also load with PyYAML.

Public API:
    load(path)                     -> dict
    find_repo_root(spec_path)      -> Path
    load_spec(path, repo=None)     -> Spec  (data + root + source path)
    validate(spec, root, check_refs=True) -> Report(errors, warnings, stats)
    build_payload(spec, report, results=None, diff=None) -> dict
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class SpecError(Exception):
    """A parse or schema failure, with an optional source location."""

    def __init__(self, message: str, line: int | None = None, path: str | None = None):
        self.message = message
        self.line = line
        self.path = path
        prefix = []
        if path:
            prefix.append(str(path))
        if line:
            prefix.append(f"line {line}")
        super().__init__((": ".join(prefix) + ": " if prefix else "") + message)


# --------------------------------------------------------------------------- #
# YAML subset parser
# --------------------------------------------------------------------------- #

_INT = re.compile(r"-?\d+")
_FLOAT = re.compile(r"-?\d+\.\d+")
_NULLS = {"", "~", "null", "Null", "NULL"}
_TRUES = {"true", "True", "TRUE"}
_FALSES = {"false", "False", "FALSE"}


class _Yaml:
    def __init__(self, text: str):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.lines = text.split("\n")
        self.i = 0

    # -- helpers ------------------------------------------------------------

    def _indent(self, line: str) -> int:
        n = 0
        for ch in line:
            if ch == " ":
                n += 1
            elif ch == "\t":
                raise SpecError("tabs are not allowed for indentation; use spaces", line=self.i + 1)
            else:
                break
        return n

    @staticmethod
    def _blank(line: str) -> bool:
        stripped = line.strip()
        return stripped == "" or stripped.startswith("#")

    def _skip(self) -> None:
        while self.i < len(self.lines) and self._blank(self.lines[self.i]):
            self.i += 1

    # -- entry --------------------------------------------------------------

    def parse(self):
        self._skip()
        if self.i >= len(self.lines):
            return None
        value = self._block(self._indent(self.lines[self.i]))
        self._skip()
        if self.i < len(self.lines):
            raise SpecError(f"unexpected content: {self.lines[self.i].strip()!r}", line=self.i + 1)
        return value

    def _block(self, indent: int):
        content = self.lines[self.i].strip()
        if content == "-" or content.startswith("- "):
            return self._seq(indent)
        return self._map(indent)

    # -- collections --------------------------------------------------------

    def _map(self, indent: int) -> dict:
        out: dict = {}
        while True:
            self._skip()
            if self.i >= len(self.lines):
                break
            raw = self.lines[self.i]
            ind = self._indent(raw)
            if ind < indent:
                break
            if ind > indent:
                raise SpecError(
                    "unexpected indentation (a key must align with the block it belongs to)",
                    line=self.i + 1,
                )
            content = raw.strip()
            if content == "-" or content.startswith("- "):
                break
            key, rest = self._split_kv(content, self.i + 1)
            if rest == "":
                self.i += 1
                self._skip()
                if self.i >= len(self.lines) or self._indent(self.lines[self.i]) <= indent:
                    out[key] = None
                else:
                    out[key] = self._block(self._indent(self.lines[self.i]))
            elif rest in ("|", "|-", "|+", ">", ">-", ">+"):
                out[key] = self._block_scalar(indent, rest)
            else:
                out[key] = self._scalar(rest, self.i + 1)
                self.i += 1
        return out

    def _seq(self, indent: int) -> list:
        out: list = []
        while True:
            self._skip()
            if self.i >= len(self.lines):
                break
            raw = self.lines[self.i]
            ind = self._indent(raw)
            if ind != indent:
                if ind > indent:
                    raise SpecError("unexpected indentation inside a list", line=self.i + 1)
                break
            content = raw.strip()
            if not (content == "-" or content.startswith("- ")):
                break
            if content == "-":
                self.i += 1
                self._skip()
                if self.i >= len(self.lines) or self._indent(self.lines[self.i]) <= indent:
                    out.append(None)
                else:
                    out.append(self._block(self._indent(self.lines[self.i])))
                continue
            rest = content[1:].lstrip()
            if self._looks_like_kv(rest):
                # "- id: x" -> re-read the same line as a map whose first key
                # starts at the column where `rest` already sits.
                col = self.lines[self.i].index(rest, ind + 1)
                self.lines[self.i] = " " * col + rest
                out.append(self._map(col))
            else:
                out.append(self._scalar(rest, self.i + 1))
                self.i += 1
        return out

    # -- keys and scalars ---------------------------------------------------

    def _split_kv(self, s: str, line_no: int) -> tuple[str, str]:
        if s[:1] in ("'", '"'):
            key, used = self._quoted(s, line_no)
            rest = s[used:].lstrip()
            if not rest.startswith(":"):
                raise SpecError("expected 'key: value'", line=line_no)
            return key, rest[1:].strip()
        depth = 0
        for idx, ch in enumerate(s):
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == ":" and depth == 0 and (idx + 1 == len(s) or s[idx + 1] in " \t"):
                return s[:idx].strip(), s[idx + 1:].strip()
        raise SpecError("expected 'key: value'", line=line_no)

    def _looks_like_kv(self, s: str) -> bool:
        try:
            self._split_kv(s, self.i + 1)
            return True
        except SpecError:
            return False

    def _quoted(self, s: str, line_no: int) -> tuple[str, int]:
        quote = s[0]
        buf = []
        idx = 1
        while idx < len(s):
            ch = s[idx]
            if quote == "'":
                if ch == "'":
                    if idx + 1 < len(s) and s[idx + 1] == "'":
                        buf.append("'")
                        idx += 2
                        continue
                    return "".join(buf), idx + 1
                buf.append(ch)
                idx += 1
            else:
                if ch == "\\" and idx + 1 < len(s):
                    nxt = s[idx + 1]
                    mapping = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}
                    if nxt in mapping:
                        buf.append(mapping[nxt])
                        idx += 2
                        continue
                    if nxt == "u" and idx + 5 < len(s):
                        try:
                            buf.append(chr(int(s[idx + 2: idx + 6], 16)))
                            idx += 6
                            continue
                        except ValueError:
                            pass
                    buf.append(nxt)
                    idx += 2
                    continue
                if ch == '"':
                    return "".join(buf), idx + 1
                buf.append(ch)
                idx += 1
        raise SpecError("unterminated quoted string", line=line_no)

    @staticmethod
    def _strip_comment(s: str) -> str:
        depth = 0
        for idx, ch in enumerate(s):
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "#" and depth == 0 and (idx == 0 or s[idx - 1] in " \t"):
                return s[:idx].rstrip()
        return s.rstrip()

    def _scalar(self, s: str, line_no: int):
        s = s.strip()
        if s.startswith(("'", '"')):
            value, used = self._quoted(s, line_no)
            if s[used:].strip():
                raise SpecError("unexpected text after a quoted scalar", line=line_no)
            return value
        s = self._strip_comment(s)
        if s in _NULLS:
            return None
        if s in _TRUES:
            return True
        if s in _FALSES:
            return False
        if _INT.fullmatch(s):
            return int(s)
        if _FLOAT.fullmatch(s):
            return float(s)
        if s.startswith("["):
            if not s.endswith("]"):
                raise SpecError("unterminated inline list", line=line_no)
            return [self._scalar(part, line_no) for part in self._split_flow(s[1:-1])]
        if s.startswith("{"):
            if not s.endswith("}"):
                raise SpecError("unterminated inline mapping", line=line_no)
            out = {}
            for part in self._split_flow(s[1:-1]):
                if not part.strip():
                    continue
                key, _, value = part.partition(":")
                out[self._scalar(key.strip(), line_no)] = self._scalar(value.strip(), line_no)
            return out
        return s

    @staticmethod
    def _split_flow(body: str) -> list[str]:
        parts, buf, depth, quote = [], [], 0, None
        for ch in body:
            if quote:
                buf.append(ch)
                if ch == quote:
                    quote = None
                continue
            if ch in "'\"":
                quote = ch
                buf.append(ch)
            elif ch in "[{":
                depth += 1
                buf.append(ch)
            elif ch in "]}":
                depth -= 1
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        if "".join(buf).strip():
            parts.append("".join(buf).strip())
        return parts

    # -- block scalars ------------------------------------------------------

    def _block_scalar(self, parent_indent: int, style: str) -> str:
        j = self.i + 1
        raw: list[str] = []
        while j < len(self.lines) and self.lines[j].strip() == "":
            raw.append("")
            j += 1
        if j >= len(self.lines):
            self.i = j
            return ""
        block_indent = self._indent(self.lines[j])
        if block_indent <= parent_indent:
            raise SpecError("a block scalar must be indented more than its key", line=self.i + 1)
        while j < len(self.lines):
            line = self.lines[j]
            if line.strip() == "":
                raw.append("")
                j += 1
                continue
            if self._indent(line) < block_indent:
                break
            raw.append(line[block_indent:])
            j += 1
        while raw and raw[-1] == "":
            raw.pop()
        self.i = j
        chomp = style[1:] if len(style) > 1 else ""
        text = "\n".join(raw) if style[0] == "|" else self._fold(raw)
        if chomp == "-":
            return text
        if chomp == "+":
            return text + ("\n" if text else "")
        return text + "\n" if text else ""

    @staticmethod
    def _fold(raw: list[str]) -> str:
        out: list[str] = []
        buf: list[str] = []
        for line in raw:
            if line == "":
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                out.append("")
            else:
                buf.append(line.strip())
        if buf:
            out.append(" ".join(buf))
        return "\n".join(out)


def parse_yaml(text: str):
    return _Yaml(text).parse()


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

_ROOT_MARKERS = (".git", "pyproject.toml", "package.json", "go.mod", "Cargo.toml", "setup.cfg")


def find_repo_root(spec_path: str | Path) -> Path:
    """Resolve the repository a spec belongs to.

    Order:
      1. `<root>/.specs/<capability>/spec.yaml` — the convention this skill writes
      2. the nearest ancestor with a project marker, never the home directory
      3. the spec's own directory

    A spec can always override this with `repo.root` (relative to the spec).
    """
    spec_path = Path(spec_path).resolve()
    parts = spec_path.parent.parts
    if len(parts) >= 2 and parts[-2] in ("specs", ".specs"):
        # <root>/.specs/<capability>/spec.yaml -> <root>
        if len(parts) >= 3 and parts[-3] == ".hermes":
            return Path(*parts[:-3])
        return Path(*parts[:-2])
    home = Path.home().resolve()
    for parent in spec_path.parents:
        if parent == home:
            break
        if any((parent / marker).exists() for marker in _ROOT_MARKERS):
            return parent
    return spec_path.parent


@dataclass
class Spec:
    data: dict
    path: Path
    root: Path


def load_spec(path: str | Path, repo: str | Path | None = None) -> Spec:
    path = Path(path).resolve()
    if not path.exists():
        raise SpecError(f"spec file not found: {path}", path=str(path))
    data = parse_yaml(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SpecError("the top level of a spec must be a mapping", path=str(path))
    root = Path(repo).resolve() if repo else find_repo_root(path)
    declared = (data.get("repo") or {}).get("root")
    if declared and not repo:
        root = (path.parent / str(declared)).resolve()
    return Spec(data=data, path=path, root=root)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

STATUSES = ("draft", "proposed", "approved", "implemented", "divergent", "superseded")
TIERS = ("micro", "standard", "machine", "flow")
# explicit: only `tests:` entries link tests to behaviours (repo keeps its own naming).
# name: also accept a BEH-NNN token in the test name.
LINK_STYLES = ("explicit", "name")
KINDS = ("behaviour", "refactor")
STEP_STATUSES = ("todo", "doing", "done", "blocked")
CHK_ID = re.compile(r"^CHK-\d+$")
STEP_ID = re.compile(r"^S-\d+$")
BEH_ID = re.compile(r"^BEH-\d{3}$")
SC_ID = re.compile(r"^SC-\d{3}$")
KIND_ID = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def add_error(self, message: str, path: str = "") -> None:
        self.errors.append({"message": message, "path": path})

    def add_warning(self, message: str, path: str = "") -> None:
        self.warnings.append({"message": message, "path": path})

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "stats": self.stats,
        }


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _ref_exists(root: Path, ref: dict) -> tuple[bool, str]:
    raw = ref.get("path")
    if not raw:
        return False, "ref without a path"
    target = (root / str(raw)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return False, f"ref escapes the repository root: {raw}"
    if not target.exists():
        return False, f"ref path does not exist: {raw}"
    symbol = ref.get("symbol")
    if symbol:
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return False, f"cannot read {raw}: {exc}"
        symbol = str(symbol).strip()
        # Accept `pkg.Class.method`, `Class::method` and plain names; the last
        # dotted segment is what actually appears in source.
        candidates = [symbol, symbol.split("::")[-1], symbol.split(".")[-1]]
        if not any(candidate and candidate in text for candidate in candidates):
            return False, f"symbol {symbol!r} not found in {raw}"
    return True, ""


def validate(spec: dict, root: Path | None = None, check_refs: bool = True) -> Report:
    report = Report()
    data = spec

    # -- envelope -----------------------------------------------------------
    kind = str(data.get("kind") or "behaviour")
    if kind not in KINDS:
        report.add_error(f"kind must be one of {', '.join(KINDS)}", "kind")

    required = ["spec", "title", "version", "status"]
    required += ["goal", "checks", "steps"] if kind == "refactor" else ["objective", "behaviours"]
    for key in required:
        if data.get(key) in (None, "", [], {}):
            report.add_error(f"missing required field: {key}", key)

    cap = data.get("spec")
    if cap and not isinstance(cap, str):
        report.add_error("spec must be a kebab-case string", "spec")
    elif cap and not KIND_ID.fullmatch(str(cap)):
        report.add_error(f"spec id {cap!r} must be kebab-case", "spec")

    status = data.get("status")
    if status and status not in STATUSES:
        report.add_error(f"status must be one of {', '.join(STATUSES)}", "status")

    tier = data.get("tier")
    if tier and tier not in TIERS:
        report.add_error(f"tier must be one of {', '.join(TIERS)}", "tier")

    link_style = data.get("link_style")
    if link_style and link_style not in LINK_STYLES:
        report.add_error(f"link_style must be one of {', '.join(LINK_STYLES)}", "link_style")

    version = data.get("version")
    if version is not None and not isinstance(version, int):
        report.add_error("version must be an integer", "version")

    if kind == "refactor":
        _validate_refactor(data, root, report, check_refs)
        return report

    objective = data.get("objective")
    if isinstance(objective, str) and len(objective.strip()) < 20:
        report.add_warning("objective is very short; state who benefits and what changes", "objective")

    behaviours = data.get("behaviours") or []
    if not isinstance(behaviours, list):
        report.add_error("behaviours must be a list", "behaviours")
        behaviours = []
    if len(behaviours) > 15:
        report.add_warning(
            f"{len(behaviours)} behaviours in one spec; more than 15 usually means two capabilities",
            "behaviours",
        )

    # -- machine ------------------------------------------------------------
    machine = data.get("machine")
    state_ids: list[str] = []
    transitions: dict[str, dict] = {}
    if machine is not None:
        if not isinstance(machine, dict):
            report.add_error("machine must be a mapping", "machine")
            machine = None
        else:
            states = machine.get("states") or []
            if not isinstance(states, list) or not states:
                report.add_error("machine.states must be a non-empty list", "machine.states")
                states = []
            seen_states = set()
            for st in states:
                if not isinstance(st, dict) or not st.get("id"):
                    report.add_error("every state needs an id", "machine.states")
                    continue
                sid = str(st["id"])
                if sid in seen_states:
                    report.add_error(f"duplicate state id: {sid}", f"machine.states.{sid}")
                seen_states.add(sid)
                state_ids.append(sid)
            initial = machine.get("initial")
            if not initial:
                report.add_error("machine.initial is required", "machine.initial")
            elif str(initial) not in seen_states:
                report.add_error(f"machine.initial {initial!r} is not a declared state", "machine.initial")

            trs = machine.get("transitions") or []
            if not isinstance(trs, list):
                report.add_error("machine.transitions must be a list", "machine.transitions")
                trs = []
            for tr in trs:
                if not isinstance(tr, dict) or not tr.get("id"):
                    report.add_error("every transition needs an id", "machine.transitions")
                    continue
                tid = str(tr["id"])
                if tid in transitions:
                    report.add_error(f"duplicate transition id: {tid}", f"machine.transitions.{tid}")
                transitions[tid] = tr
                if not tr.get("event"):
                    report.add_error(f"transition {tid} needs an event (`event`)", f"machine.transitions.{tid}")
                if not tr.get("to"):
                    report.add_error(f"transition {tid} needs a target (`to`)", f"machine.transitions.{tid}")
                elif str(tr["to"]) not in seen_states:
                    report.add_error(f"transition {tid} targets unknown state {tr['to']!r}", f"machine.transitions.{tid}")
                frm = _as_list(tr.get("from"))
                if not frm:
                    report.add_error(f"transition {tid} needs a source (`from`)", f"machine.transitions.{tid}")
                for src in frm:
                    if str(src) not in seen_states:
                        report.add_error(f"transition {tid} starts at unknown state {src!r}", f"machine.transitions.{tid}")

            # reachability
            if machine.get("initial") in seen_states:
                adj: dict[str, set] = {sid: set() for sid in state_ids}
                for tr in transitions.values():
                    for src in _as_list(tr.get("from")):
                        if str(src) in adj and tr.get("to") in adj:
                            adj[str(src)].add(str(tr["to"]))
                seen, queue = {str(machine["initial"])}, [str(machine["initial"])]
                while queue:
                    node = queue.pop()
                    for nxt in adj.get(node, ()):  # noqa: B007
                        if nxt not in seen:
                            seen.add(nxt)
                            queue.append(nxt)
                for sid in state_ids:
                    if sid not in seen:
                        report.add_warning(f"state {sid!r} is unreachable from {machine['initial']}", f"machine.states.{sid}")

    flow = data.get("flow")
    step_ids: list[str] = []
    if flow is not None:
        if machine is not None:
            report.add_error("a spec declares either `machine` or `flow`, not both", "flow")
        if not isinstance(flow, dict):
            report.add_error("flow must be a mapping", "flow")
        else:
            steps = flow.get("steps") or []
            if not isinstance(steps, list) or not steps:
                report.add_error("flow.steps must be a non-empty list", "flow.steps")
                steps = []
            for step in steps:
                if not isinstance(step, dict) or not step.get("id"):
                    report.add_error("every flow step needs an id", "flow.steps")
                    continue
                step_ids.append(str(step["id"]))
            for step in steps:
                for nxt in _as_list((step or {}).get("next")):
                    if str(nxt) not in step_ids:
                        report.add_error(f"flow step {step.get('id')} points at unknown next {nxt!r}", "flow.steps")

    # -- behaviours ---------------------------------------------------------
    seen_beh: set[str] = set()
    seen_sc: set[str] = set()
    attached: dict[str, list[str]] = {tid: [] for tid in transitions}
    for idx, beh in enumerate(behaviours):
        where = f"behaviours[{idx}]"
        if not isinstance(beh, dict):
            report.add_error("a behaviour must be a mapping", where)
            continue
        bid = beh.get("id")
        if not bid:
            report.add_error("behaviour without an id", where)
            continue
        bid = str(bid)
        where = f"behaviours.{bid}"
        if not BEH_ID.fullmatch(bid):
            report.add_error(f"behaviour id {bid!r} must match BEH-NNN", where)
        if bid in seen_beh:
            report.add_error(f"duplicate behaviour id: {bid}", where)
        seen_beh.add(bid)

        title = beh.get("title")
        if not title:
            report.add_error(f"{bid} needs a title", where)
        bstatus = beh.get("status")
        if bstatus and bstatus not in STATUSES:
            report.add_error(f"{bid} has unknown status {bstatus!r}", where)
        if bstatus == "implemented" and not _as_list(beh.get("tests")):
            report.add_warning(f"{bid} is marked implemented but lists no tests", where)

        rule = beh.get("rule")
        if not rule:
            report.add_error(f"{bid} needs a rule sentence (EARS: WHEN … SHALL …)", where)
        elif " shall " not in f" {str(rule).lower()} ":
            report.add_error(f"{bid} rule must contain SHALL (EARS form)", where)

        scenarios = beh.get("scenarios") or []
        if not isinstance(scenarios, list) or not scenarios:
            report.add_error(f"{bid} needs at least one scenario", where)
            scenarios = []
        for sidx, sc in enumerate(scenarios):
            swhere = f"{where}.scenarios[{sidx}]"
            if not isinstance(sc, dict):
                report.add_error("a scenario must be a mapping", swhere)
                continue
            sid = sc.get("id")
            if not sid:
                report.add_error(f"{bid} scenario {sidx} needs an id", swhere)
            else:
                sid = str(sid)
                if not SC_ID.fullmatch(sid):
                    report.add_error(f"scenario id {sid!r} must match SC-NNN", swhere)
                if sid in seen_sc:
                    report.add_error(f"duplicate scenario id: {sid}", swhere)
                seen_sc.add(sid)
            when = sc.get("when")
            if not when:
                report.add_error(f"{bid} scenario {sid or sidx} needs a `when`", swhere)
            elif isinstance(when, list):
                report.add_error(f"{bid} scenario {sid or sidx} has several `when` steps; split it", swhere)
            then = sc.get("then")
            if not _as_list(then):
                report.add_error(f"{bid} scenario {sid or sidx} needs at least one `then`", swhere)
            for outcome in _as_list(then):
                low = str(outcome).lower()
                if re.search(r"\bcalls?\b|\binvokes?\b", low):
                    report.add_warning(
                        f"{bid} scenario {sid or sidx}: `then` looks like an internal call, not observable behaviour",
                        swhere,
                    )

        tid = beh.get("transition")
        if tid:
            if tid not in transitions:
                report.add_error(f"{bid} links to unknown transition {tid!r}", where)
            else:
                attached[str(tid)].append(bid)

        for ref in _as_list(beh.get("refs")):
            if not isinstance(ref, dict):
                report.add_error(f"{bid} has a malformed ref (expected a mapping)", where)
                continue
            if check_refs and root is not None:
                exists, why = _ref_exists(root, ref)
                if not exists:
                    report.add_error(f"{bid}: {why}", where)

    for tid, bids in attached.items():
        if not bids:
            src = ", ".join(str(x) for x in _as_list(transitions[tid].get("from")))
            dst = transitions[tid].get("to")
            report.add_warning(
                f"transition {tid} ({src} → {dst}) has no behaviour attached",
                f"machine.transitions.{tid}",
            )

    # -- conventions / context ---------------------------------------------
    for section in ("conventions", "context"):
        for item in _as_list(data.get(section)):
            if not isinstance(item, dict) or not item.get("id"):
                report.add_error(f"every {section} entry needs an id", section)
                continue
            if section == "conventions" and not item.get("rule"):
                report.add_error(f"convention {item['id']} needs a rule", f"{section}.{item['id']}")
            if section == "context" and not item.get("note"):
                report.add_error(f"context {item['id']} needs a note", f"{section}.{item['id']}")
            for ref in _as_list(item.get("refs")):
                if check_refs and root is not None:
                    exists, why = _ref_exists(root, ref)
                    if not exists:
                        report.add_error(f"{item['id']}: {why}", f"{section}.{item['id']}")

    # -- stats --------------------------------------------------------------
    impl = sum(1 for b in behaviours if isinstance(b, dict) and b.get("status") == "implemented")
    report.stats = {
        "behaviours": len(behaviours),
        "scenarios": sum(len(_as_list((b or {}).get("scenarios"))) for b in behaviours if isinstance(b, dict)),
        "implemented": impl,
        "states": len(state_ids),
        "transitions": len(transitions),
        "steps": len(step_ids),
        "errors": len(report.errors),
        "warnings": len(report.warnings),
    }
    return report


# --------------------------------------------------------------------------- #
# Payload for the renderer
# --------------------------------------------------------------------------- #


def _ref_status(root: Path | None, ref: dict, check_refs: bool) -> dict:
    out = dict(ref)
    if not check_refs or root is None:
        out["ok"] = None
        return out
    exists, why = _ref_exists(root, ref)
    out["ok"] = exists
    if not exists:
        out["why"] = why
    return out


def _result_for(beh: dict, results: dict | None) -> tuple[str, list]:
    """Return (status, tests detail) for one behaviour."""
    if not results:
        return "", []
    table = (results.get("behaviours") or {}).get(beh["id"])
    if not table:
        return ("missing" if _as_list(beh.get("tests")) else ""), []
    return table.get("status", ""), table.get("tests", [])


def build_payload(
    spec: Spec,
    report: Report,
    results: dict | None = None,
    diff: dict | None = None,
    check_refs: bool = True,
) -> dict:
    data = spec.data
    if str(data.get("kind") or "behaviour") == "refactor":
        return _payload_refactor(spec, report, results, diff, check_refs)
    root = spec.root
    behaviours = [b for b in (data.get("behaviours") or []) if isinstance(b, dict) and b.get("id")]
    by_id = {str(b["id"]): b for b in behaviours}

    machine = data.get("machine")
    if isinstance(machine, dict):
        states = []
        for st in machine.get("states") or []:
            if not isinstance(st, dict) or not st.get("id"):
                continue
            states.append(
                {
                    "id": str(st["id"]),
                    "name": st.get("name") or str(st["id"]),
                    "description": st.get("description") or "",
                }
            )
        transitions = []
        for tr in machine.get("transitions") or []:
            if not isinstance(tr, dict) or not tr.get("id"):
                continue
            transitions.append(
                {
                    "id": str(tr["id"]),
                    "from": [str(x) for x in _as_list(tr.get("from"))],
                    "to": str(tr.get("to") or ""),
                    "event": str(tr.get("event") or ""),
                    "guard": str(tr.get("guard") or ""),
                    "effect": str(tr.get("effect") or ""),
                    "refs": [_ref_status(root, r, check_refs) for r in _as_list(tr.get("refs")) if isinstance(r, dict)],
                    "behaviours": [
                        str(b["id"]) for b in behaviours if isinstance(b, dict) and b.get("transition") == tr.get("id")
                    ],
                }
            )
        machine = {"initial": str(machine.get("initial") or ""), "states": states, "transitions": transitions}

    flow = data.get("flow")
    if isinstance(flow, dict):
        flow = {
            "steps": [
                {
                    "id": str(s.get("id")),
                    "name": s.get("name") or str(s.get("id")),
                    "description": s.get("description") or "",
                    "next": [str(x) for x in _as_list(s.get("next"))],
                    "behaviours": [
                        str(b["id"]) for b in behaviours if isinstance(b, dict) and b.get("transition") == s.get("id")
                    ],
                }
                for s in flow.get("steps") or []
                if isinstance(s, dict) and s.get("id")
            ]
        }

    out_behaviours = []
    for beh in behaviours:
        status, tests_detail = _result_for(beh, results)
        out_behaviours.append(
            {
                "id": str(beh["id"]),
                "title": beh.get("title") or "",
                "rule": beh.get("rule") or "",
                "status": beh.get("status") or "draft",
                "transition": beh.get("transition") or "",
                "scenarios": [
                    {
                        "id": sc.get("id") or "",
                        "given": _as_list(sc.get("given")),
                        "when": sc.get("when") or "",
                        "then": _as_list(sc.get("then")),
                    }
                    for sc in _as_list(beh.get("scenarios"))
                    if isinstance(sc, dict)
                ],
                "refs": [_ref_status(root, r, check_refs) for r in _as_list(beh.get("refs")) if isinstance(r, dict)],
                "tests": [str(t) for t in _as_list(beh.get("tests"))],
                "result": status,
                "results": tests_detail,
            }
        )

    conventions = []
    for item in _as_list(data.get("conventions")):
        if isinstance(item, dict) and item.get("id"):
            conventions.append(
                {
                    "id": str(item["id"]),
                    "rule": item.get("rule") or "",
                    "refs": [_ref_status(root, r, check_refs) for r in _as_list(item.get("refs")) if isinstance(r, dict)],
                }
            )
    context = []
    for item in _as_list(data.get("context")):
        if isinstance(item, dict) and item.get("id"):
            context.append(
                {
                    "id": str(item["id"]),
                    "note": item.get("note") or "",
                    "refs": [_ref_status(root, r, check_refs) for r in _as_list(item.get("refs")) if isinstance(r, dict)],
                }
            )

    counts = {
        "behaviours": len(out_behaviours),
        "passing": sum(1 for b in out_behaviours if b["result"] == "pass"),
        "failing": sum(1 for b in out_behaviours if b["result"] == "fail"),
        "untested": sum(1 for b in out_behaviours if not b["tests"]),
        "uncoveredTransitions": sum(1 for t in (machine or {}).get("transitions", []) if not t["behaviours"]),
        "deadRefs": sum(1 for b in out_behaviours for r in b["refs"] if r.get("ok") is False),
    }

    return {
        "spec": data.get("spec") or "",
        "title": data.get("title") or "",
        "version": data.get("version") or 1,
        "status": data.get("status") or "draft",
        "tier": data.get("tier") or "",
        "objective": (data.get("objective") or "").strip(),
        "source": str(spec.path),
        "root": str(spec.root),
        "generated": results.get("generated") if results else None,
        "machine": machine,
        "flow": flow,
        "behaviours": out_behaviours,
        "conventions": conventions,
        "context": context,
        "counts": counts,
        "report": report.as_dict(),
        "diff": diff or {"added": [], "changed": [], "removed": []},
    }


def dump_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


# --------------------------------------------------------------------------- #
# Running repo commands (shared by spec_verify and spec_link)
# --------------------------------------------------------------------------- #


def fix_exe(cmd: str) -> str:
    """cmd.exe treats `/` as a switch, so `.venv/Scripts/python.exe` must become a
    backslash path on Windows. Only the executable token is touched; arguments keep
    their slashes (pytest, node and friends accept them)."""
    if os.name != "nt":
        return cmd
    match = re.match(r'^([^\s"\']+)', cmd)
    if not match:
        return cmd
    head = match.group(1)
    if "/" in head and not re.match(r"^[A-Za-z]+://", head):
        return head.replace("/", "\\") + cmd[len(head):]
    return cmd


def run_command(cmd: str, cwd: Path, timeout: int = 1800) -> tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    proc = subprocess.run(fix_exe(cmd), cwd=str(cwd), shell=True, capture_output=True, timeout=timeout, env=env)
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    return proc.returncode, out + err


# --------------------------------------------------------------------------- #
# Refactor plans (kind: refactor)
# --------------------------------------------------------------------------- #


def _validate_refactor(data: dict, root: Path | None, report: Report, check_refs: bool) -> None:
    """Steps, structural checks and invariants — no behaviours."""
    goal = str(data.get("goal") or "").strip()
    if len(goal) < 20:
        report.add_warning("goal is very short; name the structural property that must be true at the end", "goal")
    if data.get("behaviours"):
        report.add_error("a refactor spec declares `invariants` and `steps`, not `behaviours`", "behaviours")
    if data.get("machine") or data.get("flow"):
        report.add_error("a refactor spec does not declare a machine or flow; use `steps`", "steps")

    checks = data.get("checks") or []
    if not isinstance(checks, list):
        report.add_error("checks must be a list", "checks")
        checks = []
    check_ids: set[str] = set()
    for idx, chk in enumerate(checks):
        where = f"checks[{idx}]"
        if not isinstance(chk, dict):
            report.add_error("a check must be a mapping", where)
            continue
        cid = str(chk.get("id") or "")
        if not CHK_ID.fullmatch(cid):
            report.add_error(f"check id {cid!r} must match CHK-N", where)
        if cid in check_ids:
            report.add_error(f"duplicate check id: {cid}", where)
        check_ids.add(cid)
        if not chk.get("title"):
            report.add_warning(f"{cid or 'check'} has no title", where)
        if not chk.get("run"):
            report.add_error(f"{cid or 'check'} needs a `run` command", where)
        if not isinstance(chk.get("expect_exit", 0), int):
            report.add_error(f"{cid or 'check'} expect_exit must be an integer", where)

    steps = data.get("steps") or []
    if not isinstance(steps, list):
        report.add_error("steps must be a list", "steps")
        steps = []
    step_ids = [str(s.get("id") or "") for s in steps if isinstance(s, dict)]
    seen: set[str] = set()
    deps: dict[str, list[str]] = {}
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            report.add_error("a step must be a mapping", f"steps[{idx}]")
            continue
        sid = str(step.get("id") or "")
        where = f"steps.{sid}"
        if not STEP_ID.fullmatch(sid):
            report.add_error(f"step id {sid!r} must match S-N", where)
        if sid in seen:
            report.add_error(f"duplicate step id: {sid}", where)
        seen.add(sid)
        if not step.get("title"):
            report.add_error(f"{sid} needs a title", where)
        status = step.get("status") or "todo"
        if status not in STEP_STATUSES:
            report.add_error(f"{sid} has unknown status {status!r}", where)
        cid = step.get("check")
        if cid and str(cid) not in check_ids:
            report.add_error(f"{sid} references unknown check {cid!r}", where)
        deps[sid] = [str(d) for d in _as_list(step.get("depends_on"))]
        for dep in deps[sid]:
            if dep not in step_ids:
                report.add_error(f"{sid} depends on unknown step {dep!r}", where)
        for touch in _as_list(step.get("touches")):
            if not isinstance(touch, dict):
                report.add_error(f"{sid} has a malformed touches entry (expected a mapping with path)", where)
                continue
            if check_refs and root is not None:
                exists, why = _ref_exists(root, touch)
                if not exists:
                    report.add_error(f"{sid}: {why}", where)

    colour: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        state = colour.get(node, 0)
        if state == 1:
            report.add_error(f"dependency cycle: {' → '.join(trail + [node])}", "steps")
            return
        if state == 2:
            return
        colour[node] = 1
        for dep in deps.get(node, []):
            if dep in deps:
                visit(dep, trail + [node])
        colour[node] = 2

    for sid in deps:
        visit(sid, [])

    invariants = _as_list(data.get("invariants"))
    if not invariants:
        report.add_warning("no invariants: a refactor needs at least one property that must still hold", "invariants")
    inv_ids: set[str] = set()
    for idx, inv in enumerate(invariants):
        if not isinstance(inv, dict):
            report.add_error("an invariant must be a mapping", f"invariants[{idx}]")
            continue
        iid = str(inv.get("id") or "")
        where = f"invariants.{iid}"
        if not re.fullmatch(r"INV-\d+", iid):
            report.add_error(f"invariant id {iid!r} must match INV-N", where)
        if iid in inv_ids:
            report.add_error(f"duplicate invariant id: {iid}", where)
        inv_ids.add(iid)
        rule = inv.get("rule")
        if not rule:
            report.add_error(f"{iid} needs a rule", where)
        elif " shall " not in f" {str(rule).lower()} ":
            report.add_error(f"{iid} rule must contain SHALL", where)
        for ref in _as_list(inv.get("refs")):
            if check_refs and root is not None and isinstance(ref, dict):
                exists, why = _ref_exists(root, ref)
                if not exists:
                    report.add_error(f"{iid}: {why}", where)

    done = sum(1 for s in steps if isinstance(s, dict) and s.get("status") == "done")
    report.stats = {
        "kind": "refactor",
        "steps": len(steps),
        "done": done,
        "checks": len(checks),
        "invariants": len(invariants),
        "errors": len(report.errors),
        "warnings": len(report.warnings),
    }


def _payload_refactor(spec: Spec, report: Report, results: dict | None, diff: dict | None, check_refs: bool) -> dict:
    data, root = spec.data, spec.root
    check_results = (results or {}).get("checks") or {}

    checks = []
    for chk in _as_list(data.get("checks")):
        if not isinstance(chk, dict) or not chk.get("id"):
            continue
        cid = str(chk["id"])
        checks.append(
            {
                "id": cid,
                "title": chk.get("title") or "",
                "run": str(chk.get("run") or ""),
                "expect_exit": chk.get("expect_exit", 0),
                "result": check_results.get(cid),
            }
        )

    steps = []
    for step in _as_list(data.get("steps")):
        if not isinstance(step, dict) or not step.get("id"):
            continue
        sid = str(step["id"])
        cid = str(step.get("check") or "")
        steps.append(
            {
                "id": sid,
                "title": step.get("title") or "",
                "status": step.get("status") or "todo",
                "note": step.get("note") or "",
                "depends_on": [str(d) for d in _as_list(step.get("depends_on"))],
                "check": cid,
                "checkResult": check_results.get(cid) if cid else None,
                "touches": [
                    _ref_status(root, t, check_refs)
                    for t in _as_list(step.get("touches"))
                    if isinstance(t, dict)
                ],
            }
        )

    invariants = []
    for inv in _as_list(data.get("invariants")):
        if not isinstance(inv, dict) or not inv.get("id"):
            continue
        invariants.append(
            {
                "id": str(inv["id"]),
                "rule": inv.get("rule") or "",
                "refs": [_ref_status(root, r, check_refs) for r in _as_list(inv.get("refs")) if isinstance(r, dict)],
                "tests": [str(t) for t in _as_list(inv.get("tests"))],
            }
        )

    counts = {
        "steps": len(steps),
        "done": sum(1 for s in steps if s["status"] == "done"),
        "doing": sum(1 for s in steps if s["status"] == "doing"),
        "todo": sum(1 for s in steps if s["status"] == "todo"),
        "blocked": sum(1 for s in steps if s["status"] == "blocked"),
        "checks": len(checks),
        "passing": sum(1 for c in checks if (c["result"] or {}).get("ok") is True),
        "failing": sum(1 for c in checks if (c["result"] or {}).get("ok") is False),
        "invariants": len(invariants),
    }

    return {
        "kind": "refactor",
        "spec": data.get("spec") or "",
        "title": data.get("title") or "",
        "version": data.get("version") or 1,
        "status": data.get("status") or "draft",
        "tier": data.get("tier") or "",
        "objective": str(data.get("goal") or "").strip(),
        "goal": str(data.get("goal") or "").strip(),
        "source": str(spec.path),
        "root": str(spec.root),
        "generated": (results or {}).get("generated"),
        "machine": None,
        "flow": None,
        "behaviours": [],
        "steps": steps,
        "checks": checks,
        "invariants": invariants,
        "conventions": [],
        "context": [],
        "counts": counts,
        "report": report.as_dict(),
        "diff": diff or {"added": [], "changed": [], "removed": []},
    }


# --------------------------------------------------------------------------- #
# Git awareness (read-only)
# --------------------------------------------------------------------------- #


def git_state(path: Path, root: Path) -> dict:
    """How git sees this file. Best-effort and never raises.

    Returns {"repo", "tracked", "ignored", "reason"}; "reason" is the
    .gitignore / .git/info/exclude line that matched, when ignored.
    """

    def run(*args: str):
        try:
            return subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True, timeout=20)
        except Exception:
            return None

    probe = run("rev-parse", "--is-inside-work-tree")
    if probe is None or probe.returncode != 0 or probe.stdout.strip() != "true":
        return {"repo": False, "tracked": False, "ignored": False, "reason": ""}

    try:
        rel = str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        rel = str(path)

    tracked = run("ls-files", "--error-unmatch", "--", rel)
    ignored = run("check-ignore", "--no-index", "-v", "--", rel)
    reason = ""
    if ignored is not None and ignored.returncode == 0 and ignored.stdout.strip():
        reason = ignored.stdout.strip().splitlines()[0].split("\t")[0]
    return {
        "repo": True,
        "tracked": tracked is not None and tracked.returncode == 0,
        "ignored": ignored is not None and ignored.returncode == 0,
        "reason": reason,
    }
