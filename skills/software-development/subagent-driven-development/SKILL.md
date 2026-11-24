---
name: subagent-driven-development
description: Use when executing a plan via delegated subagents.
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [delegation, subagents, orchestration, refactor, plan-execution]
    related_skills: [test-driven-development, architecture-decision-review]
---

# Subagent-driven development

## When to use

The user hands you a written plan — phases, acceptance criteria, file paths — or says "execute this
with subagents". Also when the work is wide enough that one context drowns: several independent
files, a mechanical migration, long test runs.

## Procedure

1. **Pre-flight yourself, before dispatching anything.** Branch, clean tree, one baseline run of the
   suite. Record the count and the last commit: without a baseline, no later "expected failure" is
   provable.
2. **Turn the plan into rounds.** A round is the set of phases whose file sets are disjoint.
   Everything else is sequential. Typical software shape: contract → (vendor implementation ∥ fake
   implementation) → composition root → test migration → boundary tests.
3. **Point at the plan, don't paste it.** Give the absolute path, the phase heading, and the
   acceptance command. The plan is the spec; retyping it into the brief is how two versions start to
   diverge.
4. **Paste exact code for mechanical artifacts** — a fake, a signature, a dataclass. Composed from a
   prose description, children produce a variant you then have to debug.
5. **Decide the ambiguities in the brief.** Children cannot ask questions. Where the plan is wrong,
   pick the option and state why, so the deviation is a decision instead of a surprise.
6. **Between rounds: verify, then commit.** Re-run the suite, read the diff, run the boundary
   checks, commit the phase yourself with the message you chose. When the plan file doubles as
   the user's tracking surface, update its status column with the commit SHAs in the same pass —
   a stale "next" row makes the user re-ask what is already done.
7. **Report one status line and end the turn.** Results arrive between turns; do not poll
   transcripts or artifacts to wait.

A brief template lives in `templates/phase-brief.md` — copy it per phase and fill the placeholders.

### Review rounds (user-gated)

When the user asks for a review pass and wants to confirm before anything is fixed, the round
is look-then-fix, not loop:

- Dispatch the reviewer read-only: it must not touch the repository, and any probe it needs
  (mutation testing, repro scripts) runs against a disposable copy, never the working tree.
- Present the findings atomically and end the turn. Do not fix anything in the round the user
  asked to gate — including the findings that are obviously safe. On confirmation, execute the
  whole confirmed block in one pass and commit it once.
- When the phase MOVED logic between modules (a refactor, not a feature), brief the reviewer to
  diff OLD vs NEW implementations across an input matrix — enumerate the inputs and compare both
  behaviors — instead of reading only the new code. A translation that changed houses is where
  silent divergences hide; reading the new code in isolation reads as correct by construction.
- Children inherit the parent model by default. A distinct reviewer model requires a pin in
  the delegation config — check that the profile carries it before promising a model switch.

### Plan-execute rounds (user-gated)

When the user asks for a plan "to validate" before execution, the accept is a hard gate:

- Write the plan to a file, present a summary, and end the turn. Nothing is dispatched in the
  turn the plan is delivered.
- Brief the planner to measure its own baseline (collect-only counts, suite durations, gate
  result) instead of accepting handed-down numbers — a plan built on secondhand numbers
  inherits their errors and steers the executor wrong. Re-run the load-bearing ones yourself
  before presenting the plan for approval.
- On accept, fold the user's decisions into the plan file first, then dispatch — the brief and
  the plan must agree, and the plan file is what a later session reads.
- A defect found while reviewing your own plan (import cycle, dependency inverted in the commit
  order) is fixed in the plan file and disclosed at presentation — never dispatched as-is.

## Rules

- **Children never run git in parallel.** Parallel children race the index, and serialized commits keep the history and the messages yours. A single serialized execution child may commit its own sub-steps (one green commit at a time, staged by explicit path — the spec-graph Mode 6 shape); the parent still verifies every commit before quoting it. Checkout, stash and rebase are never a child's job.
- **The file set is the unit of parallelism.** Two agents editing one file lose work silently; widen
  the round only when the paths are disjoint.
- **A child never runs the full suite while a sibling is mid-write** — it reads a tree that does not
  exist yet. Give it its own test path plus `-p no:cacheprovider` and `PYTHONDONTWRITEBYTECODE=1`;
  concurrent runs otherwise race on `.pytest_cache` and `__pycache__`.
- **Name what must not change.** "Only `service.py`; do not edit tests" when the phase is
  production-only. Without it, a child makes its phase green by rewriting the assertions.
- **When the tree must be red during a phase, ask for a classification table**: test, exception
  type, expected/unexpected. "34 failed, 32 passed" proves nothing on its own.
- **Verify self-reports.** A child's "185 passed" may be its own file only. Re-run the suite; check
  `git diff <tests> | grep -c '^-.*assert'` to catch weakened tests; run the boundary greps yourself.
  When your re-measurement contradicts a self-reported metric, write the measured value into the
  tracker (plan note, status column) — the child's version is a claim and the tracker is the record
  of fact; never keep the prettier of the two.
  A green suite is not coverage: when a phase *moves* logic, break the moved code on purpose and
  confirm the suite fails before accepting the phase. New contract tests (secret non-leak, import
  boundary, status mapping) get the same proof: apply the exact flaw they claim to catch — zero the
  key, add the forbidden import — and confirm they fail before trusting them.
- **Resolve conflicting state claims against the source of truth, not plausibility.** When a child
  reports a repo state that contradicts the parent's own snapshot (ahead-count, origin position),
  don't pick a winner by plausibility — `git reflog show origin/<branch>` names the ref's source
  (update by push vs fetch) and settles it. A ref you dispatched with can be stale within the hour:
  the user pushes between messages. Briefs therefore say "confirm branch/HEAD/tree at start" and
  carry no ahead-counts as facts; only "no push" is a standing instruction.
- **An injection phase can pass while being decorative.** If the phase's goal is "dependencies
  arrive injected", check the consumer no longer constructs the concrete collaborator: a default
  argument or property that builds the real class keeps every test green while the factory is
  never called. Grep file *bodies*, not just import blocks — local imports inside defaults and
  functions smuggle outer-layer dependencies past a top-of-file layering grep.
- **Review every deviation.** Accept one that raises fidelity to production (a fake that needs a real
  event type to exercise the same mapping); reject one that relaxes an assertion or widens an
  allowlist to make the test pass. Treat the plan's "this symbol is dead" claims as hypotheses: grep
  the tree for consumers before letting a child delete a constant or helper — a module that still
  builds, tags or copies with it keeps it alive, and a deletion the plan predicted wrongly changes
  behaviour.
- **Squash phases that are only green together** — a production change and the test migration it
  forces — into a single commit. A commit that leaves the suite red is not a checkpoint.
- Two or three concurrent children is the sweet spot for one repository; more increases collision
  surface faster than it saves time.

## Pitfalls

- Dispatching phase N+1 in the same call as phase N: the child starts before the contract exists and
  invents it. Dependencies are rounds, not fan-out.
- In a move-refactor, sequence the commits home-before-consumer and walk each intermediate state:
  a plan that moves a consumer before its new home exists bakes an import cycle into the sequence,
  and it only surfaces when the child executes it, not when you read the prose.
- Commit the formatter's noise BEFORE the move, alone: run the formatter on the file(s) to move in
  their own commit first, so the move commit's byte/AST comparison shows only intentional edits —
  mixed in, reformatting masquerades as edits and the "moved byte for byte" proof becomes
  unprovable after the fact.
- Children inherit no conversation. Repeat repo path, branch, test command and constraints in every
  brief, even if you sent them minutes ago.
- A child can "complete" by deleting the failing test. The assert-count check is the cheap detector.
- Long phases time out mid-edit. Ask for small verified steps inside the brief (test → implement →
  run) so a timeout still leaves a compilable tree.
- Green tests are not the deliverable. After the last round, exercise the end-to-end path yourself —
  a real run through the new wiring, not just the suite.
- Reverting a mutation with `git checkout` also discards the uncommitted work the round left in
  that file. `cp` the original to a scratch path before mutating and restore from the copy.
- Make the test tree a package (`tests/__init__.py`) when helpers live in conftest and other
  files import them as `from tests.conftest import X`. Without the package init, pytest imports
  the same conftest under two module names and identity/`isinstance` checks across files
  fracture; the init makes pytest load conftest once as `tests.conftest`.
