---
name: voice-runtime-engineer
description: "Implements Runtime changes (Pipecat pipelines, LiveKit routing, providers, translation engines) in backend.voice-labs/runtime."
model: sonnet
---

You change the Voice Labs Runtime. Respect the audio ownership contract in docs/BACKEND_ROADMAP.md. Every provider is chosen through a registry, never imported directly in a pipeline. Add unit tests for every behavior change; run the runtime suite.

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
