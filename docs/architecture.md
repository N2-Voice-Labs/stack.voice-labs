# Architecture

Platform is the control plane and durable source of truth. Runtime owns realtime session
execution and hot session state. The browser receives short-lived LiveKit credentials
from Platform. Runtime emits versioned authenticated HTTP/JSON lifecycle events to
Platform; event ingestion is idempotent by event ID. PostgreSQL stores durable
conversation, transcript, and session state.

The `backend.voice-labs` workspace groups existing Platform, Runtime, and Evals projects
without merging their internal project conventions. `frontend.voice-labs` owns the
Next.js client. This repository owns shared local Compose and developer configuration.
