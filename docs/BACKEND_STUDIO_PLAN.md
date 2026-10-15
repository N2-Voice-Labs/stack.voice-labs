# Backend Milestone 8 — Voice Studio, Deployments, and Calls

Status: implemented in staged backend (frontend untouched)

This milestone turns the platform model from "Agent = everything" into reusable
**Voice → Agent → Deployment → Call** objects. It was explicitly approved as a new
milestone ahead of the open real-provider acceptance gates in `BACKEND_MVP.md`; those
gates stay open and nothing here claims provider behavior.

```text
Voice (library / clone / design)  ─┐
Knowledge documents ──────────────┼─→ Agent ─→ Deployment (web / sip / api) ─→ Conversation (call)
Tools ────────────────────────────┘                                   │            │
                                                Campaign → targets ───┘     outcome, handoff, analytics
```

## Boundaries

- Platform stores durable metadata only. It does not process audio, store raw voice
  samples, or call clone/design provider APIs in this milestone. Voice samples are
  referenced by `sample_reference` (an external storage URI).
- Provider provisioning (clone/design jobs), TTS previews, PSTN dialing, SIP transfer,
  embeddings, and outcome summarization by an LLM are **deferred**; the platform records
  the state those workers will drive.
- Voice cloning is consent-based: a clone request without an explicit consent
  attestation is rejected, and consent/provenance metadata is kept with the voice.
- Configuration JSON on new objects reuses the existing secret-key rejection; secrets use
  references only.
- Runtime changes are limited to accepting the new event types it may emit.

## Tasks

### Wave 1 — data model (sequential)

- [x] **VS-001** Models and Alembic migration `0004_voice_studio`:
  `voices`, `deployments`, `campaigns`, `campaign_targets`, `tools`, `agent_tools`,
  `knowledge_documents`, `agent_knowledge_documents`; `agents.voice_profile_id`;
  `conversations.deployment_id`, `channel`, `outcome`, `summary`, `intent`, `actions`,
  `outcome_recorded_at`. Upgrade and downgrade both work.
- [x] **VS-002** Shared validation helpers (secret-key rejection, E.164 phone numbers)
  in a module the routers can import without importing `main`.

### Wave 2 — independent routers (parallel, one module each)

- [x] **VS-010 Voices** `src/platform/voices.py`
  - `POST /voices` (library voice: TTS provider + provider voice ID, created `ready`).
  - `POST /voices/clone` — requires `consent` (`confirmed: true`, `subject_name`,
    `statement`, `method: self|authorized`) and `sample_reference`; created `pending`.
    Missing/false consent → `422 voice_consent_required`.
  - `POST /voices/design` — natural-language `design_prompt` plus style attributes;
    created `pending`.
  - `GET /voices`, `GET /voices/{id}`, `PATCH /voices/{id}` (name, languages, style),
    `POST /voices/{id}/status` (validated transitions: `pending→processing→ready|failed`,
    `failed→pending`, `ready↔disabled`; `ready` requires a provider voice ID),
    `DELETE /voices/{id}` (soft disable).
  - Style attributes: `energy`, `warmth`, `speed` in `[0, 1]`, `style` label.
- [x] **VS-011 Deployments** `src/platform/deployments.py`
  - `channel: web|sip|api`, `status: active|paused|archived`, configuration JSON;
    `sip` requires an E.164 `phone_number`. CRUD with agent validation.
- [x] **VS-012 Campaigns** `src/platform/campaigns.py`
  - Campaign (agent, sip deployment, schedule window, timezone, status) and targets
    (E.164 phone, name, variables; deduplicated per campaign; ≤1000 per request).
  - Status transitions `draft→scheduled→running⇄paused→completed`, any non-terminal →
    `cancelled`. Scheduling requires an active SIP deployment and at least one target.
  - Per-target status and attempts; no dialer.
- [x] **VS-013 Tools** `src/platform/tools.py` (covers BE-050)
  - Tool (name unique, description, JSON input schema, type, configuration, enabled);
    `PUT /agents/{id}/tools` replaces the agent's enabled tool set.
- [x] **VS-014 Knowledge** `src/platform/knowledge.py` (storage part of BE-065)
  - Text documents (title, source, content, metadata, version bumped on content change);
    `PUT /agents/{id}/knowledge` assigns documents. No chunking or embeddings yet.
- [x] **VS-015 Agent templates** `src/platform/templates.py`
  - Static persona templates (support, sales, receptionist, booking, restaurant,
    travel); `GET /agent-templates`, `POST /agent-templates/{key}/agents` with overrides.

### Wave 3 — integration (sequential, touches `main.py`)

- [x] **VS-020** Wire routers. Agent create/update validates `voice_profile_id`.
- [x] **VS-021** Session creation resolves the agent's voice profile (must be `ready` →
  `409 selected_voice_unavailable`) into the runtime contract `voice_id`, falling back to
  the legacy `agent.voice_id`; accepts optional `deployment_id` (active, same agent) and
  records deployment/channel on the conversation.
- [x] **VS-022** Runtime events `ToolCalled`, `HandoffRequested`, `OutcomeRecorded`
  accepted by Platform and declared in Runtime's event type. `HandoffRequested` sets
  outcome `escalated`; `OutcomeRecorded` sets outcome/summary/intent/actions.
- [x] **VS-023** `PUT /conversations/{id}/outcome` and outcome fields on conversation
  reads; `GET /conversations` filters by `agent_id`, `status`, `outcome`.
  Outcomes: `resolved`, `booked`, `callback_requested`, `no_answer`, `declined`,
  `escalated`, `failed`, `other`.
- [x] **VS-024** `GET /analytics/summary` (optional `agent_id`, `since`): conversation
  counts by status/outcome/channel, message language distribution, and per-stage latency
  p50/p95 from `LatencyMeasured` events.

### Wave 4 — documentation and verification

- [x] **VS-030** Update `contracts.md`, `BACKEND_TASKS.md`, `PROGRESS.md`, and docs nav.
- [x] **VS-031** Platform, Runtime, and stack acceptance suites pass; migration
  upgrade/downgrade verified against PostgreSQL when the local Compose database is
  available (otherwise recorded as unverified).

## Deferred

Voice provisioning workers (clone/design via provider APIs), voice preview synthesis,
sample upload storage, outbound dialer and call queue, SIP transfer for handoff,
pgvector retrieval, LLM call summaries, dubbing, audiobook features, authorization and
multi-tenancy (BE-070).
