# hermes-skills

Agent skills I use with [Hermes Agent](https://hermes-agent.nousresearch.com/docs).

| Skill | What it does |
|---|---|
| [`spec-graph`](skills/software-development/spec-graph) | Behaviour specs as validated YAML plus an interactive graph; refactor plans with structural checks. |
| [`explainer-video`](skills/creative/explainer-video) | Script to narrated motion graphics with Pillow and ffmpeg. |

## Install

Hermes loads skills from `~/.hermes/skills` (`%LOCALAPPDATA%\hermes\skills` on
Windows). Copy the category folders in:

```bash
cp -r skills/* ~/.hermes/skills/
```

Each skill is self-contained: `SKILL.md` plus `references/`, `templates/` and,
where relevant, `scripts/`. The two skills here share no code.

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

## explainer-video

Script to narrated motion graphics: Pillow for frames, ffmpeg for assembly, and
optional forced alignment for captions. The references cover the renderer, audio
sync and ffmpeg assembly.

## License

MIT — see [LICENSE](LICENSE).
