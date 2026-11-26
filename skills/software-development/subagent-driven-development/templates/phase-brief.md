# Phase brief: <phase title>

## Context

Repo: `<absolute path>` (branch `<branch>`).
`<Two or three lines: what exists now, what is missing, which module the phase touches.>`

Read first: `<absolute path to plan>` — section "<phase heading>". The test and the code are there;
follow them exactly.

## Deliverables

- `<file 1>`
- `<file 2>`

## Forbidden

- No git commands (no add, commit, checkout, stash).
- Do not edit `<files owned by another phase>`.
- Do not run the full suite. Only:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend uv run --project backend pytest <test file> -q -p no:cacheprovider`

## Exact code (do not improvise)

```python
<paste the class, signature or dataclass verbatim>
```

## Method

TDD: write the test, run it, confirm the failure mode matches what was promised (`ModuleNotFoundError`,
`AttributeError`, an assertion), then implement the minimum, then run again.

## Spec checkpoint (only when the plan carries a behaviour spec)

Flip to `implemented` only the behaviours this phase lands, with their linked tests. The spec's
top-level `version` and `status` are not yours to change — approval lives with the parent.

## Verify

1. `<command>` → `<expected output>`
2. `<grep>` → `<expected result>`
3. `uv run --project backend ruff check <files>` → `All checks passed!`

## Report

Files created/modified; the tail of each command with the exact counts (`37 passed`, `0 failed`) — a
bare "green" is not a measurement; every deviation from the plan with the reason. If
the suite is expected to be red at this point, send a table of test → exception type →
expected/unexpected. A contradiction between plan and code — a wrong boundary number, a missing
symbol — is reported, never reconciled silently by bending the code to the plan.
