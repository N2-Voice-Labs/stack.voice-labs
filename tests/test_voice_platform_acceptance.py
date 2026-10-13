"""Opt-in cross-service Platform -> Runtime -> LiveKit acceptance test."""

import asyncio
import math
import os
import socket
import subprocess
import sys
import time
from contextlib import suppress
from array import array
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

_WORKSPACE = Path(__file__).resolve().parents[1]
_BACKEND = _WORKSPACE.parent / "backend.voice-labs"
for _project in ("platform", "runtime"):
    sys.path.insert(0, str(_BACKEND / _project))

# Use a dedicated opt-in URL for disposable acceptance databases; never inherit
# the app's normal database URL into tests that create and persist test records.
os.environ["PLATFORM_DATABASE_URL"] = os.getenv(
    "PLATFORM_ACCEPTANCE_DATABASE_URL", "sqlite://"
)
os.environ["PLATFORM_AUTO_CREATE_SCHEMA"] = "1"

from src.platform import main as platform_main  # noqa: E402
from src.runtime import api as runtime_api  # noqa: E402
from src.runtime import events_client as runtime_events_client  # noqa: E402

_LIVEKIT_CONFIGURED = all(
    os.getenv(name) for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
)


@pytest.mark.skipif(
    not _LIVEKIT_CONFIGURED,
    reason="Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET to run",
)
def test_platform_handoff_persists_runtime_transcript_and_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_verify_cross_service_session(monkeypatch))


def test_platform_hands_off_deferred_session_and_recovers_runtime_state_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_verify_runtime_state_loss_retry(monkeypatch))


def test_platform_retries_after_runtime_process_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_verify_runtime_process_restart(monkeypatch))


@pytest.mark.skipif(
    not _LIVEKIT_CONFIGURED,
    reason="Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET to run",
)
def test_platform_rejoins_original_livekit_room_after_runtime_process_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_verify_runtime_process_restart(monkeypatch, with_livekit=True))


async def _verify_runtime_process_restart(
    monkeypatch: pytest.MonkeyPatch, *, with_livekit: bool = False
) -> None:
    runtime_token = f"process-recovery-{uuid4()}"
    monkeypatch.setenv("PLATFORM_RUNTIME_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_PLATFORM_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_API_URL", "http://127.0.0.1:0")
    monkeypatch.setenv("RUNTIME_TEST_LIVEKIT", "1" if with_livekit else "0")
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join(
            str(_BACKEND / "runtime")
        ),
    )

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    runtime_url = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("RUNTIME_API_URL", runtime_url)
    child_code = """
import asyncio
import os
import uvicorn
from src.runtime import api

if os.environ.get("RUNTIME_TEST_LIVEKIT") == "1":
    from livekit import rtc
    from src.runtime.pipeline import create_runtime_token

    audio_frame_count = 0

    async def receive_audio(track):
        global audio_frame_count
        async for event in rtc.AudioStream(track):
            if event.frame.data:
                audio_frame_count += 1

    async def run_session(request):
        room = rtc.Room()

        @room.on("track_subscribed")
        def on_track_subscribed(track, _publication, _participant):
            asyncio.create_task(receive_audio(track))

        await room.connect(
            os.environ["LIVEKIT_URL"], create_runtime_token(request.room_name)
        )
        await asyncio.Event().wait()

    async def report_audio_frames():
        return {"audio_frames": audio_frame_count}

    api.app.add_api_route("/_acceptance/audio-frames", report_audio_frames)
else:
    async def run_session(request):
        await asyncio.Event().wait()

api.run_session = run_session
uvicorn.run(api.app, host="127.0.0.1", port=int(__import__("os").environ["RUNTIME_TEST_PORT"]), log_level="critical")
"""
    monkeypatch.setenv("RUNTIME_TEST_PORT", str(port))
    children: list[subprocess.Popen] = []
    livekit = None
    browser = None
    source = None
    audio_publisher: asyncio.Task | None = None

    def start_runtime() -> subprocess.Popen:
        child = subprocess.Popen(
            [sys.executable, "-c", child_code],
            cwd=_BACKEND / "runtime",
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        children.append(child)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise AssertionError(f"Runtime process exited: {child.returncode}")
            try:
                response = httpx.get(f"{runtime_url}/health", timeout=0.25)
                if response.status_code == 200:
                    return child
            except httpx.HTTPError:
                time.sleep(0.05)
        raise AssertionError("Runtime health endpoint did not become ready")

    platform_transport = httpx.ASGITransport(app=platform_main.app)
    real_client = httpx.AsyncClient

    class RuntimeHttpClient:
        def __init__(self, *, timeout: float) -> None:
            self.client = real_client(timeout=timeout)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info) -> None:
            await self.client.aclose()

        async def get(self, url: str, **kwargs):
            return await self.client.get(url, **kwargs)

        async def post(self, url: str, **kwargs):
            return await self.client.post(url, **kwargs)

    monkeypatch.setattr(
        platform_main,
        "httpx",
        SimpleNamespace(AsyncClient=RuntimeHttpClient, HTTPError=httpx.HTTPError),
    )
    first = start_runtime()
    try:
        async with platform_main.app.router.lifespan_context(platform_main.app):
            async with real_client(
                transport=platform_transport, base_url="http://platform.test"
            ) as platform:
                agent_response = await platform.post(
                    "/agents",
                    json={
                        "name": "Restart recovery",
                        "system_prompt": "Keep this contract.",
                        "voice_id": "voice",
                    },
                )
                assert agent_response.status_code == 201
                session_response = await platform.post(
                    "/voice/sessions", json={"agent_id": agent_response.json()["id"]}
                )
                assert session_response.status_code == 201
                session = session_response.json()
                if with_livekit:
                    from livekit import api as livekit_api
                    from livekit import rtc as livekit_rtc

                    livekit = livekit_api.LiveKitAPI(
                        os.environ["LIVEKIT_URL"].replace("ws", "http", 1),
                        api_key=os.environ["LIVEKIT_API_KEY"],
                        api_secret=os.environ["LIVEKIT_API_SECRET"],
                    )
                    browser = livekit_rtc.Room()
                    source = livekit_rtc.AudioSource(sample_rate=48000, num_channels=1)
                    await browser.connect(
                        session["connection"]["url"], session["connection"]["token"]
                    )
                    track = livekit_rtc.LocalAudioTrack.create_audio_track(
                        "restart-recovery-input", source
                    )
                    await browser.local_participant.publish_track(track)

                    async def publish_audio_until_stopped() -> None:
                        for frame_index in range(1000):
                            samples = array(
                                "h",
                                (
                                    int(
                                        8000
                                        * math.sin(
                                            2
                                            * math.pi
                                            * 440
                                            * (frame_index * 480 + index)
                                            / 48000
                                        )
                                    )
                                    for index in range(480)
                                ),
                            )
                            await source.capture_frame(
                                livekit_rtc.AudioFrame(
                                    data=samples.tobytes(),
                                    sample_rate=48000,
                                    num_channels=1,
                                    samples_per_channel=480,
                                )
                            )
                            await asyncio.sleep(0.01)

                    audio_publisher = asyncio.create_task(publish_audio_until_stopped())

                    async def wait_for_runtime_participant(
                        previous_sid: str | None = None,
                    ) -> str:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            response = await livekit.room.list_participants(
                                livekit_api.ListParticipantsRequest(
                                    room=session["room_name"]
                                )
                            )
                            identities = {
                                item.identity for item in response.participants
                            }
                            runtime_participants = [
                                item
                                for item in response.participants
                                if item.identity
                                == f"voice-labs-agent-{session['room_name']}"
                            ]
                            if len(runtime_participants) == 1 and (
                                previous_sid is None
                                or runtime_participants[0].sid != previous_sid
                            ):
                                assert f"browser-{session['session_id']}" in identities
                                assert len(
                                    [
                                        identity
                                        for identity in identities
                                        if identity.startswith("voice-labs-agent-")
                                    ]
                                ) == 1
                                return runtime_participants[0].sid
                            await asyncio.sleep(0.1)
                        raise AssertionError(
                            "Runtime did not rejoin the original LiveKit room"
                        )

                    async def wait_for_audio_frames() -> int:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            response = httpx.get(
                                f"{runtime_url}/_acceptance/audio-frames", timeout=1
                            )
                            if response.status_code == 200:
                                count = response.json()["audio_frames"]
                                if count > 0:
                                    return count
                            await asyncio.sleep(0.1)
                        raise AssertionError(
                            "Runtime did not receive audio published to the session room"
                        )

                    original_runtime_sid = await wait_for_runtime_participant()
                    await wait_for_audio_frames()
                runtime_started = await platform.post(
                    "/runtime/events",
                    headers={"X-Runtime-Token": runtime_token},
                    json={
                        "event_id": str(uuid4()),
                        "event_type": "RuntimeStarted",
                        "schema_version": 1,
                        "session_id": session["session_id"],
                        "conversation_id": session["conversation_id"],
                        "agent_id": agent_response.json()["id"],
                        "payload": {"room_name": session["room_name"]},
                    },
                )
                assert runtime_started.status_code == 202
                persisted = await platform.get(
                    f"/voice/sessions/{session['session_id']}"
                )
                assert persisted.json()["status"] == "running"

                first.kill()
                first.wait(timeout=5)
                second = start_runtime()
                assert second.pid != first.pid

                retry = await platform.post(
                    f"/voice/sessions/{session['session_id']}/ensure-running"
                )
                assert retry.status_code == 200, retry.text
                assert retry.json() == {
                    "session_status": "running",
                    "runtime_status": "accepted",
                }
                retry_again = await platform.post(
                    f"/voice/sessions/{session['session_id']}/ensure-running"
                )
                assert retry_again.status_code == 200, retry_again.text
                assert retry_again.json() == {
                    "session_status": "running",
                    "runtime_status": "starting",
                }
                if with_livekit:
                    await wait_for_runtime_participant(original_runtime_sid)
                    assert await wait_for_audio_frames() > 0
    finally:
        if audio_publisher and not audio_publisher.done():
            audio_publisher.cancel()
            await asyncio.gather(audio_publisher, return_exceptions=True)
        if with_livekit:
            with suppress(Exception):
                if browser:
                    await asyncio.wait_for(browser.disconnect(), timeout=5)
            with suppress(Exception):
                if source:
                    await asyncio.wait_for(source.aclose(), timeout=5)
            with suppress(Exception):
                if livekit:
                    await asyncio.wait_for(livekit.aclose(), timeout=5)
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


async def _verify_runtime_state_loss_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_token = f"recovery-{uuid4()}"
    monkeypatch.setenv("PLATFORM_RUNTIME_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_PLATFORM_TOKEN", runtime_token)
    monkeypatch.delenv("RUNTIME_API_URL", raising=False)
    for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.delenv(name, raising=False)

    original_async_client = httpx.AsyncClient
    platform_transport = httpx.ASGITransport(app=platform_main.app)
    runtime_transport = httpx.ASGITransport(app=runtime_api.app)
    run_started = asyncio.Event()
    runtime_tasks: list[asyncio.Task] = []
    received_contracts: list[dict[str, object]] = []

    async def hold_runtime_before_pipeline(request) -> None:
        received_contracts.append(request.model_dump(mode="json"))
        current_task = asyncio.current_task()
        assert current_task is not None
        runtime_tasks.append(current_task)
        run_started.set()
        await asyncio.Event().wait()

    class RuntimeHttpClient:
        def __init__(self, *, timeout: float) -> None:
            self.client = original_async_client(
                transport=runtime_transport,
                base_url="http://runtime.test",
                timeout=timeout,
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info) -> None:
            await self.client.aclose()

        async def get(self, *args, **kwargs):
            return await self.client.get(*args, **kwargs)

        async def post(self, *args, **kwargs):
            return await self.client.post(*args, **kwargs)

    for state_name in (
        "_active_sessions",
        "_runtime_sessions",
        "_session_contracts",
        "_session_states",
    ):
        monkeypatch.setattr(runtime_api, state_name, {})
    monkeypatch.setattr(runtime_api, "run_session", hold_runtime_before_pipeline)
    monkeypatch.setattr(
        platform_main,
        "httpx",
        SimpleNamespace(AsyncClient=RuntimeHttpClient),
    )

    try:
        async with platform_main.app.router.lifespan_context(platform_main.app):
            async with runtime_api.app.router.lifespan_context(runtime_api.app):
                async with original_async_client(
                    transport=platform_transport,
                    base_url="http://platform.test",
                ) as platform:
                    agent_response = await platform.post(
                        "/agents",
                        json={
                            "name": "Restart recovery agent",
                            "system_prompt": "Use the original saved prompt.",
                            "voice_id": "recovery-voice",
                        },
                    )
                    assert agent_response.status_code == 201
                    agent = agent_response.json()

                    session_response = await platform.post(
                        "/voice/sessions",
                        json={"agent_id": agent["id"]},
                    )
                    assert session_response.status_code == 201
                    session = session_response.json()
                    assert session["runtime_status"] == "not_configured"

                    # A later Runtime configuration must consume the exact
                    # contract saved when Platform created this session.
                    monkeypatch.setenv("RUNTIME_API_URL", "http://runtime.test")
                    handoff_response = await platform.post(
                        f"/voice/sessions/{session['session_id']}/ensure-running"
                    )
                    assert handoff_response.status_code == 200
                    assert handoff_response.json() == {
                        "session_status": "created",
                        "runtime_status": "accepted",
                    }
                    await asyncio.wait_for(run_started.wait(), timeout=5)

                    # Stop the controlled pre-pipeline task, then model a fresh
                    # Runtime process with empty in-memory session registries.
                    first_task = runtime_tasks[0]
                    first_task.cancel()
                    await asyncio.gather(first_task, return_exceptions=True)
                    for state_name in (
                        "_active_sessions",
                        "_runtime_sessions",
                        "_session_contracts",
                        "_session_states",
                    ):
                        getattr(runtime_api, state_name).clear()

                    run_started.clear()
                    retry_response = await platform.post(
                        f"/voice/sessions/{session['session_id']}/ensure-running"
                    )
                    assert retry_response.status_code == 200
                    assert retry_response.json() == {
                        "session_status": "created",
                        "runtime_status": "accepted",
                    }
                    await asyncio.wait_for(run_started.wait(), timeout=5)

                    assert len(received_contracts) == 2
                    assert received_contracts[0] == received_contracts[1]
                    assert received_contracts[1] == {
                        "session_id": session["session_id"],
                        "conversation_id": session["conversation_id"],
                        "agent_id": agent["id"],
                        "room_name": session["room_name"],
                        "system_prompt": "Use the original saved prompt.",
                        "voice_id": "recovery-voice",
                        "providers": {},
                        "provider_settings": {},
                    }
    finally:
        for task in runtime_tasks:
            if not task.done():
                task.cancel()
        if runtime_tasks:
            await asyncio.gather(*runtime_tasks, return_exceptions=True)


async def _verify_cross_service_session(monkeypatch: pytest.MonkeyPatch) -> None:
    livekit_api = pytest.importorskip("livekit.api")
    livekit_rtc = pytest.importorskip("livekit.rtc")
    frame_processor = pytest.importorskip("pipecat.processors.frame_processor")
    pipecat_frames = pytest.importorskip("pipecat.frames.frames")
    tts_module = pytest.importorskip("pipecat.services.tts_service")
    deepgram_stt = pytest.importorskip("pipecat.services.deepgram.stt")
    openai_llm = pytest.importorskip("pipecat.services.openai.llm")
    cartesia_tts = pytest.importorskip("pipecat.services.cartesia.tts")
    runtime_token = f"acceptance-{uuid4()}"
    monkeypatch.setenv("PLATFORM_RUNTIME_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_PLATFORM_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_API_URL", "http://runtime.test")
    monkeypatch.setenv("RUNTIME_PLATFORM_URL", "http://platform.test")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-only-not-a-provider-credential")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-not-a-provider-credential")
    monkeypatch.setenv("CARTESIA_API_KEY", "test-only-not-a-provider-credential")
    monkeypatch.setenv("CARTESIA_VOICE_ID", "acceptance-test-voice")

    original_async_client = httpx.AsyncClient
    platform_transport = httpx.ASGITransport(app=platform_main.app)
    runtime_transport = httpx.ASGITransport(app=runtime_api.app)

    class PlatformHttpClient:
        """Runtime event HTTP client routed into the real Platform ASGI app."""

        def __init__(self, *, base_url: str, timeout: float) -> None:
            self.client = original_async_client(
                transport=platform_transport,
                base_url=base_url,
                timeout=timeout,
            )

        async def post(self, *args, **kwargs):
            return await self.client.post(*args, **kwargs)

        async def aclose(self) -> None:
            await self.client.aclose()

    class RuntimeHttpClient:
        """Platform handoff HTTP client routed into the real Runtime ASGI app."""

        def __init__(self, *, timeout: float) -> None:
            self.client = original_async_client(
                transport=runtime_transport,
                base_url="http://runtime.test",
                timeout=timeout,
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info) -> None:
            await self.client.aclose()

        async def post(self, *args, **kwargs):
            return await self.client.post(*args, **kwargs)

        async def get(self, *args, **kwargs):
            return await self.client.get(*args, **kwargs)

    monkeypatch.setattr(
        runtime_events_client,
        "httpx",
        SimpleNamespace(AsyncClient=PlatformHttpClient),
    )
    monkeypatch.setattr(
        platform_main,
        "httpx",
        SimpleNamespace(AsyncClient=RuntimeHttpClient),
    )

    input_audio_frame = pipecat_frames.InputAudioRawFrame
    transcription_frame = pipecat_frames.TranscriptionFrame
    audio_received = asyncio.Event()
    tts_started = asyncio.Event()
    assistant_audio_received = asyncio.Event()
    tts_finished = asyncio.Event()
    barge_in_requested = asyncio.Event()
    assistant_audio_frame_count = 0
    generated_tts_frame_count = 0

    class StubSTTService(frame_processor.FrameProcessor):
        class Settings:
            def __init__(self, **values) -> None:
                self.values = values

        def __init__(self, *args, **kwargs) -> None:
            self.initial_transcript_sent = False
            self.barge_in_transcript_sent = False
            super().__init__(*args, **kwargs)

        async def process_frame(self, frame, direction) -> None:
            await frame_processor.FrameProcessor.process_frame(self, frame, direction)
            if isinstance(frame, input_audio_frame):
                audio_received.set()
                transcript = None
                if not self.initial_transcript_sent:
                    self.initial_transcript_sent = True
                    transcript = "synthetic integration transcript"
                elif barge_in_requested.is_set() and not self.barge_in_transcript_sent:
                    self.barge_in_transcript_sent = True
                    transcript = "synthetic barge-in utterance"
                if transcript:
                    await self.push_frame(
                        transcription_frame(
                            transcript,
                            "acceptance-browser",
                            "now",
                            finalized=True,
                        ),
                        direction,
                    )
            await self.push_frame(frame, direction)

    class StubLLMService(frame_processor.FrameProcessor):
        class Settings:
            def __init__(self, **values) -> None:
                self.values = values

        def __init__(self, *args, **kwargs) -> None:
            self.response_sent = False
            super().__init__(*args, **kwargs)

        async def process_frame(self, frame, direction) -> None:
            await super().process_frame(frame, direction)
            await self.push_frame(frame, direction)
            if (
                isinstance(frame, pipecat_frames.LLMContextFrame)
                and not self.response_sent
            ):
                self.response_sent = True
                await self.push_frame(
                    pipecat_frames.LLMFullResponseStartFrame(), direction
                )
                await self.push_frame(
                    pipecat_frames.TextFrame("A synthetic assistant response."),
                    direction,
                )
                await self.push_frame(
                    pipecat_frames.LLMFullResponseEndFrame(), direction
                )

    class StubTTSService(tts_module.TTSService):
        class Settings(cartesia_tts.CartesiaTTSService.Settings):
            def __init__(self, **values) -> None:
                for name in (
                    "model",
                    "language",
                    "generation_config",
                    "pronunciation_dict_id",
                ):
                    values.setdefault(name, None)
                super().__init__(**values)

        def __init__(self, *, api_key: str, settings) -> None:
            super().__init__(sample_rate=24000, settings=settings)

        async def run_tts(self, text: str, context_id: str):
            nonlocal generated_tts_frame_count
            tts_started.set()
            try:
                for frame_index in range(100):
                    generated_tts_frame_count += 1
                    samples = array(
                        "h",
                        (
                            int(
                                5000
                                * math.sin(
                                    2
                                    * math.pi
                                    * 330
                                    * (frame_index * 480 + index)
                                    / 24000
                                )
                            )
                            for index in range(480)
                        ),
                    )
                    yield pipecat_frames.TTSAudioRawFrame(
                        samples.tobytes(), sample_rate=24000, num_channels=1
                    )
                    await asyncio.sleep(0.02)
            finally:
                tts_finished.set()

    monkeypatch.setattr(deepgram_stt, "DeepgramSTTService", StubSTTService)
    monkeypatch.setattr(openai_llm, "OpenAILLMService", StubLLMService)
    monkeypatch.setattr(cartesia_tts, "CartesiaTTSService", StubTTSService)

    browser = livekit_rtc.Room()
    source = livekit_rtc.AudioSource(sample_rate=48000, num_channels=1)
    livekit = livekit_api.LiveKitAPI(
        os.environ["LIVEKIT_URL"].replace("ws", "http", 1),
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )
    room_name = ""
    session_id = ""
    audio_tasks: list[asyncio.Task] = []

    async def receive_agent_audio(track) -> None:
        nonlocal assistant_audio_frame_count
        async for event in livekit_rtc.AudioStream(track):
            if tts_started.is_set() and event.frame.data:
                pcm_samples = array("h", event.frame.data)
                if not pcm_samples or max(map(abs, pcm_samples)) < 200:
                    continue
                assistant_audio_frame_count += 1
                assistant_audio_received.set()

    def on_track_subscribed(track, _publication, _participant) -> None:
        audio_tasks.append(asyncio.create_task(receive_agent_audio(track)))

    async def close_media_clients() -> None:
        with suppress(Exception):
            await asyncio.wait_for(browser.disconnect(), timeout=5)
        for task in audio_tasks:
            task.cancel()
        if audio_tasks:
            await asyncio.wait(audio_tasks, timeout=2)
        with suppress(Exception):
            await asyncio.wait_for(source.aclose(), timeout=5)
        with suppress(Exception):
            await asyncio.wait_for(livekit.aclose(), timeout=5)

    browser.on("track_subscribed", on_track_subscribed)

    async with platform_main.app.router.lifespan_context(platform_main.app):
        async with runtime_api.app.router.lifespan_context(runtime_api.app):
            async with original_async_client(
                transport=platform_transport,
                base_url="http://platform.test",
            ) as platform:
                agent_response = await platform.post(
                    "/agents",
                    json={
                        "name": "Cross-service voice acceptance",
                        "system_prompt": "Respond briefly.",
                        "voice_id": "acceptance-test-voice",
                    },
                )
                assert agent_response.status_code == 201
                agent = agent_response.json()

                session_response = await platform.post(
                    "/voice/sessions", json={"agent_id": agent["id"]}
                )
                assert session_response.status_code == 201
                session = session_response.json()
                session_id = session["session_id"]
                conversation_id = session["conversation_id"]
                room_name = session["room_name"]
                assert session["runtime_status"] == "accepted"
                assert session["connection"]["token"]

                ensure_response = await platform.post(
                    f"/voice/sessions/{session_id}/ensure-running"
                )
                assert ensure_response.status_code == 200
                ensure_state = ensure_response.json()
                assert ensure_state["session_status"] in {"created", "running"}
                assert ensure_state["runtime_status"] in {
                    "starting",
                    "connecting",
                    "running",
                    "listening",
                    "speaking",
                }

                await browser.connect(
                    session["connection"]["url"], session["connection"]["token"]
                )
                participants = await livekit.room.list_participants(
                    livekit_api.ListParticipantsRequest(room=room_name)
                )
                identities = {
                    participant.identity for participant in participants.participants
                }
                assert f"browser-{session_id}" in identities
                agent_identities = [
                    identity
                    for identity in identities
                    if identity.startswith("voice-labs-agent-")
                ]
                assert len(agent_identities) == 1
                track = livekit_rtc.LocalAudioTrack.create_audio_track(
                    "acceptance-tone", source
                )
                await browser.local_participant.publish_track(track)

                async def send_voiced_audio(frame_count: int) -> None:
                    for frame_index in range(frame_count):
                        sample_rate = 48000
                        samples_per_frame = 480
                        offset = frame_index * samples_per_frame
                        samples = array(
                            "h",
                            (
                                int(
                                    8000
                                    * (
                                        0.65
                                        * math.sin(
                                            2
                                            * math.pi
                                            * 125
                                            * (offset + index)
                                            / sample_rate
                                        )
                                        + 0.25
                                        * math.sin(
                                            2
                                            * math.pi
                                            * 250
                                            * (offset + index)
                                            / sample_rate
                                        )
                                        + 0.1
                                        * math.sin(
                                            2
                                            * math.pi
                                            * 375
                                            * (offset + index)
                                            / sample_rate
                                        )
                                    )
                                )
                                for index in range(samples_per_frame)
                            ),
                        )
                        await source.capture_frame(
                            livekit_rtc.AudioFrame(
                                data=samples.tobytes(),
                                sample_rate=sample_rate,
                                num_channels=1,
                                samples_per_channel=samples_per_frame,
                            )
                        )
                        await asyncio.sleep(0.01)

                await send_voiced_audio(30)

                await asyncio.wait_for(audio_received.wait(), timeout=15)
                await asyncio.wait_for(tts_started.wait(), timeout=15)
                try:
                    await asyncio.wait_for(assistant_audio_received.wait(), timeout=10)
                except TimeoutError as error:
                    await close_media_clients()
                    raise AssertionError(
                        "Runtime generated TTS but the browser received no LiveKit audio "
                        f"(generated frames: {generated_tts_frame_count})"
                    ) from error
                try:
                    audio_count_before_barge_in = assistant_audio_frame_count
                    assert audio_count_before_barge_in > 0
                    barge_in_requested.set()
                    await send_voiced_audio(30)

                    for _ in range(150):
                        runtime_response = await platform.get(
                            f"/conversations/{conversation_id}/runtime-state"
                        )
                        runtime_state = runtime_response.json()
                        event_types = [
                            event["event_type"] for event in runtime_state["events"]
                        ]
                        if "AgentSpeechCancelled" in event_types:
                            break
                        await asyncio.sleep(0.1)

                    assert tts_finished.is_set()
                    assert generated_tts_frame_count < 100
                    await asyncio.sleep(0.5)
                    assert (
                        assistant_audio_frame_count <= audio_count_before_barge_in + 20
                    )
                except BaseException:
                    await close_media_clients()
                    raise

                messages = []
                runtime_state = {}
                for _ in range(100):
                    messages_response = await platform.get(
                        f"/conversations/{conversation_id}/messages"
                    )
                    runtime_response = await platform.get(
                        f"/conversations/{conversation_id}/runtime-state"
                    )
                    messages = messages_response.json()
                    runtime_state = runtime_response.json()
                    event_types = {
                        event["event_type"] for event in runtime_state["events"]
                    }
                    if "RuntimeStarted" in event_types and any(
                        message["content"] == "synthetic integration transcript"
                        for message in messages
                    ):
                        break
                    await asyncio.sleep(0.1)

                assert any(
                    message["content"] == "synthetic integration transcript"
                    and message["role"] == "user"
                    for message in messages
                )
                assert "RuntimeStarted" in {
                    event["event_type"] for event in runtime_state["events"]
                }
                lifecycle_events = [
                    event["event_type"] for event in runtime_state["events"]
                ]
                assert "UserInterrupted" in lifecycle_events
                assert lifecycle_events.count("UserInterrupted") == 2
                assert lifecycle_events.count("AgentSpeechStarted") == 1
                assert lifecycle_events.count("AgentSpeechCancelled") == 1
                speech_started = lifecycle_events.index("AgentSpeechStarted")
                speech_cancelled = lifecycle_events.index("AgentSpeechCancelled")
                assert speech_started < speech_cancelled
                started_event = next(
                    event
                    for event in runtime_state["events"]
                    if event["event_type"] == "RuntimeStarted"
                )
                assert started_event["payload"]["room_name"] == room_name
                assert runtime_state["session_status"] == "running"

                await browser.disconnect()
                for _ in range(100):
                    session_response = await platform.get(
                        f"/voice/sessions/{session_id}"
                    )
                    runtime_response = await platform.get(
                        f"/conversations/{conversation_id}/runtime-state"
                    )
                    runtime_state = runtime_response.json()
                    if session_response.json()["status"] == "ended":
                        break
                    await asyncio.sleep(0.1)

                assert session_response.json()["status"] == "ended"
                assert "SessionEnded" in {
                    event["event_type"] for event in runtime_state["events"]
                }
                assert runtime_state["session_status"] == "ended"

    await close_media_clients()
