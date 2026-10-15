# Quickstart: API tour (no provider keys)

A five-minute tour of the Voice Labs Platform API. You will create a voice, an agent, a
phone deployment and a session, simulate the events a Runtime would send, and read back the
resulting conversation and analytics.

No Deepgram, OpenAI or Cartesia keys are needed. Nothing here produces audio: Platform only
stores records, and you play the part of the Runtime with `curl`. For real speech, see
[Quickstart: talk to an agent](quickstart-voice.md).

## Before you start

You need Git, Docker (with Compose), Python 3.11+, `curl`, `jq` and `uuidgen`
(`uuidgen` and `curl` ship with macOS and most Linux distributions; `brew install jq` or
`apt install jq` for the rest). The workspace layout is three sibling directories:

```text
stack.voice-labs/      # this repository: Compose, .env.example, docs
backend.voice-labs/    # platform/, runtime/, evals/
frontend.voice-labs/   # Next.js web app (not needed for this tour)
```

## 1. Set up the environment

From `stack.voice-labs`:

```bash
cp .env.example .env
docker compose up -d
docker compose ps
```

For this tour only PostgreSQL is required; Compose also starts Valkey and LiveKit, which
you can leave running. Wait until `postgres` shows `healthy`.

`.env` is gitignored and shared by all apps. The defaults work as they are, including
`PLATFORM_RUNTIME_TOKEN=local-runtime-token-change-me`, which you will use in step 7.

## 2. Start Platform in API-only mode

In a second terminal, from `backend.voice-labs/platform`. With [uv](https://docs.astral.sh/uv/)
(the path the stack README uses):

```bash
uv sync --extra test
set -a; source ../../stack.voice-labs/.env; set +a
unset RUNTIME_API_URL
export PYTHONDONTWRITEBYTECODE=1
uv run python -m alembic upgrade head
uv run uvicorn src.platform.main:app --reload --port 8000
```

Without uv, create a virtual environment outside the repositories and use it instead
(see [Development](development.md#python-environments)); the last two commands become
`python -m alembic upgrade head` and `python -m uvicorn src.platform.main:app --reload --port 8000`.

`unset RUNTIME_API_URL` is what makes this "API-only". With it set, Platform tries to hand
every new session to a Runtime, and session creation fails with `503 runtime_unavailable`
when no Runtime is listening on port 8001.

Check that it is up:

```bash
curl -s http://localhost:8000/health
```

```json
{"status":"ok"}
```

You can follow this tour in Swagger UI instead of `curl`: open
<http://localhost:8000/docs> and use "Try it out" on the same endpoints, in the same order.
The `curl` version is easier to copy, so the rest of the page uses it.

## 3. Run the tour

Open a third terminal in `stack.voice-labs` and load the shared settings so
`PLATFORM_RUNTIME_TOKEN` is available. Keep this terminal for every remaining step, because
later steps reuse its shell variables.

```bash
set -a; source .env; set +a
API=http://localhost:8000
api() { curl -sS -H 'content-type: application/json' "$@"; }
```

IDs, timestamps and the room name will differ from the sample output below.

### Create a TTS provider

A voice belongs to a text-to-speech provider record. This is metadata only; no key is
involved and nothing is called.

```bash
TTS_ID=$(api -X POST $API/providers -d '{"kind":"tts","provider":"cartesia"}' | jq -r .id)
echo "$TTS_ID"
```

### Create a library voice

A library voice points at a voice ID that already exists at the provider. It is created
with status `ready`. The ID below is a placeholder, which is fine for this tour but would
fail at synthesis in a real call (see the voice quickstart).

```bash
VOICE_ID=$(api -X POST $API/voices \
  -d "{\"name\":\"Demo voice\",\"tts_provider_id\":\"$TTS_ID\",\"provider_voice_id\":\"demo-voice-id\"}" \
  | jq -r .id)
api $API/voices/$VOICE_ID | jq '{name, source, status, provider_voice_id, languages}'
```

```json
{
  "name": "Demo voice",
  "source": "library",
  "status": "ready",
  "provider_voice_id": "demo-voice-id",
  "languages": ["en", "ru"]
}
```

### Try a clone without consent

Cloning a voice requires explicit, recorded consent. Leave it out and Platform refuses:

```bash
api -w '\nHTTP %{http_code}\n' -X POST $API/voices/clone \
  -d '{"name":"Cloned voice","sample_reference":"s3://samples/anna.wav"}'
```

```text
{"detail":"voice_consent_required"}
HTTP 422
```

A valid clone sends `consent` with `confirmed: true`, `subject_name`, `statement` and
`method` (`self` or `authorized`). It is stored with status `pending`; actual cloning at
the provider is not implemented. See [Contracts](contracts.md#voices).

### Create an agent from a template

Templates are ready-made personas. `receptionist` creates an enabled agent with a system
prompt and `en`/`ru` languages. No voice, provider or tool is attached.

```bash
AGENT_ID=$(api -X POST $API/agent-templates/receptionist/agents -d '{"name":"Front desk"}' | jq -r .id)
```

Attach the voice with a `PATCH`:

```bash
api -X PATCH $API/agents/$AGENT_ID -d "{\"voice_profile_id\":\"$VOICE_ID\"}" \
  | jq '{id, name, voice_profile_id, status}'
```

```json
{
  "id": "6bfa04d0-…",
  "name": "Front desk",
  "voice_profile_id": "486fc341-…",
  "status": "enabled"
}
```

### Create a SIP deployment

A deployment says where an agent is reachable. `sip` requires an E.164 phone number
(`+` and 7 to 15 digits). It is a record only: nothing answers a phone yet.

```bash
DEP_ID=$(api -X POST $API/deployments \
  -d "{\"agent_id\":\"$AGENT_ID\",\"name\":\"Main line\",\"channel\":\"sip\",\"phone_number\":\"+14155550123\"}" \
  | jq -r .id)
api $API/deployments/$DEP_ID | jq '{name, channel, status, phone_number}'
```

```json
{
  "name": "Main line",
  "channel": "sip",
  "status": "active",
  "phone_number": "+14155550123"
}
```

### Create a session

This is the call Platform makes when someone starts talking to an agent. Passing
`deployment_id` records the deployment and its channel on the conversation.

```bash
SESSION=$(api -X POST $API/voice/sessions -d "{\"agent_id\":\"$AGENT_ID\",\"deployment_id\":\"$DEP_ID\"}")
echo "$SESSION" | jq '{session_id, conversation_id, session_status, connection_status, runtime_status, room_name}'
SESSION_ID=$(echo "$SESSION" | jq -r .session_id)
CONV_ID=$(echo "$SESSION" | jq -r .conversation_id)
```

```json
{
  "session_id": "df1e969e-…",
  "conversation_id": "5a2ec8d3-…",
  "session_status": "created",
  "connection_status": "configured",
  "runtime_status": "manual_start_required",
  "room_name": "voice-labs-df1e969e-…"
}
```

`runtime_status: "manual_start_required"` is expected here. LiveKit is configured (so
Platform minted a room token), but `RUNTIME_API_URL` is unset, so nobody was asked to join
the room. The response also contains `connection.url` and `connection.token`, which a
browser would use to join.

### Simulate Runtime events

A real Runtime reports what happened by posting events to `POST /runtime/events`,
authenticated with the `X-Runtime-Token` header. The token must equal
`PLATFORM_RUNTIME_TOKEN`. Every event has a unique `event_id`; Platform ingests each ID
once, so resending the same event is safe.

First, the caller asks for a human (`HandoffRequested`):

```bash
api -w '\nHTTP %{http_code}\n' -X POST $API/runtime/events \
  -H "X-Runtime-Token: $PLATFORM_RUNTIME_TOKEN" \
  -d "{\"event_id\":\"$(uuidgen)\",\"event_type\":\"HandoffRequested\",\"schema_version\":1,
       \"session_id\":\"$SESSION_ID\",\"conversation_id\":\"$CONV_ID\",\"agent_id\":\"$AGENT_ID\",
       \"payload\":{\"reason\":\"caller asked for a human\",\"target\":\"front-desk\"}}"
```

```text
{"status":"accepted"}
HTTP 202
```

Then the agent records a result (`OutcomeRecorded`), which overrides the `escalated`
outcome the handoff just set:

```bash
api -w '\nHTTP %{http_code}\n' -X POST $API/runtime/events \
  -H "X-Runtime-Token: $PLATFORM_RUNTIME_TOKEN" \
  -d "{\"event_id\":\"$(uuidgen)\",\"event_type\":\"OutcomeRecorded\",\"schema_version\":1,
       \"session_id\":\"$SESSION_ID\",\"conversation_id\":\"$CONV_ID\",\"agent_id\":\"$AGENT_ID\",
       \"payload\":{\"outcome\":\"booked\",\"summary\":\"Booked a visit for Tuesday\",\"intent\":\"book_appointment\"}}"
```

```text
{"status":"accepted"}
HTTP 202
```

The handoff only records intent; nothing is transferred. Valid outcomes are `resolved`,
`booked`, `callback_requested`, `no_answer`, `declined`, `escalated`, `failed` and `other`.

### Read the conversation

List conversations filtered by agent:

```bash
api "$API/conversations?agent_id=$AGENT_ID" | jq '.[0]'
```

```json
{
  "id": "5a2ec8d3-…",
  "agent_id": "6bfa04d0-…",
  "status": "active",
  "started_at": "2026-10-14T14:45:31.100980Z",
  "ended_at": null,
  "metadata": {},
  "deployment_id": "794d4432-…",
  "channel": "sip",
  "outcome": "booked",
  "summary": "Booked a visit for Tuesday",
  "intent": "book_appointment",
  "actions": [
    {
      "type": "handoff_requested",
      "reason": "caller asked for a human",
      "target": "front-desk"
    }
  ],
  "outcome_recorded_at": "2026-10-14T14:45:31.155304Z"
}
```

Note `channel: "sip"` (from the deployment), `outcome: "booked"` (the later write wins) and
the handoff preserved in `actions`. The status stays `active` because no Runtime ever sent
`RuntimeStarted` or `SessionEnded`.

### Read the analytics

```bash
api "$API/analytics/summary?agent_id=$AGENT_ID" | jq
```

```json
{
  "conversations": {
    "total": 1,
    "by_status": { "active": 1 },
    "by_outcome": { "booked": 1 },
    "by_channel": { "sip": 1 }
  },
  "languages": {},
  "latency": {}
}
```

`languages` stays empty because there are no transcript messages, and `latency` is empty
because the Runtime does not emit `LatencyMeasured` events yet. The same endpoint accepts a
`since` filter (ISO datetime).

## Tidy up

Close the session so the conversation no longer looks active. In API-only mode this only
updates Platform's records:

```bash
api -X POST $API/voice/sessions/$SESSION_ID/end
```

```json
{"status":"ended"}
```

There is no delete for conversations. `DELETE /agents/{id}`, `/voices/{id}` and
`/deployments/{id}` disable or archive records rather than removing them. For a clean slate,
stop Platform and run `docker compose down -v` in `stack.voice-labs` to drop the database
volume (this erases all local data).

## Where next

- [Quickstart: talk to an agent](quickstart-voice.md) adds a Runtime, the web app and real
  provider keys.
- [Contracts](contracts.md) lists every endpoint, field and error code used above.
- [Troubleshooting](troubleshooting.md) covers errors such as `runtime_unavailable` and
  `invalid_runtime_token`.
