# Contracts

Runtime events carry `event_id`, `event_type`, `schema_version`, session/conversation/
agent IDs, timestamp, optional trace ID, and payload. Platform authenticates Runtime
requests and ingests events idempotently by event ID.

Platform-to-Runtime session handoff includes the selected agent/conversation/session
context and LiveKit room details. Runtime must join the requested room and report
lifecycle changes; the durable record remains owned by Platform.

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
`style`; `null` is rejected), `POST /voices/{id}/status`, `DELETE /voices/{id}` (`204`,
sets `status=disabled`). Voice fields: `id`, `name`, `source` (`library|clone|design`),
`status`, `tts_provider_id`, `provider_voice_id`, `languages` (default `["en","ru"]`),
`style`, `design_prompt`, `sample_reference`, `consent`, `failure_reason`, timestamps.

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
  "sample_reference": "s3://voice-samples/anna.wav",
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

### Campaigns and targets

Campaigns are durable records only. **No dialer exists:** moving a campaign to `running`
places no calls and leaves every target `pending`; `attempts` and `conversation_id` on
targets are reserved for a future worker.

`POST /campaigns`, `GET /campaigns` (filters `agent_id`, `status`), `GET /campaigns/{id}`,
`PATCH /campaigns/{id}`, `POST /campaigns/{id}/status`, `POST /campaigns/{id}/targets`,
`GET /campaigns/{id}/targets`. Create body: `name`, `agent_id`, `deployment_id`,
`schedule_start?`, `schedule_end?` (naive datetimes are treated as UTC), `timezone`
(IANA, default `UTC`), `max_attempts` (1-10, default 1), `configuration`. Reads add
`status` (starts `draft`) and `target_counts` (`{"<target status>": n}`).

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
(`pending`), `attempts`, `conversation_id`, timestamps. A concurrent insert race that
persists returns `409 target_conflict`.

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
