---
name: commit
description: "Use when committing: Conventional Commits, pt-BR body."
version: 1.3.1
author: LuizzDutra (ported from the OpenCode config skill of the same name)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [git, commit, conventional-commits, pt-br]
    related_skills: [requesting-code-review, github, comment-hygiene]
---

# Commit

Turn the current repository changes into one or more well-formed commits.
Nothing lands until the message and the file list are agreed.

## When to Use

- The user asks to commit, save, or "ship" the current changes.
- A task is finished and the diff is about to be staged.
- **Skip for:** amending someone else's unpushed commit the user is still
  editing, or repos whose history uses a different convention — match that
  style instead (step 5).

## Workflow

1. `git status --short` first — `git diff HEAD` never shows untracked files.
   Then `git diff --cached` (staged) and `git diff` (unstaged).
2. If nothing is staged but work is unstaged, ask before staging. Stage by
   explicit path, never `git add -A` on a repo you have not inspected.
3. Secret check — do it before staging, every time, even for a "quick
   commit". List the exact paths, then stop if any basename is a dotenv file,
   `auth.json`, `service.json`, `*.key`, `*.pem` or `*.local.json(c)`:
   ```bash
   git status --short
   git diff --cached --name-only
   ```
   Do not try to read a suspicious file to decide — Hermes refuses to read
   `.env`-class files at all, and that refusal is the point.
4. **Comment check** on Python diffs. Load `comment-hygiene` (`skill_view`) and
   run `python $SKILL/scripts/comment_scan.py --staged`, with `$SKILL` set to
   the `skill_dir` it returns. The scan reads only the added lines, so legacy
   hits in the tree never appear. A process marker (`P1.5`, `S-10`, `CHK-8`,
   `OQ-2`) or a commit hash in a **new** comment or docstring is not committed
   as-is: rewrite it to state the fact, or delete the sentence. If the marker
   sits in a contract docstring (a FastAPI route handler or a `BaseModel`),
   the generated schema must be regenerated in the same commit. For other
   languages, apply the same rule by eye.
5. `git log --oneline -10` — judge the convention by the bulk of recent
   history, not by one prefixed commit: a single `feat:` among plain messages
   still means the repo is non-conventional. If it does not follow Conventional
   Commits, match its existing style (capitalization, language, prefix or no
   prefix) instead of this spec.
6. Classify the change, propose the message, and commit after approval. If
   the user said "commit" and the change is unambiguous, skip the approval
   step for the message only — never for the secret check. In a fresh clone,
   check `git config user.email` before the first commit — an unset identity
   fails the commit after everything is staged. If unset, set
   `user.name`/`user.email` repo-local (no `--global`), copying both from the
   repo's own history (`git log -1 --format='%an <%ae>'`).

## Message format

```
<type>(<scope>): <description>

<body>
```

- **type**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`, `revert`
- **scope**: optional, affected area (e.g. `config`, `skills`)
- **description**: imperative, lowercase first letter, no trailing period,
  ≤ 72 chars
- **language**: `description` and `body` in **pt-BR** by default. English only
  when the user asks for it ("em inglês", "in English"). `type`, `scope` and
  the `BREAKING CHANGE:` footer stay English either way.
- **body**: optional; explain *why*, not *what* — the diff shows the what.
  Wrap at 72 chars.
- **Structural commits carry the consequences in the body.** For a move, rename or
  split, the diff is a wall of R-lines; list the semantic shifts it hides (path
  indices that changed meaning, dirs newly in lint scope, build context that
  changed, duplicate config entries that collapsed) — that is the why the diff
  cannot show.

Example:

```
fix(skills): impede leitura de .env pela ferramenta de terminal

O guard embutido cobria apenas as ferramentas de arquivo, deixando `cat .env`
passar. O hook bloqueia por basename em qualquer ferramenta.
```

## Rules

- One logical change per commit; offer to split unrelated changes.
- Never amend, rebase, or force-push commits that are already pushed without
  explicit confirmation. Amending your own unpushed commit is the move when
  the user asks to redo it ("refaça o commit") — keep the message in a temp
  file and pass `-F`, so pt-BR text survives shell quoting. `git push --force` is hard-denied in this profile's
  `approvals.deny` — do not attempt it; report it instead.
- Run the repository's own checks before committing when they are cheap
  (tests, lint, build) — the FULL gate command, never the subset you believe you touched:
  lint scope covers paths outside the edited files (scripts/, generated docs), and a violation
  there, e.g. a long `help=` string, leaves HEAD red for the next session. For anything larger,
  load `requesting-code-review` instead of improvising a verification pass.
- New comments and docstrings follow `comment-hygiene`: no plan, step, check or
  commit reference — state the fact or delete the sentence. The history of how
  the code got here belongs to the message and the ADR, not to the code.
- Do not commit generated artifacts, editor noise, or files the user did not
  mention. When in doubt about a hunk, ask.
