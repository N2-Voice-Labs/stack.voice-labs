# Development

Run shared local infrastructure from this repository with `docker compose up -d` after
copying `.env.example` to `.env`. Compose owns PostgreSQL, Valkey, and LiveKit.
Platform, Runtime, and Evals live under `backend.voice-labs/{platform,runtime,evals}`;
the web client lives in `frontend.voice-labs`.

Platform uses PostgreSQL and Alembic migrations; its unit/API tests use isolated SQLite.
LiveKit tokens require `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`, plus
the official `livekit-api` package. Runtime voice execution additionally requires the
optional Pipecat/LiveKit dependencies and configured STT, LLM, and TTS providers.

Use the stack README for startup commands and real-provider acceptance instructions.
Stubbed or synthetic-media tests do not establish real provider behavior.
