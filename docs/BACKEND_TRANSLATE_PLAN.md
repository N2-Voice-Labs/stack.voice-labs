# Backend Milestone 10: Live translation (interpreter mode)

Status: stage 1 done and verified with real providers (backend only; frontend untouched)

An agent can run as an **interpreter** instead of an assistant: it repeats what each
speaker says in the other language, using a chosen voice. This builds on the existing
Runtime (LiveKit + Pipecat) and providers. The first stage needs no new provider keys.

## Design decisions

- **Cascaded first, streaming later.** Stage 1 uses Deepgram STT → OpenAI translation →
  Cartesia TTS per finished utterance. Expected delay is about 1.5–3 s after the speaker
  stops. Stage 2 adds a streaming speech-to-speech engine (OpenAI `gpt-realtime-translate`),
  which translates while the speaker is still talking, as a second engine. We compare the
  two on latency and quality rather than assuming either is better.
- **Direction.** `auto` translates each utterance into the *other* language of the pair,
  using Deepgram's multilingual detection. It is only allowed when both languages are in
  Deepgram's code-switching set (`en, es, fr, de, hi, ru, pt, ja, it, nl`), so English ↔
  Russian works. `one_way` fixes the source and target (e.g. `ko → en`) and supports any
  language both providers handle.
- **Voice.** Translations are spoken by the agent's voice profile (a Cartesia multilingual
  voice), so a consented clone of the user's own voice can speak the translation.
- **No instant cloning of other callers.** Copying a caller's voice in real time without
  their consent is impersonation, so we only use voice profiles that passed the consent
  check. Interpreter sessions should announce that an AI interpreter is on the call.
- **No barge-in in interpreter mode.** A translation is never cut off by the other person
  starting to speak; their speech is translated next.
- **Not marketed as zero latency.** We measure the delay from the end of speech to the first
  translated audio and report p50/p95 through the existing analytics.

## Contract

Agents gain `mode` (`agent` | `interpreter`, default `agent`) and `interpreter`
(`null` or an object):

```json
{
  "mode": "interpreter",
  "interpreter": {
    "languages": ["en", "ru"],
    "direction": "auto"
  }
}
```

- `languages`: exactly two distinct codes from the supported set
  `en, ru, ko, ja, zh, es, fr, de, it, pt, nl, hi, tr, pl`.
- `direction`: `auto` (both languages must be in Deepgram's code-switching set) or
  `one_way` (`languages[0]` → `languages[1]`).
- `mode: "interpreter"` requires `interpreter`; `mode: "agent"` requires it to be null.

The Platform→Runtime session contract always carries `mode` and `interpreter` (null for
assistant agents).

## Tasks

### Stage 1: cascaded interpreter

- [x] **TR-001 Platform.** `agents.mode` and `agents.interpreter` with migration `0005`,
  validation and error codes, API read/write, session contract fields, tests.
- [x] **TR-002 Runtime.** Interpreter pipeline: STT with `multi` (auto) or the fixed source
  language (one_way) → translation processor (strict translate-only prompt, no memory
  beyond a short window for consistency) → TTS in the target language with the agent's
  voice. Emits `TranscriptFinal` for the original (user) and the translation (assistant)
  with language metadata, plus latency events. Interruptions disabled.
- [x] **TR-003 Verification.** Real-provider check with synthesized English and Russian
  speech in both directions; record measured latency.

  Result (2026-10-15, English ↔ Russian, `auto`, real Deepgram/OpenAI `gpt-4.1-mini`/Cartesia,
  synthesized speech played into a live LiveKit session, n=2):

  | Utterance | Translation |
  | --- | --- |
  | ru: "Здравствуйте. Хотел бы записаться на прием на завтра утром." | en: "Hello. I would like to make an appointment for tomorrow morning." |
  | en: "Hello. Would like to book an appointment for tomorrow morning." | ru: "Здравствуйте. Хотел бы записаться на прием на завтра утром." |

  | Stage | p50 |
  | --- | --- |
  | STT first result | 415 ms |
  | Translation (OpenAI) | 1,623 ms |
  | TTS first audio | 191 ms |
  | End of speech → first translated audio | 1,819 ms |

  The translation call dominates. Next optimizations: stream the translation into TTS
  sentence by sentence, try a faster model, and compare with the streaming engine (TR-010).

### Stage 2: streaming engine

- [ ] **TR-010** `engine: "cascaded" | "realtime"` on the interpreter config; a Runtime
  adapter for OpenAI `gpt-realtime-translate` (provider voice, not the user's).
- [ ] **TR-011** Latency and quality comparison between engines on the evaluation set.

### Stage 3: two speakers, two voices

- [ ] **TR-020** Per-participant language and voice: each speaker hears the other in that
  speaker's own consented voice profile.

### Stage 4: phone calls

- [ ] **TR-030** Bridge two SIP legs through LiveKit with the interpreter in the middle
  (depends on SIP work in [Backend Live Plan](BACKEND_LIVE_PLAN.md)). PSTN audio is often
  8 kHz, which lowers recognition quality, so prefer HD voice trunks.
