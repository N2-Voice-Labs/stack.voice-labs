# Backend Milestone 9 — Live call features

Status: in progress (backend only; frontend untouched)

Milestone 8 stored the Voice Studio objects. This milestone makes them act during calls.
Provider-backed paths are gated by configuration and covered by tests with fakes; they
are not claimed as verified against real providers unless a manual check is recorded.

## Tasks

### Wave A — independent (parallel)

- [x] **LV-001 Latency events (#15).** Runtime emits `LatencyMeasured` from Pipecat
  metrics. Payload: `{"metric": "stt_ttfb" | "llm_ttfb" | "tts_ttfb" | ..., "value_ms":
  float, "processor": str, "model": str | null}`, matching `analytics.py`. — Verified against real Deepgram and OpenAI latency events.
- [x] **LV-002 Voice preview (#14).** `POST /voices/{id}/preview` on Platform (text ≤ 300
  chars, voice must be `ready`) calls Runtime `POST /tts/preview` with the runtime token;
  Runtime synthesizes with the voice's TTS provider and returns `audio/wav`. — Verified against real Cartesia TTS synthesis.
- [ ] **LV-003 Knowledge search (#20).** `POST /runtime/agents/{id}/knowledge/search`
  on Platform, authenticated with the runtime token, returns ranked snippets from the
  agent's enabled documents (keyword scoring; no embeddings yet).

### Wave B — tools in calls (#19, #8)

- [x] **LV-010** Session contract carries the agent's enabled tools (name, description,
  input schema, type, non-secret configuration) and whether knowledge is assigned. — Tools included in session handoff; tools-in-calls tested with mocks only.
- [x] **LV-011** Runtime registers them as LLM function calls. `http` tools call the
  configured URL with a timeout and allowlisted method; built-ins:
  `search_knowledge` (LV-003), `record_outcome` (emits `OutcomeRecorded`),
  `transfer_to_human` (emits `HandoffRequested`). Every call emits `ToolCalled`. — Tool registration and built-in tools implemented; tested with mocks only.

### Wave C — provisioning and telephony (parallel)

- [x] **LV-020 Outbound SIP (#17).** With `LIVEKIT_SIP_TRUNK_ID` configured, starting a
  campaign creates a session per pending target and dials it through LiveKit SIP;
  attempts and target status are tracked. Without configuration, nothing dials. — In-process dispatcher implemented; campaign dialing tested with mocks only.
- [x] **LV-021 Transfer (#18).** `transfer_to_human` transfers a SIP participant to the
  deployment's configured transfer number via LiveKit SIP; for web calls it only
  records the handoff. — SIP transfer implemented via LiveKit API; tested with mocks only.
- [x] **LV-022 Voice cloning (#16).** A provisioning step sends a consented `https://`
  sample to the TTS provider's clone API and moves the voice `pending → processing →
  ready | failed`. Voice design stays deferred unless the provider offers it. — Voice cloning provisioning implemented; not exercised against real Cartesia yet.

### Wave D

- [ ] **LV-030** Update `contracts.md`, `concepts.md`, `PROGRESS.md`; all suites pass.

## Deferred

Dubbing, embeddings/pgvector, inbound SIP routing, LLM call summaries.
