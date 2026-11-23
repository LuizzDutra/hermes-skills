---
name: spec-graph
description: "Behaviour specs as YAML + reviewable graph, before code."
version: 1.3.2
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [spec, behaviour, bdd, graph, requirements, tdd, yaml]
    related_skills: [test-driven-development, spike, requesting-code-review, systematic-debugging]
---

# spec-graph

A behaviour spec is a **validated YAML file**; the graph is a **projection of that file**, never a drawing made from chat prose. The same file gives you review, test skeletons and pass/fail evidence.

```
propose ──▶ render ──▶ human review ──▶ implement (TDD, one behaviour)
   ▲            │                          │
   └── amend ───┴──── verify ──────────────┘
```

**Core principle:** if it is not in the YAML, it is not in the graph, and it is not in the spec.

## When to use

- A new feature with observable behaviour.
- A **behaviour change** to existing code (delta spec; see below).
- Anything with states, guards or an order of operations.
- Adopting the skill in a repo that already has tests: bootstrap the links with `spec_link.py` (see `references/workflows.md`).
- A **refactor** with a checkable structural target and more than a couple of steps (`kind: refactor`, Mode 6).
- The user says "spec this", "what should it do first", "show me the behaviour", "implement this spec".

**Not for:** typos, formatting, dependency bumps, a one-step refactor, or a refactor whose goal cannot be expressed as a command ("clean up X"). Open-ended exploration goes to `spike` first, then comes back with what it learned.

## Artifacts

```
.specs/<capability>/
  spec.yaml      # commit this — source of truth and review artifact
  graph.html     # generated: interactive review surface (do not commit)
  results.json   # generated: test evidence (do not commit)
  checks.json    # generated: refactor checks (do not commit)
```

`.specs/` keeps the project root clean and reads as tooling to teammates who
never install the skill.

**Commit `spec.yaml`, and nothing else.** It is the decision a reviewer needs;
everything next to it is rebuilt by the scripts:

```gitignore
.specs/**/graph.html
.specs/**/results.json
.specs/**/checks.json
```

**Respect the ignore.** Before staging, run `spec_lint.py`: it prints a `git`
line saying whether the spec is tracked, untracked, or ignored. If it is
ignored — by `.gitignore` or `.git/info/exclude` — the file is deliberately
local. Report that and stop: **never `git add -f` a spec**. The same holds for
an excluded directory: do not edit `.gitignore` or `.git/info/exclude` to make
your spec show up.

Four tiers — pick the smallest honest one and say which you picked:

| tier | shape | use for |
|---|---|---|
| `micro` | behaviours only, no graph | one endpoint, one rule, 2-4 behaviours |
| `standard` | behaviours + conventions/context | a feature without a lifecycle |
| `machine` | states + transitions | lifecycles, statuses, permission flows |
| `flow` | steps + branches | pipelines, request paths, ingestion |

Ids: `BEH-001` behaviour, `SC-001` scenario, `T-1` transition, `INV-1` convention, `CTX-1` context.

## Scripts (stdlib only, Python 3.9+)

Set `SKILL` to the `skill_dir` returned by `skill_view(name='spec-graph')`.

| command | does |
|---|---|
| `python $SKILL/scripts/spec_lint.py .specs/x/spec.yaml` | schema, ids, machine wiring, **file/symbol refs** |
| `python $SKILL/scripts/spec_render.py .specs/x/spec.yaml` | writes `graph.html` |
| `python $SKILL/scripts/spec_render.py spec.yaml --results results.json --diff old.yaml` | graph with pass/fail + change rings |
| `python $SKILL/scripts/spec_verify.py spec.yaml --render` | runs `repo.commands.test`, parses JUnit, marks the graph |
| `python $SKILL/scripts/spec_link.py spec.yaml --check` | fail when a linked test id no longer exists |
| `python $SKILL/scripts/spec_link.py spec.yaml --apply` | suggest + write the `tests:` links (diff first) |
| `python $SKILL/scripts/spec_checks.py plan.yaml --render` | runs a refactor plan's checks, marks the steps |
| `python $SKILL/scripts/spec_tests.py spec.yaml --only BEH-003` | failing test skeleton for TDD |

`spec_render.py` exits 1 when lint fails — the HTML still renders, with a red banner, so the review can continue while errors exist.

**Working on the scripts.** They are stdlib-only on purpose (no PyYAML, no pytest import): exercise them with a bare interpreter — `python spec_lint.py --help` — not only with the repo's venv, or an accidental third-party import goes unnoticed. Never call `subprocess` directly to run a repo command: use `run_command()` from `spec_model.py`, which repairs the executable token on Windows (cmd.exe reads `.venv/Scripts/python.exe` as switches) and decodes child output as bytes. Read `references/renderer.md` before touching `graph.html`.

## Mode 1 — propose (agent drafts, human reviews)

1. **Discover before writing.** Search the repo for entry points, the state model, existing tests and naming. Open every file you intend to cite — a ref you did not open is a guess.
2. **State assumptions first**, as a short list, before the spec: stack, storage, auth, scope. Silence reads as consent.
3. **Write `spec.yaml`** into `.specs/<capability>/`. Pick the tier. Every behaviour gets an EARS rule, at least one scenario, and only real refs.
4. **Lint until clean:** `spec_lint.py`. Fix errors; read warnings (uncovered transitions are usually missing behaviours, occasionally a missing state).
5. **Render and show it:**
   ```
   python $SKILL/scripts/spec_render.py .specs/<cap>/spec.yaml
   ```
   then put this alone on its own line in your reply: `::preview{file="<abs path>/graph.html"}`
6. **Stop.** Summarise in 3-5 lines: tier, behaviour count, the risky parts, and **Open Questions** as a numbered list. Do not write code, do not start tests, do not "quickly scaffold" anything. Approval comes in a later turn.

## Mode 2 — ingest (human gives the spec, agent implements)

When the user hands over a spec — prose, a `.feature` file, a ticket, or a partial YAML:

1. Read it whole. Do not start from the first paragraph you can map.
2. Normalise it into `spec.yaml` **without changing intent**. Where the source is silent, do not invent: put the gap under Open Questions.
3. Emit an **ASSUMPTIONS** block — every inference you made, one line each, numbered, so the user can veto them in one reply.
4. Lint, render, preview, and stop with: assumptions, open questions, and "approve to implement".
5. Only after explicit approval, go to Mode 4.

An ingested spec is not an approved spec. The approval is a separate human message.

## Mode 3 — amend (delta, not rewrite)

For behaviour changes to shipped code, the spec covers **only what changes**:

```yaml
# .specs/<capability>/delta-<change>.yaml
spec: <capability>
delta_of: <capability>
current: "what happens today"
new: "what must happen after"
must_not_change: [BEH-004]
```

Render the new file with `--diff .specs/<capability>/spec.yaml`: added and changed behaviours get a dashed ring. After the change ships and tests pass, fold the delta into the main spec, bump `version`, and delete the delta file. Never edit a shipped spec to describe behaviour that does not exist yet.

Rules that keep a delta reviewable:

- **Only the affected subgraph.** The delta's `machine` copies the states and edges the change touches, not the whole machine — a copy drifts the first time the main spec moves.
- **Write it to its own HTML.** `--out .specs/<capability>/delta-<change>.html`; the default output is `graph.html`, which would overwrite the main graph sitting in the same directory.
- **Additive by construction.** A delta carries what changes; `--diff` reports added and changed behaviours, never removals, because the untouched ones still live in the main spec.
- **A new operation is its own behaviour.** When a decided rule needs something the shipped spec lacks (removing a line, reassigning a coupon), add that operation as a behaviour in the delta — do not hide it inside a `when` clause.
- **Folding can overflow the cap.** Count before folding: if the delta pushes the capability past 15 behaviours, the change belongs in a new capability (e.g. `discounts`) instead of growing the old one.

## Mode 4 — implement (approved spec → TDD)

1. Order behaviours by dependency: transitions that unblock others first.
2. For each behaviour, **one at a time**:
   - `spec_tests.py --only BEH-00N` gives a skeleton; refine it into a real failing test with the name the repo would use anyway.
   - Link it: `spec_link.py --apply` suggests candidates from the test names, you confirm the diff. The mapping lives in the spec, never in the test name.
   - Run it, watch it fail for the right reason.
   - Minimal code to pass. Run the whole suite.
3. Update `status` as you go: `approved` → `implemented`. A behaviour is `implemented` only when its tests exist and pass.

**Do not generate all tests first.** The `test-driven-development` skill forbids horizontal slicing: all-RED then all-GREEN produces tests written against imagined interfaces. One behaviour per Red-Green-Refactor cycle.

## Mode 5 — verify (evidence, not claims)

```
python $SKILL/scripts/spec_verify.py .specs/<cap>/spec.yaml --render
```

It runs the repo's test command, parses JUnit, and maps cases to behaviours by the `tests:` entry in each behaviour (exact node id, or the same function at a new path). A `BEH-NNN` token in the test name is accepted **only** when the spec sets `link_style: name`. Re-render, preview, and report the table.

**The command must emit JUnit XML.** The verifier runs `repo.commands.test` exactly as written and does not inject `--junitxml`; if the repo has no reporter, add one and set `repo.commands.junit` before claiming verification. TRX/TAP output needs conversion first. No report means no evidence: the verifier exits 2, and the graph stays teal/unverified.

- **A failing behaviour is `divergent`**, not "almost done". Say which scenario failed and fix code or spec — but decide which is wrong *with the user* when the spec was already approved.
- **A behaviour with no matching test** is `untested`; the graph shows it amber with `missing`.
- **A dead ref** means the code moved: re-resolve the ref, do not delete the citation.

## Mode 6 — refactor plans (`kind: refactor`)

A refactor has no new behaviour, so a behaviour spec would only mirror the test suite. What it does have is a **structural target** and an **order of steps** — same file format, different body:

```yaml
kind: refactor
spec: split-money
title: Extract cent arithmetic into money.py
goal: "All multiplication of prices lives in orderkit/money.py."
invariants:
  - id: INV-1
    rule: "Order.total_cents SHALL keep its name and stay frozen after submit."
    refs: [{path: orderkit/order.py, symbol: total_cents}]
checks:
  - id: CHK-1
    title: order.py no longer owns the total
    run: .venv/bin/python scripts/check_structure.py no-compute-total
steps:
  - id: S-1
    title: Add money.py with line_total
    status: done
    touches: [{path: orderkit/money.py}]
    check: CHK-1
```

Rules:

- `goal` names a property a **command can check**. "Clean up billing" is not a goal; "no module in `domain/` imports `infra/`" is.
- `checks` are shell commands where **exit 0 means the property holds**. For grep-style checks that pass when nothing matches, set `expect_exit: 1`.
- `invariants` are what must still be true afterwards (public API, error types, the suite). They carry refs, and optionally the tests that would catch a regression.
- `steps` form a DAG via `depends_on`; `status` is `todo | doing | done | blocked`.
- **A step marked `done` whose check fails is a lie**, and the graph paints it red. Same rule as behaviours: evidence, not claims.

Loop: `spec_lint.py` → `spec_checks.py --render` → preview → update a status → re-run. The linter rejects dependency cycles, unknown check ids, and `touches` paths that do not exist.

**Finishing.** Fold the outcome into the capability's spec as a new `INV-N`
(refs to the new structure) and bump that spec's `version`; then move it to
`.specs/archive/<capability>/` and set `status: implemented`. Root resolution
follows any `.specs` ancestor, so the archived plan still lints and its checks
still run.

Do **not** track progress by editing the graph or by flipping colours: status lives in the plan, results come from the last run.

## Hard rules

- Every `rule` contains **SHALL** (EARS). If you cannot phrase it that way, you do not yet know the behaviour.
- **One `When` per scenario.** A second action is a second scenario.
- `Then` states something observable from outside: output, stored state, a message, a status. Not "calls X", not a class name.
- **Refs must exist.** `spec_lint.py` checks path and symbol; cite `Class.method` or a test name, and prefer symbol over line number. Every cited file must have been opened in this session.
- **Only `spec.yaml` is committed.** Never stage `graph.html`, `results.json` or `checks.json`; never `git add -f` a spec that `.gitignore` or `.git/info/exclude` excludes.
- **A refactor plan states a checkable goal.** If no command can tell you whether the refactor is finished, it is a task list, not a plan.
- **Link tests in the spec, not in their names.** The default `link_style: explicit` keeps `BEH-NNN` out of the repo: tests keep their natural names, the behaviour carries `tests:`. Renamed or deleted tests are caught by `spec_link.py --check`. Use `link_style: name` only when the team wants ids in the names.
- **Never approve your own spec.** Draft → user approves. No exceptions, including "the user seems busy".
- **≤ 15 behaviours per spec.** More means two capabilities — split them.
- **No new dependency in the repo** for this (no Cucumber, no pydantic). The scripts are stdlib-only by design.
- The graph is generated only from the validated YAML. Never hand-edit `graph.html`.

## Review surface

The HTML is self-contained (no CDN) and adapts to the frame:

- **Graph** — states as nodes, events as labelled edges; edge colour = worst attached behaviour; dashed = transition with no behaviour; click a node/edge for guard, effect, behaviours, refs.
- **Behaviours** — invariants and context first, then behaviour cards grouped by status.
- **Trace** — behaviours → tests → cited files, orphans highlighted.
- **Table** — plain reading view for review.
- **Plan / Steps / Checks** — for `kind: refactor`: steps as a dependency graph, step cards with the attached check, and the last check run.
- **Unverified vs passing** — teal = `implemented` with no test run behind it; green appears only after `spec_verify.py` wrote `results.json`. Never read teal as done, and never "fix" it by editing the colour.
- **Inspector** — rule, scenarios, tests with pass/fail, refs with `open` actions, and an **Ask to change this behaviour** button that sends a prompt back into the chat.

Use the frame: one `::preview{file="..."}` line, no prose dump of the whole spec. Point at the 2-3 behaviours that need a decision. When the user asks to open a graph by name, re-render it first — the file on disk may predate the last edit to the YAML.

## Red flags

| Symptom | Reality |
|---|---|
| Graph drawn from your summary instead of the YAML | The graph is now a lie; regenerate from the file |
| A ref you never opened | It is a guess; open it or drop it |
| "I'll add the error cases later" | They are behaviours; add them now or list them as out of scope |
| Spec and code both changed in the same turn | Review gate skipped; revert to spec-only |
| 25 behaviours in one file | Two capabilities; split |
| A test with no behaviour link | `spec_link.py` suggests the node id; the graph shows it amber until confirmed |
| `BEH-001` stamped into every test name | A convention the repo did not ask for; use explicit links |
| "Implemented" with no tests | It is `approved`, not `implemented` |
| Everything green before any test ran | Without `results.json` every claim is teal/unverified; green is earned by a run |
| Editing a shipped spec for unreleased behaviour | Use a delta spec |

## Verification checklist

- [ ] `spec_lint.py` passes (warnings read, not ignored)
- [ ] every ref path and symbol exists; every cited file was opened
- [ ] every behaviour has ≥1 scenario, one `When` each, observable `Then`s
- [ ] graph rendered from this exact file, preview shown
- [ ] approvals came from the user, in a later turn
- [ ] `spec_link.py --check` passes: every linked test id still exists
- [ ] `spec_verify.py` run after implementation; no `fail`, no `missing`
- [ ] refactor plans: `spec_checks.py` run, and no step is `done` with a red check, unmapped tests triaged
- [ ] spec committed with the code; delta folded in when shipped

## Files

- `references/format.md` — full YAML schema, EARS patterns, id rules, parser subset
- `references/workflows.md` — exact wording for propose/ingest/amend/implement/verify
- `references/renderer.md` — invariants for maintaining the HTML review surface
- `templates/spec.spec.yaml` — annotated behaviour-spec starting point
- `templates/refactor.plan.yaml` — `kind: refactor` starting point
- `scripts/` — lint, render, verify, link, checks, test skeletons (stdlib only)
