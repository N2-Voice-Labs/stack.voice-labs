# Backend roadmap: from working demo to real interpreter

Status: Phase 0 done; Phase 1 done except the SIP trunk (backend only; frontend untouched)

Priorities now follow the [North Star plan](NORTH_STAR_PLAN.md).

We are not rewriting Voice Labs. The Platform → session contract → Runtime → LiveKit
architecture stays. The next step is making Runtime handle several participants with
different languages and **different audio ownership** correctly.

## Audio ownership contract

Every audio track in an interpreter room has one owner and an explicit audience.

| Track | Published by | Who may hear it |
| --- | --- | --- |
| `A_original` (A's microphone) | Participant A | Runtime only |
| `B_original` (B's microphone) | Participant B | Runtime only |
| `A_translation` (A's words in B's language, A's voice) | Runtime | B only |
| `B_translation` (B's words in A's language, B's voice) | Runtime | A only |
| `agent_audio` (assistant replies, single-caller modes) | Runtime | the caller(s) |

Rules:

1. A participant never hears their own microphone or their own translation.
2. In interpreter mode, participants do **not** hear each other's original audio by default.
   A session option `hear_original: true` lets listeners also hear the original quietly
   underneath (some users prefer it); default off.
3. Enforcement is server-side (Runtime and the LiveKit server API), so it works for any
   client: browser, phone (SIP) or API, without trusting the client.
4. Single-participant sessions (agent, agent + translator, one-speaker interpreter) keep
   today's behavior: Runtime publishes one track that the caller hears.

## Phase 0: make the interpreter correct

- [x] **RM-001 Participant context + per-listener routing.** One context per participant
  (identity, source and target language, voice, input lane, output track) and routing that
  enforces the ownership contract above.
- [x] **RM-002 Audio ownership contract** (this document) enforced and tested. Runtime
  publishes one `translation-for-<identity>` track per listener (subscription permissions
  allow only that listener) and unsubscribes participants from each other's microphones
  through the LiveKit server API. Verified live 2026-10-18 (Korean ↔ English): each person
  heard only the other's translation; `hear_original: true` works; single-caller sessions
  unchanged. Limits: a join-time leak of up to ~0.1 s, and a client that re-subscribes itself
  can override the server. The web app must play any subscribed audio track, not only
  `pipecat-audio`.
- [x] **RM-003 First-audio latency instrumentation.** Timestamps T0 speaker starts, T1 VAD
  detects, T2 first transcript, T3 translation starts, T4 first audible translated audio,
  T5 playback stable; report `time_to_first_audio = T4 − T0` per utterance, per engine.
  Done: one `utterance_timeline` event per utterance; `GET /analytics/summary` has a
  `timeline` section. Measured 2026-10-18 (about 3 s utterances, first audio from the moment
  the speaker starts, p50): realtime 0.79 s; cascaded instant 3.9 s, accurate 4.4 s,
  balanced 5.1 s; two-person routed 3.3–4.7 s. Cascaded figures include the speech itself;
  after the speaker stops, cascaded speaks in 0.8–1.1 s.
- [x] **RM-004 Basic authentication and authorization.** Done: `PLATFORM_API_KEYS`,
  session tokens, migration `0007_session_tokens`; see Contracts. API keys for the Platform API (off
  when unset for local development); session-scoped tokens so a participant can only act
  on their own session; never expose the API publicly without it.

## Phase 1: make it extensible

- [x] **RM-010 Small `TranslationEngine` interface** implemented by the cascaded and
  realtime engines, so a new provider (Qwen, local models) plugs in without touching
  pipelines. Done: `runtime/translation_engine.py` registry with cascaded and realtime
  engines.
- [x] **RM-011 Instant / Balanced / Accurate** translation modes (engine choice plus
  turn-end waiting). Done: `interpreter.latency_mode` — instant (0.2 s pause, 20-char
  chunks, gpt-4.1-nano, realtime engine when one-way), balanced (default; 0.3 s, 40 chars,
  gpt-4.1-mini), accurate (0.7 s, sentences only, gpt-4.1).
- [x] **RM-012 Evaluation dataset**: about 150 short consented or synthetic recordings
  (EN↔KO, RU↔EN, code-switched, noisy/phone-quality, interruptions, names and numbers,
  domain terms) with reference transcripts and translations, plus a runner. Done: dataset
  v1 (140 synthetic items) in `backend.voice-labs/evals`; first small run in
  [Evaluation](evaluation.md). References still need review by native Korean and Russian
  speakers; real consented recordings can be added with the same manifest.
- [ ] **RM-013 First SIP trunk** (account with a SIP provider) wired to LiveKit.

## Phase 2: prove it in the real world

- [ ] **RM-020** Phone ↔ browser interpreter.
- [ ] **RM-021** Phone ↔ phone interpreter.
- [ ] **RM-022** Provider benchmark on the evaluation set: time to first audio, translation
  quality, missing meaning, voice similarity, cost.

## Phase 3: push the technology

- [ ] **RM-030** Streaming/stability layer for mid-sentence translation (committed vs
  unstable tokens), only when we build our own incremental translation.
- [ ] **RM-031** Voice-preserving translation with consented voice profiles by default.
- [ ] **RM-032** Live self-cloning (the speaker's own voice, with consent, during the call).

Related plans: [Studio](BACKEND_STUDIO_PLAN.md), [Live](BACKEND_LIVE_PLAN.md),
[Translation](BACKEND_TRANSLATE_PLAN.md).
