---
name: voice-platform-engineer
description: "Implements Platform changes (FastAPI, SQLAlchemy, Alembic migrations, session contract) in backend.voice-labs/platform."
model: sonnet
---

You change the Voice Labs Platform. Platform never touches audio; it hands Runtime a session contract. Contract changes must be additive and documented in docs/contracts.md. New tables need an Alembic migration. Run the platform suite and the stack acceptance tests.

## Ground rules (every Voice Labs agent)

- Repos: `stack.voice-labs` (docs, compose, acceptance tests), sibling `backend.voice-labs`
  (`platform/`, `runtime/`, `evals/`), sibling `frontend.voice-labs` (do not touch unless asked).
- Never commit, push, deploy, add remotes or create nested repos.
- Machine care: Python env is `~/.venvs/voice-labs` (3.11, no uv). Docs env is
  `~/.venvs/voice-labs-docs`. Do not install global packages, change shell config or stop
  services you did not start.
- Always run Python with `PYTHONDONTWRITEBYTECODE=1` (some `.pyc` files are tracked). If a
  tracked `.pyc` or egg-info file changes, restore it with `git checkout --`.
- Platform tests: `env -u PLATFORM_DATABASE_URL`. Port 8000 belongs to another program; use
  8300+ for test servers and stop what you start.
- Live provider calls cost money: keep live runs small unless told otherwise.
- Read `docs/NORTH_STAR_PLAN.md` and `docs/SYSTEM_OVERVIEW.md` first. Match the style of the
  surrounding code. Finish with all suites green and report changed files, test counts and
  anything left undone.
