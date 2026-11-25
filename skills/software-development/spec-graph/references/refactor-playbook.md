# Refactor playbook

What running a `kind: refactor` plan actually costs beyond the loop (`spec_lint.py` → `spec_checks.py --render` → preview → flip a status). Each section is a failure that has already happened once; `workflows.md` has the procedure and `format.md` the schema.

## Checks are shell commands, and YAML eats them

A check passes when its exit code equals `expect_exit` (default 0), so a grep that passes by finding nothing needs `expect_exit: 1`. Quote patterns as fixed strings (`grep -qF`): inside a YAML scalar, regex metacharacters plus shell quoting is a triple negotiation.

When the `run:` scalar must stay double-quoted YAML because it contains single quotes, write regex escapes doubled — `rbac\\.authorization` in the file renders as `rbac\.authorization` — and inner shell quotes as `\"`. Echo the scalar through a shell once before trusting a fresh check to run as written; a check that fails to parse looks exactly like a check that failed on the property.

## Upgrading placeholder checks at completion

A step that is still `todo` often carries a cheap placeholder check (`test -d infra/k8s`, `test -f money.py`) — correct, because a pending-work check must fail today. When the step lands, replace it with a regression-grade check before flipping `status: done`: minimum file or object counts, line caps on the slimmed-down entrypoint, a byte-diff of the entrypoint's observable output against a golden captured before the move, and grep negatives proving the moved content no longer lives in the old place.

A directory-existence check passes again the moment someone deletes the refactor; a real one fails the graph when the refactor is undone. A step that *removes* content needs the mirror operation: re-anchor every count check at the new exact number before flipping to `done`, or the stale count fails after a legitimate removal and somebody loosens it into decoration. When the exact number matters, enforce it in a repo invariant test and keep the grep check broad.

## Consolidating checks when a boundary gains a suite

A step's arrival often hands the plan a stronger check that subsumes several old ones: the rule migrates into a repo test file that reads imports by AST, and the per-step checks become dead weight — a `test -f` milestone passes on an empty file, and a textual grep cannot see `from app import adapters` because the token `app.adapters` never appears in that shape.

When that happens: delete the subsumed checks, repoint every step that cited them at the surviving one, retitle it for the whole boundary it now guards, and restate the affected `INV-N` at the stronger rule. A retired id left in a `check:` line is a lint failure.

Prove the new suite bites by probing each evasion shape (aliased import, direct module import, allowlisted symbol) against a temp tree before trusting it. Patch **every** module-level `Path` constant the probe's failure path touches, not just the directory under test: a helper that formats results with `path.relative_to(APP)` throws a path error before the assertion fires, and the probe then "passes" for the wrong reason.

## Several edits to one plan are one scripted pass

Repointing steps, retiring checks, appending a step, rewriting a header — one scripted pass that asserts each replacement landed, not one tool call per line. A silent no-op replacement is the usual way a plan ends up half-edited while the graph looks fine.

## Amending a plan mid-flight

A user-approved scope change becomes **new steps**, not edits to shipped ones. Each new `todo` step carries exactly one new check; the new property gets its own `INV-N`; and any downstream step that documents the end state (docs, summaries) gains the new steps in `depends_on` so it cannot close first.

Run each new check **before** its step exists. A pending-work check must fail today — one that already passes is decoration, not a marker. State the out-of-scope boundary in the step's `note` ("the adapter for the next storage backend does not enter this plan") so the step cannot grow once implementation starts.

## Delegating a big step

A step too large for one turn splits across two subagents, with the gate kept by the parent.

1. A **planning subagent** (read-only) writes a step plan to `.specs/<capability>/s<N>-plan.md`, measures a real baseline itself (collected counts, durations, coverage), classifies by content — not by file name — and closes with numbered Open Questions. Tell it the plan YAML is untouchable and that every number it reports must come from a command it actually ran.
2. The owner validates, then an **execution subagent** commits one sub-step at a time, each green under the repo's own gate before the commit, staged by explicit path only.
3. **Only the parent flips `status: done`**, after re-running the check itself — a child's self-report is not evidence. Re-derive the child's headline numbers from the repo (collected test count, the gate command's tail, coverage from the report file) before quoting them. When the re-derivation disagrees with the child's figure, write the **measured** value into the step's `note` and say which number moved: the child's figure is a claim, the file on disk is the fact. Never leave the prettier of the two in the plan. Re-run `spec_checks.py --render` after the flip.

A child that "completes" by deleting a failing test is caught by the assert-count diff, not by reading its summary.

## A check run races a worker mid-edit

While an execution subagent is mid-step on the same tree, run only `spec_lint.py` — a pure read of the plan — and defer `spec_checks.py --render` until the child's commits land. Checks execute shell commands against the live working tree, so a mid-edit run can fail spuriously or pass on a half-state.

Scope-verify the child's commit by the commit itself (`git show --stat <sha>`), never by a range from an earlier point: a range sweeps in sibling commits' files and false-flags scope violations.

## Proving a no-behaviour-change step

"No behaviour change" is verified from the diff, not from the green suite. `git diff <base>..HEAD -- <test root>` must contain zero changed `assert` lines, generated contract artifacts (OpenAPI JSON, goldens) must be byte-identical, and every hunk on the hot path must show imports swapped with call arguments preserved — a suite can stay green while a call site silently loses an argument.

Read the hunks, not the summary. The diff of a few-line hot path fits on a screen and settles the question.

## Before moving a file any check cites

Checks cite exact paths, so a move silently breaks a check that a fresh run would only expose later. Grep the plan and the rendered HTML for the paths first.

When the move is of tests, prove nothing was lost by diffing collected test ids normalized by basename (`--collect-only -q | grep :: | sed 's|.*/||' | sort`) before and after. Count path arithmetic too: grep the moving tests for `parents[` and `Path(__file__)` — a move that adds a directory level breaks relative-depth reads before it breaks imports, and a plan that only predicted import breakage underestimates the blast radius.

## Finishing

Fold the outcome into the capability's spec as a new `INV-N` (refs to the new structure) and bump that spec's `version`; then move the plan to `.specs/archive/<capability>/` and set `status: implemented`. Root resolution follows any `.specs` ancestor, so the archived plan still lints and its checks still run.

Do **not** track progress by editing the graph or by flipping colours: status lives in the plan, and the colours come from the last run.
