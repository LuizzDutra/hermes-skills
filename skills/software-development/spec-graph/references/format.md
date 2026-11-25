# spec.yaml — format reference

One file per capability, at `.specs/<capability>/spec.yaml`. It is the source of truth: `graph.html` and the test evidence are generated from it, never edited by hand.

This file owns the schema. `SKILL.md` owns the gates and the hard rules, `references/workflows.md` owns the wording of each mode, `references/renderer.md` owns the review surface.

## Top level

| field | type | required | notes |
|---|---|---|---|
| `kind` | enum | no | `behaviour` (default) or `refactor` |
| `spec` | string | yes | kebab-case capability id, unique in the repo |
| `title` | string | yes | human name shown in the graph |
| `version` | int | yes | bump when a delta is folded in; starts at 1 |
| `status` | enum | yes | `draft`, `proposed`, `approved`, `implemented`, `superseded` — see Status lifecycle |
| `tier` | enum | no | `micro`, `standard`, `machine`, `flow` — informational, the graph follows the data |
| `link_style` | enum | no | `explicit` (default) or `name` — how tests find behaviours |
| `objective` | string | yes | who benefits, what changes, what must stay true |
| `repo.commands.test` | string | for verify | the exact command, including the JUnit reporter |
| `repo.commands.junit` | string | no | default `reports/junit.xml` |
| `repo.commands.collect` | string | no | command that lists test ids; default is `pytest --collect-only -q` on the test command's interpreter |
| `repo.root` | string | no | repo root relative to the spec; otherwise discovered — pass `--repo` when the spec lives outside the repo |
| `conventions` | list | no | repo-wide invariants every behaviour inherits (`INV-N`) |
| `context` | list | no | facts a newcomer needs (`CTX-N`): money units, error types, naming |
| `machine` | mapping | one of | states + transitions |
| `flow` | mapping | one of | steps + branches |
| `behaviours` | list | yes | 1–15 entries; more means two capabilities |

Exactly one of `machine` / `flow`, or neither (`micro` / `standard`). A `refactor` plan uses `steps` instead and still needs `version` and `status`.

Ids: `BEH-001` behaviour, `SC-001` scenario, `T-1` transition, `INV-1` convention or invariant, `CTX-1` context, `CHK-1` check, `S-1` step. Ids are stable: never renumber, retire instead.

## Behaviours

```yaml
behaviours:
  - id: BEH-001                     # BEH-NNN, stable, never renumbered
    title: Starting a queued job moves it to running
    rule: "WHEN a queued job is started THE SYSTEM SHALL record started_at and move the job to running."
    status: approved                # draft | proposed | approved | implemented
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

Enforced by `spec_lint.py`: id patterns `BEH-NNN` and `SC-NNN` with no duplicates; `rule` contains `SHALL`; `when` is a string (a list is rejected — one `When` per scenario); `then` is non-empty, and a `then` that says "calls X" gets a warning; `status: implemented` without `tests` gets a warning; `transition` must name a real `T-N` or `S-N`, and an uncovered transition or step gets a warning.

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

Checks: `initial` must exist; every `from`/`to` must exist; duplicate ids are errors; unreachable states and behaviour-less transitions are warnings.

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

`next` may be a list (branching). Steps are referenced from `behaviour.transition` the same way transitions are, and a step with no behaviour gets the same warning as an uncovered transition. Every step needs an incoming `next:` from somewhere: an orphan lands in the last column and widens the whole graph past what the frame can hold (see the review surface in `SKILL.md`).

## Refactor plans (`kind: refactor`)

A refactor must not change observable behaviour, so the test suite is the contract and writing scenarios for it would only mirror the tests. The plan states the structural target, the steps and the evidence instead.

```yaml
kind: refactor
spec: split-money
title: Extract cent arithmetic into money.py
version: 1
status: approved
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

Step status: `todo`, `doing`, `done`, `blocked`. `depends_on` must be acyclic. Validation rejects dependency cycles, unknown check ids, missing `touches` paths, duplicate ids, unknown statuses, and `behaviours` / `machine` / `flow` inside a refactor plan.

Check semantics: `run` executes from the repo root through the shell, and the check passes when the exit code equals `expect_exit` (default `0`). A grep that passes by finding nothing needs `expect_exit: 1`. `spec_checks.py` writes `checks.json`; the plan graph colours the steps and badges the result.

Running plans in anger — upgrading placeholder checks, consolidating checks into a repo suite, amending a plan mid-flight, delegating a big step, proving a no-behaviour-change step, moving files a check cites — is in `references/refactor-playbook.md`.

## EARS phrasing

The `rule` is one sentence, always in the same order: preconditions, trigger, system, response.

| pattern | shape | example |
|---|---|---|
| ubiquitous | The system SHALL response | The API shall reject requests without a token. |
| state-driven | While state, the system SHALL response | While the order is shipped, the system shall reject cancellation. |
| event-driven | When trigger, the system SHALL response | When a payment is recorded, the system shall store the payment id. |
| unwanted | If trigger, then the system SHALL response | If the email is unknown, then the system shall return the same message. |
| optional | Where feature, the system SHALL response | Where SSO is enabled, the system shall hide the password field. |
| complex | While state, when trigger, the system SHALL response | While offline, when a retry fires, the system shall queue the request. |

The token is literal in the YAML: a Portuguese repo writes `O SISTEMA SHALL registrar o horário` — the linter greps for the word, and a fully translated rule (`DEVE`) fails lint. A sentence that needs "and" to describe two triggers is two behaviours.

## Status lifecycle

```
draft ──▶ proposed ──▶ approved ──▶ implemented
             │             │             │
             └── superseded            divergent (a test disagrees)
```

| status | who sets it | what it means |
|---|---|---|
| `draft` | the agent, while writing | not shown to anyone yet; may not even lint clean |
| `proposed` | propose and ingest, at the end of their turn | rendered and awaiting the human's approval — the agent stops here |
| `approved` | the human, in a later message | the gate passed, implementation may start |
| `implemented` | the agent, once a linked test passes | evidence exists; still teal until a run is recorded |
| `divergent` | the report, never the file | an approved behaviour whose test disagrees |
| `superseded` | the human | replaced by another capability or a folded delta |

Only a human moves a spec to `approved`. `spec_verify.py` never edits the file: it reports pass/fail and the graph paints the difference. `divergent` is the case where the spec was approved and the code does something else — decide *with the user* whether the spec or the code is wrong.

The graph paints four buckets, not six: `implemented` (teal without a test run, green with one), `untested`, `proposed`, `failing`. `approved` folds into `untested` — agreed and not built is untested, and a separate bucket told the reviewer nothing — while `draft` and `divergent` keep their own colours but stay out of the legend. Palette details belong to `references/renderer.md`.

## References

```yaml
refs:
  - path: orderkit/order.py
    symbol: Order.submit
```

- `path` is relative to the repo root; it must exist.
- `symbol` must appear in the file. `Class.method`, `Class::method` and plain names are accepted (the last segment is matched).
- Prefer symbols over line numbers: a moved function should not invalidate a citation.
- `spec_lint.py --no-refs` skips the checks for a spec drafted before the code exists. A spec with unchecked refs is not ready for an implementation gate.
- A dead ref means the code moved: re-resolve it, do not delete the citation.

## Linking tests

`link_style: explicit` (the default) keeps the spec's vocabulary out of the repo: tests are named the way the project already names them, and the mapping lives here, on the behaviour.

```yaml
tests:
  - tests/test_order.py::test_add_item_to_draft_updates_total
```

`link_style: name` additionally accepts a `BEH-NNN` token in the test name. Opt into it only when the team wants that convention visible in CI output and grep.

`spec_link.py` maintains the mapping: no flag lists suggestions and unlinked tests, `--check` exits 1 when a declared id no longer exists (use it in pre-commit or CI), `--apply` prints the diff of links it would write, `--apply --yes` writes them (`.bak` kept, links that still resolve are merged).

Collection uses `repo.commands.collect` when set, otherwise the test command's interpreter with `-m pytest --collect-only -q`. Suggestions are weighted token overlap between the behaviour's title/rule and the test's function name — a starting point, not an authority. A renamed test is reported as *stale*; the same function at a new path is reported as *moved* and still resolves.

When a test is also cited in `refs` as evidence, a rename breaks two things: `spec_lint.py` fails on the `symbol` and `spec_link.py --check` fails on the node id. Fix both — the lint error is not noise, it is the citation rotting.

## Making tests reportable

`spec_verify.py` needs JUnit XML, not console text. Put the reporter in `repo.commands.test` so one command both runs the suite and writes the report.

| stack | fragment |
|---|---|
| pytest | `--junitxml=reports/junit.xml` |
| vitest | `--reporter=junit --outputFile=reports/junit.xml` |
| jest | `--reporters=default --reporters=jest-junit` (output via `JEST_JUNIT_OUTPUT_*`) |
| Go | `gotestsum --junitfile reports/junit.xml -- ./...` |

TRX (dotnet), TAP and plain console output are not JUnit: convert them (`trx2junit`, `tap-junit`) and point `repo.commands.junit` at the result. A missing report is a setup error — the verifier exits 2 and says so; it never reports a green run.

A `BEH-NNN` token in the test name is not the mapping: links are matched by the declared `tests:` entry, so renaming a test drops the behaviour to `missing` until the entry follows.

## Parser subset

The scripts parse a documented YAML subset with their own stdlib parser, so a machine with no PyYAML still works. The grammar, its two quoting rules (`: ` and a leading `-`, `?` or `#` must be quoted; never use `on`/`yes`/`no`/`off` as keys) and the PyYAML round-trip check live in the module docstring of `scripts/spec_model.py`. The shape of `results.json` lives in `scripts/spec_verify.py`. One source each, next to the code that implements it.
