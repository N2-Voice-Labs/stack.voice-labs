# Development

How to set up a working copy, run each service, run the tests, and keep the repositories
clean. For a guided first run see [Quickstart: API tour](quickstart-api.md) and
[Quickstart: talk to an agent](quickstart-voice.md); for symptoms and fixes see
[Troubleshooting](troubleshooting.md).

## Repository layout

The workspace is a set of sibling directories. Paths in this documentation assume this layout.

| Directory | Owns |
| --- | --- |
| `stack.voice-labs` | `compose.yml` (PostgreSQL, Valkey, LiveKit), `.env.example`, this documentation site, cross-service acceptance tests in `tests/` |
| `backend.voice-labs/platform` | Platform API (FastAPI): agents, voices, deployments, sessions, conversations, analytics; Alembic migrations |
| `backend.voice-labs/runtime` | Runtime API and Pipecat voice pipeline: joins LiveKit rooms, runs STT, LLM and TTS |
| `backend.voice-labs/evals` | Evaluation datasets and metrics (deterministic checks only so far) |
| `frontend.voice-labs` | Next.js web app |

The six original repositories (`platform`, `runtime`, `web`, `evals`, `docs`, `infra`
`.voice-labs`) are recoverable source copies and are not edited. Compose starts
infrastructure only; Platform, Runtime and the web app run from their own directories.

## Environments

### Shared configuration

All three apps read the same settings from `stack.voice-labs/.env`:

```bash
cd stack.voice-labs
cp .env.example .env
```

`.env` is gitignored. Export it into each app's shell before starting it (no per-app copies):

```bash
# in backend.voice-labs/platform or backend.voice-labs/runtime
set -a; source ../../stack.voice-labs/.env; set +a

# in frontend.voice-labs
set -a; source ../stack.voice-labs/.env; set +a
```

Keep `PLATFORM_RUNTIME_TOKEN` and `RUNTIME_PLATFORM_TOKEN` identical. If you change
`POSTGRES_PORT` or `LIVEKIT_PORT`, also edit `PLATFORM_DATABASE_URL` or `LIVEKIT_URL`;
Compose does not rewrite application URLs. Without `PLATFORM_DATABASE_URL`, Platform falls
back to a local SQLite file (`voice_labs.db`, gitignored), which is easy to mistake for your
PostgreSQL data.

Variables that change behavior:

| Variable | Effect |
| --- | --- |
| `RUNTIME_API_URL` | Where Platform hands sessions to Runtime. Unset it for API-only work; session creation then returns `runtime_status: "manual_start_required"`. |
| `PLATFORM_WEB_ORIGIN` | Browser origins allowed by Platform CORS, comma-separated (default `http://localhost:3000`), for example `http://localhost:3000,https://your-frontend.example`. Restart Platform after changing it. |
| `PLATFORM_ALLOW_PRIVATE_NETWORK` | `1` enables Chrome private-network preflight answers, for a hosted page calling a local Platform. |
| `PLATFORM_AUTO_CREATE_SCHEMA` | `1` creates tables at startup without Alembic. Used by tests; use migrations for real data. |
| `NEXT_PUBLIC_PLATFORM_URL` | Platform URL used by the web app (default `http://localhost:8000`). |

### Python environments

Python 3.11 or newer is required. The stack README uses [uv](https://docs.astral.sh/uv/):
`uv sync --extra test` (Platform) and `uv sync --extra voice --extra test` (Runtime), then
`uv run <command>`.

Without uv, a plain virtual environment kept **outside** the repositories works. From
`stack.voice-labs`:

```bash
python3.11 -m venv ~/.venvs/voice-labs
~/.venvs/voice-labs/bin/pip install \
  -e "../backend.voice-labs/platform[test]" \
  -e "../backend.voice-labs/runtime[voice,test]"
source ~/.venvs/voice-labs/bin/activate
```

A conda environment with Python 3.11 works the same way. Drop the `voice` extra if you do not
need real speech; it pulls in Pipecat and the provider SDKs. In the rest of this page,
replace `uv run python` with `python` if you activated a virtual environment.

### Node

`frontend.voice-labs` uses npm: `npm ci` installs from the lockfile.

## Running the services

Start infrastructure first, from `stack.voice-labs`:

```bash
docker compose up -d
docker compose ps
```

Then, each in its own terminal with `.env` exported as above:

| Service | Directory | Command | URL |
| --- | --- | --- | --- |
| Platform | `backend.voice-labs/platform` | `python -m alembic upgrade head`, then `python -m uvicorn src.platform.main:app --reload --port 8000` | <http://localhost:8000> (Swagger UI at `/docs`) |
| Runtime | `backend.voice-labs/runtime` | `python -m uvicorn src.runtime.api:app --reload --port 8001` | <http://localhost:8001> |
| Web app | `frontend.voice-labs` | `npm ci && npm run dev` | <http://localhost:3000> |

Platform does not process audio and Runtime keeps no durable state: Platform owns agents,
conversations and transcripts, Runtime owns the live session.

## Tests

Set `PYTHONDONTWRITEBYTECODE=1` for every Python test run (see
[Conventions](#conventions)). Run each suite from its own directory:

```bash
export PYTHONDONTWRITEBYTECODE=1
cd backend.voice-labs/platform && python -m pytest -q   # 99 passed, 1 skipped
cd backend.voice-labs/runtime  && python -m pytest -q   # 44 passed, 6 skipped
cd backend.voice-labs/evals    && python -m pytest -q
```

The counts are from the latest recorded run and will change as tests are added. The skips
are intentional:

- Platform skips the PostgreSQL concurrency test unless `PLATFORM_TEST_POSTGRES_URL` is set.
- Runtime skips 6 LiveKit integration tests unless a LiveKit server is configured.

Platform unit and API tests use isolated in-memory SQLite and do not need Docker.

### Runtime LiveKit tests

```bash
docker compose up -d livekit      # from stack.voice-labs
export LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret
cd ../backend.voice-labs/runtime && python -m pytest -q
```

### PostgreSQL-backed Platform test

Run it only against a disposable database, never your dev database. A throwaway
PostgreSQL container that keeps nothing on disk:

```bash
docker run -d --rm --name vl-test-pg --tmpfs /var/lib/postgresql/data \
  -e POSTGRES_DB=vl -e POSTGRES_USER=vl -e POSTGRES_PASSWORD=vl \
  -p 55432:5432 postgres:16-alpine

cd backend.voice-labs/platform
export PLATFORM_TEST_POSTGRES_URL=postgresql+psycopg://vl:vl@localhost:55432/vl
export PLATFORM_DATABASE_URL="$PLATFORM_TEST_POSTGRES_URL"
python -m alembic upgrade head
python -m pytest -q tests/test_postgres_concurrency.py

docker stop vl-test-pg
```

### Frontend

From `frontend.voice-labs`:

```bash
npm test            # vitest unit tests
npm run typecheck   # tsc --noEmit
npm run build       # production build
npm run test:e2e    # Playwright; needs LiveKit (docker compose up -d livekit)
```

The Playwright suite starts its own isolated Platform and Runtime with deterministic
speech stand-ins. It needs a Chrome binary; set `CHROME_BIN=/path/to/chrome` if it is not
found. See [Progress](PROGRESS.md) for how the journeys are run.

## Migrations

Alembic lives in `backend.voice-labs/platform/migrations`; it reads `PLATFORM_DATABASE_URL`.
The current chain ends at `0004_voice_studio`. From `backend.voice-labs/platform`:

```bash
python -m alembic upgrade head                    # apply
python -m alembic current                         # show the applied revision
python -m alembic revision -m "describe change"   # new revision file
```

A schema change should survive a round trip. Against a disposable database, check that it
upgrades, downgrades and upgrades again:

```bash
python -m alembic upgrade head
python -m alembic downgrade 0003_conversation_indexes
python -m alembic upgrade head
```

Then run the Platform suite against that migrated schema as well as against SQLite.

## Acceptance tests

The cross-service tests live in `stack.voice-labs/tests` and exercise Platform and Runtime
together. They need both packages importable, so run them in an environment with both
installed (the virtual environment above, or `uv` with both projects).

```bash
cd stack.voice-labs
export PYTHONDONTWRITEBYTECODE=1
python -m pytest -q tests
```

Without LiveKit the LiveKit cases skip. To include them:

```bash
docker compose up -d livekit
export LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret
python -m pytest -q tests
```

These tests stub speech recognition, the language model and synthesis. The opt-in
real-provider test (`tests/test_real_voice_acceptance.py`) sends real audio to Deepgram,
OpenAI and Cartesia, **can incur charges**, and has not been run yet. It needs
`VOICE_ACCEPTANCE_REAL_PROVIDERS=1`, a WAV file and its transcript; the README's
"Real-provider acceptance" section has the full procedure. By default acceptance tests use
an in-memory database; if you set `PLATFORM_ACCEPTANCE_DATABASE_URL`, point it at a
disposable database because records are retained. Never point any test at your real dev
database.

## Documentation site

The site is built with [Zensical](https://zensical.org) from `mkdocs.yml` and `docs/`. From
`stack.voice-labs`:

```bash
python3.11 -m venv ~/.venvs/voice-labs-docs
source ~/.venvs/voice-labs-docs/bin/activate
pip install -r requirements.txt
zensical build --strict
```

`zensical build --strict` is the documented check and writes the (gitignored) `site/`
directory; run it before handing off doc changes, because strict mode fails on broken links
and missing pages. For a live preview run `zensical serve -a 127.0.0.1:8080` and open
http://127.0.0.1:8080. The default port is 8000, which collides with Platform. New pages must be added
to `nav` in `mkdocs.yml` to appear in the menu.

## Conventions

- **No secrets in Git.** Provider keys live only in the gitignored `stack.voice-labs/.env`.
  Never commit, paste or log them. Platform payloads reference secrets
  (`secret_reference`) and reject secret-looking configuration keys. Rotate any key you
  exposed.
- **No commits from tooling by default.** Do not add remotes or submodules, push or deploy
  without explicit agreement. Commit only the files you changed on purpose.
- **Set `PYTHONDONTWRITEBYTECODE=1`.** `backend.voice-labs` tracks some `__pycache__/*.pyc`
  files, and test runs otherwise modify them, polluting `git status`. If it already
  happened, restore them with `git checkout -- <path>`.
- **Editable installs touch tracked metadata.** `pip install -e` rewrites
  `platform/src/platform_voice_labs.egg-info/SOURCES.txt`. Restore it from
  `backend.voice-labs` with:

  ```bash
  git checkout -- platform/src/platform_voice_labs.egg-info/
  ```

- **Keep virtual environments outside the repositories** (for example `~/.venvs/...`) so
  they never show up as changes.
- **Report only what you ran.** Stubbed or synthetic-media tests do not establish real
  provider behavior; say so, as [Progress](PROGRESS.md) does.
- **Keep the docs accurate.** Update Compose, `.env.example`, setup instructions and these
  pages together whenever commands, ports or variables change.
