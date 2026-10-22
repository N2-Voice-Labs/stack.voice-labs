# Concepts

This page explains the objects you work with in Voice Labs and how they connect. It describes
what the code does today. Endpoint and error-code details live in [Contracts](contracts.md).

## The object model

```text
Voice (library / clone / design) ─┐
Knowledge documents ──────────────┼─► Agent ─► Deployment (web / sip / api) ─► Conversation (call)
Tools ────────────────────────────┘      ▲            ▲                           │
Provider configs (stt / llm / tts) ──────┘            │                           ├─ Messages (transcript)
Agent templates ──(create)──► Agent         Campaign ─┘ (sip only) ── targets     ├─ Runtime events
                                                                                  └─ Outcome + actions
```

The path to remember is **Voice → Agent → Deployment → Conversation**. A voice is reusable
across agents. An agent can have several deployments. Each call is one conversation.

## Platform vs Runtime

| | Platform | Runtime |
| --- | --- | --- |
| Role | Durable control plane and source of truth | Live session and audio pipeline |
| Owns | Agents, voices, providers, deployments, conversations, transcripts, outcomes, analytics | LiveKit connection, Pipecat pipeline, VAD, turn detection, STT/LLM/TTS calls, interruptions |
| State | PostgreSQL | In memory for the life of one session |
| Audio | Never touches it | Handles all of it |

Platform creates a conversation and a voice session, issues the browser's LiveKit token, and hands
Runtime the session context: agent, room, system prompt, voice ID, and selected providers.
Runtime posts events back to `POST /runtime/events` with a service token. Platform
authenticates them and stores each event once.

## Agent

An agent is either a conversational persona or an interpreter. A **conversational agent**
has `name`, `description`, `system_prompt`, `enabled_languages` (default `["en","ru"]`),
optional `stt_provider_id`, `llm_provider_id`, `tts_provider_id`, a legacy `voice_id`
string, an optional `voice_profile_id`, and `status`. An **interpreter agent** has
`mode=interpreter`, an `interpreter` configuration (languages, direction, engine), and
no system prompt or voice. Both have `status` (`enabled` or `disabled`).

- **Statuses:** `enabled` (default) or `disabled`. `DELETE /agents/{id}` disables, not removes.
- **Endpoints:** `POST/GET /agents`, `GET/PATCH/DELETE /agents/{id}`.
- Starting a session requires an `enabled` agent (`409 agent_not_enabled` otherwise).
- **Default:** `mode=agent` (conversational). Set to `mode=interpreter` with an
  `interpreter` config to create a translator agent.

**Today:** instructions, languages, providers, and voice reach Runtime at session start
for conversational agents. Interpreter agents are recorded and bridge-callable; they reach
Runtime with their mode and interpreter configuration.
**Not yet:** assigned tools and knowledge are not sent to Runtime.

## Provider configs

A provider config names an STT, LLM, or TTS provider (`kind` is `stt`, `llm`, or `tts`) plus
non-secret `configuration` and an optional `secret_reference`. Secret-looking keys (`secret`,
`password`, `token`, `api_key`, `apikey`) are rejected at any depth, so use references.

- **Endpoints:** `POST /providers`, `GET /providers`.
- The agent's provider must exist, be enabled, and match the kind.

**Today:** Runtime supports Deepgram (STT), OpenAI or OpenAI-compatible (LLM), and Cartesia (TTS).
Only a small set of settings is forwarded (STT `model`, `language`, `interim_results`,
`smart_format`; LLM `model`, `temperature`, `max_tokens`, `top_p`; TTS `model`, `language`).
Any other provider name is rejected by Runtime when the session starts. API keys come from the environment, not the database.

STT and TTS providers come from small registries in Runtime (`runtime/speech_providers.py`),
the same pattern as translation engines. Adding a provider (for example ElevenLabs TTS) is one
factory and one `register_tts(...)` call; pipelines never import a vendor directly. The agent's
provider records decide which one a session uses.

## Voice

A voice is a reusable TTS identity. It has a `source`, a `status`, `languages` (default
`["en","ru"]`), and optional `style` (`energy`, `warmth`, `speed` from 0 to 1, plus a `style` label).

| Source | Created with | Starts as |
| --- | --- | --- |
| `library` | `POST /voices` with a TTS provider and provider voice ID | `ready` |
| `clone` | `POST /voices/clone` with `sample_reference` and `consent` | `pending` |
| `design` | `POST /voices/design` with a `design_prompt` | `pending` |

Statuses move as `pending → processing → ready | failed`, `failed → pending`, and
`ready ↔ disabled`. Moving to `ready` needs a provider voice ID. Other endpoints:
`GET /voices`, `GET/PATCH /voices/{id}`, `POST /voices/{id}/status`, `POST /voices/{id}/provision`,
`POST /voices/{id}/preview`, `DELETE /voices/{id}` (soft disable).

An agent points at a voice with `voice_profile_id`. At session start, the voice must be `ready`
(`409 selected_voice_unavailable` otherwise) and its provider voice ID is sent to Runtime as
`voice_id`. Without a profile, the legacy `voice_id` is used.

### Consent-based voice cloning

Cloning requires explicit consent: `consent` must have `confirmed: true`, a `subject_name`,
a `statement` (why cloning is needed), and a `method` (`self` for the subject, `authorized`
for a delegate). Without it you get `422 voice_consent_required`.

`POST /voices/{id}/provision` (on a `source=clone` voice in `pending` or `failed` status)
sends the consented sample to Runtime. Runtime downloads it from the HTTPS `sample_reference`
URL (≤10 MB, audio content-type, host must be public), validates it, and uploads it to the
TTS provider's clone API. The voice moves to `processing`, then to `ready` with a
`provider_voice_id` on success or to `failed` with a `failure_reason` on error.

`POST /voices/{id}/preview` (on a `ready` voice) returns audio (MIME type `audio/wav`)
synthesized with the voice's provider and voice ID.

**Today:** cloning provisioning is implemented (routes to Runtime, which validates and uploads).
Voice preview and library voice provisioning are verified against Cartesia.
**Not yet:** voice design stays `pending` until something external moves its status; cloning
is not exercised against a real Cartesia trunk. Consent provenance is kept on the voice
record and the server adds `recorded_at`; Platform never stores raw samples.

## Deployment

A deployment makes an agent reachable on a channel.

- **Fields:** `agent_id`, `name`, `channel` (`web`, `sip`, or `api`, fixed at creation), `status`
  (`active`, `paused`, `archived`), `phone_number`, `configuration`.
- **Rules:** a `sip` deployment requires an E.164 `phone_number`; other channels must not have
  one. `archived` is terminal.
- **Endpoints:** `POST/GET /deployments`, `GET/PATCH/DELETE /deployments/{id}` (delete archives),
  `POST /deployments/{id}/bridge-call` (SIP deployment with a cascaded, `auto`-direction
  interpreter).
- Pass `deployment_id` to `POST /voice/sessions` to record the deployment and channel on the
  conversation. It must be active and belong to the same agent.
- **SIP configuration:** `configuration.transfer_to` (validated `+E.164` or tel:/sip:/sips: URI)
  sets the destination for `transfer_to_human` handoffs.

**Today:** the `web` path is what has a running client. Deployments tag conversations with a
channel. `sip` deployments can dial outbound campaigns and bridge interpreter calls (with
`LIVEKIT_SIP_TRUNK_ID` configured).
**Not yet:** `api` deployments are records only.

## Conversation (call)

A conversation is the durable record of one interaction. It has `status`, `agent_id`,
`deployment_id`, `channel` (default `web`), `started_at`/`ended_at`, plus outcome fields
(below). Each conversation has a voice session (the live connection) and ordered messages.
Messages carry `role`, `content`, an optional `primary_language`, and `detected_languages`, so
mixed-language utterances are representable.

- **Endpoints:** `POST /voice/sessions`, `GET /voice/sessions/{id}`, `POST /voice/sessions/{id}/end`,
  `GET /conversations` (filters `agent_id`, `status`, `outcome`, `channel`),
  `GET /conversations/{id}`, `/messages`, `/runtime-state`.

## Runtime events

Runtime reports what happens in a session as versioned events (`schema_version` 1), each with
an `event_id`, session, conversation, and agent IDs, and a payload. Platform dedupes by `event_id`.

| Group | Events |
| --- | --- |
| Lifecycle | `RuntimeStarted`, `SessionEnded`, `SessionFailed`, `RuntimeFailed` |
| Turn-taking | `SpeechStarted`, `SpeechStopped`, `TurnCompleted`, `AgentSpeechStarted`, `UserInterrupted`, `AgentSpeechCancelled` |
| Content | `TranscriptFinal` (creates a message) |
| Metrics | `LatencyMeasured` |
| Actions | `ToolCalled`, `HandoffRequested`, `OutcomeRecorded` |

**Today:** Runtime emits the lifecycle, turn-taking, and `TranscriptFinal` events.
**Not yet:** Runtime does not emit `LatencyMeasured`, `ToolCalled`, `HandoffRequested`, or
`OutcomeRecorded`. Platform accepts and handles them, so they are ready for when Runtime does.

## Outcomes and handoff

A conversation can end with an `outcome`: `resolved`, `booked`, `callback_requested`,
`no_answer`, `declined`, `escalated`, `failed`, or `other`. It is `null` until recorded. Related
fields are `summary`, `intent` (up to 200 characters), `actions` (a list of objects), and
`outcome_recorded_at`.

- Record one with `PUT /conversations/{id}/outcome`, or via an `OutcomeRecorded` event.
- A `HandoffRequested` event sets `outcome=escalated` and appends a `handoff_requested` action
  with the reason and target. The last write wins.
- In a SIP call, the agent's `transfer_to_human` tool initiates a transfer to the deployment's
  configured `transfer_to` destination (or the `SIP_TRANSFER_TO` environment variable) via
  LiveKit SIP, or records the handoff intent if no SIP participant exists (e.g., a web call).

**Today:** outcomes are stored and filterable through the API. SIP transfer is implemented
(transfers the calling SIP participant to the configured destination).
**Not yet:** nothing generates summaries with an LLM. Transfer is not exercised against
a real SIP trunk.

## Tools

A tool is metadata for something an agent could call: a unique snake_case `name`,
`description`, a JSON-Schema `input_schema`, `tool_type` (`http` or `builtin`),
`configuration`, and `enabled`.

- **Endpoints:** `POST/GET /tools`, `GET/PATCH/DELETE /tools/{id}` (delete disables),
  `PUT /agents/{id}/tools` (replaces the agent's set), `GET /agents/{id}/tools`.

**Today:** tools are stored and assignable to agents.
**Not yet:** tools are not included in the Platform-to-Runtime handoff, so a live agent cannot call them.

## Knowledge documents

Text documents for grounding: `title`, `source`, `content` (up to 1,000,000 characters),
`metadata`, `enabled`, and a `version` that increments only when `content` changes.

- **Endpoints:** `POST/GET /knowledge/documents`, `GET/PATCH/DELETE /knowledge/documents/{id}`
  (delete disables), `PUT /agents/{id}/knowledge`, `GET /agents/{id}/knowledge`.

**Today:** documents are stored and assignable.
**Not yet:** no chunking, embeddings, or retrieval, and nothing reaches Runtime.

## Agent templates

Six static personas: `customer_support`, `sales`, `receptionist`, `booking`, `restaurant`,
`travel`. Each has a name, description, `system_prompt`, `enabled_languages`, and
`suggested_tools`.

- **Endpoints:** `GET /agent-templates`, `GET /agent-templates/{key}`,
  `POST /agent-templates/{key}/agents` (creates an enabled agent; optional overrides).

**Today:** a template pre-fills a new agent.
**Not yet:** `suggested_tools` are names only. No tools are created or assigned, and the new
agent has no voice or provider until you set them.

## Interpreter mode

An agent has three possible modes:

1. **Assistant mode** (`mode=agent`, no `translation`): conversational agent that reasons in one language, ignores what the caller speaks, and answers in the agent's configured voice.

2. **Interpreter mode** (`mode=interpreter`): translator between two parties. The agent repeats what each speaker says in the other language, using agreed voice profiles. Both parties join the same LiveKit room; the interpreter sits between them.

3. **Assistant + translator** (`mode=agent` with `translation`): the agent reasons in one language (the `working_language`) while callers speak others. The caller's speech is translated in, the agent's reply is translated out, and both are spoken in the caller's language. This is useful for multilingual receptionists and customer support.

### Interpreter agent (mode=interpreter)

An interpreter agent carries an `interpreter` configuration:

```json
{
  "languages": ["en", "ru"],
  "direction": "auto",
  "engine": "cascaded"
}
```

- **Two engines:**
  - `cascaded` (default): separate STT → LLM → TTS chains. Expected latency 1.5–3 s after the speaker stops. Supports both languages with the agent's voice.
  - `realtime` (OpenAI gpt-realtime-translate): translates while the speaker talks. Latency ~1 s after the speaker starts. One-way only (`languages[0] → languages[1]`); uses provider voices, not the agent's. Target language must be in OpenAI's output set.

- **Direction:**
  - `auto`: bidirectional (each utterance flips to the other language). Requires both languages in Deepgram's code-switching set.
  - `one_way`: fixed mapping (`languages[0] → languages[1]`). Supports any language pair both providers handle.

- **Two speakers:** Each participant declares a language and optionally a consented voice profile. The interpreter listens in the first speaker's language, translates to the second's, and speaks with the assigned voice. `POST /voice/sessions` with a `participant` field creates the first speaker; `POST /voice/sessions/{id}/participants` adds the second.

- **Consent rule:** Voices come from consented voice profiles (not cloned from live call audio). Instant cloning of the other person's voice without consent would be impersonation.

- **No barge-in:** A translation is never cut off by the other person starting to speak; their speech is queued and translated next, maintaining speaker fairness.

- **Creation:** `POST /agents` with `mode=interpreter` requires an `interpreter` config; `mode=agent` forbids it.

**Today:** `engine=cascaded` with `direction=auto` verified with real Deepgram/OpenAI/Cartesia (1.47 s end-to-speech p50). Two-person mode verified with Korean ↔ English (0.8–1.4 s). `engine=realtime` verified with real OpenAI (0.96 s p50 from speech start); transcription text occasionally misses spaces. Bridge-call endpoint dials both parties, handled by the interpreter, and records the session.

**Not yet:** SIP transfer and phone calls use mocks only. Per-listener audio routing (only the other person hears the translation) is future work; everyone in the room hears all audio.

### Assistant + translator (mode=agent with translation)

An agent stays in its own language while supporting callers who speak others:

```json
{
  "translation": {
    "working_language": "en",
    "caller_languages": ["ru"]
  }
}
```

The LLM, tools, and knowledge stay in `working_language`; inbound speech is translated from each `caller_language`, and outbound speech is translated to the caller's language. The agent's instructions, reasoning, and function calls are all in English; only the audio in/out is translated.

Automatic language detection works if both the `working_language` and all `caller_languages` are in Deepgram's code-switching set; otherwise one fixed caller language is required.

**Today:** Verified with real Deepgram/OpenAI/Cartesia (English agent, Russian caller, 1.9 s p50 end-to-speech).

**Not yet:** Voice cloning for agent replies is not yet exercised; `provider_settings.llm.translation_model` defaults to `gpt-4.1-nano`.

## Campaigns and targets

A campaign groups outbound-call targets for an agent and a SIP deployment, with a schedule
window, timezone, and `max_attempts`. Targets have an E.164 phone number, optional name and
variables, and are deduplicated per campaign.

Campaign statuses: `draft → scheduled → running ⇄ paused → completed`, and any non-terminal
state can go to `cancelled`. Scheduling needs an active SIP deployment and at least one target.

- **Endpoints:** `POST/GET /campaigns`, `GET/PATCH /campaigns/{id}`, `POST /campaigns/{id}/status`,
  `POST /campaigns/{id}/dial-next`, `POST/GET /campaigns/{id}/targets`.
- **Dispatcher:** when a campaign moves to `running` and `LIVEKIT_SIP_TRUNK_ID` is configured,
  an in-process dispatcher opens a voice session per pending target, dials it, and tracks the
  outcome. Targets transition `pending → calling → completed | failed | no_answer`. Failed or
  unanswered calls retry if `attempts < max_attempts`.

**Today:** durable records, validated status transitions, and an in-process dialer. Setting a
campaign to `running` dials pending targets (if SIP is configured).
**Not yet:** the dispatcher does not honour `schedule_start`/`schedule_end` or `retry_delay_*`
config, and is per-process (not safe for multi-replica). A crash leaves in-flight targets in
`calling`.

## Analytics

`GET /analytics/summary` (optional `agent_id`, `since`) returns conversation counts by status,
outcome, and channel; a message count by `primary_language`; and p50/p95 latency by metric.
Missing values count as `unknown`.

**Today:** counts and language distribution work.
**Not yet:** `latency` is empty (`{}`) because Runtime does not emit `LatencyMeasured`. The payload shape
is provisional.

## Not covered yet

Platform has no authentication or multi-tenancy (deferred). The web app covers agents and
conversations; the Milestone 8 objects above are API-only for now.
