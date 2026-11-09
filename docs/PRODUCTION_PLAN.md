# Production plan

Status: started 2026-10-22. Step 0 done except key rotation and /docs decision; Step 1 in progress.

See [North Star Plan](NORTH_STAR_PLAN.md) and [Backend status](BACKEND_STATUS.md).

## Goal

The core loop works with real providers, is measured, and has ~800 tests. What remains for production is correctness, latency, reliability and the phone proof, not more features.

## Step 0 (this week)

- [ ] **PR-00-commit** Commit both repos. Done when both stack.voice-labs and backend.voice-labs have clean diffs. **Owner: you**
- [ ] **PR-00-ci** CI running all test suites and the docs build on every push. Done when GitHub Actions runs evals, platform tests, runtime tests, and zensical on each push. **Owner: you**
- [ ] **PR-00-keys** Rotate the API keys shared in chat. Done when all Slack messages with keys are deleted and new secrets are in place. **Owner: you**
- [ ] **PR-00-api-doc** Decide on /docs and /openapi.json: off in production or behind auth. Done when the choice is documented and Platform enforces it. **Owner: you**

## Step 1: Make it correct before fast

- [ ] **PR-10** Fix accurate-mode Russian bug: in the 2026-10-21 benchmark 26/30 RU→EN and 30/30 EN→RU sentences were never heard. Done when the benchmark re-runs and both directions reach 30/30. **Owner: agent.** Result 2026-10-22: not a mode bug. Cartesia ran out of credits mid-run and the TTS service went silent for the rest of the run. Re-run the two cells once Cartesia is topped up and the OpenAI key is replaced.
- [ ] **PR-11** Close privacy holes in two-person calls: participants get LiveKit tokens that cannot subscribe to raw microphones; only Runtime routes tracks; remove the ~0.1 s join-time leak. Done when a code review confirms no token field exposes raw streams and latency plots show the join-time leak gone. **Owner: agent.** Implemented 2026-10-22 (code and tests): the mic room token cannot subscribe, and each person hears their translation in a private listen room; a 650-attempt forced-subscribe loop received no mic audio. Still open: full live run with translations (blocked on provider accounts), the web app change, and phone participants (still use the old routing). Phone participants: done in code (own phone room, `POST /voice/sessions/{id}/phone-participants`), needs a SIP trunk to verify; `bridge-call` still uses old routing. Off by default (`PLATFORM_PRIVATE_LISTENING=0`) until the web app ships; contract in [Frontend: private listening](frontend-private-listening.md).
- [x] **PR-12** Explain the realtime gap: 0.79 s in a hand test vs first audio at end of sentence in the benchmark. Check runner pacing and realtime session turn detection. Done when the gap is measured and root-caused in a trace. **Owner: agent.** Done 2026-10-22: the hand test fed audio about 1 s ahead of real time; our realtime setup streams continuously and does not wait for end of speech; the remaining ~2–3 s is the model's own lag, which varies by sentence. The benchmark numbers are the real ones, so 1.2 s from speech start is unlikely with `gpt-realtime-translate`.

## Step 2: Make it fast

Targets: step-by-step p95 ≤ 1.5 s after speech ends, realtime p95 ≤ 1.2 s from speech start. Measure with the same `live_latency` command every time.

- [x] **PR-20** Time translation and TTS separately (new timeline marks). Done when latency events include separate translation and TTS phases. **Owner: agent** Done 2026-10-22 in code: new marks `translation_first_token`, `translation_first_chunk`, `tts_request`; shown in the live_latency "Where the time goes" table. Live numbers pending.
- [ ] **PR-21** Stream LLM output into TTS by clause. Done when p95 latency drops by 0.2–0.3 s and traces show overlapping LLM and TTS spans. **Owner: agent** Already streamed by clause; balanced now sends its first clause at 20 characters instead of 40. Live numbers pending.
- [ ] **PR-22** Keep provider connections warm (persistent TTS websocket, pre-open at call start). Done when TTS websocket stays open for the call duration and cold starts disappear. **Owner: agent** Findings: Cartesia and Deepgram connect at pipeline start; remaining cold cost is the first Cartesia context and idle sockets. Measure with the PR-20 marks before adding keepalive.
- [ ] **PR-23** Turn-detection model instead of silence timer (cuts 0.3–0.5 s). Done when turn-detection switches to a model and p95 drops. **Owner: agent**
- [ ] **PR-24** Smallest model for Instant that passes quality evals. Done when a smaller LLM passes the evaluation set without changing task quality. **Owner: agent**
- [ ] **PR-25** Host servers near providers / users. Done when latency targets are met in the production region. **Owner: agent**

## Step 3: Make it reliable

- [ ] **PR-30** Provider fallback realtime→step-by-step, timeouts and retries on every provider call, reconnect dropped streams (NS-04). Also emit a session error event when a provider dies (PR-10 found that an exhausted Cartesia quota left calls silent with no error). Done when a provider timeout falls back smoothly and calls finish without hanging. **Owner: agent** Done 2026-10-22 in code: `ProviderFailed` and `EngineFallback` events; auth/quota errors end the call cleanly (`SessionFailed`, reason `provider_failed`); realtime outages fall back to step-by-step; 41 tests incl. 401/402 mid-call. Open: per-direction failure in two-person calls, `ProviderReconnected`, live network-kill test.
- [ ] **PR-31** Calls always end cleanly, no hung rooms or stuck workers. Done when no trace shows a call that did not emit a `CallEnded` or `ParticipantLeft` event. **Owner: agent**
- [ ] **PR-32** Rejoin within 60 s keeps routing (NS-05). Done when a test kills the connection, rejoins, and audio routes correctly on return. **Owner: agent**
- [ ] **PR-33** Capacity control: per-worker call limit, "busy" response, autoscaling. Done when Platform returns 503 if workers are saturated and autoscale rules are in place. **Owner: agent**

## Step 4: Production infrastructure

- [ ] **PR-40** LiveKit production (TURN, UDP ports, TLS). Done when LiveKit is behind a stable FQDN with signed TLS and TURN is configured. **Owner: agent**
- [ ] **PR-41** Secrets manager, Postgres backups, migrations in CI. Done when secrets are in a vault, `pg_dump` runs nightly, and Alembic migrations are gated in the pipeline. **Owner: agent**
- [ ] **PR-42** Observability: structured logs, one trace per call with the utterance timeline, error tracking (e.g. Sentry), alerts on p95 latency and failed calls. Done when every call emits one trace and alarms fire if p95 exceeds targets. **Owner: agent**
- [ ] **PR-43** Limits: rate limits on token and session endpoints, hard cap on session length. Done when burst traffic gets 429 and long sessions are cut after 4 hours. **Owner: agent**
- [ ] **PR-44** Tenancy: organizations, per-org keys, per-org data isolation. Done when multiple orgs can coexist in one deployment and their data is isolated. **Owner: agent**

## Step 5: Make it useful

- [ ] **PR-50** SIP trunk (Twilio/Telnyx) and number → browser↔phone proof, then rerun evals with 8 kHz phone audio. Done when a phone call between two people completes the test suite and one eval run passes on phone audio. **Owner: you buy the trunk; agent implements**
- [ ] **PR-51** Cost per minute per provider tracked from day one (needed for RM-022 and pricing). Done when each call emits a cost field and the monthly bill matches provider invoices. **Owner: agent**
- [ ] **PR-52** Remove Cartesia-specific field names before adding ElevenLabs. Done when field names are generic and ElevenLabs is a drop-in replacement. **Owner: agent**
- [ ] **PR-53** Agents with a glossary auto-route to the step-by-step engine instead of the realtime engine silently ignoring terms. Done when agent mode with a glossary uses cascaded, not realtime. **Owner: agent**
- [ ] **PR-54** Native Korean and Russian reviewers for evaluation references. Done when two native speakers have reviewed and approved the references. **Owner: you**
- [ ] **PR-55** Data handling: recording-consent flag, retention period for audio and transcripts, delete API, audit trail for voice-clone consent (clinics and visa offices are target customers). Done when a call can be deleted and no trace of audio, transcript, or consent remains. **Owner: agent**

## Do not do yet

Production voice cloning, an AI joining a two-person call, translation in the speaker's own voice. Wait until Steps 1–3 and the phone proof are done.
