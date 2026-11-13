# System overview

> **UNAI** (formerly Voice Labs) is a B2B AI communication platform: AI voice agents (primary), real-time translation, AI chatbots and developer APIs. First market: university admissions offices. First MVP: the AI Admissions Assistant for international students at Inha University. Calls run in the browser over WebRTC (LiveKit); telephone/SIP calling is deferred.

UNAI is Voice Labs renamed and repositioned as an industry-neutral B2B AI Communication Platform. This page describes the platform, architecture and existing capabilities. Last reviewed 2026-11-11. The evidence marks below are a
summary; the maintained status is [Status](https://github.com/N2-Voice-Labs/backend.voice-labs/blob/main/docs/status.md) and the current goal is
[Goal](https://github.com/N2-Voice-Labs/backend.voice-labs/blob/main/docs/goal.md).

## What it is

UNAI is a B2B AI Communication Platform (AI-as-a-Service): AI voice agents are primary, supported by real-time translation, secondary AI chatbots and developer APIs. The first target market is university admissions, with an Inha University international-student admissions assistant MVP. The MVP uses browser WebRTC through LiveKit; phone and SIP deployments are deferred. The platform stays industry-neutral, and institution knowledge and prompts live in agent data.

## Architecture

```text
 Browser (Next.js)                         Deferred phone (SIP) path
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
| `frontend` | Next.js web app, deployed to Cloudflare Workers |

## Features

✅ verified with real providers · 🧪 implemented and covered by automated tests only ·
⏳ planned

### Conversational agents

| Feature | Status | Notes |
| --- | --- | --- |
| Talk to an agent in the browser | ✅ (2026-10) | Speech → text → LLM → speech; reply in about 1.65 s; not re-run on current code |
| English, Russian and mixed speech | ✅ | Deepgram multilingual mode; messages store `primary_language` and `detected_languages` |
| Interruptions (barge-in) | 🧪 | The agent stops speaking when the caller talks; time to stop not measured |
| Agent templates | ✅ | Support, sales, receptionist, booking, restaurant, travel |
| Tools during calls | 🧪 | HTTP tools plus built-ins `record_outcome`, `transfer_to_human`, `search_knowledge` |
| Knowledge documents | 🧪 | Keyword search over assigned documents (no embeddings yet) |
| Call outcomes and handoff | 🧪 | Outcome, summary, intent, actions per conversation |
| Agent + translator | ✅ | Agent thinks in English, caller hears Russian/Korean; 1.9 s p50 |

### Voices

| Feature | Status | Notes |
| --- | --- | --- |
| Voice library | ✅ | Reusable voices shared by agents |
| Voice preview | ✅ | Type text, hear the voice (Cartesia and ElevenLabs verified against the real APIs) |
| Consent-gated cloning | 🧪 | Clone from a public `https://` sample with a recorded consent statement |
| Voice design (from a description) | ⏳ | Stored only; no provider generates it yet |
| Live self-clone during a call | ⏳ | Proposed: clone your own voice from your first seconds of speech |

### Live translation (interpreter mode)

| Feature | Status | Notes |
| --- | --- | --- |
| Interpreter, cascaded engine | ✅ | STT → translation → TTS; EN ↔ RU auto direction; 1.47 s after the speaker stops |
| Interpreter, realtime engine | ✅ | OpenAI `gpt-realtime-translate`; starts 0.96 s after the speaker starts; one-way, provider voice |
| Two speakers, each in their own language and voice | 🧪 | Per-person speech lanes; ✅ Korean ↔ English 0.8–1.4 s on 2026-10-18, routing rebuilt since and not re-measured |
| Translated call by shareable link (`/calls`, `POST /translations`) | ✅ one call (2026-11-07) | Two phones, English → Korean, ElevenLabs STT/TTS + Google Translation; 1.29 s median over 37 recorded sentences |
| Phone interpreter (bridge two numbers) | 🧪 | Needs a SIP trunk |

### Deployments, phone and operations

| Feature | Status | Notes |
| --- | --- | --- |
| Deployments (web, SIP, API) | ✅ web / 🧪 SIP | Channel recorded on every conversation |
| Outbound campaign dialing | 🧪 | Off until `LIVEKIT_SIP_TRUNK_ID` is set |
| Transfer to a human | 🧪 | LiveKit SIP transfer to the deployment's `transfer_to` |
| Analytics | ✅ | Counts by outcome/channel/language; STT, LLM, TTS and translation latency p50/p95 |
| API keys with roles, session tokens | ✅ | Organization keys, roles, per-call tokens, stored hashed |
| Login UI | ⏳ | |
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
| [Alembic](https://github.com/sqlalchemy/alembic) | 1.20.0 | Database migrations (`0001`–`0014`) |
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
| [ElevenLabs](https://elevenlabs.io) | Speech-to-text (realtime) and text-to-speech (live, preview); no cloning | `eleven_flash_v2_5` by default |
| [Google Cloud Translation](https://cloud.google.com/translate) | Sentence translation in translation sessions | Gemini (OpenAI-compatible endpoint) as fallback |
| [Cloudflare Workers](https://workers.cloudflare.com) | Hosting the web app | — |

Providers sit behind interfaces, so they can be swapped for self-hosted options (e.g.
Qwen3-ASR, Chatterbox, models served with vLLM) once benchmarks justify it.

## Quality and testing

Run the suites with the commands in the backend `README.md` (Checks). The last recorded counts
and every real-provider run, with dates, are in [Status](https://github.com/N2-Voice-Labs/backend.voice-labs/blob/main/docs/status.md).

Measured latency (end of speech → first audio unless noted):

| Mode | p50 |
| --- | --- |
| Agent | ~1.65 s |
| Interpreter, cascaded | 1.47 s |
| Interpreter, two speakers | 0.8–1.4 s (2026-10-18, older routing) |
| Translated call by link | 1.29 s (2026-11-06, 37 recordings) |
| Interpreter, realtime | 0.96 s after the speaker *starts* |
| Agent + translator | 1.9 s |

## Not done yet

- Agent tools, knowledge, interruption and handoff verified with real providers (see [Goal](https://github.com/N2-Voice-Labs/backend.voice-labs/blob/main/docs/goal.md)).
- Cloud deployment of Platform and Runtime.
- Login UI for the web app.
- Real SIP trunk testing (dialing, transfer, phone interpreter).
- Voice cloning against real Cartesia with a consented recording.
- Embedding-based knowledge search; evaluation results on natural speech.

To run everything locally, follow the [team guide](run-locally.md).
