# Backend status: what we have and what is expected

Updated 2026-10-22. Backend only; the web app is not covered here. For the architecture see
[System overview](SYSTEM_OVERVIEW.md), and for the direction see the
[North Star plan](NORTH_STAR_PLAN.md).

**Legend:** ✅ works and was tested with real providers · 🧪 works in tests with mocks only ·
🟡 partly done · ⏳ planned · 🔒 blocked on something outside the code

## In one paragraph

Voice Labs has two backend services. The **Platform** (FastAPI, PostgreSQL) stores agents,
voices, conversations and settings, and hands each call a "session contract". The **Runtime**
(FastAPI, Pipecat, LiveKit) runs the live audio: it listens, translates, speaks and reports
events back. The Platform never touches audio. Today a browser caller can talk to a voice
agent, use live translation between two people, or use an agent that also translates for the
caller. Phone calls are written but have not been tried with a real phone line.

## What works today

### Voice agents

| Feature | Status | Notes |
| --- | --- | --- |
| Talk to an agent in a browser (speech in, speech out) | ✅ | Deepgram → OpenAI → Cartesia through LiveKit. About 1.65 s from the end of speech to the first reply audio. |
| Interruption (barge-in) in agent calls | ✅ | The agent stops when the caller speaks. Not yet measured. |
| Agent settings: prompt, language, model, voice, temperature | ✅ | Agent templates for quick starts. |
| Tools the agent can call (HTTP tools) | 🧪 | Run by Runtime with timeouts and logging; verified with mock servers. |
| Knowledge documents attached to an agent | 🧪 | Text is added to the agent's context. |
| Conversation outcomes, actions and filters | ✅ | Stored per conversation and filterable. |
| Transcripts and events | ✅ | Versioned, repeat-safe events from Runtime to Platform. |

### Live translation (interpreter mode)

| Feature | Status | Notes |
| --- | --- | --- |
| One speaker, translated speech back (step-by-step engine) | ✅ | Deepgram → OpenAI → Cartesia. 1.47 s after speech ends. |
| Realtime engine (OpenAI `gpt-realtime-translate`) | ✅ | One direction only, 13 output languages, provider voice. |
| Two people, each hearing only the other's translation | ✅ | Verified Korean ↔ English. Each person has their own speech lane, and the original microphones stay private. `hear_original` lets listeners also hear the original quietly. |
| Direction: `one_way` or `auto` | ✅ | `auto` works for the languages Deepgram can detect together (English, Spanish, French, German, Hindi, Russian, Portuguese, Japanese, Italian, Dutch). Korean pairs need `one_way`. |
| Latency modes: instant, balanced, accurate | ✅ | Different pause, chunk size and model. Instant uses the realtime engine for one-way calls. |
| Agent + translator (an English agent talking to a Russian caller) | ✅ | The agent works in one language and the caller speaks another. About 1.9 s. |
| Glossary (terms that must be translated a certain way, or kept) | ✅ | Per agent. "residence permit" now becomes "вид на жительство". Also sent to Deepgram to hear the terms better. Step-by-step engine only. |
| Voice cloning with consent | 🧪 | Only https samples, with checks against internal addresses, a 10 MB limit and a consent record. Tested with mocks, not with a real clone. |
| Voice preview | ✅ | Checked against real Cartesia. |

### Phone calls (SIP)

| Feature | Status | Notes |
| --- | --- | --- |
| Outbound calls, campaigns with targets, dial-next | 🧪 | Behind `LIVEKIT_SIP_TRUNK_ID`. Mocks only. |
| Bridge call and transfer to another number | 🧪 | Bridge needs the step-by-step engine with `auto`. |
| Phone ↔ browser and phone ↔ phone interpreter | 🔒 | Needs a SIP provider account (Twilio or Telnyx) and a phone number. |

### Platform API and safety

| Feature | Status | Notes |
| --- | --- | --- |
| Agents, providers, voices, deployments, conversations | ✅ | PostgreSQL with migrations up to `0007`. |
| API keys (`PLATFORM_API_KEYS`) and per-session tokens (`vls_…`) | ✅ | Off when no keys are set, so local development is unchanged. Tokens are stored hashed. |
| Runtime authentication (`X-Runtime-Token`) | ✅ | Platform and Runtime only accept each other. |
| CORS for the web app, localhost and the deployed site | ✅ | `PLATFORM_WEB_ORIGIN` takes a comma-separated list. |
| Analytics summary: conversations, languages, p50/p95 latency, timeline per engine | ✅ | `GET /analytics/summary`. |
| `/docs` and `/openapi.json` stay public when auth is on | 🟡 | Decision needed. |

### Provider flexibility

| Slot | Today | Swappable? |
| --- | --- | --- |
| Speech recognition (STT) | Deepgram nova-3 | ✅ registry; a second provider is NS-07 |
| Language model | OpenAI (gpt-4.1, mini, nano) and OpenAI-compatible APIs | ✅ registry |
| Voice output (TTS) | Cartesia sonic-3.6 | ✅ registry; ElevenLabs is NS-07 |
| Translation engine | step-by-step, realtime | ✅ registry |
| Realtime translation | OpenAI `gpt-realtime-translate` | ✅ same registry; Qwen is NS-07 |

The Cartesia key and voice fields still have Cartesia-specific names, and voice preview and
cloning are Cartesia-only. Both need to be generalised before ElevenLabs works end to end.

### Measuring and testing

| Feature | Status | Notes |
| --- | --- | --- |
| One timeline per translated utterance (speech start, voice detected, first transcript, translation start, first audio, stable playback) | ✅ | Emitted as `utterance_timeline` events. |
| Evaluation set: 140 synthetic items (EN↔KO, RU↔EN, mixed languages, names and numbers, domain terms, phone quality, interruptions) | ✅ | The reference translations still need a native Korean and Russian reviewer. |
| Quality scoring: word error rate, Korean character error rate, chrF, term recall | ✅ | `evals/`. |
| Live latency runner (`live_latency`) | ✅ | One command, p50/p95 per engine, mode and language pair, with a "where the time goes" table. |
| Tests | ✅ | Runtime 437, Platform 300, evals 55, stack acceptance 6 (+3 that need real keys). |

## Latest live measurements (2026-10-21, 30 sentences per row, one speaker)

Times are seconds after the speaker started, typical case (p50) and slow case (p95). Sentences
are about 3.3 s long, so step-by-step times include the speech itself.

| Engine and mode | Pair | Translation heard, p50 / p95 | After speech ends, p50 / p95 |
| --- | --- | --- | --- |
| Realtime, instant | KO→EN | 3.98 / 5.16 | 0.67 / 1.79 |
| Realtime, instant | EN→KO | 3.87 / 5.15 | 0.31 / 1.93 |
| Realtime, instant | RU→EN | 4.17 / 5.88 | 0.90 / 1.96 |
| Realtime, instant | EN→RU | 4.10 / 6.21 | 0.98 / 3.08 |
| Step-by-step, instant | KO→EN | 5.24 / 6.19 | 2.02 / 2.48 |
| Step-by-step, balanced | KO→EN | 4.86 / 6.42 | 1.96 / 2.45 |
| Step-by-step, accurate | KO→EN | 5.71 / 6.67 | 2.28 / 2.70 |

Other pairs are within about half a second of these. Full tables are in the run reports.

**What this tells us**

- Nothing meets the targets yet (realtime ≤ 1.2 s from speech start, step-by-step ≤ 1.5 s
  after speech ends). Korean is not specifically worse than Russian.
- **Step-by-step:** the translation request starts about 0.3–0.5 s after the speaker
  finishes, and the first audio arrives about 1.0–1.3 s after that. More time goes to
  waiting for the end of the sentence and to translation plus voice than to recognising speech.
- **Realtime:** the first audio arrives at roughly the end of the sentence, not during it. An
  earlier hand test reached 0.79 s from speech start. The two disagree, and the difference
  (speech style, how the audio is paced, or the model's behaviour) is not explained yet. Find
  out why before tuning anything.
- **Accurate mode lost most Russian sentences:** 26 of 30 for RU→EN and all 30 for EN→RU
  were never heard. The cause is not found. It is a real bug or limit to investigate, not a
  result.
- These came from synthetic voices played into a LiveKit room on this machine, so they include
  local network and playout time. Real microphones and phone audio will differ.

## What is expected next

Order follows the [North Star plan](NORTH_STAR_PLAN.md). The first proof is a Korean speaker
in a browser and an English speaker on a phone, talking to each other live.

| Next | What it adds | Needs |
| --- | --- | --- |
| **Investigate the benchmark** | Explain the realtime gap and the accurate-mode misses; rerun with the same command. | nothing |
| **NS-02 Interruption policy** | When someone keeps talking, the old translation finishes and the new one queues. When the listener starts talking, the translation they hear gets quieter instead of stopping. Measure time to stop in agent calls. | nothing |
| **NS-03 Audio quality** | Check recorded translations for gaps, clipping and loudness. | nothing (recordings already saved) |
| **NS-04 Provider failure handling** | If realtime fails, fall back to step-by-step; reconnect dropped speech or voice connections; end a direction cleanly instead of hanging. | nothing |
| **NS-05 Rejoin** | Someone who drops and returns within 60 s keeps their settings and routing. | nothing |
| **NS-07 Second providers** | ElevenLabs voices, Qwen for translation and realtime, one more speech-recognition provider with strong Korean. | API keys |
| **RM-013 → RM-020 Phone** | SIP trunk, then browser ↔ phone interpreter (the first proof), then phone ↔ phone. | SIP account and a number |
| **RM-022 Provider benchmark** | Same call with each provider mix; compare speed, quality, cost per minute. Pick the default stack. | NS-01, NS-03, NS-07 |
| **Human ↔ AI calls, AI phone calls, an AI joining a two-person call** | The same layer used by agents. | phone line working |
| **Later:** mid-sentence translation stability, translation in the speaker's own voice, live self-cloning | Research-level features. | consent flows, provider support |

## Open decisions and risks

1. **Phone proof is blocked** until a SIP account and number exist.
2. **The web app must play any subscribed audio track** (`translation-for-<identity>`), not
   only `pipecat-audio`, or two-person calls are silent in the browser.
3. **API keys were shared in chat**: rotate them.
4. **Reference translations** in the evaluation set need a native Korean and Russian reviewer
   before the quality scores can be trusted.
5. **Realtime and glossary:** the realtime engine cannot use a glossary, so the terms feature
   works only with the step-by-step engine.
6. **Voice cloning and SIP** have only been tested with mocks.
7. **Join-time leak:** a participant can hear up to about 0.1 s of another's original voice
   when joining, and a client that subscribes by itself can override server-side routing.
8. **Nothing is committed yet** in either repository.

## Open source and services we use

| Part | What we use |
| --- | --- |
| Realtime audio and rooms | LiveKit (self-hosted server, SIP, server API) |
| Audio pipeline | Pipecat 1.12 |
| Voice activity detection | Silero VAD |
| Speech recognition | Deepgram nova-3 |
| Language model and translation | OpenAI gpt-4.1 family, `gpt-realtime-translate` |
| Voice output and cloning | Cartesia sonic-3.6 |
| API and data | FastAPI, SQLAlchemy, Alembic, PostgreSQL, Pydantic |
| Docs | Zensical (MkDocs-compatible), built with `--strict` |
