# Backend MVP Definition of Done

The first backend milestone is complete when one browser can have a measurable, interruptible, persisted voice conversation with one configured agent.

## User journey

1. A configured agent exists in `platform.voice-labs`.
2. The browser requests a voice session for that agent.
3. The platform authorizes the request, creates a conversation/session, and returns LiveKit connection information.
4. The browser joins LiveKit and sends microphone audio.
5. The runtime joins the same session and receives the audio.
6. VAD and turn detection identify a completed user turn.
7. STT produces a transcript and flexible language metadata, including a primary language when available and detected languages for mixed-language speech.
8. The LLM streams a response using the configured agent context.
9. TTS produces audio and the browser hears the response.
10. The user interrupts the response; queued/generated speech is cancelled.
11. The runtime emits transcript and timing events to the platform, and the platform persists them.
12. The platform finalizes the conversation and voice session.

## Required API behavior

### Create session

```http
POST /voice/sessions
```

Request:

```json
{
  "agent_id": "agent-id"
}
```

Response shape:

```json
{
  "session_id": "session-id",
  "conversation_id": "conversation-id",
  "connection": {
    "url": "https://livekit.example",
    "token": "short-lived-token"
  }
}
```

The exact API envelope may follow the selected FastAPI template, but the information above is required.

### Conversation reads

The platform exposes:

```text
GET /conversations
GET /conversations/{id}
GET /conversations/{id}/messages
```

The returned messages include role, content, optional `primary_language`, optional `detected_languages`, timestamps, and session association when applicable. A mixed-language message may look like this:

```json
{
  "role": "user",
  "content": "Мне нужно book an appointment на tomorrow.",
  "primary_language": "ru",
  "detected_languages": ["ru", "en"]
}
```

Word-level language segments are not required for V1.

## Required runtime events

At minimum, the runtime can produce:

```text
SpeechStarted
SpeechStopped
TurnCompleted
AgentSpeechStarted
UserInterrupted
AgentSpeechCancelled
TranscriptFinal
LatencyMeasured
SessionEnded
```

Events contain session ID, conversation ID, agent ID, event ID, event timestamp, trace ID where available, and a schema version. The first implementation sends them as authenticated HTTP/JSON requests to the platform. Retries must not duplicate durable messages or corrupt final session state.

```json
{
  "event_id": "event-id",
  "event_type": "TranscriptFinal",
  "schema_version": 1,
  "session_id": "session-id",
  "conversation_id": "conversation-id",
  "timestamp": "2026-10-01T00:00:00Z",
  "payload": {}
}
```

## Required measurements

Record these timestamps for every successful turn where the signal is available:

```text
speech_end_at
stt_final_at
llm_first_token_at
tts_first_audio_at
playback_started_at
```

Derive:

```text
STT latency
LLM time to first token
TTS time to first audio
end-to-end end-of-turn to first-audio latency
```

All measurements are tagged with session ID, conversation ID, agent ID, provider, primary language when known, detected languages when available, and trace ID.

## Acceptance checklist

- [ ] A fresh local setup can start PostgreSQL, Valkey, LiveKit, platform, and runtime.
- [ ] A platform health check and runtime health check pass.
- [ ] An agent can be created and retrieved through the platform API.
- [ ] A provider configuration can be selected by an agent without exposing secrets.
- [ ] A voice session can be created only for an enabled agent.
- [ ] The browser receives valid LiveKit connection information.
- [ ] The runtime joins and leaves the LiveKit session cleanly.
- [ ] English audio produces a transcript and spoken response.
- [ ] Russian audio produces a transcript and spoken response.
- [ ] At least one English/Russian code-switched utterance is processed without manual language selection.
- [ ] A user can interrupt the agent while it is speaking.
- [ ] The final transcript is visible through the platform conversation API.
- [ ] Mixed-language messages can retain primary and detected language metadata without being forced into one language.
- [ ] Session status and end time are persisted.
- [ ] Per-stage latency values are persisted or queryable through observability tooling.
- [ ] Provider, transport, and platform failure paths have automated tests or documented manual checks.
- [ ] The evaluation run records model/provider versions, dataset version, hardware, WER, code-switch WER, and latency.

## Evidence required before calling the MVP complete

Store or link the following evidence in the project documentation or evaluation repository:

- local setup instructions that another team member can follow;
- API contract examples;
- one successful end-to-end session recording or reproducible demo procedure;
- automated test output;
- a latency trace for a complete turn;
- interruption test result;
- English, Russian, and code-switched evaluation results;
- known limitations and deferred work.

## Completion rule

Do not optimize providers or add more infrastructure before this checklist is passing and the baseline measurements exist. New work must either support this vertical slice, improve measurement quality, or be explicitly approved as a new milestone.
