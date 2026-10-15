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

An agent is the configured persona: `name`, `description`, `system_prompt`,
`enabled_languages` (default `["en","ru"]`), optional `stt_provider_id`, `llm_provider_id`,
`tts_provider_id`, a legacy `voice_id` string, an optional `voice_profile_id`, and `status`.

- **Statuses:** `enabled` (default) or `disabled`. `DELETE /agents/{id}` disables, not removes.
- **Endpoints:** `POST/GET /agents`, `GET/PATCH/DELETE /agents/{id}`.
- Starting a session requires an `enabled` agent (`409 agent_not_enabled` otherwise).

**Today:** instructions, languages, providers, and voice reach Runtime at session start.
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
Any other provider name is rejected by Runtime. API keys come from the environment, not the database.

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
`GET /voices`, `GET/PATCH /voices/{id}`, `POST /voices/{id}/status`, `DELETE /voices/{id}`
(soft disable).

An agent points at a voice with `voice_profile_id`. At session start, the voice must be `ready`
(`409 selected_voice_unavailable` otherwise) and its provider voice ID is sent to Runtime as
`voice_id`. Without a profile, the legacy `voice_id` is used.

**Today:** these are records plus a status lifecycle. A library voice carries a real provider voice ID that is sent to Runtime (real-provider
speech with it has not been recorded as verified).
**Not yet:** no provider clone or design job runs, so a clone or design voice stays `pending`
until something external moves its status. There is no preview synthesis and no sample upload
storage; `sample_reference` is just an external URI such as `s3://...`.

### Consent-based cloning

Voice Labs treats cloning as something that needs permission:

- **Consent attestation is required.** `consent` must have `confirmed: true`, a `subject_name`,
  a `statement`, and a `method` of `self` or `authorized`. Without it you get
  `422 voice_consent_required`.
- **Provenance is kept.** The consent record is stored with the voice, and the server adds
  `recorded_at`.
- **No raw samples in Platform.** Only the `sample_reference` is stored.
- **Disclose that it is AI.** Agents using cloned or synthetic voices should tell callers they
  are talking to an AI. This is a guideline for how you write agent instructions; Platform does not
  enforce it.

## Deployment

A deployment makes an agent reachable on a channel.

- **Fields:** `agent_id`, `name`, `channel` (`web`, `sip`, or `api`, fixed at creation), `status`
  (`active`, `paused`, `archived`), `phone_number`, `configuration`.
- **Rules:** a `sip` deployment requires an E.164 `phone_number`; other channels must not have
  one. `archived` is terminal.
- **Endpoints:** `POST/GET /deployments`, `GET/PATCH/DELETE /deployments/{id}` (delete archives).
- Pass `deployment_id` to `POST /voice/sessions` to record the deployment and channel on the
  conversation. It must be active and belong to the same agent.

**Today:** the `web` path is what has a running client. Deployments tag conversations with a channel.
**Not yet:** nothing answers a phone number. `sip` and `api` deployments are records only.

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

**Today:** outcomes are stored and filterable through the API.
**Not yet:** nothing generates summaries with an LLM, and no call is actually transferred.
A handoff only records the intent.

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

## Campaigns and targets

A campaign groups outbound-call targets for an agent and a SIP deployment, with a schedule
window, timezone, and `max_attempts`. Targets have an E.164 phone number, optional name and
variables, and are deduplicated per campaign.

Campaign statuses: `draft → scheduled → running ⇄ paused → completed`, and any non-terminal
state can go to `cancelled`. Scheduling needs an active SIP deployment and at least one target.

- **Endpoints:** `POST/GET /campaigns`, `GET/PATCH /campaigns/{id}`, `POST /campaigns/{id}/status`,
  `POST/GET /campaigns/{id}/targets`.

**Today:** durable records and validated status transitions.
**Not yet:** there is no dialer. Setting a campaign to `running` places no calls; targets stay
`pending`.

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
