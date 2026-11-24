# hermes-skills

Agent skills I use with [Hermes Agent](https://hermes-agent.nousresearch.com/docs).

| Skill | What it does |
|---|---|
| [`spec-graph`](skills/software-development/spec-graph) | Behaviour specs as validated YAML plus an interactive graph; refactor plans with structural checks. |
| [`comment-hygiene`](skills/comment-hygiene) | Comments and docstrings that describe the code in front of the reader, not the plan that produced it. |
| [`commit`](skills/software-development/commit) | One well-formed commit per logical change: Conventional Commits, pt-BR body, secret check first. |
| [`subagent-driven-development`](skills/software-development/subagent-driven-development) | Execute an approved plan in rounds of delegated subagents, with the parent keeping the gate. |
| [`explainer-video`](skills/creative/explainer-video) | Script to narrated motion graphics with Pillow and ffmpeg. |

## Install

Hermes loads skills from `~/.hermes/skills` (`%LOCALAPPDATA%\hermes\skills` on
Windows). Copy the category folders in:

```bash
cp -r skills/* ~/.hermes/skills/
```

Each skill is self-contained: `SKILL.md` plus `references/`, `templates/` and,
where relevant, `scripts/`. The skills here share no code.

## spec-graph

A behaviour spec is a YAML file; the graph is a projection of it, never a drawing
made from chat prose.

- **behaviour** specs: EARS rules, Given/When/Then scenarios, file references that
  must exist, tests linked by node id. The repo keeps its own test naming unless
  you opt into `link_style: name`.
- **refactor** plans: a checkable goal, invariants, shell checks and ordered steps
  with status, so progress and evidence live in the same picture.
- The scripts are standard library only — they ship their own YAML subset parser
  and run on a bare Python 3.9+.
- Specs live in `.specs/<capability>/spec.yaml` — commit that file, ignore the
  generated `graph.html`, `results.json` and `checks.json`. If the path is
  gitignored or excluded in `.git/info/exclude`, it stays local: the skill says so
  and never force-adds it.
- `graph.html` is generated: self-contained, no CDN, inherits the host theme.

The gate is `python scripts/spec_lint.py <spec>`; `spec_render.py` builds the
graph, `spec_verify.py` maps JUnit results back onto behaviours, and
`spec_checks.py` runs a refactor plan's structural checks.

## comment-hygiene

A comment describes the code in front of the reader — not the conversation that
produced it, the plan that ordered it, or the version timeline. The skill lists
what never belongs in a comment or docstring (addressing the requester, plan and
step ids, changelog narration) and what does (the why, the invariant, the risk
avoided, legacy tolerance), plus the rule that a contract docstring is published
text. `scripts/comment_scan.py --staged` reads only the added lines, so legacy
hits in the tree never surface.

## commit

Turns the current changes into one or more well-formed commits: `git status
--short` first (a plain diff hides untracked files), a secret check by basename
before staging, the comment scan on new Python lines, then the convention the
history actually uses. Message is Conventional Commits, with description and body
in pt-BR and the body explaining why.

## subagent-driven-development

Executes a written plan in rounds of delegated subagents. A round is the set of
phases whose file sets are disjoint; the parent keeps every gate — pre-flight
baseline, verification between rounds, the commits and the end-to-end run.
Children get the plan's path plus a phase heading instead of a retyped copy, their
self-reported numbers are re-measured, and a child that "completes" by deleting a
failing test is caught by the assert-count diff. `templates/phase-brief.md` is the
per-phase brief.

## explainer-video

Script to narrated motion graphics: Pillow for frames, ffmpeg for assembly, and
optional forced alignment for captions. The references cover the renderer, audio
sync and ffmpeg assembly.

## License

MIT — see [LICENSE](LICENSE).
