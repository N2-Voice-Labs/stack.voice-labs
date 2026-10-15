# Quickstart: talk to an agent

This page takes you from a fresh checkout to speaking with an agent in your browser:
microphone, LiveKit, Runtime (Deepgram, OpenAI, Cartesia), and back to your speakers. It
uses the local web app. If you only want to explore the API without any provider keys, use
[Quickstart: API tour](quickstart-api.md) first.

> **Verification status.** With real provider keys, a session has been observed to start:
> Runtime joined the LiveKit room and connected to Deepgram and Cartesia. A complete spoken
> turn (you speak, the agent answers aloud) has **not** been recorded as verified, and the
> opt-in real-provider acceptance test has not been run. Automated browser tests use
> deterministic stand-ins for speech recognition, the language model and synthesis, so they
> do not prove provider behavior. Treat the first turn on your machine as the real test, and
> see [Troubleshooting](troubleshooting.md) if something is silent.

## What you need

- Everything from the [API tour](quickstart-api.md#before-you-start), except `jq`.
- Node.js and npm (for the web app) and Google Chrome.
- A microphone.
- Accounts and API keys for three **paid** services (most offer trial credit; real usage is
  billed to you):

| Service | Used for | `.env` variable |
| --- | --- | --- |
| Deepgram | Speech-to-text | `DEEPGRAM_API_KEY` |
| OpenAI | Language model | `OPENAI_API_KEY` |
| Cartesia | Text-to-speech | `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID` |

Runtime supports only these providers today: `deepgram` for STT, `openai` or
`openai-compatible` for the LLM, and `cartesia` for TTS. Agents that select any other
provider fail at session start.

## 1. Add your keys

```bash
cd stack.voice-labs
cp .env.example .env     # skip if you already did this
```

Edit `.env` and fill in the four values:

```bash
DEEPGRAM_API_KEY=...
OPENAI_API_KEY=...
CARTESIA_API_KEY=...
CARTESIA_VOICE_ID=...    # a voice ID copied from your Cartesia voice library
```

If you use an OpenAI-compatible server instead of OpenAI, Runtime also reads an optional
`OPENAI_BASE_URL`; it is not in `.env.example`.

> **Keep keys out of Git.** `.env` is gitignored: put keys there and nowhere else. Never
> commit them, paste them into issues, chat or screenshots, or put them in API payloads
> (Platform rejects secret-looking configuration keys for this reason). If a key is ever
> exposed, revoke it at the provider and create a new one.

Placeholder or empty values do not give you speech. Runtime should report a configuration or
connectivity failure instead of a working session.

## 2. Start the stack

```bash
cd stack.voice-labs
docker compose up -d
docker compose ps        # wait until postgres is healthy
```

Then three terminals. Each loads the same `.env`. The paths assume the sibling layout
(`stack.voice-labs`, `backend.voice-labs`, `frontend.voice-labs` side by side). Examples use
uv; without it, see [Development](development.md#python-environments) for the virtual
environment equivalent.

**Terminal 1: Platform** (from `backend.voice-labs/platform`). Do **not** `unset
RUNTIME_API_URL` this time; Platform needs it to hand sessions to Runtime.

```bash
uv sync --extra test
set -a; source ../../stack.voice-labs/.env; set +a
export PYTHONDONTWRITEBYTECODE=1
uv run python -m alembic upgrade head
uv run uvicorn src.platform.main:app --reload --port 8000
```

**Terminal 2: Runtime** (from `backend.voice-labs/runtime`). The `voice` extra installs
Pipecat and the provider integrations, which is a large download.

```bash
uv sync --extra voice --extra test
set -a; source ../../stack.voice-labs/.env; set +a
export PYTHONDONTWRITEBYTECODE=1
uv run uvicorn src.runtime.api:app --reload --port 8001
```

**Terminal 3: web app** (from `frontend.voice-labs`):

```bash
npm ci
set -a; source ../stack.voice-labs/.env; set +a
npm run dev
```

Check each piece:

```bash
curl -s http://localhost:8000/health      # {"status":"ok"}
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:3000/agents   # 200
```

`PLATFORM_RUNTIME_TOKEN` and `RUNTIME_PLATFORM_TOKEN` in `.env` must be identical. They are
by default; if you change one, change both and restart both services.

## 3. Choose an agent

Use an agent that will not fail at synthesis. Two safe choices:

- **No voice at all.** An agent with no voice ID and no voice profile speaks with
  `CARTESIA_VOICE_ID` from `.env`. Create one in the web app at
  <http://localhost:3000/agents/new> and leave **Voice ID** empty, or from the API:

  ```bash
  curl -s -X POST http://localhost:8000/agent-templates/receptionist/agents \
    -H 'content-type: application/json' -d '{"name":"Voice test"}'
  ```

- **A real voice.** See [Use a real library voice](#optional-use-a-real-library-voice).

Avoid agents whose **Voice ID** field, or whose voice profile's `provider_voice_id`, holds a
made-up value (such as the `demo-voice-id` used in the API tour). Cartesia has no such
voice, so synthesis fails. If an agent's voice profile is not `ready`, session creation
returns `409 selected_voice_unavailable`.

## 4. Have the conversation

1. Open <http://localhost:3000/agents> and pick your agent.
2. Click **Talk to this agent** (it opens `/agents/<id>/test`).
3. Click **Start conversation** and allow the microphone when Chrome asks.
4. Speak. The page shows the connection state and, as events arrive, activity such as
   "Listening to you" and "Agent speaking", plus the transcript.
5. Click **End conversation** when done. Leaving the page also ends the session.

If Chrome blocked the microphone earlier, click the lock icon next to the address bar,
allow the microphone, and reload. Use Chrome for this tour; Safari may refuse mixed
https/localhost combinations (see the hosted-frontend section below).

## 5. Check the transcript from the API

Each turn is persisted by Platform from Runtime's events. Find the conversation and read its
messages:

```bash
curl -s "http://localhost:8000/conversations?agent_id=<AGENT_ID>" | jq '.[0] | {id, status, channel}'
curl -s http://localhost:8000/conversations/<CONVERSATION_ID>/messages | jq
```

Expected shape (content depends on what was said):

```json
[
  {
    "id": "…",
    "role": "user",
    "content": "Hello, I would like to book an appointment.",
    "primary_language": "en",
    "detected_languages": ["en"],
    "created_at": "…"
  }
]
```

Assistant replies appear as `role: "assistant"` messages. The `runtime-state` endpoint shows
the raw event trail, which is the quickest way to see how far a session got:

```bash
curl -s http://localhost:8000/conversations/<CONVERSATION_ID>/runtime-state | jq '[.session_status] + [.events[].event_type]'
```

A healthy start includes `RuntimeStarted`; speech adds `SpeechStarted`, `TranscriptFinal`,
`AgentSpeechStarted` and so on. A failure shows `SessionFailed` or `RuntimeFailed`. If the
transcript stays empty, check the Runtime terminal for provider errors (bad key, no credit,
unsupported provider, unknown voice ID).

## Optional: use a real library voice

To pick a voice per agent instead of the `.env` default, register a Cartesia voice ID as a
library voice and attach it. Replace `<CARTESIA_VOICE_ID>` with a real ID from your Cartesia
account and `<AGENT_ID>` with your agent:

```bash
API=http://localhost:8000
api() { curl -sS -H 'content-type: application/json' "$@"; }

TTS_ID=$(api -X POST $API/providers -d '{"kind":"tts","provider":"cartesia"}' | jq -r .id)
VOICE_ID=$(api -X POST $API/voices \
  -d "{\"name\":\"My Cartesia voice\",\"tts_provider_id\":\"$TTS_ID\",\"provider_voice_id\":\"<CARTESIA_VOICE_ID>\"}" | jq -r .id)
api -X PATCH $API/agents/<AGENT_ID> -d "{\"voice_profile_id\":\"$VOICE_ID\"}" | jq '{name, voice_profile_id}'
```

The next session for that agent sends the voice's `provider_voice_id` to Runtime. Platform
does not check that the ID exists at Cartesia; a wrong ID only shows up as a synthesis
failure in Runtime. Cloned and designed voices are records only today (they stay `pending`
because provider provisioning is not implemented), so they cannot be used for speech yet.

## Using a hosted frontend

A hosted build of the web app (for example one deployed to Cloudflare Workers) does **not**
work fully with a Platform on your own machine:

- The deployed build has no `NEXT_PUBLIC_PLATFORM_URL`, so it falls back to
  `http://localhost:8000`.
- Pages such as Agents are server components that render on the hosting provider's servers.
  There, `localhost` is the server, not your machine, so you see "Can't reach the platform"
  or "Platform API is unavailable".
- Browser-side calls from a hosted https page to `http://localhost` also depend on browser
  rules: Chrome needs Platform to answer private-network preflights
  (`PLATFORM_ALLOW_PRIVATE_NETWORK=1`) and the hosted origin listed in `PLATFORM_WEB_ORIGIN`
  (comma-separated, for example `http://localhost:3000,https://your-frontend.example`), and
  Safari blocks it outright.

The reliable fix is to run the web app locally (step 2). The alternative is to make Platform
reachable at a public URL, for example through a tunnel, and set `NEXT_PUBLIC_PLATFORM_URL`
to it in the hosted build before building it. Be careful: **Platform has no authentication
yet.** Anyone who learns a public URL can create sessions that spend your Deepgram, OpenAI
and Cartesia credit and can read and change your agents and conversations. Do not leave such
a tunnel open, and do not share it.

## Stop everything

Press `Ctrl+C` in each terminal, then `docker compose down` in `stack.voice-labs` (add `-v`
to also erase the local database).
