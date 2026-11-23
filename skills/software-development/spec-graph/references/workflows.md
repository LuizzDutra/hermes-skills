# Workflows

Exact behaviour for each mode. The gates are the point: a spec that nobody
approved is a draft, not an instruction.

## propose

**Before writing anything**, search the repo and then say what you found:

```
ASSUMPTIONS
1. Python service, pytest, no framework — inferred from pyproject.toml and tests/
2. Orders are in-memory aggregates; persistence is out of scope for this spec
3. Money stays integer cents; no currency conversion
→ Correct these now, or I will proceed with them.
```

Then write the spec, lint it, render it, show `::preview{file="..."}`, and stop
with:

```
order-lifecycle · machine tier · 9 behaviours · 14 scenarios
Rendered above: states, transitions, and who owns each one.

Risk: T-5 (shipped → delivered) has no behaviour — either it needs one or the
state is decorative.

OPEN QUESTIONS
1. Can a refund be partial? The scenarios currently assume full refund only.
2. Is cancellation allowed after payment but before shipping? I assumed yes.
3. Who can cancel — customer, admin, both?
```

**Do not** write code, tests, migrations, or "just the interface" in this turn.
If the user says "go ahead and implement" in the same message as their request,
that is approval of *the idea*, not of a spec they have not seen. Ask for one
review pass: "I will draft it first — two minutes — then you approve."

## ingest

The user pastes a spec, a ticket, a `.feature` file, or a half-written YAML.

1. Extract every behaviour you can. Keep their words where they are precise.
2. For anything the source leaves implicit, **choose the conservative reading and
   label it**. Never silently widen scope.
3. Emit the normalised file plus:

```
ASSUMPTIONS I HAD TO MAKE
1. "fast" = p95 under 300ms — the ticket gives no number
2. The retry limit is 3 (existing RetryPolicy default)
3. Refunds are full only, because the flow has no amount field

OPEN QUESTIONS
1. Should the link expire after 15 minutes or 24 hours?
2. Does "notify the user" mean email, in-app, or both?
```

4. Render, preview, stop. The gate is explicit approval, not silence.

If the source contradicts itself, do not pick a side: put both readings in the
message and ask.

## bootstrap (repo has tests, no spec)

Adopting the skill where the tests already exist.

1. **Scope to one capability**, not the repo. Write `spec.yaml` for behaviour
   that already ships (ingest), and mark `implemented` only where a test exists.
2. **Collect and link:** `spec_link.py spec.yaml` lists suggestions and
   unlinked tests. Suggestions are weighted token overlap, not authority — read
   each one, then `--apply --yes`. Use `--top 2` when a behaviour legitimately
   has two tests.
3. **Expect gaps, and resolve them.** A test with no behaviour is either legacy
   or behaviour nobody wrote down; a behaviour with no test is a claim. Say
   which is which before calling the bootstrap done.
4. **Add `spec_link.py --check` to pre-commit or CI.** A rename then fails
   loudly instead of silently dropping coverage.
5. Commit the spec with the code. From here the mapping is maintained, not
   rediscovered.

Name-token matching (`link_style: name`) can pair a test with a behaviour that
never described it: the token proves the author typed the id, not that the
behaviour exists. Keep explicit links as the default and check every
name-matched pair once.

## amend

Shipped behaviour changes get a delta spec, not an edit of the shipped one:

```yaml
spec: order-lifecycle
delta_of: order-lifecycle
version: 2
status: proposed
current: "Cancelling is allowed in draft and submitted."
new: "Cancelling is also allowed in paid, before shipping."
must_not_change: [BEH-004, BEH-005]
```

Write only the affected behaviours (new ids for new behaviour, same ids for
changed behaviour), render with `--diff specs/order-lifecycle/spec.yaml`, and
show the ringed nodes. When it ships: bump the main spec, merge the behaviours,
delete the delta.

## implement

Order by dependency, then one behaviour per cycle:

```
BEH-004 pay ──▶ BEH-005 ship ──▶ BEH-007 refund
```

Per behaviour:

1. `spec_tests.py --only BEH-004` → skeleton.
2. Turn the skeleton into a real test, named the way the repo names tests.
3. Link it: `spec_link.py --apply` proposes candidates; confirm the diff, then write.
4. Run it. Watch it fail for the intended reason (`pytest ... -q`).
5. Minimal implementation. Run the whole suite.
6. Mark `status: implemented` in the YAML, re-render, next behaviour.

Refactor between behaviours only while green. If a scenario turns out to be
wrong mid-implementation, stop and amend the spec first — the code follows the
approved spec, not the other way round.

## verify

```
python $SKILL/scripts/spec_verify.py specs/order-lifecycle/spec.yaml --render
```

Report the table, not adjectives:

```
✓ BEH-001 pass   2 tests
✗ BEH-004 FAIL   2 tests   test_paying_twice_is_rejected
? BEH-009 no match         declared test id does not exist
```

Then:

- **fail** → the behaviour is `divergent`. Open the failing test, decide whether
  code or spec is wrong, and say which. Do not soften it to "mostly working".
- **missing** → the declared test is not in the report. Check the path, the test
  name, and the JUnit reporter before editing anything.
- **unmapped tests** → tests that belong to no behaviour. Either they are legacy
  or a behaviour is missing. List them; do not silently ignore. `spec_link.py`
  scores them against behaviour titles and proposes links; `--check` catches a
  declared id that was renamed or deleted.

## refactor

A refactor gets a plan, not scenarios. Start from the **target structure**, not
from the diff you intend to make.

1. **Write the goal as a command you could run.** "billing is a leaf module" is
   a goal because `lint-imports` can answer it. "Clean up billing" is not.
2. **List the invariants**: public API, error types, the suite that must stay
   green. Cite them; if a regression would be caught by tests, name those tests.
3. **Write the checks first.** If you cannot express the goal as a check, the
   goal is not finished being thought through.
4. **Break the work into steps** that end in a checkable state, and order them
   with `depends_on`. Each step names the files it touches.
5. **Lint, render, show the plan, stop.** Then move one step at a time:
   `status: doing` → change code → `spec_checks.py` → green → `status: done`.

Rules:

- Never mark a step `done` because the code "looks right"; the check decides.
- A step that needs a new check is a design smell: either the step is two
  steps, or the goal was too vague.
- Do not add behaviours to a refactor plan. If the work changes observable
  behaviour, that part is a behaviour spec (a delta), not a step.
- When every step is `done` and every check passes, fold the outcome into the
  capability's spec if the structure is worth recording, then archive the plan.

## Review etiquette in chat

- One `::preview{file="..."}` line per reply, no screenshots of the same graph.
- Two or three sentences: what changed, what needs a decision.
- Number the open questions; the user answers "1 yes, 2 email only" in one line.
- Never paste the whole YAML into chat. Point at ids.
- If the user edits `spec.yaml` by hand, re-run lint and render before replying —
  their edit is the new source of truth, including when it breaks a rule.

## Autonomous mode (no human available)

An agent must not approve its own spec.

- If the task arrives with acceptance criteria that are already testable,
  restate them as scenarios **without changing scope**, mark `status: approved`,
  and continue to implementation.
- If the criteria are missing or untestable, write the spec as `proposed`, render
  it, and stop with the open questions as a blocker. Say plainly that the
  implementation is blocked on a decision, not on effort.

## Failure modes to avoid

| behaviour | why it is wrong |
|---|---|
| Writing the spec after the code "to document it" | That is documentation; it cannot gate anything |
| Approving your own draft because the user is away | The approval is the product decision |
| Adding a behaviour mid-implementation without telling anyone | Scope grew silently; graph and tests drift |
| Marking `implemented` because the code looks right | Only a passing, mapped test earns the status |
| Deleting a dead ref instead of re-resolving it | The citation was the point; find where the symbol moved |
| Rendering a graph from your memory of the spec | Regenerate from the file, always |
