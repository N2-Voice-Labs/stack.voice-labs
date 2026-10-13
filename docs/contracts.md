# Contracts

Runtime events carry `event_id`, `event_type`, `schema_version`, session/conversation/
agent IDs, timestamp, optional trace ID, and payload. Platform authenticates Runtime
requests and ingests events idempotently by event ID.

Platform-to-Runtime session handoff includes the selected agent/conversation/session
context and LiveKit room details. Runtime must join the requested room and report
lifecycle changes; the durable record remains owned by Platform.
