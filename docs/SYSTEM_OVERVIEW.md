# System overview

What Voice Labs is today, what it can do, how the parts fit together, and which open-source
projects and services it is built on. Status as of 2026-10-18.

## What it is

Voice Labs is a platform for real-time voice AI agents that understand and speak more than
one language, including callers who mix languages in one sentence (English–Russian first;
Korean added through translation). You create a voice, give an agent instructions, tools and
knowledge, put it on the web or a phone line, and review every call afterwards. The same
runtime can also act as a live interpreter between two people.

## Architecture

```text
 Browser (Next.js)                         Phone (SIP, behind configuration)
      │ WebRTC audio                              │
      ▼                                           ▼
 ┌────────────────────────── LiveKit (media server) ──────────────────────────┐
 └───────────────────────────────────▲────────────────────────────────────────┘
                                     │ joins the room, streams audio both ways
 ┌───────────────────────────────────┴────────────────────────────────────────┐
 │ Runtime (FastAPI + Pipecat)                                                │
 │   Silero VAD → Smart Turn → Deepgram STT → OpenAI LLM (+tools) → Cartesia  │
 │   or: interpreter pipelines (cascaded / OpenAI realtime / two speakers)    │
 └──────────────┬──────────────────────────────────────────▲──────────────────┘
                │ authenticated, versioned events           │ session contract
                ▼                                           │
 ┌──────────────────────────────────────────────────────────┴─────────────────┐
 │ Platform (FastAPI + SQLAlchemy) ── PostgreSQL                              │
 │   agents, voices, deployments, campaigns, tools, knowledge, conversations, │
 │   outcomes, analytics. Never touches audio.                                │
 └────────────────────────────────────────────────────────────────────────────┘
```

- **Platform** is the control plane and source of truth. It validates requests, stores
  everything durable, issues short-lived LiveKit tokens and hands each call to Runtime as a
  *session contract* (agent prompt, voice, providers, tools, mode, languages).
- **Runtime** runs each live call as a Pipecat pipeline inside a LiveKit room and reports
  back events: speech start/stop, transcripts with languages, latency, tool calls,
  outcomes, handoffs. Events carry an ID and schema version and are stored once even if
  Runtime retries.
- **LiveKit** carries real-time audio (WebRTC for browsers, SIP for phones).
- **Web app** (Next.js) is the user interface; it calls Platform and joins LiveKit.

Services authenticate with a shared runtime token (`X-Runtime-Token`). Provider API keys live
only in environment configuration, never in the database or API responses.

## Repositories

| Repository | Contents |
| --- | --- |
| `stack.voice-labs` | Docker Compose (PostgreSQL, Valkey, LiveKit), shared `.env`, this documentation site, cross-service acceptance tests |
| `backend.voice-labs` | `platform/` (control-plane API), `runtime/` (voice pipelines), `evals/` (WER and terminology metrics) |
| `frontend.voice-labs` | Next.js web app, deployed to Cloudflare Workers |

## Features

✅ verified with real providers · 🧪 implemented and covered by automated tests only ·
⏳ planned

### Conversational agents

| Feature | Status | Notes |
| --- | --- | --- |
| Talk to an agent in the browser | ✅ | Speech → text → LLM → speech; reply in about 1.65 s |
| English, Russian and mixed speech | ✅ | Deepgram multilingual mode; messages store `primary_language` and `detected_languages` |
| Interruptions (barge-in) | ✅ | The agent stops speaking when the caller talks |
| Agent templates | ✅ | Support, sales, receptionist, booking, restaurant, travel |
| Tools during calls | 🧪 | HTTP tools plus built-ins `record_outcome`, `transfer_to_human`, `search_knowledge` |
| Knowledge documents | 🧪 | Keyword search over assigned documents (no embeddings yet) |
| Call outcomes and handoff | 🧪 | Outcome, summary, intent, actions per conversation |
| Agent + translator | ✅ | Agent thinks in English, caller hears Russian/Korean; 1.9 s p50 |

### Voices

| Feature | Status | Notes |
| --- | --- | --- |
| Voice library | ✅ | Reusable voices shared by agents |
| Voice preview | ✅ | Type text, hear the voice (Cartesia) |
| Consent-gated cloning | 🧪 | Clone from a public `https://` sample with a recorded consent statement |
| Voice design (from a description) | ⏳ | Stored only; no provider generates it yet |
| Live self-clone during a call | ⏳ | Proposed: clone your own voice from your first seconds of speech |

### Live translation (interpreter mode)

| Feature | Status | Notes |
| --- | --- | --- |
| Interpreter, cascaded engine | ✅ | STT → translation → TTS; EN ↔ RU auto direction; 1.47 s after the speaker stops |
| Interpreter, realtime engine | ✅ | OpenAI `gpt-realtime-translate`; starts 0.96 s after the speaker starts; one-way, provider voice |
| Two speakers, each in their own language and voice | ✅ | Per-person speech lanes; Korean ↔ English verified, 0.8–1.4 s |
| Phone interpreter (bridge two numbers) | 🧪 | Needs a SIP trunk |

### Deployments, phone and operations

| Feature | Status | Notes |
| --- | --- | --- |
| Deployments (web, SIP, API) | ✅ web / 🧪 SIP | Channel recorded on every conversation |
| Outbound campaign dialing | 🧪 | Off until `LIVEKIT_SIP_TRUNK_ID` is set |
| Transfer to a human | 🧪 | LiveKit SIP transfer to the deployment's `transfer_to` |
| Analytics | ✅ | Counts by outcome/channel/language; STT, LLM, TTS and translation latency p50/p95 |
| User accounts and login | ⏳ | Required before public deployment |
| Cloud deployment of the backend | ⏳ | Planned: Cloudflare Containers + LiveKit Cloud |

## How the pieces are integrated

### A normal call

1. The web app calls `POST /voice/sessions`. Platform checks the agent, its voice and
   deployment, creates the conversation, signs a LiveKit token and posts the session
   contract to Runtime.
2. The browser joins the LiveKit room; Runtime joins the same room.
3. Runtime's Pipecat pipeline: **Silero VAD** detects speech, **Smart Turn** decides when the
   caller has finished, **Deepgram** transcribes, **OpenAI** replies (calling tools if
   needed), **Cartesia** speaks, LiveKit plays it to the caller.
4. Runtime posts events to `POST /runtime/events`; Platform stores transcripts, session state,
   outcomes and latency, which feed conversation history and analytics.

### Runtime pipelines

| Mode | Pipeline |
| --- | --- |
| Agent | VAD → STT → user turn → LLM (+tools) → TTS |
| Agent + translator | STT → inbound translation → LLM → outbound translation → TTS |
| Interpreter, cascaded | VAD → STT → turn buffer → streaming translation → TTS in target language |
| Interpreter, two speakers | One VAD + STT lane per person → translation into the other person's language → TTS in the speaker's voice |
| Interpreter, realtime | Audio streamed to OpenAI `gpt-realtime-translate`; translated audio played back as it arrives |

Notable engineering details:

- **Streaming translation.** Translations are spoken sentence by sentence while the model is
  still writing, which cut the interpreter delay from 1.82 s to 1.47 s.
- **Per-person resampling.** Pipecat's LiveKit input converted every participant's audio
  through one shared resampler, which leaked one person's speech into the other's lane.
  Runtime now resamples each participant separately.
- **Silence-aware latency.** OpenAI's realtime engine streams silence before speech; latency
  is measured from the first audible chunk, not the first chunk.
- **Safe sample download.** Voice samples are fetched only from public `https://` hosts;
  private, loopback, link-local and carrier-grade NAT addresses are refused, and the
  validated address is pinned to prevent DNS rebinding.

## Open-source projects we use

| Project | Version in use | What it does here |
| --- | --- | --- |
| [Pipecat](https://github.com/pipecat-ai/pipecat) | 1.12.0 | Real-time voice pipeline: frames, VAD, turn handling, STT/LLM/TTS services, interruptions |
| [LiveKit](https://github.com/livekit/livekit) server, Python SDK, `livekit-api` | server `latest`, SDK 1.1.20, API 1.2.1 | WebRTC media, rooms, tokens, SIP dialing and transfer |
| [Silero VAD](https://github.com/snakers4/silero-vad) | via Pipecat | Detects when someone is speaking |
| [Smart Turn](https://github.com/pipecat-ai/smart-turn) | v3 via Pipecat | Decides when a speaker has finished their turn |
| [ONNX Runtime](https://github.com/microsoft/onnxruntime) | 1.24.4 | Runs the VAD and turn models on CPU |
| [FastAPI](https://github.com/fastapi/fastapi) | 0.143.1 | Platform and Runtime HTTP APIs |
| [Pydantic](https://github.com/pydantic/pydantic) | 2.14.1 | Request validation and settings |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.54.0 | ASGI server |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | 2.1.4 | Database models and queries |
| [Alembic](https://github.com/sqlalchemy/alembic) | 1.20.0 | Database migrations (`0001`–`0006`) |
| [psycopg](https://github.com/psycopg/psycopg) | 3.3.6 | PostgreSQL driver |
| [HTTPX](https://github.com/encode/httpx) | 0.28.1 | Service-to-service and provider HTTP calls |
| [websockets](https://github.com/python-websockets/websockets) | 17.2 | OpenAI realtime translation connection |
| [PostgreSQL](https://www.postgresql.org) | 16 | Primary database |
| [Valkey](https://github.com/valkey-io/valkey) | 8 | Cache / session state (provisioned, not yet used by the code) |
| [Next.js](https://github.com/vercel/next.js) + [React](https://github.com/facebook/react) | 16.3.8 | Web app |
| [livekit-client](https://github.com/livekit/client-sdk-js) | latest | Browser audio connection |
| [OpenNext for Cloudflare](https://github.com/opennextjs/opennextjs-cloudflare) | 1.20 | Deploys the web app to Cloudflare Workers |
| [Vitest](https://github.com/vitest-dev/vitest), [Playwright](https://github.com/microsoft/playwright), [pytest](https://github.com/pytest-dev/pytest) | — | Frontend, browser and backend tests |
| [Zensical](https://zensical.org) | — | This documentation site |
| [Docker Compose](https://docs.docker.com/compose/) / [Colima](https://github.com/abiosoft/colima) | — | Local infrastructure |

Versions are the ones installed in the local development environment; dependency ranges are
in each `pyproject.toml` and `package.json`.

## External services (paid APIs)

| Service | Used for | Models / settings |
| --- | --- | --- |
| [Deepgram](https://deepgram.com) | Speech-to-text | Nova-3, `multi` for EN/RU code-switching, fixed language for others (e.g. Korean) |
| [OpenAI](https://platform.openai.com) | Agent replies, translation, realtime interpretation | `gpt-4.1` (agent default), `gpt-4.1-mini` / `gpt-4.1-nano` (translation), `gpt-realtime-translate` |
| [Cartesia](https://cartesia.ai) | Text-to-speech, voice preview, voice cloning | `sonic-3.6`, multilingual voices |
| [Cloudflare Workers](https://workers.cloudflare.com) | Hosting the web app | — |

Providers sit behind interfaces, so they can be swapped for self-hosted options (e.g.
Qwen3-ASR, Chatterbox, models served with vLLM) once benchmarks justify it.

## Quality and testing

| Suite | Result |
| --- | --- |
| Platform (API, validation, migrations) | 235 passed |
| Runtime (pipelines, translation, events, tools, SIP) | 293 passed |
| Cross-service acceptance (Platform → Runtime → LiveKit) | passing |
| Real-provider checks | Agent reply, voice preview, latency, all interpreter modes, agent + translator |

Measured latency (end of speech → first audio unless noted):

| Mode | p50 |
| --- | --- |
| Agent | ~1.65 s |
| Interpreter, cascaded | 1.47 s |
| Interpreter, two speakers | 0.8–1.4 s |
| Interpreter, realtime | 0.96 s after the speaker *starts* |
| Agent + translator | 1.9 s |

## Not done yet

- User authentication and authorization (required before any public deployment).
- Cloud deployment of Platform and Runtime.
- Frontend screens for voices, deployments, campaigns, tools, knowledge, interpreter setup.
- Real SIP trunk testing (dialing, transfer, phone interpreter).
- Voice cloning against real Cartesia with a consented recording; live self-clone.
- Embedding-based knowledge search; evaluation benchmark results (WER, code-switch WER).
- Per-listener audio routing in two-person calls (today everyone hears all audio).

See the plans for details: [Studio](BACKEND_STUDIO_PLAN.md), [Live](BACKEND_LIVE_PLAN.md),
[Translation](BACKEND_TRANSLATE_PLAN.md). To run everything locally, follow the
[team guide](run-locally.md).
