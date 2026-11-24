# spec.yaml — format reference

One file per capability, at `.specs/<capability>/spec.yaml`. It is the source of
truth: `graph.html` and the test evidence are generated from it, never edited by
hand.

## Version control

`.specs/` is tooling, not architecture — but the YAML inside it is a decision
record someone will need to review.

| file | git |
|---|---|
| `spec.yaml` | **commit** |
| `graph.html`, `results.json`, `checks.json` | ignore (rebuilt by the scripts) |

```gitignore
.specs/**/graph.html
.specs/**/results.json
.specs/**/checks.json
```

`spec_lint.py` prints the git state: `tracked`, `untracked`, or `ignored` with the
rule that matched. An ignored spec — by `.gitignore` or `.git/info/exclude` — is
deliberately local: leave it, never `git add -f`. A repository that tracks
generated artifacts gets a warning.

## Top level

| field | type | required | notes |
|---|---|---|---|
| `kind` | enum | no | `behaviour` (default) or `refactor` |
| `spec` | string | yes | kebab-case capability id, unique in the repo |
| `title` | string | yes | human name shown in the graph |
| `version` | int | yes | bump when a delta is folded in |
| `status` | enum | yes | `draft`, `proposed`, `approved`, `implemented`, `superseded` |
| `tier` | enum | no | `micro`, `standard`, `machine`, `flow` — informational, the graph follows the data |
| `link_style` | enum | no | `explicit` (default) or `name` — how tests find behaviours |
| `objective` | string | yes | who benefits, what changes, what must stay true |
| `repo.commands.test` | string | for verify | the exact command, including the JUnit reporter |
| `repo.commands.junit` | string | no | default `reports/junit.xml` |
| `repo.root` | string | no | repo root relative to the spec; otherwise discovered — pass `--repo` when the spec lives outside the repo |
| `conventions` | list | no | repo-wide invariants every behaviour inherits (`INV-N`) |
| `context` | list | no | facts a newcomer needs (`CTX-N`): money units, error types, naming |
| `machine` | mapping | one of | states + transitions |
| `flow` | mapping | one of | steps + branches |
| `behaviours` | list | yes | 1–15 entries |

Exactly one of `machine` / `flow`, or neither (`micro` / `standard`). A `refactor` plan uses `steps` instead — see below.

## Behaviours

```yaml
behaviours:
  - id: BEH-001                     # BEH-NNN, stable, never renumbered
    title: Starting a queued job moves it to running
    rule: "WHEN a queued job is started THE SYSTEM SHALL record started_at and move the job to running."
    status: approved                # draft | proposed | approved | implemented | divergent
    transition: T-1                 # optional link into the machine/flow
    scenarios:
      - id: SC-001                  # SC-NNN, unique in the file
        given:                      # string or list; optional
          - "a job in the queue"
        when: "the worker starts the job"     # exactly one action, a string
        then:                                 # list; observable outcomes
          - "the job is running"
          - "started_at is set"
    refs:
      - path: src/worker.py
        symbol: Worker.start        # symbol first; line numbers rot
    tests:
      - tests/test_worker.py::test_start_moves_job_to_running
```

Rules enforced by `spec_lint.py`:

- id patterns `BEH-NNN`, `SC-NNN`; no duplicates.
- `rule` must contain `SHALL`.
- `when` is a string (a list is rejected: one `When` per scenario).
- `then` is non-empty; a `then` that says "calls X" gets a warning.
- `status: implemented` without `tests` gets a warning.
- `transition` must name a machine transition (`T-N`) or a flow step (`S-N`);
  an uncovered transition or step gets a warning.

## Machine

```yaml
machine:
  initial: idle
  states:
    - id: idle
      name: Idle
      description: "Nothing in flight."
  transitions:
    - id: T-1
      from: idle            # string or list (one edge per source)
      to: running
      event: start          # the trigger; `on` is avoided on purpose (YAML 1.1 booleans)
      guard: "a job is queued"
      effect: "sets started_at"
      refs:
        - path: src/worker.py
          symbol: Worker.start
```

Checks: `initial` must exist; every `from`/`to` must exist; duplicate ids are
errors; unreachable states and behaviour-less transitions are warnings.

## Flow

```yaml
flow:
  steps:
    - id: S-1
      name: Receive file
      description: "Validate header and size."
      next: [S-2]
    - id: S-2
      name: Parse
      next: []
```

`next` may be a list (branching). Steps can be referenced from
`behaviour.transition` the same way transitions are, and a step with no
behaviour gets the same warning as an uncovered transition.

## Refactor plans (`kind: refactor`)

A refactor must not change observable behaviour, so the test suite is the
contract — writing scenarios for it would only mirror the tests. The plan states
the structural target, the steps, and the evidence instead.

```yaml
kind: refactor
spec: split-money
title: Extract cent arithmetic into money.py
goal: "All multiplication of prices lives in orderkit/money.py."

invariants:
  - id: INV-1
    rule: "Order.total_cents SHALL keep its name and stay frozen after submit."
    refs: [{path: orderkit/order.py, symbol: total_cents}]
    tests: [tests/test_order.py::test_total_is_frozen_at_submit]

checks:
  - id: CHK-1
    title: order.py no longer owns the total
    run: python scripts/check_structure.py no-compute-total

steps:
  - id: S-1
    title: Add money.py with line_total
    status: done
    touches: [{path: orderkit/money.py}]
    check: CHK-1
```

| field | type | notes |
|---|---|---|
| `goal` | string | structural property, checkable by a command |
| `invariants` | list | `INV-N`, `rule` containing SHALL, `refs`, optional `tests` |
| `checks` | list | `CHK-N`, `title`, `run`, optional `expect_exit` (default 0) |
| `steps` | list | `S-N`, `title`, `status`, `depends_on`, `touches`, `check`, `note` |

Step status: `todo`, `doing`, `done`, `blocked`. `depends_on` must be acyclic.

**Check semantics.** `run` executes from the repo root through the shell; the
check passes when the exit code equals `expect_exit` (default `0`). A grep that
passes by finding nothing needs `expect_exit: 1`. `spec_checks.py` writes
`checks.json`; the plan graph colours the steps and badges the check result.

```
python spec_checks.py .specs/split-money/spec.yaml --render
```

A step whose status is `done` but whose check fails is painted as a failure —
the same "evidence, not claims" rule as behaviours.

Validation rejects: dependency cycles, unknown check ids, missing `touches`
paths, duplicate ids, unknown statuses, and `behaviours`/`machine`/`flow` inside
a refactor plan.

**Finishing a plan.** Fold the result into the capability's spec as a new
`INV-N` (refs to the new structure, `version` bumped), then move the plan
directory to `.specs/archive/<capability>/` and set `status: implemented`. Root
resolution follows the `.specs` ancestor, so an archived plan still lints and
`spec_checks.py` still runs its checks. Only the YAML is committed; the
generated files stay ignored.

## EARS phrasing

The `rule` is one sentence, always in the same order: preconditions, trigger,
system, response.

| pattern | shape | example |
|---|---|---|
| ubiquitous | The `<system>` shall `<response>` | The API shall reject requests without a token. |
| state-driven | While `<state>`, the `<system>` shall `<response>` | While the order is shipped, the system shall reject cancellation. |
| event-driven | When `<trigger>`, the `<system>` shall `<response>` | When a payment is recorded, the system shall store the payment id. |
| unwanted | If `<trigger>`, then the `<system>` shall `<response>` | If the email is unknown, then the system shall return the same message. |
| optional | Where `<feature>`, the `<system>` shall `<response>` | Where SSO is enabled, the system shall hide the password field. |
| complex | While `<state>`, when `<trigger>`, the `<system>` shall `<response>` | While offline, when a retry fires, the system shall queue the request. |

If the sentence needs "and" to describe two different triggers, it is two
behaviours.

## Status lifecycle

```
draft ──▶ proposed ──▶ approved ──▶ implemented
              │            │             │
              └── superseded            divergent (test disagrees)
```

`status` is a human decision. `spec_verify.py` never edits the file; it reports
pass/fail and the graph paints the difference. `divergent` is for the case where
the spec was approved and the code does something else — decide with the user
whether the spec or the code is wrong.

## References

```yaml
refs:
  - path: orderkit/order.py
    symbol: Order.submit
```

- `path` is relative to the repo root; it must exist.
- `symbol` must appear in the file. `Class.method`, `Class::method` and plain
  names are accepted (the last segment is matched).
- Prefer symbols over line numbers. A moved function should not invalidate a
  citation.
- `spec_lint.py --no-refs` skips the checks (for a spec drafted before the code
  exists). A spec with unchecked refs is not ready for an implementation gate.

## Linking tests

`link_style: explicit` (the default) keeps the spec's vocabulary out of the repo:
tests are named the way the project already names them, and the mapping lives
here, on the behaviour:

```yaml
tests:
  - tests/test_order.py::test_add_item_to_draft_updates_total
```

`link_style: name` additionally accepts a `BEH-NNN` token in the test name. Opt
into it only when the team wants that convention visible in CI output and grep.

`spec_link.py` maintains the mapping:

| command | does |
|---|---|
| `spec_link.py spec.yaml` | collects tests, shows suggestions and unlinked tests |
| `spec_link.py spec.yaml --check` | exit 1 when a declared id no longer exists — use in pre-commit or CI |
| `spec_link.py spec.yaml --apply` | prints the diff of links it would write |
| `spec_link.py spec.yaml --apply --yes` | writes them (`.bak` kept), merging links that still resolve |

Collection uses `repo.commands.collect` when set, otherwise the test command's
interpreter with `-m pytest --collect-only -q`. Suggestions are weighted token
overlap between the behaviour's title/rule and the test's function name — a
starting point, not an authority. Renaming a test is reported as *stale*;
moving it to another file is reported as *moved*.

When a test is also cited in `refs` (as evidence), a rename breaks two things:
`spec_lint.py` fails on the `symbol`, and `spec_link.py --check` fails on the
node id. Fix both — the lint error is not noise, it is the citation rotting.

## YAML subset

The scripts ship a small parser, so a machine with no PyYAML still works. It
supports: block mappings/sequences by indentation, plain and quoted scalars,
`true`/`false`/`null`/numbers, inline lists `[a, b]`, inline maps `{k: v}`,
comments, and block scalars `|` / `>` (with `-`/`+` chomping). It does **not**
support anchors, aliases, multi-document files, tags, or multi-line plain
scalars — use `>` for paragraphs.

Two consequences:

- Quote any value containing `: ` (colon-space) or starting with `-`, `?`, `#`.
- Do not use `on`, `yes`, `no`, `off` as keys: YAML 1.1 parsers (PyYAML) turn
  them into booleans. Use `event`, not `on`.

The subset round-trips identically under PyYAML for the files this skill
produces, so other tooling can read them. When you change the parser, diff its
output against `yaml.safe_load` on a real spec before trusting it — YAML 1.1
boolean keys and folded-scalar chomping are where the two diverge.

## Making tests reportable

`spec_verify.py` needs JUnit XML, not console text. Put the reporter in
`repo.commands.test` so one command both runs the suite and writes the report:

| stack | fragment |
|---|---|
| pytest | `--junitxml=reports/junit.xml` |
| vitest | `--reporter=junit --outputFile=reports/junit.xml` |
| jest | `--reporters=default --reporters=jest-junit` (output via `JEST_JUNIT_OUTPUT_*`) |
| Go | `gotestsum --junitfile reports/junit.xml -- ./...` |

TRX (dotnet), TAP and plain console output are not JUnit: convert them
(`trx2junit`, `tap-junit`) and point `repo.commands.junit` at the result. A
missing report is a setup error — the verifier exits 2 and says so, it never
reports a green run.

A `BEH-NNN` token in the test name is not the mapping: links are matched by the
declared `tests:` entry, and renaming a test drops the behaviour to `missing`
until the entry follows (`spec_link.py --check` enforces it). `link_style: name`
merely adds the token as an optional secondary match.

## results.json

Written by `spec_verify.py`, read by `spec_render.py --results`:

```json
{
  "generated": "2026-11-22T22:18:43-03:00",
  "command": "pytest -q --junitxml=reports/junit.xml",
  "exit_code": 0,
  "totals": {"tests": 14, "passed": 14, "failed": 0, "skipped": 0},
  "behaviours": {
    "BEH-001": {"status": "pass", "tests": [{"name": "tests/test_order.py::test_add_item_to_draft_updates_total", "ok": true}]}
  },
  "unmapped": ["tests/test_misc.py::test_smoke"]
}
```

`behaviours.<id>.status` is `pass`, `fail` or `missing`. Absent means no test was
declared for that behaviour.
