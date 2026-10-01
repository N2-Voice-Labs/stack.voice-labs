# Voice Labs Backend Architecture

Status: proposed

This document defines the first backend boundary for Voice Labs. It is intentionally small: the platform owns durable business state, while the runtime owns live audio execution.

## Services

```text
platform.voice-labs
    control plane and durable business state

runtime.voice-labs
    real-time voice execution
```

The workspace repository coordinates these projects under `src/` but does not become a third backend service.

## Responsibilities

### `platform.voice-labs`

- agent configuration and CRUD;
- provider configuration and provider selection;
- conversation and message persistence;
- voice-session creation and authorization;
- tool and knowledge metadata;
- transcript and latency-event ingestion;
- durable API contracts for web clients and the runtime.

The platform does not process audio or own a live Pipecat pipeline.

### `runtime.voice-labs`

- LiveKit connection and media handling;
- Pipecat pipeline orchestration;
- VAD and turn detection;
- streaming STT, LLM, and TTS execution;
- barge-in and cancellation;
- tool execution during a live session;
- per-stage timing and runtime events;
- final session handoff to the platform.

The runtime does not become the source of truth for agents, conversations, or provider configuration.

## Runtime/platform event transport

The first implementation uses authenticated HTTP with JSON between the runtime and the platform. The runtime emits transcript, timing, tool, and lifecycle events to an internal platform API; the platform validates and persists the durable results.

The event schema is transport-independent so a message bus can be introduced later without changing the domain contract. Kafka, NATS, RabbitMQ, and similar infrastructure are out of scope for the first implementation.

## Request and event flow

```text
Web client
    │
    │ create session
    ▼
Platform API ── Agent / provider / conversation state ── PostgreSQL
    │
    │ LiveKit room and token
    ▼
LiveKit
    │
    ▼
Runtime
    ├── Pipecat
    ├── Silero VAD
    ├── Smart Turn
    ├── STTProvider
    ├── LLMProvider
    ├── ToolRegistry
    └── TTSProvider
    │
    ├── audio through LiveKit to the client
    └── transcript/events/latencies to the platform
```

## Initial domain model

The first durable model contains only the following entities:

| Entity | Purpose |
| --- | --- |
| `Agent` | Instructions, language policy, selected providers, and voice configuration |
| `ProviderConfig` | A named STT, LLM, or TTS provider configuration |
| `Conversation` | Durable historical record for one agent interaction |
| `Message` | User, assistant, tool, or system transcript entry |
| `VoiceSession` | Durable platform record for one live realtime connection belonging to a conversation |
| `Tool` | Tool metadata, input schema, and execution configuration |
| `AgentTool` | Association between an agent and an enabled tool |
| `KnowledgeDocument` | Source content available to retrieval and grounding |

Do not add billing, workflow builders, phone numbers, organizations, roles, or a general analytics platform to the first vertical slice unless a concrete demo requirement makes one necessary.

## Provider boundaries

Runtime code must expose stable Voice Labs provider capabilities and selection rules without duplicating provider SDK behavior. Prefer native Pipecat integrations when they satisfy our requirements. Add a Voice Labs adapter only when Pipecat does not already provide the required integration or normalization.

The provider factory maps platform configuration to a native Pipecat provider or a focused Voice Labs adapter:

```text
Provider factory
├── native Pipecat provider
└── focused Voice Labs adapter when required

Voice Labs provider boundary
├── STTProvider
├── QwenASRProvider
├── FasterWhisperProvider
└── CloudSTTProvider

LLMProvider
└── OpenAICompatibleProvider

TTSProvider
├── ChatterboxProvider
└── CloudTTSProvider
```

The first candidates are Qwen3-ASR, faster-whisper, Chatterbox Multilingual, and an OpenAI-compatible endpoint such as vLLM. They remain experiments until the evaluation plan establishes accuracy, latency, and operational fit.

Providers declare capabilities instead of pretending every implementation supports every feature:

```text
ProviderCapabilities
    streaming
    language_detection
    code_switching
    word_timestamps
    confidence
    cancellation
    tool_calling
    voice_cloning
```

For example, Qwen ASR may declare multilingual support and streaming while marking code-switching as benchmark-required. A provider that lacks word timestamps must not be forced to emulate them.

## Infrastructure decisions

- LiveKit provides realtime media transport and rooms.
- Pipecat provides voice-pipeline orchestration.
- Silero VAD detects speech activity.
- Smart Turn helps determine whether a conversational turn is complete.
- PostgreSQL stores durable state.
- pgvector may be enabled in PostgreSQL for the first knowledge-retrieval implementation.
- Valkey stores cache and short-lived coordination state.
- OpenTelemetry, Prometheus, and Grafana provide instrumentation and monitoring.

We do not build our own WebRTC server, RTP router, VAD model, turn detector, inference server, vector database, cache server, or metrics system for the MVP.

## Session terminology and lifecycle

`VoiceSession` is the durable platform/domain entity. `RuntimeSession` is the live runtime object that owns one active pipeline. Keeping these names distinct prevents in-memory lifecycle state from being confused with the platform record.

```text
create → connect → listen → detect turn → transcribe → generate → speak
                                      ↑                         │
                                      └── interrupt / cancel ───┘
                                    ↓
                                     end → persist final state
```

Hot state such as audio buffers, cancellation tokens, active streams, and current turn state stays in the runtime process. Valkey is reserved for short-lived lookup, rate limits, cache, and future distributed coordination.

## Security and configuration rules

- Provider secrets must not be stored as raw values in ordinary JSON configuration.
- MVP configuration may reference environment-provided secrets.
- Session creation must authorize the requested agent before issuing connection credentials.
- Runtime-to-platform calls must authenticate as a service, not as an anonymous client.
- Logs and traces must not contain provider secrets, access tokens, or raw audio by default.
- Message language metadata must support mixed-language utterances. Use optional `primary_language` plus optional `detected_languages`; do not force one language value to represent every message.

## Consequences

This split keeps business state stable while the realtime implementation evolves. It also lets the runtime swap STT, LLM, or TTS providers without changing platform APIs. The tradeoff is an explicit service boundary and event contract between the two repositories; those contracts must be versioned and tested before the services are deployed independently.
