# Voice Labs

The first vertical slice is a browser conversation through Platform, LiveKit, Runtime,
VAD/turn detection, STT, LLM, and TTS, with durable lifecycle events written back to
PostgreSQL. Provider-backed behavior is considered verified only after configured real
credentials and real audio have been used.

The local workspace consists of `backend.voice-labs` (Platform, Runtime, and Evals),
`frontend.voice-labs` (web), and this stack repository (shared infrastructure,
configuration, documentation, and acceptance checks). See the root README for setup.
