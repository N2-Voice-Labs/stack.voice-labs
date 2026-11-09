# Frontend: private listening

## What it is and why

In a two-participant interpreter session, each participant's audio flows through the Runtime as translation. The Platform offers a scheme to ensure that a participant never receives another participant's raw microphone, not even for an instant while the client loads or before a subscription is denied.

This is needed because LiveKit auto-subscribes joining participants to every published track within ~0.1–0.2 s of joining, before server-side unsubscribe requests can be processed. A participant with `can_subscribe=true` cannot be denied one track while allowed another, so the scheme splits each participant's audio across two rooms: the session room (for publishing their microphone) and a private listen room (for receiving their translation).

## When `connection.listen` is present

`connection.listen` is present when **all** of these are true:

1. **Flag enabled**: `PLATFORM_PRIVATE_LISTENING=1` in the Platform's `.env` (default `0`; off until the web app joins the listen room).
2. **Session mode**: The agent is an interpreter (`mode="interpreter"`).
3. **Participants exist**: The session has at least one participant declared (via `POST /voice/sessions` with a `participant` body, or added later with `POST /voice/sessions/{id}/participants`).
4. **Not hearing original**: `interpreter.hear_original` is not `true`.

`connection.listen` is **absent** when:

- `PLATFORM_PRIVATE_LISTENING=0` (the default; sessions use one room with server-side unsubscribe routing).
- The agent is not an interpreter or the session has no participants.
- `hear_original: true` (both people share one room and can hear each other's microphone).
- Single-participant or agent sessions (no interpreter participants).

**Guest behaviour**: A guest added with `POST /voice/sessions/{id}/participants` inherits the session's mode set at creation. If the session started with `connection.listen`, the guest's response also includes it.

## JSON response shapes

### POST /voice/sessions (create session)

Excerpt with `connection` when `private_listening=true`:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "room_name": "voice-labs-550e8400-e29b-41d4-a716-446655440000",
  "connection": {
    "url": "wss://livekit.example.com",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "listen": {
      "url": "wss://livekit.example.com",
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "room_name": "voice-labs-550e8400-e29b-41d4-a716-446655440000--listen--browser-550e8400e29b41d4a716446655440000",
      "track": "translation-for-browser-550e8400e29b41d4a716446655440000"
    }
  },
  "session_status": "created",
  "connection_status": "configured",
  "runtime_status": "accepted",
  "session_token": "vls_550e8400e29b41d4a716446655440000abcd1234"
}
```

When `private_listening=false`, the response omits the `listen` object:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440001",
  "room_name": "voice-labs-550e8400-e29b-41d4-a716-446655440000",
  "connection": {
    "url": "wss://livekit.example.com",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "session_status": "created",
  "connection_status": "configured",
  "runtime_status": "accepted",
  "session_token": "vls_550e8400e29b41d4a716446655440000abcd1234"
}
```

### POST /voice/sessions/{id}/participants (add guest)

Response with `connection.listen`:

```json
{
  "participant_identity": "guest-a1b2c3d4",
  "connection": {
    "url": "wss://livekit.example.com",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "listen": {
      "url": "wss://livekit.example.com",
      "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "room_name": "voice-labs-550e8400-e29b-41d4-a716-446655440000--listen--guest-a1b2c3d4",
      "track": "translation-for-guest-a1b2c3d4"
    }
  },
  "session_token": "vls_guest_a1b2c3d4abcd5678efgh"
}
```

**Field types and semantics:**

| Field | Type | Meaning |
| --- | --- | --- |
| `connection.url` | string | WebSocket URL of the LiveKit server. Same for both rooms. |
| `connection.token` | string | JWT token for the session room. `canPublish=true`, `canSubscribe=false` (if private). Signs you in to join and publish your microphone. |
| `connection.listen.url` | string | WebSocket URL (same as `connection.url`). |
| `connection.listen.token` | string | JWT token for the listen room. `canPublish=false`, `canPublishData=false`, `canSubscribe=true`. Signs you in to receive translations only. |
| `connection.listen.room_name` | string | Full name of the listen room, format `<session_room>--listen--<identity>`. |
| `connection.listen.track` | string | Name of the audio track published by Runtime in the listen room, format `translation-for-<identity>`. |

## Token grants

**Session room** (`connection.url` with `connection.token`):

- `canPublish: true` — publish your microphone.
- `canSubscribe: false` (when private) — receive no audio from the session room (enforcement on server, so auto-subscribe and client subscriptions both fail).

**Listen room** (`connection.listen.url` with `connection.listen.token`):

- `canPublish: false` — you cannot publish in the listen room.
- `canPublishData: false` — you cannot send data messages.
- `canSubscribe: true` — receive the Runtime's translation track and any other subscribed tracks.

## Client implementation

### Steps for both creator and guest

When `connection.listen` is present:

1. **Connect to the session room** using `connection.url` and `connection.token`. Publish your microphone here.
2. **Connect to the listen room** using `connection.listen.url` and `connection.listen.token` with the **same `identity`** as the session room (the client library typically infers this from the token).
3. **Subscribe to translation tracks** in the listen room. Auto-subscribe to all tracks with kind `audio`, or manually subscribe to the specific track named by `connection.listen.track`.
4. **Play all subscribed audio** from the listen room. Do not play audio from the session room (it contains only microphone publishes).
5. **On disconnect/end**: Disconnect from both rooms cleanly.
6. **On reconnect** (e.g. network hiccup): Reconnect to both rooms using the same credentials. The Platform does not reissue tokens; reuse the ones from the session creation or participant responses.

When `connection.listen` is absent (fallback behavior):

- Connect to the session room using `connection.url` and `connection.token`.
- Publish your microphone.
- Auto-subscribe to all tracks in that room.
- Play all subscribed audio. The Runtime's unsubscribe-after-join server API will remove the other person's microphone within ~0.1 s.

### JavaScript code sketch (livekit-client)

```javascript
import {
  connect,
  LocalParticipant,
  Participant,
  RoomOptions,
  TrackKind,
} from 'livekit-client';

async function joinSession(sessionResponse) {
  const { connection, room_name } = sessionResponse;
  
  // Join the session room (publish microphone)
  const sessionRoom = await connect(connection.url, connection.token, {
    autoSubscribe: false, // Manual control preferred
    audio: true,
    video: false,
  });
  
  // Publish local microphone
  await sessionRoom.localParticipant.setMicrophoneEnabled(true);
  
  // If private listening: join the listen room separately
  let listenRoom = null;
  if (connection.listen) {
    listenRoom = await connect(
      connection.listen.url,
      connection.listen.token,
      {
        autoSubscribe: true, // Auto-subscribe to Runtime's translation track
        audio: true,
        video: false,
      }
    );
  }
  
  // Play audio from the listen room (or session room if no private listening)
  const audioRoom = listenRoom || sessionRoom;
  
  audioRoom.on('trackSubscribed', (track) => {
    if (track.kind === TrackKind.Audio) {
      const audio = document.createElement('audio');
      audio.id = `audio-${track.sid}`;
      audio.autoplay = true;
      audio.controls = false;
      audio.playsinline = true;
      audio.srcObject = new MediaStream([track.mediaStreamTrack]);
      document.body.appendChild(audio);
    }
  });
  
  audioRoom.on('trackUnsubscribed', (track) => {
    const audioEl = document.getElementById(`audio-${track.sid}`);
    if (audioEl) {
      audioEl.remove();
    }
  });
  
  // Handle disconnection
  sessionRoom.on('disconnected', () => {
    sessionRoom.disconnect();
    if (listenRoom) {
      listenRoom.disconnect();
    }
  });
  
  return { sessionRoom, listenRoom };
}
```

## What the client must NOT expect

- **No audio in the session room**: When private listening is enabled, the session room carries only microphone publishes from participants. No translation or other audio will be heard there, even if auto-subscribed.
- **No raw microphone of others**: The session room token has `canSubscribe=false`. Even if the client tries to subscribe to another participant's track or forces a server-side subscription, LiveKit enforces the token and refuses.
- **Track names are stable**: The translation track in the listen room is always named `translation-for-<identity>`. The Runtime publishes exactly one track per participant.
- **Listen room is private**: Only that participant and the Runtime join the listen room. Other participants cannot hear the translation or interfere.

## How to test locally

1. **Enable private listening** in the stack `.env` file:
   ```bash
   echo "PLATFORM_PRIVATE_LISTENING=1" >> .env
   ```

2. **Restart Platform**:
   ```bash
   # Kill any running Platform instance and restart it
   make up  # or your local run command
   ```

3. **Create a session**:
   ```bash
   curl -X POST http://localhost:8000/voice/sessions \
     -H "Content-Type: application/json" \
     -d '{
       "agent_id": "<interpreter-agent-uuid>",
       "participant": {
         "language": "en",
         "display_name": "Alice"
       }
     }'
   ```
   Verify that `connection.listen` is present in the response.

4. **Add a second participant**:
   ```bash
   curl -X POST http://localhost:8000/voice/sessions/<session-id>/participants \
     -H "Content-Type: application/json" \
     -d '{
       "language": "ru",
       "display_name": "Bob"
     }'
   ```
   Verify that the response includes `connection.listen`.

5. **Connect with a LiveKit client** (web or SDK) using both `connection.url`/`connection.token` (session room) and `connection.listen.url`/`connection.listen.token` (listen room). Verify:
   - Microphone audio flows to the session room only.
   - Translation audio appears in the listen room only.
   - Toggling `PLATFORM_PRIVATE_LISTENING=0` and restarting reverts to single-room mode.
