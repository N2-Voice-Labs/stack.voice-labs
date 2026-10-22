# Voice Labs

Voice Labs is a platform for building **real-time, multilingual voice AI agents**. The idea:

1. **Create a voice.** Pick a library voice, or register a consent-gated clone or designed voice.
2. **Configure an agent.** Give it instructions, language settings, a voice, and (soon) tools and knowledge.
3. **Deploy it.** Define web, phone (SIP), or API deployments. Today only web has a working client; SIP and API are records.
4. **Monitor calls.** Review transcripts, outcomes, handoffs, and analytics.

The core differentiator is **English/Russian code-switching**: callers who switch languages
between or inside sentences. Initial language work covers English, Russian, and mixed
English/Russian. Other languages (Korean, Kyrgyz, Kazakh) are deferred until the first
vertical slice is measured.

## How a call works

```text
Browser mic
   │  WebRTC
   ▼
LiveKit  ◄──── Platform issues a short-lived room token
   │
   ▼
Runtime (Pipecat pipeline)
   Silero VAD + Smart Turn  →  Deepgram STT  →  OpenAI LLM  →  Cartesia TTS
   │                                                              │
   │ audio back through LiveKit to the browser  ◄─────────────────┘
   │
   └─ lifecycle and transcript events (HTTP/JSON, authenticated)
         ▼
      Platform  →  PostgreSQL (conversations, messages, session state)
```

- **Platform** (FastAPI) is the control plane and durable source of truth. It never touches audio.
- **Runtime** owns the live session: LiveKit, the Pipecat pipeline, VAD, turn detection, and
  barge-in (interruptions).
- Runtime reports events to Platform. Platform stores each event once (idempotent by event ID).

See [Concepts](concepts.md) for the object model and [Contracts](contracts.md) for API details.

## The three repositories

| Repository | Owns |
| --- | --- |
| `stack.voice-labs` (this repo) | Docker Compose (PostgreSQL, Valkey, LiveKit), shared `.env`, this docs site, cross-service acceptance tests |
| `backend.voice-labs` | `platform/` (control-plane API), `runtime/` (live voice pipeline), `evals/` (evaluation tooling) in one uv workspace |
| `frontend.voice-labs` | The Next.js web app (agent management, conversation history, Voice Playground) |

Compose starts infrastructure only. Platform, Runtime, and the web app run from their own repositories.

## Start here

| Page | Use it to |
| --- | --- |
| [System overview](SYSTEM_OVERVIEW.md) | Everything we have: features, architecture, open-source stack, status |
| [Run locally (team guide)](run-locally.md) | **Start here:** run the whole stack on your machine and talk to an agent |
| [Quickstart: API tour](quickstart-api.md) | Take a 5-minute API tour, no provider keys needed |
| [Quickstart: voice](quickstart-voice.md) | Talk to an agent with real speech |
| [Concepts](concepts.md) | Learn the Voice, Agent, Deployment, and Conversation model |
| [Development](development.md) | Run tests and work on the code |
| [Troubleshooting](troubleshooting.md) | Fix common setup and runtime problems |
| [Contracts](contracts.md) | Look up endpoints, events, and error codes |

## Architecture diagrams

<a href="architecture/c4.level.svg"><img src="architecture/c4.level.svg" alt="C4 Level 1: system context" width="100%"></a>

<a href="architecture/c4-container.svg"><img src="architecture/c4-container.svg" alt="C4 Level 2: container diagram" width="100%"></a>

## Current status

Last progress update: 2026-10-14 (see `PROGRESS.md` in this repo).

**Verified**

- Automated suites pass: Platform, Runtime, Evals, stack acceptance, frontend unit tests, and a Playwright browser suite.
- The LiveKit and Pipecat path works end to end with **stubbed** STT, LLM, and TTS: room handoff, audio frames, interruption, disconnect, recovery, and transcript persistence in PostgreSQL.
- Silero VAD detects speech during assistant playback in an optional browser test (STT still stubbed).
- Backend Milestone 8 (voices, deployments, campaigns, tools, knowledge, templates, outcomes, analytics) is implemented in Platform, with migration `0004_voice_studio` checked on PostgreSQL 16.

**Not yet verified**

- A full spoken turn with real Deepgram, OpenAI, and Cartesia credentials has **not** been recorded as passing. The opt-in real-provider test exists but has not been run.
- English, Russian, and code-switch evaluation results (WER, latency) are pending.
- Natural-speech quality, language detection, and latency are not established.

**Deferred**

- Voice cloning and design provider jobs, voice previews, and sample upload storage.
- Outbound dialing (campaigns record state only), SIP transfer for handoff, and phone call handling.
- Sending tools and knowledge to Runtime, plus retrieval (chunking, embeddings).
- LLM call summaries, authentication and multi-tenancy, and web UI for Milestone 8 features.
- Benchmarking open-source STT/LLM/TTS alternatives, and additional languages.
