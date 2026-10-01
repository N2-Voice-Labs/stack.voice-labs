# Voice Labs Backend Tasks

Status: planned

This is the implementation backlog for the first backend milestone. Tasks are ordered by dependency. Check a task only when its acceptance criteria and tests are complete.

## Milestone 0 — workspace and contracts

- [ ] **BE-001** Confirm repository locations and ownership under `src/platform` and `src/runtime`.
  - Decide the exact Git submodule URLs and default branches.
  - Record the decision in the workspace documentation.
  - Do not add a third backend service.
- [ ] **BE-002** Bootstrap `platform.voice-labs` from `bybatkhuu/rest-fastapi-orm-template`.
  - Preserve the template's root layout and conventions.
  - Add a health endpoint, local configuration, migrations, and test command.
- [ ] **BE-003** Bootstrap `runtime.voice-labs` from `bybatkhuu/rest-fastapi-template`.
  - Preserve the template's root layout and conventions.
  - Add a health endpoint, local configuration, and test command.
- [ ] **BE-004** Add the two repositories as submodules under `src/platform` and `src/runtime`.
  - A fresh clone can initialize both submodules.
  - The workspace README explains the update workflow.
- [ ] **BE-005** Define the platform/runtime API and event contract.
  - Use authenticated HTTP/JSON from runtime to platform for V1.
  - Document session creation, runtime authentication, transcript events, latency events, tool events, and finalization.
  - Include IDs, timestamps, status values, error behavior, idempotency, and `schema_version`.
- [ ] **BE-006** Add local Docker Compose dependencies for PostgreSQL, Valkey, and LiveKit.
  - Services have health checks, persistent local volumes, and documented ports.
  - Secrets use `.env` or documented local defaults only.

## Milestone 1 — platform control plane

- [ ] **BE-010** Configure PostgreSQL and migrations in `platform.voice-labs`.
  - The application can connect using environment configuration.
  - Migration and rollback commands are documented.
- [ ] **BE-011** Implement the `Agent` model and repository/service layer.
  - Fields: identity, description, system prompt, enabled languages, provider references, voice ID, status, timestamps.
  - Validate referenced provider IDs and status transitions.
- [ ] **BE-012** Implement Agent CRUD API.
  - `POST /agents`
  - `GET /agents`
  - `GET /agents/{id}`
  - `PATCH /agents/{id}`
  - `DELETE /agents/{id}`
  - Add validation, pagination where the template expects it, and API tests.
- [ ] **BE-013** Implement `ProviderConfig`.
  - Support `stt`, `llm`, and `tts` kinds.
  - Store non-secret configuration and secret references separately.
  - Add enabled/disabled behavior and validation.
- [ ] **BE-014** Implement ProviderConfig API and tests.
  - Agents can reference enabled provider configurations.
  - API responses never expose secret values.
- [ ] **BE-015** Implement `Conversation` and `Message` persistence.
  - Support `user`, `assistant`, `tool`, and `system` roles.
  - Preserve optional `primary_language`, optional `detected_languages`, metadata, ordering, and timestamps.
- [ ] **BE-016** Implement conversation read APIs.
  - `GET /conversations`
  - `GET /conversations/{id}`
  - `GET /conversations/{id}/messages`
  - Add filtering by agent and status where useful for the first demo.
- [ ] **BE-017** Implement `VoiceSession` creation.
  - `POST /voice/sessions` accepts an agent ID.
  - Verify the agent is enabled.
  - Create or associate a conversation.
  - Return a session ID, conversation ID, LiveKit URL, and short-lived connection token.
- [ ] **BE-018** Implement runtime service authentication.
  - Authenticate runtime callbacks and event ingestion.
  - Reject invalid, expired, or incorrectly scoped credentials.
- [ ] **BE-019** Implement transcript and latency event ingestion.
  - Accept authenticated HTTP/JSON events with event ID and schema version.
  - Events are idempotent or safely deduplicated.
  - Invalid session IDs and malformed payloads have consistent errors.
- [ ] **BE-020** Implement session finalization.
  - Persist final status, end time, transcript metadata, and measured timings.
  - Repeated finalization does not corrupt the record.

## Milestone 2 — runtime foundation

- [ ] **BE-030** Add a runtime configuration loader.
  - Configure platform URL, LiveKit credentials, provider endpoints, timeouts, and observability.
  - Fail clearly when required configuration is missing.
- [ ] **BE-031** Add the `RuntimeSession` runtime object.
  - Own agent configuration, conversation context, transport, pipeline components, tool registry, and lifecycle state.
  - Keep it distinct from the platform's durable `VoiceSession` record.
  - Make valid states and shutdown behavior explicit.
- [ ] **BE-032** Integrate LiveKit transport.
  - Runtime can join the room returned by the platform.
  - Audio input and output are connected.
  - Connection failures and cleanup are tested.
- [ ] **BE-033** Integrate Pipecat in an isolated pipeline module.
  - Keep Pipecat-specific imports out of platform/domain code.
  - Add a minimal pipeline test or local smoke test.
- [ ] **BE-034** Add Silero VAD.
  - Emit speech-started and speech-stopped runtime events.
  - Record timestamps for each event.
- [ ] **BE-035** Add Smart Turn.
  - Emit turn-completed events.
  - Test natural pauses, short utterances, and false turn completion cases.
- [ ] **BE-036** Add runtime error and shutdown handling.
  - Disconnect transport, cancel streams, and finalize the session exactly once.
  - Report actionable errors to the platform without leaking secrets.

## Milestone 3 — provider adapters and first conversation

- [ ] **BE-040** Define the `STTProvider` interface.
  - Support streaming or incremental results, final results, flexible language metadata, confidence, and timing.
- [ ] **BE-040A** Define provider capability metadata.
  - Support declarations for streaming, language detection, code-switching, word timestamps, confidence, cancellation, tool calling, and voice cloning.
  - Provider selection validates required capabilities instead of assuming every provider supports every feature.
  - Prefer native Pipecat integrations; add a Voice Labs adapter only where Pipecat does not satisfy the requirement.
- [ ] **BE-041** Implement the first STT adapter.
  - Start with Qwen3-ASR or faster-whisper based on the evaluation environment.
  - Make the choice and limitations explicit in the experiment notes.
- [ ] **BE-042** Define the `LLMProvider` interface.
  - Support streaming tokens, cancellation, system context, conversation messages, and tool calls.
- [ ] **BE-043** Implement an OpenAI-compatible LLM adapter.
  - Support a local vLLM endpoint and a configurable external endpoint.
  - Add timeout, retry, and cancellation behavior.
- [ ] **BE-044** Define the `TTSProvider` interface.
  - Support streaming audio, language/voice selection, cancellation, and timing.
- [ ] **BE-045** Implement the first TTS adapter.
  - Start with Chatterbox Multilingual or the selected baseline.
  - Test Russian, English, Korean, and mixed-language output separately.
- [ ] **BE-046** Connect STT → LLM → TTS through the runtime pipeline.
  - A browser microphone can produce an audible response.
  - The system works without manually selecting the language for English/Russian test utterances.
- [ ] **BE-047** Persist the final transcript.
  - Runtime emits events; platform persists them.
  - User and assistant messages retain role, primary/detected language metadata, timestamps, and session/conversation IDs.
- [ ] **BE-048** Add barge-in.
  - Detect user speech while the agent speaks.
  - Cancel LLM/TTS work where possible.
  - Clear queued output audio.
  - Emit `UserInterrupted` and `AgentSpeechCancelled` events.

## Milestone 4 — first useful immigration agent

- [ ] **BE-050** Implement `Tool` and `AgentTool` persistence.
  - Store name, description, input schema, type, configuration, and enabled state.
- [ ] **BE-051** Implement the runtime `ToolRegistry`.
  - Register only tools enabled for the current agent.
  - Validate arguments against the declared schema.
  - Record tool calls and failures as messages/events.
- [ ] **BE-052** Implement `search_immigration_information`.
  - Define the input/output contract.
  - Return source references and a grounded answer context.
  - Handle no-result and source-unavailable cases.
- [ ] **BE-053** Connect the minimal immigration tool to the live session.
  - A voice question can retrieve official immigration information and produce a grounded response.

## Milestone 5 — observability and evaluation

- [ ] **BE-060** Add OpenTelemetry traces.
  - Tag spans with session ID, conversation ID, agent ID, language metadata, provider, and trace ID.
  - Exclude secrets and raw audio by default.
- [ ] **BE-061** Measure per-stage timings.
  - Speech end → STT final.
  - STT final → LLM first token.
  - LLM first token → TTS first audio.
  - TTS first audio → playback started.
  - End-of-turn → first audio.
- [ ] **BE-062** Export Prometheus metrics and add a minimal Grafana dashboard.
  - Track request/session counts, failures, cancellations, latency percentiles, and provider labels.
- [ ] **BE-063** Consume the evaluation baseline from `evals.voice-labs`.
  - Depend on a versioned English/Russian code-switch dataset and benchmark report.
  - Record the dataset/model/provider version used by backend integration tests.
- [ ] **BE-064** Add automated conversation smoke tests.
  - Required documents, office hours, appointments, corrections, pauses, and interruption scenarios.

## Milestone 6 — knowledge retrieval

- [ ] **BE-065** Implement `KnowledgeDocument` storage and ingestion.
  - Store source, title, clean content, metadata, chunks, and version.
  - Preserve source attribution.
- [ ] **BE-066** Add PostgreSQL + pgvector retrieval.
  - Add embeddings only after the text/chunking contract is stable.
  - Evaluate exact and approximate search only when the dataset needs it.
- [ ] **BE-067** Connect full retrieval and tool calling to the live session.
  - Test that answers stay grounded in the available immigration sources.

## Milestone 7 — hardening and release readiness

- [ ] **BE-070** Add authorization checks for agents, sessions, conversations, and runtime callbacks.
- [ ] **BE-071** Add rate limits and bounded resource usage.
  - Cover session creation, concurrent sessions, tool calls, audio duration, and provider timeouts.
- [ ] **BE-072** Add retry, timeout, cancellation, and fallback policies per provider.
- [ ] **BE-073** Add structured logs and correlation IDs across platform, runtime, and LiveKit.
- [ ] **BE-074** Add database indexes based on measured query patterns.
- [ ] **BE-075** Add backup, migration, and rollback documentation for platform data.
- [ ] **BE-076** Run failure tests.
  - Provider unavailable, LiveKit disconnect, client disconnect, duplicate events, partial TTS, invalid tool arguments, and platform outage.
- [ ] **BE-077** Run the complete MVP acceptance checklist in `docs/BACKEND_MVP.md`.

## Explicitly out of scope for the first vertical slice

- billing and usage-based charging;
- multi-organization tenancy unless required by the demo;
- workflow builder;
- phone-number provisioning and PSTN/SIP production integration;
- custom WebRTC/media infrastructure;
- custom STT, TTS, VAD, turn-detection, LLM-serving, cache, or vector-database systems;
- a separate analytics platform;
- generalized integration marketplace.
