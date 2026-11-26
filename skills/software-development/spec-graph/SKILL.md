---
name: spec-graph
description: "Behaviour specs as YAML + reviewable graph, before code."
version: 1.4.5
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

## Quick start

Set `SKILL` to the `skill_dir` that `skill_view(name='spec-graph')` returns, then:

```
cp $SKILL/templates/spec.spec.yaml .specs/<capability>/spec.yaml   # or refactor.plan.yaml, delta.spec.yaml, demo.spec.yaml
python $SKILL/scripts/spec_lint.py .specs/<capability>/spec.yaml   # fix errors, read warnings
python $SKILL/scripts/spec_render.py .specs/<capability>/spec.yaml # writes graph.html next to the spec
```

Put this alone on its own line in your reply: `::preview{file="<abs path>/.specs/<capability>/graph.html"}` — then stop for approval.

## When to use

- A new feature with observable behaviour, or a **behaviour change** to shipped code (delta spec).
- Anything with states, guards or an order of operations.
- Adopting the skill in a repo that already has tests: bootstrap the links with `spec_link.py` (`references/workflows.md`).
- A **refactor** with a checkable structural target and more than a couple of steps (`kind: refactor`).
- The user says "spec this", "what should it do first", "show me the behaviour", "implement this spec".
- The user asks for a **demo or mock graph** that exercises every status bucket: start from `templates/demo.spec.yaml` and back it with a real test run, never with hand-painted colours.

**Not for:** typos, formatting, dependency bumps, a one-step refactor, or a refactor whose goal cannot be expressed as a command ("clean up X"). Open-ended exploration goes to `spike` first, then comes back with what it learned.

Four tiers — pick the smallest honest one and say which you picked:

| tier | shape | use for |
|---|---|---|
| `micro` | behaviours only, no graph | one endpoint, one rule, 2-4 behaviours |
| `standard` | behaviours + conventions/context | a feature without a lifecycle |
| `machine` | states + transitions | lifecycles, statuses, permission flows |
| `flow` | steps + branches | pipelines, request paths, ingestion |

## Modes

One row per mode; the exact wording, the ASSUMPTIONS/OPEN QUESTIONS blocks and the autonomous fallback live in `references/workflows.md`.

| mode | what you do | the gate |
|---|---|---|
| **propose** | discover the repo, state assumptions, write `spec.yaml` as `proposed`, lint, render, preview | stop. Approval comes in a later message |
| **ingest** | normalise a spec the user handed over without changing intent; label every inference | stop. An ingested spec is not an approved spec |
| **amend** | delta spec for shipped behaviour: only the affected subgraph, own HTML, `--diff` for rings | stop. Fold into the main spec only after it ships |
| **implement** | one behaviour per red-green cycle: skeleton → real test → link → minimal code | the suite green, per behaviour |
| **verify** | run the repo's tests, map JUnit onto behaviours, re-render | no `fail`, no `missing` |
| **refactor** | plan with a checkable goal, invariants, checks, ordered steps (`kind: refactor`) | every check green, no step `done` while its check is red |

The refactor mode is where plans go wrong in practice — read `references/refactor-playbook.md` before the second step of any plan bigger than a couple of files.

## Artifacts

```
.specs/<capability>/
  spec.yaml      # commit this — source of truth and review artifact
  graph.html     # generated: interactive review surface (do not commit)
  results.json   # generated: test evidence (do not commit)
  checks.json    # generated: refactor checks (do not commit)
```

**Commit `spec.yaml`, and nothing else.** It is the decision a reviewer needs; everything next to it is rebuilt by the scripts, so the three generated files go in `.gitignore`.

**Respect the ignore.** `spec_lint.py` prints a `git` line saying whether the spec is tracked, untracked, or ignored. If it is ignored — by `.gitignore` or `.git/info/exclude` — the file is deliberately local: report that and stop. Never `git add -f` a spec, and never edit `.gitignore` or `.git/info/exclude` to make your spec show up.

## Scripts (stdlib only, Python 3.9+)

| command | does |
|---|---|
| `python $SKILL/scripts/spec_lint.py <spec>` | schema, ids, machine wiring, file/symbol refs, git state |
| `python $SKILL/scripts/spec_render.py <spec>` | writes `graph.html`; with `--results` and `--diff` it paints pass/fail and change rings |
| `python $SKILL/scripts/spec_verify.py <spec> --render` | runs `repo.commands.test`, parses JUnit, marks the graph |

The other four are one `--help` away: `spec_link.py` (suggest, apply and check the `tests:` links), `spec_checks.py` (run a plan's checks, `--render` to refresh), `spec_tests.py` (a failing skeleton for one behaviour), `spec_model.py` (the library the rest import).

Exit codes, because "it printed something" is not a result:

| script | 0 | 1 | 2 |
|---|---|---|---|
| `spec_lint.py` | no errors (warnings are fine) | schema, ref or wiring error | — |
| `spec_render.py` | written, lint clean | written **with a red banner** — lint failed, not evidence | — |
| `spec_verify.py` | every declared behaviour passed | a behaviour failed or is missing | no JUnit report: a setup error, never a green run |
| `spec_checks.py` | every step's check satisfied | at least one check failed | — |
| `spec_link.py --check` | every declared test id resolves | a declared id is stale | collection failed |

**Working on the scripts.** They are stdlib-only on purpose (no PyYAML, no pytest import): exercise them with a bare interpreter — `python spec_lint.py --help` — not only with the repo's venv, or an accidental third-party import goes unnoticed. Never call `subprocess` directly to run a repo command: use `run_command()` from `spec_model.py`, which repairs the executable token on Windows (cmd.exe reads `.venv/Scripts/python.exe` as switches) and decodes child output as bytes. Read `references/renderer.md` before touching `graph.html`.

**Mirror edits into the repo the skill was installed from.** The profile copy is what runs; the installed tree is the source of truth — resolve that repo from the skill directory (`git -C <skill_dir> rev-parse --show-toplevel`, or the repo that contains it), never from a hardcoded path. After a batch of edits copy every changed file across, prove parity with `diff -rq --exclude=__pycache__` between the two trees, and commit; leave the push to the user. An edit left only in the profile is overwritten by the next install. Diff the two trees **before** committing: parallel sessions mirror profile edits into the repo under their own commits, and a commit that only re-copies already-mirrored files comes back `nothing to commit` — the parity diff tells you whether anything is still yours to commit.

## Hard rules

- **Every `rule` contains `SHALL`; a scenario has exactly one `when`; every `then` is observable from outside** (output, stored state, a message, a status — not "calls X"). A sentence that needs "and" for two triggers is two behaviours.
- **Refs must exist and must have been opened in this session.** `spec_lint.py` checks path and symbol; cite `Class.method` or a test name, and prefer symbol over line number.
- **Only `spec.yaml` is committed.** Never stage `graph.html`, `results.json` or `checks.json`; never `git add -f` a spec that git ignores.
- **Never approve your own spec.** Draft → the human approves. No exceptions, including "the user seems busy".
- **≤15 behaviours per spec.** More means two capabilities — split them.
- **The graph is generated only from the YAML that linted.** An invalid spec still renders, with a red banner, so review can continue — that render is never evidence.
- **Never hand-edit `graph.html`.** If a label is wrong, the YAML or the payload is wrong.
- **A render is verified by measurement, not by vision** — and only when you changed the renderer (see the review surface).
- **A refactor plan states a checkable goal.** If no command can tell you whether the refactor finished, it is a task list, not a plan.
- **Link tests in the spec, not in their names.** The default `link_style: explicit` keeps `BEH-NNN` out of the repo; `spec_link.py --check` catches a renamed or deleted test.
- **No new dependency in the repo for this** (no Cucumber, no pydantic). The scripts are stdlib-only by design.

## Review surface

The HTML is self-contained (no CDN) and adapts to the frame.

- **Graph** — states as nodes, events as labelled edges; edge colour = worst attached behaviour, dashed = transition with no behaviour; a node click lists the **behaviours attached to it first**, then the transitions in and out; an edge click shows guard, effect, behaviours, refs. The status filter and the search box dim everything that does not match, so typing `BEH-010` points at the step that owns it.
- **Behaviours** — invariants and context first, then behaviour cards grouped by status.
- **Scenarios** — one row per scenario; a row opens the full `given`/`when`/`then`. Hidden on a refactor plan.
- **Trace** — behaviours → tests → cited files, with orphans highlighted.
- **Table** — a plain reading view for review.
- **Plan / Steps / Checks** — for `kind: refactor`: steps as a dependency graph, each step card with its check, and the last check run.
- **Inspector** — rule, scenarios, tests with pass/fail, refs with `open` actions, an **Ask to change this behaviour** button that sends a prompt back into the chat, and `showScenario`/`showMeta` panels behind every clamped card. Anything cut off in a card must be readable here.

**Colour is status, never decoration.** `implemented` is teal until `spec_verify.py` writes `results.json` and green after; `approved` paints as untested, `proposed` has its own colour, a failing linked test paints red, and a `done` step with a failing check stays red. Never read teal as done and never "fix" it by editing the palette. The four buckets, the palette and the light/dark rule are in `references/renderer.md`.

**The render is a view, not the deliverable.** The preview pans, zooms and refits, and the panel docks or scrolls; a column that clips at 960px or a flow with six layers is a viewing nuisance, never a spec defect. Do not add, merge, split or reorder behaviours and steps to make a picture fit, do not compare viewports, and do not volunteer layout findings — the YAML describes the system, the graph shows what the YAML says, and the reviewer's question is about the behaviour.

**Measure only when you touched the renderer.** The page exposes `window.__probe()`: one call returns the fit (`bbox × k` against the stage width), the inspector's rect and `position`, whether a click actually opened a panel, any node off screen, the bucket counts and the computed colours. That is for editing `spec_render.py` and for click paths — a spec turn does not run it. Either way, no screenshot and no vision pass on a render you just generated: the numbers are for whoever wrote the renderer, the YAML is what the reviewer reads. Vision belongs to images the repo produces as output, never to `graph.html`. A click still needs **real pointer input** (`Input.dispatchMouseEvent`): a `dispatchEvent(new MouseEvent('click'))` probe never goes through the `setPointerCapture` the pan gesture installs, so it can pass while a real click does nothing.

**Show it, don't dump it.** One `::preview{file="..."}` line, no prose copy of the spec. When the user asks to open a graph by name, re-render first: the file on disk may predate the last edit to the YAML.

## Red flags

| Symptom | Reality |
|---|---|
| "I'll add the error cases later" | They are behaviours; add them now or list them as out of scope |
| Spec and code both changed in the same turn | The review gate was skipped; revert to spec-only |
| A test with no behaviour link | `spec_link.py` suggests the node id; the graph shows it amber until confirmed |
| Refs copied from a sibling spec | Old specs rot after a repo restructure (stale paths fail lint in bulk) — read them for field shape and tone, and take every path and symbol from a file opened this session |
| "Implemented" with no tests | It is `untested`; the claim needs a run and a linked test |
| Everything green before any test ran | Without `results.json` every claim is teal; green is earned by a run |
| A graph that clips or looks dense at 960px | It pans and refits. Reshaping the spec for the picture changes the system being specified |

## Verification checklist

- [ ] `spec_lint.py` passes (warnings read, not ignored)
- [ ] every ref path and symbol exists; every cited file was opened
- [ ] every behaviour has ≥1 scenario, one `when` each, observable `then`s
- [ ] graph rendered from this exact file and preview shown (run `window.__probe()` only if you changed the renderer)
- [ ] approvals came from the user, in a later turn
- [ ] `spec_link.py --check` passes: every linked test id still exists
- [ ] `spec_verify.py` run after implementation; no `fail`, no `missing`
- [ ] refactor plans: `spec_checks.py` run, no step `done` with a red check, unmapped tests triaged
- [ ] spec committed with the code; delta folded in when shipped

## Files

- `references/format.md` — the schema: fields, ids, EARS patterns, refs, linking, status lifecycle
- `references/workflows.md` — the exact wording of each mode, review etiquette, autonomous mode
- `references/refactor-playbook.md` — what running a plan costs: checks, consolidation, delegation, moves
- `references/renderer.md` — invariants for maintaining the HTML review surface
- `templates/spec.spec.yaml`, `templates/refactor.plan.yaml`, `templates/delta.spec.yaml`, `templates/demo.spec.yaml`
- `scripts/` — lint, render, verify, link, checks, test skeletons (stdlib only)
