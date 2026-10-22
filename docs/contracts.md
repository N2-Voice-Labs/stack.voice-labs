# Contracts

Runtime events carry `event_id`, `event_type`, `schema_version`, session/conversation/
agent IDs, timestamp, optional trace ID, and payload. Platform authenticates Runtime
requests and ingests events idempotently by event ID.

Platform-to-Runtime session handoff includes the selected agent/conversation/session
context and LiveKit room details. Runtime must join the requested room and report
lifecycle changes; the durable record remains owned by Platform.

## Authentication

The Platform API is protected by admin API keys, configured with the environment variable
`PLATFORM_API_KEYS` (comma-separated, any key is accepted). **When it is unset or empty,
authentication is disabled** and Platform logs one startup warning; this is the local
development default. Never expose the API publicly without setting it.

When enabled, every endpoint requires `Authorization: Bearer <key>`. Protection is on by
default: a route is open only if it is explicitly allowlisted.

| Route | Credential |
| --- | --- |
| `GET /health` | None (public) |
| `POST /runtime/events`, `POST /runtime/agents/{agent_id}/knowledge/search` | Runtime token (`X-Runtime-Token`); the admin key is not used here |
| `GET /voice/sessions/{id}`, `POST /voice/sessions/{id}/end`, `POST /voice/sessions/{id}/ensure-running`, `POST /voice/sessions/{id}/participants`, `GET /conversations/{id}`, `GET /conversations/{id}/messages`, `GET /conversations/{id}/runtime-state` | Admin key, or a session token for that session (see below) |
| Everything else, including `POST /voice/sessions` | Admin key |

Errors: `401 authentication_required` (no `Authorization` header), `401 invalid_api_key`
(wrong key or not a `Bearer` credential; the response carries `WWW-Authenticate: Bearer`),
`403 forbidden` (a session token used on another session, on a creator-only route as a guest,
or on a route that is not session-scoped). CORS allows the `authorization` header.

### Session tokens

`POST /voice/sessions` returns an extra `session_token` (prefix `vls_`) for the creator. Adding
a participant with `POST /voice/sessions/{id}/participants` returns one for that guest as
`session_token`. Tokens are random, shown once, and only their SHA-256 digests are stored
(`voice_sessions.session_token_hash` and `guest_token_hashes`, migration `0007_session_tokens`).
A token works only on the session-scoped routes above and only for its own session (and its
conversation). Only the creator's token may add participants; a guest's token may not.
A browser can therefore be handed a session token instead of an admin key. Tokens are returned
even while authentication is disabled but are not required.

## Milestone 8: Voice Studio, Deployments, and Calls

Backend-only contracts for the **Voice → Agent → Deployment → Call** model (see
[Backend Milestone 8](BACKEND_STUDIO_PLAN.md)). Platform stores durable metadata only: no
audio, no raw voice samples, no provider provisioning, TTS preview, PSTN dialing, SIP
transfer, embeddings, or LLM summaries. Error bodies are `{"detail": "<code>"}`; request
shape/format failures (for example a non-E.164 phone number or a secret-looking
`configuration` key) return FastAPI's standard `422` validation `detail` list instead of a
code. All `configuration`/`metadata` objects reject secret-looking keys (`secret`, `password`,
`token`, `api_key`, `apikey`, matched case-insensitively at any depth); use references.
Phone numbers must match E.164 (`^\+[1-9]\d{6,14}$`). Unknown IDs on `GET`/`PATCH`/`DELETE`
return `404` with `<object>_not_found`.

### Voices

`POST /voices` (library), `POST /voices/clone`, `POST /voices/design`, `GET /voices`
(filters `status`, `source`), `GET /voices/{id}`, `PATCH /voices/{id}` (`name`, `languages`,
`style`; `null` is rejected), `POST /voices/{id}/status`, `POST /voices/{id}/provision`,
`POST /voices/{id}/preview`, `DELETE /voices/{id}` (`204`, sets `status=disabled`). Voice
fields: `id`, `name`, `source` (`library|clone|design`), `status`, `tts_provider_id`,
`provider_voice_id`, `languages` (default `["en","ru"]`), `style`, `design_prompt`,
`sample_reference`, `consent`, `failure_reason`, timestamps.

| Create | Required | Initial status |
| --- | --- | --- |
| `POST /voices` | `name`, `tts_provider_id`, `provider_voice_id` | `ready` |
| `POST /voices/clone` | `name`, `sample_reference`, `consent` | `pending` |
| `POST /voices/design` | `name`, `design_prompt` (≤2000 chars) | `pending` |

`style` accepts only `energy`, `warmth`, `speed` (floats in `[0, 1]`) and `style` (label,
≤50 chars); other keys are rejected. `tts_provider_id`, when given, must be an enabled `tts`
provider (`422 invalid_tts_provider_id`).

Clone consent is mandatory and stored with the voice, with a server `recorded_at` added:

```json
{
  "name": "Support voice",
  "sample_reference": "https://example.com/anna.wav",
  "consent": {
    "confirmed": true,
    "subject_name": "Anna Petrova",
    "statement": "I consent to cloning my voice for this agent.",
    "method": "self"
  }
}
```

`method` is `self` or `authorized`. Clone errors: `422 voice_consent_required` (consent
missing or `confirmed` is not `true`), `422 invalid_sample_reference` (not a
`scheme://...` reference without whitespace, or longer than 1024 chars).

`POST /voices/{id}/status` takes `{"status", "provider_voice_id?", "failure_reason?"}`.
Transitions are validated (`409 invalid_voice_status_transition`); moving to `ready`
requires a provider voice ID in the request or already on the voice
(`422 provider_voice_id_required`). `failure_reason` is kept only for `failed` and cleared
otherwise.

| From | Allowed next |
| --- | --- |
| `pending` | `processing`, `failed` |
| `processing` | `ready`, `failed` |
| `failed` | `pending` |
| `ready` | `disabled` |
| `disabled` | `ready` (only if a `provider_voice_id` was already set; otherwise `409`) |

#### Voice cloning provisioning

`POST /voices/{id}/provision` triggers the provisioning of a cloned voice: Platform sends
a request to Runtime, which downloads the consented `sample_reference` (HTTPS only,
≤10 MB, audio content-type, host must be public IPv4/IPv6), validates it, and uploads it
to the TTS provider's clone API. Platform records the `provider_voice_id` on success or a
`failure_reason` on error. The voice must have `source=clone` and `status` in
`{"pending", "failed"}` (`409 invalid_voice_status_transition` otherwise); it must carry
valid `consent` with `confirmed: true` (`409 voice_consent_required` otherwise);
`sample_reference` must be HTTPS (`422 unsupported_sample_url` otherwise).

Request timeout: 60 seconds. The voice is moved to `processing` before the request and to
`ready` on success or `failed` with a `failure_reason` on error.

Failure reasons (safe to expose):
- `unsupported_sample_url`: sample URL is not HTTPS
- `sample_unavailable`: sample host did not resolve, returned HTTP error, is private/loopback, or is too large (>10 MB)
- `clone_provider_error`: the TTS provider (Cartesia) call failed
- `tts_not_configured`: provider credentials not set in Runtime
- `unsupported_tts_provider`: provider name is not supported by Runtime
- `invalid_runtime_token`: Platform runtime token is invalid
- `runtime_error_NNN`: Runtime returned HTTP NNN without a recognized error code
- `runtime_unreachable`: network error reaching Runtime
- `runtime_invalid_response`: Runtime response was malformed or had no provider voice ID

**Status:** Implemented and tested with mocks. Not exercised against a real Cartesia
trunk; sample download and clone upload shape follow
`https://docs.cartesia.ai/api-reference/voices/clone`.

#### Voice preview

`POST /voices/{id}/preview` with `{"text"}` (≤300 chars) returns audio (MIME type
`audio/wav`) synthesized by the voice's TTS provider. The voice must have `status=ready`
and a `provider_voice_id` (`409 voice_not_ready` otherwise). Platform forwards the request
to Runtime's `POST /tts/preview` endpoint with the voice provider, ID, and text.

Errors: `409 voice_not_ready`, `503 runtime_not_configured`, `503 runtime_auth_not_configured`,
`502 voice_preview_failed` (Runtime error or timeout).

**Status:** Verified against real Cartesia.

**Agent voice.** Agents gain `voice_profile_id` (nullable) on create/update/read. It must
reference an existing, non-disabled voice (`422 invalid_voice_profile_id`); it need not be
`ready` yet. The legacy `voice_id` string stays supported.

### Deployments

`POST /deployments`, `GET /deployments` (filters `agent_id`, `channel`, `status`),
`GET /deployments/{id}`, `PATCH /deployments/{id}` (`name`, `status`, `phone_number`,
`configuration`), `DELETE /deployments/{id}` (`204`, archives). Fields: `id`, `agent_id`,
`name`, `channel`, `status`, `phone_number`, `configuration`, timestamps.

| Rule | Detail |
| --- | --- |
| `channel` | `web`, `sip`, `api`; fixed at creation |
| `status` | `active` (default), `paused`, `archived`; archived is terminal |
| Phone | `sip` requires E.164 `phone_number` (`422 phone_number_required`); other channels must not have one (`422 phone_number_only_for_sip`) |
| Agent | must exist and not be `disabled` (`422 invalid_agent_id`); not changeable after creation |
| Archived | `PATCH` returns `409 deployment_archived` |

Phone numbers are not checked for uniqueness across deployments.

**Sessions.** `POST /voice/sessions` accepts `{"agent_id", "deployment_id?"}`. With a
`deployment_id` it returns `404 deployment_not_found`, `409 deployment_not_active`, or
`409 deployment_agent_mismatch` (these follow the existing `409 agent_not_enabled`). The
session response shape is unchanged; the deployment is recorded on the conversation:
`deployment_id` and `channel` (the deployment's channel, or `web` when none is given).

**Voice resolution.** The runtime handoff `voice_id` is `agent.voice_id` unless the agent has
a `voice_profile_id`; then the voice must be `status=ready` with a `provider_voice_id`
(otherwise `409 selected_voice_unavailable`) and its `provider_voice_id` is sent as
`voice_id`.

### SIP and outbound calls

`POST /deployments/{id}/bridge-call` bridges two phone numbers into a single LiveKit
room with an interpreter agent. The deployment must have `channel=sip` and an agent with
`mode=interpreter` using the `cascaded` engine and `direction: "auto"`; otherwise the call is
refused with `422 bridge_requires_two_way_interpreter` before anything is dialed (the two
legs aren't registered as separate participants yet, so the language has to be detected per
utterance). Both legs join the same room and the agent hears and speaks
translations. Request: `{"from_number", "to_number"}` (both E.164). The `from` party is
dialed first, then `to`; if either fails, both calls are hung up and the session is ended.
Response: `session_id`, `conversation_id`, `room_name`, and `participants` list with
`role` (`from` or `to`), phone number, SIP identity, and LiveKit participant ID.

Errors:
- `422 deployment_not_sip`: deployment channel is not `sip`
- `422 agent_not_interpreter`: agent mode is not `interpreter`
- `409 deployment_not_active`: deployment status is not `active`
- `422 bridge_numbers_must_differ`: `from_number` equals `to_number`
- `409 sip_not_configured`: LiveKit SIP trunk not configured
- `502 session_create_failed`: could not create voice session
- `502 sip_dial_failed`: could not dial one or both numbers

#### Outbound campaign dialing

`POST /campaigns/{id}/dial-next` (for demos and tests) dials exactly one pending target
and waits for the attempt to resolve (answered or failed), then returns once the result
is known. The campaign must be `running` and SIP must be configured. Returns
`{"result": "completed" | "failed" | "no_answer", "target": {...}}`.

Errors:
- `409 sip_not_configured`: LiveKit SIP trunk not configured
- `409 campaign_not_running`: campaign status is not `running`
- `409 no_pending_targets`: no pending targets remain

When a campaign's status is set to `running` and `LIVEKIT_SIP_TRUNK_ID` is configured,
an in-process dispatcher starts dialing pending targets. For each attempt it opens a voice
session, dials the target into that room, and records whether the call was answered,
failed, or got no answer. Targets transition: `pending → calling → completed | failed |
no_answer`. Failed or unanswered attempts retry if `attempts < max_attempts`, else move
to their final status. The dispatcher runs one process per Platform instance (not safe
for multi-replica deployments) and does not honour `schedule_start`/`schedule_end` or
`retry_delay_*` configuration. A crash leaves the in-flight target in `calling`.

**Configuration and environment:**
- `LIVEKIT_SIP_TRUNK_ID`: LiveKit outbound SIP trunk ID (required to enable dialing)
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`: LiveKit credentials (required)
- `LIVEKIT_SIP_RINGING_TIMEOUT_S`: seconds to let callee ring (default 30)
- `LIVEKIT_SIP_KRISP`: `1` to enable Krisp noise cancellation on the SIP leg
- `PLATFORM_API_URL`: where Platform reaches itself to open voice sessions (default
  `http://localhost:8000`)

#### SIP transfer

When the LLM calls `transfer_to_human` in a SIP call (a call from a `sip` deployment),
Runtime transfers the SIP participant to the configured destination. The destination is
resolved from the session's `transfer_to` (set by Platform from
`deployment.configuration.transfer_to`), or from `SIP_TRANSFER_TO` environment variable.
Bare E.164 numbers are converted to `tel:+...` URIs; `tel:`, `sip:`, and `sips:` URIs
pass through as-is.

Web sessions (no SIP participant) record the handoff intent without transferring.

**Configuration and environment:**
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`: required; the transfer handler is
  installed whenever these are set (no trunk ID needed for transfers)
- `SIP_TRANSFER_TO`: default destination for transfers (E.164 or tel:/sip:/sips: URI);
  overridden by `deployment.configuration.transfer_to` per session

`deployment.configuration.transfer_to` is validated on create and update: `+E.164` or a
`tel:`/`sip:`/`sips:` URI without spaces, at most 255 characters (`422`, message
`invalid_transfer_to`).

Tool errors: `transfer_not_configured` (a SIP caller but no destination; the agent is told no
human is being connected), `transfer_failed` (LiveKit returned a transfer failure reason),
`transfer_not_configured` (no destination resolved), `livekit_api_not_installed`,
plus generic `TransferError` on network or API failure.

**Status:** Implemented and tested with mocks. Not verified against a real SIP trunk.

### Campaigns and targets

When `LIVEKIT_SIP_TRUNK_ID` is configured, moving a campaign to `running` starts an
in-process dispatcher that dials pending targets. Otherwise campaigns are durable records
only and setting to `running` places no calls.

`POST /campaigns`, `GET /campaigns` (filters `agent_id`, `status`), `GET /campaigns/{id}`,
`PATCH /campaigns/{id}`, `POST /campaigns/{id}/status`, `POST /campaigns/{id}/dial-next`,
`POST /campaigns/{id}/targets`, `GET /campaigns/{id}/targets`. Create body: `name`,
`agent_id`, `deployment_id`, `schedule_start?`, `schedule_end?` (naive datetimes are
treated as UTC), `timezone` (IANA, default `UTC`), `max_attempts` (1-10, default 1),
`configuration`. Reads add `status` (starts `draft`) and `target_counts`
(`{"<target status>": n}`). The `configuration` may include `max_concurrent_calls` (1-10,
default 1) to limit concurrent outbound dials.

| Error | Cause |
| --- | --- |
| `422 invalid_agent_id` / `invalid_deployment_id` | unknown agent / deployment |
| `409 deployment_agent_mismatch` | deployment belongs to another agent |
| `422 campaign_requires_sip_deployment` | deployment channel is not `sip` |
| `422 invalid_timezone` / `invalid_schedule` | bad IANA zone / `schedule_end <= schedule_start` |
| `409 campaign_not_editable` | `PATCH` outside `draft`/`scheduled`; add targets outside `draft`/`scheduled`/`paused` |
| `409 invalid_campaign_status_transition` | transition not in the table below |
| `409 deployment_not_active` | moving to `scheduled` or `running` with a non-active deployment |
| `409 campaign_has_no_targets` | moving to `scheduled` or `running` with zero targets |

| From | Allowed next |
| --- | --- |
| `draft` | `scheduled`, `cancelled` |
| `scheduled` | `draft`, `running`, `cancelled` |
| `running` | `paused`, `completed`, `cancelled` |
| `paused` | `running`, `cancelled` |
| `completed`, `cancelled` | none |

`POST /campaigns/{id}/targets` takes `{"targets": [{"phone_number", "name?",
"variables?"}]}` (1-1000 per request) and dedupes by phone number within the campaign and
within the request:

```json
{ "added": 2, "skipped_duplicates": 1 }
```

`GET /campaigns/{id}/targets` accepts `status`, `limit` (1-500, default 100), `offset`.
Target fields: `id`, `campaign_id`, `phone_number`, `name`, `variables`, `status`
(`pending | calling | completed | failed | no_answer`), `attempts`, `conversation_id`,
timestamps. A concurrent insert race that persists returns `409 target_conflict`.

### Tools and knowledge

**Tools.** `POST /tools`, `GET /tools` (filter `enabled`), `GET`/`PATCH /tools/{id}`,
`DELETE /tools/{id}` (`204`, sets `enabled=false`). Fields: `id`, `name`
(`^[a-z][a-z0-9_]{0,63}$`, unique, else `409 tool_name_conflict`), `description`,
`tool_type` (`http` default, or `builtin`), `input_schema` (JSON Schema object: top-level
`"type": "object"`, `properties` an object if present), `configuration`, `enabled`.

`PUT /agents/{id}/tools` with `{"tool_ids": [...]}` **replaces** the agent's tool set
(duplicates collapsed; `[]` clears) and returns the tools sorted by name. Unknown or disabled
tools return `422 invalid_tool_id`. `GET /agents/{id}/tools` lists the assigned tools
(including any disabled after assignment). Unknown agent: `404 agent_not_found`.

**Knowledge documents.** `POST /knowledge/documents`, `GET /knowledge/documents` (filter
`enabled`; summaries omit `content`), `GET`/`PATCH /knowledge/documents/{id}`,
`DELETE` (`204`, sets `enabled=false`). Fields: `id`, `title` (≤300), `source` (≤1024),
`content` (1 to 1,000,000 chars), `metadata`, `enabled`, `version`, `content_length`,
timestamps. `version` starts at `1` and increments only when a `PATCH` changes `content` to
a different value; metadata, title, and `enabled` edits do not bump it.

`PUT /agents/{id}/knowledge` with `{"document_ids": [...]}` replaces the agent's document
set (same semantics as tools; `422 invalid_knowledge_document_id` for unknown or disabled
documents) and returns summaries sorted by title; `GET` lists them.

Tools and knowledge are stored and assignable only: neither is included in the Platform to
Runtime session handoff yet, and there is no chunking or retrieval.

### Agent templates

Static personas: `customer_support`, `sales`, `receptionist`, `booking`, `restaurant`,
`travel`. `GET /agent-templates` and `GET /agent-templates/{key}` return `key`, `name`,
`description`, `system_prompt`, `enabled_languages`, and `suggested_tools` (names only; no
tools are created or assigned). Unknown key: `404 agent_template_not_found`.

`POST /agent-templates/{key}/agents` (`201`) creates an `enabled` agent from the template.
The optional body overrides `name`, `description`, `system_prompt`, `enabled_languages`; the
response is `{id, name, description, system_prompt, enabled_languages, status,
template_key}`. No voice, provider, or tool is set.

### Conversation outcomes, actions, and filters

Conversation reads (`GET /conversations`, `GET /conversations/{id}`) gain:

| Field | Meaning |
| --- | --- |
| `deployment_id`, `channel` | origin (`channel` defaults to `web`) |
| `outcome` | one of the values below, or `null` until recorded |
| `summary`, `intent` | free text; `intent` ≤200 chars |
| `actions` | list of objects (`[]` by default) |
| `outcome_recorded_at` | time of the last outcome write |

Outcomes: `resolved`, `booked`, `callback_requested`, `no_answer`, `declined`, `escalated`,
`failed`, `other`.

`GET /conversations` filters: `agent_id`, `status`, `outcome`, `channel` (combinable),
newest first.

`PUT /conversations/{id}/outcome` with `{"outcome", "summary?", "intent?", "actions?"}`
records an outcome and returns the conversation. Omitted optional fields keep their existing
values (they are not cleared); `actions` replaces the list when sent. Errors:
`422 invalid_outcome`, `404 conversation_not_found`.

### New Runtime events

`ToolCalled`, `HandoffRequested`, and `OutcomeRecorded` are accepted by
`POST /runtime/events` and declared in Runtime's `RuntimeEventType`. They use the standard
envelope (schema version `1`, idempotent by `event_id`) and appear in
`GET /conversations/{id}/runtime-state`. Payloads are validated before the duplicate check;
a duplicate event causes no second effect.

| Event | Payload | Effect on conversation | Errors |
| --- | --- | --- | --- |
| `ToolCalled` | `tool_name` (non-empty string, required), `arguments?` (object), `status?`, `error?` (strings) | none beyond storing the event | `422 invalid_tool_event` |
| `HandoffRequested` | `reason?`, `target?` (strings) | sets `outcome=escalated`, `outcome_recorded_at`, appends `{"type":"handoff_requested","reason","target"}` to `actions` | `422 invalid_handoff_event` |
| `OutcomeRecorded` | `outcome` (required, valid value), `summary?`, `intent?` (≤200), `actions?` (list of objects) | same as `PUT .../outcome` | `422 invalid_outcome` (bad outcome), `422 invalid_outcome_event` (other fields) |

Later writes win: an `OutcomeRecorded` after a handoff replaces `escalated`, and a handoff
overwrites any earlier outcome. SIP transfer itself is not implemented; the handoff event
only records intent.

### Analytics

`GET /analytics/summary?agent_id=<uuid>&since=<ISO datetime>` (both optional; `since`
filters on conversation `started_at`, naive values are UTC). Missing values are counted
under `"unknown"`.

```json
{
  "conversations": {
    "total": 12,
    "by_status": { "ended": 10, "failed": 2 },
    "by_outcome": { "resolved": 6, "booked": 2, "unknown": 4 },
    "by_channel": { "web": 9, "sip": 3 }
  },
  "languages": { "en": 40, "ru": 22, "unknown": 3 },
  "latency": { "stt": { "count": 25, "p50": 120.0, "p95": 310.0 } }
}
```

`languages` counts messages by `primary_language`. `latency` is keyed by metric name with
nearest-rank `p50`/`p95` over `LatencyMeasured` events.

**Provisional:** Runtime does not emit `LatencyMeasured` yet, so `latency` is `{}` in
practice and the payload shape is not a stable contract. Platform currently accepts a
metric name in the first string among `metric`, `stage`, `name` and a number (not
boolean) in the first of `value_ms`, `latency_ms`, `duration_ms`, `value`; other events are
skipped. Runtime must fix the real payload before this is relied upon.

### Interpreter mode

An agent with `mode=interpreter` acts as a translator between two parties in a SIP call.
Instead of a personality, it carries an `interpreter` configuration with the language
pair and translation engine:

```json
{
  "mode": "interpreter",
  "interpreter": {
    "languages": ["en", "ru"],
    "direction": "auto",
    "engine": "cascaded"
  }
}
```

| Field | Values | Detail |
| --- | --- | --- |
| `languages` | list of 2 distinct IANA codes | Required; supported: `en`, `ru`, `ko`, `ja`, `zh`, `es`, `fr`, `de`, `it`, `pt`, `nl`, `hi`, `tr`, `pl` |
| `direction` | `auto` (default) or `one_way` | `auto` requires both languages in Deepgram's code-switching set (`en`, `es`, `fr`, `de`, `hi`, `ru`, `pt`, `ja`, `it`, `nl`) |
| `engine` | `cascaded` (default) or `realtime` | `cascaded`: separate STT → LLM → TTS pipeline; `realtime`: OpenAI gpt-realtime-translate (one_way only, provider voices, target language must be in its output set: `es`, `pt`, `fr`, `ja`, `ru`, `zh`, `de`, `ko`, `hi`, `id`, `vi`, `it`, `en`) |

Creating or updating an agent requires `interpreter` if and only if `mode=interpreter`;
omitting it when mode is `interpreter` raises `422 interpreter_config_required`, and
including it when mode is `agent` raises `422 interpreter_config_not_allowed`.

Invalid combinations raise `422 invalid_interpreter_config`:
- `engine=realtime` with `direction != one_way`
- `engine=realtime` with target language (second in `languages`) not in the realtime
  output set

**Status:** `direction=auto` and `engine=cascaded` verified 2026-10-18 with real Deepgram/OpenAI/Cartesia (1.47 s end-to-speech p50). `engine=realtime` verified with real OpenAI gpt-realtime-translate (0.96 s p50 from speech start); transcription text occasionally misses spaces between streamed pieces. Bridge-call endpoint dials both parties, handled by the interpreter. SIP transfer and dialing implemented with mocks only.

#### Two-participant sessions

An interpreter agent with `engine=cascaded` can conduct a two-person call with per-participant language and voice profiles. Both parties join the same LiveKit room; each hears the other in their chosen voice and declared language.

**Create a session with a participant:**

`POST /voice/sessions` takes an optional `participant` in the body:

```json
{
  "agent_id": "...",
  "deployment_id": "...",
  "participant": {
    "language": "en",
    "voice_profile_id": "...",
    "display_name": "Alice"
  }
}
```

- `language` (required): one of the agent's `interpreter.languages`.
- `voice_profile_id` (optional): a `status=ready` voice profile with a `provider_voice_id`. Without it, the agent's voice is used.
- `display_name` (optional, ≤100 chars): how the interpreter names this speaker in transcripts.

Returns session response with `participants` object in `runtime_contract` containing the first participant's entry: `{language, voice_id, display_name}`.

**Add the second participant:**

`POST /voice/sessions/{session_id}/participants` takes the same `ParticipantIn` body.

Returns:

```json
{
  "session_id": "...",
  "conversation_id": "...",
  "room_name": "...",
  "participant": {
    "language": "ko",
    "voice_id": "...",
    "display_name": "Bob"
  }
}
```

Validation and errors:
- `404 voice_session_not_found`: session does not exist.
- `409 session_not_active`: session is not `created` or `running`.
- `409 participants_not_enabled`: no first participant; call `POST /voice/sessions` with a `participant` first.
- `409 session_full`: session already has 2 participants (max is 2).
- `422 invalid_participant_language`: participant language not in `interpreter.languages`.
- `422 participants_require_cascaded_interpreter`: agent is not an interpreter or uses `engine=realtime`.
- `409 selected_voice_unavailable`: voice profile is not `status=ready` or lacks a `provider_voice_id`.

**Status:** Verified 2026-10-18 with Korean ↔ English (0.8–1.4 s end-to-speech). Fixed Pipecat shared-resampler crosstalk; everyone hears all audio (per-listener routing deferred).

#### Agent translation (assistant + translator)

An agent with `mode=agent` can work in its own language while callers speak others via a `translation` field. The agent's reasoning, tools, and knowledge stay in the working language; inbound and outbound speech are automatically translated.

`POST /agents` or `PATCH /agents/{id}` with `translation` (on a non-interpreter agent):

```json
{
  "translation": {
    "working_language": "en",
    "caller_languages": ["ru"]
  }
}
```

- `working_language` (required): agent's language for LLM, tools, and knowledge; must be in `INTERPRETER_LANGUAGES`.
- `caller_languages` (required): list of 1–4 distinct codes callers speak; must all be in `INTERPRETER_LANGUAGES`, cannot include `working_language`.

Validation rules:
- `translation` requires `mode=agent` (`422 translation_not_allowed_for_interpreter` if `mode=interpreter`).
- If all caller languages and the working language are in Deepgram's code-switching set (`en`, `es`, `fr`, `de`, `hi`, `ru`, `pt`, `ja`, `it`, `nl`), automatic per-utterance language detection is enabled. Otherwise, exactly one (fixed) caller language is allowed; multiple without automatic detection raises `422 invalid_translation_config`.
- All language codes must be distinct and in the supported set.

Errors:
- `422 translation_not_allowed_for_interpreter`: agent mode is `interpreter`.
- `422 invalid_translation_config`: field types invalid, unknown language, >4 caller languages, duplicates, working language in caller list, or multiple fixed languages without automatic detection capability.

The LLM model for translation defaults to `gpt-4.1-nano`; override with `provider_settings.llm.translation_model` in Runtime.

**Status:** Verified 2026-10-18 with English receptionist agent and Russian caller (n=2); end-to-speech p50 1.9 s.

#### TranscriptFinal payload fields for interpreter and translator modes

For interpreter and agent+translator modes, `TranscriptFinal` events emit language and translation metadata in the `payload`:

**User utterances in interpreter mode (role=user):**
- `speaker_user_id`: LiveKit participant ID of the speaker.
- `primary_language`: spoken language (detected or declared).
- `target_language`: language into which the translator repeats.
- `speaker_name`: optional display name from the session.

**Agent translations in interpreter mode (role=assistant):**
- `speaker_user_id`: whom the interpreter is repeating.
- `source_language`: the speaker's language.
- `target_language`: language of the spoken translation.
- `primary_language`: language of the output translation.
- `speaker_name`: optional display name from the session.

**Inbound user speech in agent+translator mode (role=user):**
- `translated_text`: text in the working language (after inbound translation).
- `primary_language`: caller's language.
- `working_language`: agent's language.
- `user_id`: LiveKit participant ID.
- `speaker_name`: optional.

**Agent response in agent+translator mode (role=assistant):**
- `original_text`: agent's response in the working language.
- `translated_text`: response in the caller's language (if translation succeeded; original if it failed).
- `primary_language`: language of the spoken output.
- `working_language`: agent's language.
- `speaker_name`: optional.

#### LatencyMeasured metrics for translation

Interpreter and agent+translator pipelines emit additional metrics in `LatencyMeasured` events:

| Metric | Stage | Meaning |
| --- | --- | --- |
| `translation_ms` | cascaded | End-to-end: speech end → translated audio (STT → LLM → TTS) |
| `translation_first_chunk_ms` | cascaded | Time to first translated text output (STT → LLM) |
| `realtime_first_audio_ms` | realtime | Time from speech start to first audible output |
| `inbound_translation_ms` | agent+translator | Caller speech → working language (LLM translation step) |
| `outbound_translation_first_chunk_ms` | agent+translator | Agent reply start → first translated text (LLM translation step) |

**Status:** Runtime emits these in TR-040 (agent+translator), TR-010 (realtime engine), and TR-004 (cascaded). Platform stores and reports them in analytics. Payload shape is provisional pending Runtime emission.

### Glossary (`interpreter.glossary`, `translation.glossary`)

An optional per-agent list of terms that translation must respect. It is stored inside the
agent's existing `interpreter` or `translation` JSON (no migration) and reaches Runtime in the
session contract.

```json
"glossary": [
  {"source": "residence permit",
   "translations": {"ru": "вид на жительство", "ko": "체류 허가"},
   "note": "optional hint"},
  {"source": "Voice Labs", "keep": true}
]
```

- At most 200 entries. `source` and each translation are 1–100 characters, `note` at most
  200, with no control characters; sources are unique ignoring case. Language codes use the
  interpreter language set. An entry has either `translations` or `keep: true`.
- `source` is the term in any language without a `translations` entry (usually the working
  language). en → ru uses the Russian term; ru → en maps it back to `source`. `keep: true`
  terms (names, brands) are never translated.
- Runtime puts the relevant entries into the translation prompt: all of them when 6 or fewer
  apply, otherwise only those whose term appears in the utterance, at most 12 per call.
- The same terms are sent to Deepgram as `keyterm` boosting (at most 100) so speech
  recognition hears them correctly.
- Applies to the cascaded engine and to agent + translator mode. The realtime engine
  (gpt-realtime-translate) has no instruction or glossary field and ignores it.
- An invalid glossary is rejected with 422 (`invalid_glossary: <reason>` for `translation`).
