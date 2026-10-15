# Troubleshooting

Find your symptom, check the cause, apply the fix. Platform errors are returned as
`{"detail": "<code>"}`; the code is the thing to look up. For setup steps see
[Development](development.md); for the tours see [API tour](quickstart-api.md) and
[Talk to an agent](quickstart-voice.md).

| Symptom | Likely cause | Jump to |
| --- | --- | --- |
| `503 runtime_unavailable` on session creation | Runtime not running, or token mismatch | [link](#503-runtime_unavailable) |
| `runtime_status: "manual_start_required"` | `RUNTIME_API_URL` unset | [link](#runtime_status-manual_start_required) |
| "Can't reach the platform" / "Platform API is unavailable" | Platform down, wrong URL, or hosted frontend | [link](#cant-reach-the-platform) |
| "Failed to fetch" / "Couldn't create a session" but Platform is healthy | Origin not in `PLATFORM_WEB_ORIGIN` | [link](#failed-to-fetch-with-a-healthy-platform-cors) |
| `400 Disallowed CORS private-network` | Hosted page calling localhost | [link](#400-disallowed-cors-private-network) |
| `409 selected_voice_unavailable` | Agent's voice profile is not `ready` | [link](#409-selected_voice_unavailable) |
| `422 voice_consent_required`, `invalid_sample_reference` | Clone request incomplete | [link](#422-voice_consent_required-and-invalid_sample_reference) |
| Session starts but the agent never speaks | Fake voice ID, bad key, no credit | [link](#session-starts-but-the-agent-is-silent) |
| `409 agent_not_enabled` | Agent disabled or ID wrong | [link](#409-agent_not_enabled) |
| `401 invalid_runtime_token`, `503 runtime_auth_not_configured` | Token missing or different | [link](#401-invalid_runtime_token-and-503-runtime_auth_not_configured) |
| `address already in use` | Port 8000, 8001 or 3000 taken | [link](#port-already-in-use) |
| Docker errors, services will not start | Docker daemon not running | [link](#docker-daemon-is-not-running) |
| `git status` shows modified `.pyc` or `egg-info` | Test runs and editable installs | [link](#modified-pyc-or-egg-info-files-after-a-run) |
| Hosted https page cannot reach localhost in Safari | Browser blocks it | [link](#safari-blocks-https-to-localhost) |

## 503 runtime_unavailable

**Symptom.** `POST /voice/sessions` returns `503` with `runtime_unavailable`. The session and
conversation are recorded as `failed`.

**Cause.** `RUNTIME_API_URL` is set (it is in `.env.example`), so Platform tried to hand the
session to Runtime, but the request failed. Either Runtime is not running on that URL, it
rejected the request, or it answered with something Platform did not accept. A common
rejection is a token mismatch: Runtime returns `401` when `RUNTIME_PLATFORM_TOKEN` differs
from Platform's `PLATFORM_RUNTIME_TOKEN`, and Platform reports that as `runtime_unavailable`.

**Fix.**

- Working on the API only? Run `unset RUNTIME_API_URL` in the Platform terminal and restart
  Platform. See [the next entry](#runtime_status-manual_start_required).
- Want Runtime? Start it (`python -m uvicorn src.runtime.api:app --reload --port 8001` from
  `backend.voice-labs/runtime`) and check that it responds:

  ```bash
  curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8001/docs   # 200
  ```

- Confirm both services were started with the same `.env` and that
  `PLATFORM_RUNTIME_TOKEN` equals `RUNTIME_PLATFORM_TOKEN`. Restart both after any change;
  they read the environment only at startup.
- Look at the Runtime terminal for the real error (for example an unsupported provider).

## runtime_status "manual_start_required"

**Symptom.** Session creation succeeds, but the response has
`"runtime_status": "manual_start_required"` and no agent ever joins.

**Cause.** This is expected when LiveKit is configured and `RUNTIME_API_URL` is not set.
Platform created the session and a browser room token but did not ask any Runtime to start.
It is the normal state in the [API tour](quickstart-api.md).

**Fix.** Nothing, for API-only work. For real conversations, run Runtime and start Platform
with `RUNTIME_API_URL=http://localhost:8001` (the `.env` default, so do not `unset` it).

## Can't reach the platform

**Symptom.** Pages in the web app show "Can't reach the platform" or "Platform API is
unavailable".

**Cause and fix.** Check in this order:

1. **Platform is not running.** `curl -s http://localhost:8000/health` should print
   `{"status":"ok"}`. If not, start Platform (and run `python -m alembic upgrade head` once).
2. **Wrong `NEXT_PUBLIC_PLATFORM_URL`.** The web app uses it (default
   `http://localhost:8000`) and Next.js reads it when it starts. Export `.env` in the web
   app's terminal (`set -a; source ../stack.voice-labs/.env; set +a`) and restart
   `npm run dev` after changing it.
3. **You are using a hosted frontend.** Pages such as Agents are server components rendered
   on the host's servers, where `localhost` is not your machine. A hosted build with a local
   backend does not work fully. Run the web app locally, or see
   [Using a hosted frontend](quickstart-voice.md#using-a-hosted-frontend), including the
   warning that a public Platform has no authentication.

## "Failed to fetch" with a healthy Platform (CORS)

**Symptom.** `/health` works from the terminal, but the web app shows "Failed to fetch" or
"Couldn't create a session". The browser console and Network tab show a failed preflight
`OPTIONS` request that returned `400` with `Disallowed CORS origin`.

**Cause.** Platform only answers browsers from origins listed in `PLATFORM_WEB_ORIGIN`
(default `http://localhost:3000`). Opening the app as `http://127.0.0.1:3000`, on another
port, or from a hosted URL is a different origin.

**Fix.** Add the exact origin (scheme, host and port, no trailing slash) to the
comma-separated list and restart Platform:

```bash
PLATFORM_WEB_ORIGIN=http://localhost:3000,http://127.0.0.1:3000
```

Or open the app at the origin that is already allowed.

## 400 Disallowed CORS private-network

**Symptom.** A hosted page (https) calling Platform on your machine fails; the preflight
`OPTIONS` returns `400` with `Disallowed CORS private-network`.

**Cause.** Chrome asks permission before a public site may reach a private address
(`localhost`), and Platform only answers that request when you opt in.

**Fix.** In the Platform environment set `PLATFORM_ALLOW_PRIVATE_NETWORK=1`, set
`PLATFORM_WEB_ORIGIN` to include the hosted page's origin, and restart Platform. This only
fixes the browser-to-Platform call. Server-rendered pages on the host still cannot reach your
`localhost`; see [Can't reach the platform](#cant-reach-the-platform).

## 409 selected_voice_unavailable

**Symptom.** `POST /voice/sessions` returns `409 selected_voice_unavailable`.

**Cause.** The agent has a `voice_profile_id`, and that voice is not `status: "ready"` or has
no `provider_voice_id`. Cloned and designed voices start as `pending` and no provisioning
exists yet to make them `ready`; a `disabled` voice also fails.

**Fix.** Inspect the voice and choose a usable one:

```bash
curl -s http://localhost:8000/voices/<VOICE_ID> | jq '{status, provider_voice_id, failure_reason}'
```

Either attach a library voice (created with `POST /voices`, which is `ready` immediately) to
the agent with `PATCH /agents/<AGENT_ID>`, or move the voice along its allowed status
transitions (see [Contracts](contracts.md#voices)).

## 422 voice_consent_required and invalid_sample_reference

**Symptom.** `POST /voices/clone` returns one of these.

**Cause.**

- `voice_consent_required`: `consent` is missing, or `consent.confirmed` is not exactly
  `true`.
- `invalid_sample_reference`: `sample_reference` is not a `scheme://...` reference without
  whitespace (for example `s3://bucket/anna.wav`), or is longer than 1024 characters. A
  local path such as `/tmp/anna.wav` is rejected.

**Fix.** Send a complete request:

```json
{
  "name": "Support voice",
  "sample_reference": "s3://voice-samples/anna.wav",
  "consent": {
    "confirmed": true,
    "subject_name": "Anna Petrova",
    "statement": "I consent to cloning my voice for this agent.",
    "method": "self"
  }
}
```

Request-shape failures such as a missing `subject_name` return FastAPI's standard `422` with a
`detail` list instead of a code. Cloning stores the record only; no sample is uploaded or
processed.

## Session starts but the agent is silent

**Symptom.** The session connects (or appears to), you speak, but there is no spoken answer,
or the transcript stays empty.

**Cause.** In rough order of likelihood:

- **A made-up voice ID.** An agent whose **Voice ID** field or voice profile holds a fake
  `provider_voice_id` (such as the `demo-voice-id` from the API tour) fails at text-to-speech.
  An agent with no voice profile uses `CARTESIA_VOICE_ID` from `.env`.
- **Missing, wrong or exhausted keys.** Real speech needs `DEEPGRAM_API_KEY`,
  `OPENAI_API_KEY`, `CARTESIA_API_KEY` and `CARTESIA_VOICE_ID`. Placeholders do not work, and
  trial credit can run out.
- **Unsupported provider.** Runtime supports Deepgram (STT), OpenAI or OpenAI-compatible
  (LLM) and Cartesia (TTS) only; an agent that selects anything else fails at start.
- **Microphone not allowed.** Chrome blocked the mic for `localhost`.

**Fix.** Read the Runtime terminal first; provider errors appear there. Then look at the
event trail:

```bash
curl -s http://localhost:8000/conversations/<CONVERSATION_ID>/runtime-state \
  | jq '{session_status, events: [.events[].event_type]}'
```

`SessionFailed` or `RuntimeFailed` means Runtime gave up; no `RuntimeStarted` means it never
got going. Test with an agent that has no Voice ID and no voice profile, fix `.env`, and
restart Runtime. Remember a complete spoken turn is [not yet recorded as
verified](quickstart-voice.md).

## 409 agent_not_enabled

**Symptom.** `POST /voice/sessions` returns `409 agent_not_enabled`.

**Cause.** The agent's `status` is not `enabled` (`DELETE /agents/{id}` sets it to
`disabled`), or the `agent_id` does not exist. Unknown agents return this same code.

**Fix.** Check the ID and the status, and re-enable if needed:

```bash
curl -s http://localhost:8000/agents/<AGENT_ID> | jq '{id, status}'
curl -s -X PATCH http://localhost:8000/agents/<AGENT_ID> \
  -H 'content-type: application/json' -d '{"status":"enabled"}'
```

Related deployment errors on the same call are `404 deployment_not_found`,
`409 deployment_not_active` and `409 deployment_agent_mismatch`.

## 401 invalid_runtime_token and 503 runtime_auth_not_configured

**Symptom.** `POST /runtime/events` returns `401 invalid_runtime_token` or
`503 runtime_auth_not_configured`. Session creation can also return
`503 runtime_auth_not_configured`.

**Cause.**

- `401`: the `X-Runtime-Token` header is missing or differs from Platform's
  `PLATFORM_RUNTIME_TOKEN`.
- `503`: Platform has no `PLATFORM_RUNTIME_TOKEN` at all (the shell never exported `.env`).
  Session creation returns it when `RUNTIME_API_URL` is set but the token is empty.

**Fix.** Export the shared `.env` in the Platform terminal and restart it. In the terminal
you run `curl` from, load the same file so the header matches:

```bash
set -a; source .env; set +a
curl -s -X POST http://localhost:8000/runtime/events \
  -H "X-Runtime-Token: $PLATFORM_RUNTIME_TOKEN" ...
```

Runtime sends `RUNTIME_PLATFORM_TOKEN`; it must equal `PLATFORM_RUNTIME_TOKEN`.

## Port already in use

**Symptom.** `Address already in use` or `[Errno 48]` when starting Platform (8000), Runtime
(8001) or the web app (3000).

**Cause.** An earlier instance is still running, often in a forgotten terminal.

**Fix.** Find the process that holds the port, and stop it if it is yours:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
kill <PID>
```

Use 8001 or 3000 in place of 8000 for the other services. If you move a service to another
port, update `RUNTIME_API_URL`, `RUNTIME_PLATFORM_URL`, `PLATFORM_API_URL` and
`NEXT_PUBLIC_PLATFORM_URL` to match. Also check that you are not talking to an old Platform
that still has stale data or a different environment.

## Docker daemon is not running

**Symptom.** `docker compose up -d` fails with `Cannot connect to the Docker daemon`, or
Platform cannot connect to PostgreSQL on `localhost:5432`.

**Fix.** Start Docker. On macOS with Docker Desktop, open the app. If you use Colima:

```bash
colima start
docker info | head -3
```

Then `docker compose up -d` and `docker compose ps` from `stack.voice-labs`, and wait for
`postgres` to be `healthy` before running `python -m alembic upgrade head`. If port 5432 is
already used by another PostgreSQL, change `POSTGRES_PORT` in `.env` and the port inside
`PLATFORM_DATABASE_URL` together.

## Modified .pyc or egg-info files after a run

**Symptom.** `git status` in `backend.voice-labs` shows changed `__pycache__/*.pyc` files or
`platform/src/platform_voice_labs.egg-info/SOURCES.txt`.

**Cause.** `backend.voice-labs` tracks some `.pyc` files that test runs rewrite, and
`pip install -e` regenerates the tracked `egg-info`.

**Fix.** Restore them, and prevent the first with `PYTHONDONTWRITEBYTECODE=1`:

```bash
cd backend.voice-labs
git checkout -- platform/src/platform_voice_labs.egg-info/
git checkout -- <path/to/changed.pyc>
export PYTHONDONTWRITEBYTECODE=1
```

Do not use a broad `git checkout .` or `git clean`; you may discard real work. Review
`git status` first.

## Safari blocks https to localhost

**Symptom.** A hosted https page works in Chrome (with
[private-network](#400-disallowed-cors-private-network) enabled) but fails in Safari with a
network or mixed-content error when calling `http://localhost:8000`.

**Cause.** Safari does not let an https page call an `http://localhost` backend.

**Fix.** Use Chrome, or better, run the web app locally and open <http://localhost:3000>,
where every call is plain http to localhost and no cross-origin special cases apply.
