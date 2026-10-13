"""Opt-in real-provider voice acceptance test using a supplied speech recording."""

import asyncio
from difflib import SequenceMatcher
import os
import re
import sys
import wave
from array import array
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

_WORKSPACE = Path(__file__).resolve().parents[1]
_BACKEND = _WORKSPACE.parent / "backend.voice-labs"
for _project in ("platform", "runtime"):
    sys.path.insert(0, str(_BACKEND / _project))

os.environ["PLATFORM_DATABASE_URL"] = os.getenv(
    "PLATFORM_ACCEPTANCE_DATABASE_URL", "sqlite://"
)
os.environ["PLATFORM_AUTO_CREATE_SCHEMA"] = "1"

from src.platform import main as platform_main  # noqa: E402
from src.runtime import api as runtime_api  # noqa: E402
from src.runtime import events_client as runtime_events_client  # noqa: E402

_REQUIRED_ENV = (
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "DEEPGRAM_API_KEY",
    "OPENAI_API_KEY",
    "CARTESIA_API_KEY",
    "CARTESIA_VOICE_ID",
    "VOICE_ACCEPTANCE_AUDIO_FILE",
    "VOICE_ACCEPTANCE_EXPECTED_TRANSCRIPT",
)
_REAL_PROVIDER_OPT_IN = os.getenv("VOICE_ACCEPTANCE_REAL_PROVIDERS") == "1"
_MISSING_CONFIGURATION = [name for name in _REQUIRED_ENV if not os.getenv(name)]
if (
    os.getenv("VOICE_ACCEPTANCE_AUDIO_FILE")
    and not Path(os.environ["VOICE_ACCEPTANCE_AUDIO_FILE"]).is_file()
):
    _MISSING_CONFIGURATION.append(
        "VOICE_ACCEPTANCE_AUDIO_FILE (must name an existing file)"
    )


def _write_test_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(pcm)


def _load_pcm_speech_wav(path: Path) -> tuple[int, int, bytes]:
    with wave.open(str(path), "rb") as recording:
        sample_rate = recording.getframerate()
        channels = recording.getnchannels()
        frame_count = recording.getnframes()
        if recording.getcomptype() != "NONE":
            raise ValueError("input must be uncompressed PCM WAV")
        if recording.getsampwidth() != 2:
            raise ValueError("input must use 16-bit PCM")
        if not 16000 <= sample_rate <= 96000:
            raise ValueError("sample rate must be 16–96 kHz")
        if channels not in {1, 2}:
            raise ValueError("input must be mono or stereo")
        if not sample_rate <= frame_count <= sample_rate * 60:
            raise ValueError("recording must be 1–60 seconds")
        audio = recording.readframes(frame_count)

    if len(audio) != frame_count * channels * 2:
        raise ValueError("recording is truncated")
    if not any(array("h", audio)):
        raise ValueError("recording contains only digital silence")
    return sample_rate, channels, audio


def _transcript_match_ratio(expected: str, observed: str) -> float:
    expected_words = re.findall(r"\w+", expected.casefold())
    observed_words = re.findall(r"\w+", observed.casefold())
    if not expected_words:
        return 0.0
    matcher = SequenceMatcher(None, expected_words, observed_words, autojunk=False)
    matched_words = sum(block.size for block in matcher.get_matching_blocks())
    return matched_words / len(expected_words)


def test_real_voice_input_accepts_non_silent_pcm_wav(tmp_path: Path) -> None:
    path = tmp_path / "speech.wav"
    _write_test_wav(path, array("h", [1200] * 16000).tobytes())

    sample_rate, channels, audio = _load_pcm_speech_wav(path)

    assert sample_rate == 16000
    assert channels == 1
    assert len(audio) == 32000


def test_real_voice_input_rejects_silent_wav_before_provider_calls(
    tmp_path: Path,
) -> None:
    path = tmp_path / "silent.wav"
    _write_test_wav(path, bytes(32000))

    with pytest.raises(ValueError, match="digital silence"):
        _load_pcm_speech_wav(path)


def test_real_voice_input_rejects_truncated_wav_before_provider_calls(
    tmp_path: Path,
) -> None:
    path = tmp_path / "truncated.wav"
    _write_test_wav(path, array("h", [1200] * 16000).tobytes())
    path.write_bytes(path.read_bytes()[:-2])

    with pytest.raises(ValueError, match="truncated"):
        _load_pcm_speech_wav(path)


def test_transcript_matching_tolerates_surrounding_words_but_measures_reference() -> (
    None
):
    assert (
        _transcript_match_ratio("a quick brown fox", "well a quick brown fox today")
        == 1.0
    )
    assert _transcript_match_ratio("the quick brown fox", "the slow brown fox") == 0.75


@pytest.mark.skipif(
    not _REAL_PROVIDER_OPT_IN,
    reason="Set VOICE_ACCEPTANCE_REAL_PROVIDERS=1 to opt into billable real-provider calls",
)
def test_real_speech_completes_provider_backed_voice_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if _MISSING_CONFIGURATION:
        pytest.fail(
            "Real-provider acceptance was explicitly requested, but configuration is "
            f"missing: {', '.join(_MISSING_CONFIGURATION)}"
        )
    asyncio.run(_verify_real_provider_session(monkeypatch))


async def _verify_real_provider_session(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        from livekit import rtc as livekit_rtc
    except ImportError as exc:
        raise RuntimeError(
            "install the LiveKit RTC dependency to run real-provider acceptance"
        ) from exc
    runtime_token = f"real-provider-{uuid4()}"
    monkeypatch.setenv("PLATFORM_RUNTIME_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_PLATFORM_TOKEN", runtime_token)
    monkeypatch.setenv("RUNTIME_API_URL", "http://runtime.test")
    monkeypatch.setenv("RUNTIME_PLATFORM_URL", "http://platform.test")

    audio_path = Path(os.environ["VOICE_ACCEPTANCE_AUDIO_FILE"])
    expected_transcript = " ".join(
        re.findall(
            r"\w+", os.environ["VOICE_ACCEPTANCE_EXPECTED_TRANSCRIPT"].casefold()
        )
    )
    if len(expected_transcript.split()) < 4:
        raise AssertionError(
            "expected transcript reference must contain at least four words"
        )
    sample_rate, channels, audio = _load_pcm_speech_wav(audio_path)

    original_async_client = httpx.AsyncClient
    platform_transport = httpx.ASGITransport(app=platform_main.app)
    runtime_transport = httpx.ASGITransport(app=runtime_api.app)

    class PlatformHttpClient:
        """Route authenticated Runtime events to the Platform ASGI application."""

        def __init__(self, *, base_url: str, timeout: float) -> None:
            self.client = original_async_client(
                transport=platform_transport,
                base_url=base_url,
                timeout=timeout,
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info) -> None:
            await self.client.aclose()

        async def post(self, *args, **kwargs):
            return await self.client.post(*args, **kwargs)

        async def aclose(self) -> None:
            await self.client.aclose()

    class RuntimeHttpClient:
        """Route Platform handoff and health requests to the Runtime ASGI app."""

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

    monkeypatch.setattr(
        runtime_events_client,
        "httpx",
        SimpleNamespace(AsyncClient=PlatformHttpClient),
    )
    monkeypatch.setattr(
        platform_main,
        "httpx",
        SimpleNamespace(AsyncClient=RuntimeHttpClient, HTTPError=httpx.HTTPError),
    )

    browser = livekit_rtc.Room()
    source = livekit_rtc.AudioSource(sample_rate=sample_rate, num_channels=channels)
    output_audio_received = asyncio.Event()
    output_tasks: list[asyncio.Task] = []
    session_id = ""
    conversation_id = ""
    runtime_identity = ""

    async def receive_agent_audio(track, participant) -> None:
        if participant.identity != runtime_identity:
            return
        async for event in livekit_rtc.AudioStream(track):
            if event.frame.data and max(map(abs, array("h", event.frame.data))) > 100:
                output_audio_received.set()

    def on_track_subscribed(track, _publication, participant) -> None:
        output_tasks.append(
            asyncio.create_task(receive_agent_audio(track, participant))
        )

    browser.on("track_subscribed", on_track_subscribed)

    async def send_recording() -> None:
        samples_per_frame = max(1, sample_rate // 100)
        bytes_per_frame = samples_per_frame * channels * 2
        for offset in range(0, len(audio), bytes_per_frame):
            frame_data = audio[offset : offset + bytes_per_frame]
            samples = len(frame_data) // (channels * 2)
            if not samples:
                continue
            await source.capture_frame(
                livekit_rtc.AudioFrame(
                    data=frame_data,
                    sample_rate=sample_rate,
                    num_channels=channels,
                    samples_per_channel=samples,
                )
            )
            await asyncio.sleep(samples / sample_rate)

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
                            "name": "Real-provider acceptance",
                            "system_prompt": "Respond with the single word FIVE.",
                            "voice_id": os.environ["CARTESIA_VOICE_ID"],
                        },
                    )
                    assert agent_response.status_code == 201, agent_response.text
                    agent = agent_response.json()
                    session_response = await platform.post(
                        "/voice/sessions", json={"agent_id": agent["id"]}
                    )
                    assert session_response.status_code == 201, session_response.text
                    session = session_response.json()
                    session_id = session["session_id"]
                    conversation_id = session["conversation_id"]
                    room_name = session["room_name"]
                    runtime_identity = os.getenv(
                        "RUNTIME_IDENTITY", f"voice-labs-agent-{room_name}"
                    )
                    assert session["runtime_status"] == "accepted"

                    await browser.connect(
                        session["connection"]["url"], session["connection"]["token"]
                    )
                    input_track = livekit_rtc.LocalAudioTrack.create_audio_track(
                        "real-speech-recording", source
                    )
                    await browser.local_participant.publish_track(input_track)

                    ready_deadline = asyncio.get_running_loop().time() + 30
                    while asyncio.get_running_loop().time() < ready_deadline:
                        state_response = await platform.get(
                            f"/conversations/{conversation_id}/runtime-state"
                        )
                        assert state_response.status_code == 200
                        runtime_state = state_response.json()
                        started_event = next(
                            (
                                event
                                for event in runtime_state["events"]
                                if event["event_type"] == "RuntimeStarted"
                            ),
                            None,
                        )
                        if started_event:
                            assert started_event["payload"]["room_name"] == room_name
                            break
                        if runtime_state["session_status"] in {"failed", "ended"}:
                            raise AssertionError(
                                f"Runtime did not join the session room: {runtime_state}"
                            )
                        await asyncio.sleep(0.2)
                    else:
                        raise AssertionError(
                            "Runtime did not join the session room before audio playback"
                        )

                    await send_recording()

                    deadline = asyncio.get_running_loop().time() + 120
                    messages = []
                    runtime_state = {}
                    while asyncio.get_running_loop().time() < deadline:
                        messages_response = await platform.get(
                            f"/conversations/{conversation_id}/messages"
                        )
                        state_response = await platform.get(
                            f"/conversations/{conversation_id}/runtime-state"
                        )
                        assert messages_response.status_code == 200
                        assert state_response.status_code == 200
                        messages = messages_response.json()
                        runtime_state = state_response.json()
                        user_messages = [
                            item for item in messages if item["role"] == "user"
                        ]
                        assistant_messages = [
                            item
                            for item in messages
                            if item["role"] == "assistant" and item["content"].strip()
                        ]
                        observed_transcript = " ".join(
                            re.findall(
                                r"\w+",
                                " ".join(
                                    item["content"] for item in user_messages
                                ).casefold(),
                            )
                        )
                        event_types = {
                            event["event_type"] for event in runtime_state["events"]
                        }
                        events = runtime_state["events"]
                        transcript_events = [
                            event
                            for event in events
                            if event["event_type"] == "TranscriptFinal"
                        ]
                        user_transcript_events = [
                            event
                            for event in transcript_events
                            if event["payload"].get("role") == "user"
                        ]
                        assistant_transcript_events = [
                            event
                            for event in transcript_events
                            if event["payload"].get("role") == "assistant"
                        ]
                        ordered_event_types = [event["event_type"] for event in events]
                        if (
                            _transcript_match_ratio(
                                expected_transcript, observed_transcript
                            )
                            >= 0.8
                            and assistant_messages
                            and "five"
                            in " ".join(
                                re.findall(
                                    r"\w+",
                                    assistant_messages[0]["content"].casefold(),
                                )
                            )
                            and "RuntimeStarted" in event_types
                            and "TranscriptFinal" in event_types
                            and "AgentSpeechStarted" in event_types
                            and "TurnCompleted" in event_types
                            and user_transcript_events
                            and assistant_transcript_events
                            and ordered_event_types.index("RuntimeStarted")
                            < ordered_event_types.index("TranscriptFinal")
                            < ordered_event_types.index("AgentSpeechStarted")
                            < ordered_event_types.index("TurnCompleted")
                            and output_audio_received.is_set()
                        ):
                            break
                        if runtime_state["session_status"] in {"failed", "ended"}:
                            raise AssertionError(
                                f"Runtime terminated before producing a response: {runtime_state}"
                            )
                        await asyncio.sleep(0.25)
                    else:
                        raise AssertionError(
                            "Timed out waiting for expected real STT transcript, LLM reply, "
                            "authenticated Runtime events, and audible TTS output"
                        )

                    started_event = next(
                        event
                        for event in runtime_state["events"]
                        if event["event_type"] == "RuntimeStarted"
                    )
                    assert started_event["payload"]["room_name"] == room_name
                    event_transcript = " ".join(
                        event["payload"]["content"] for event in user_transcript_events
                    )
                    assert (
                        _transcript_match_ratio(expected_transcript, event_transcript)
                        >= 0.8
                    )
                    assert "five" in " ".join(
                        re.findall(
                            r"\w+",
                            " ".join(
                                event["payload"]["content"]
                                for event in assistant_transcript_events
                            ).casefold(),
                        )
                    )
                    assert "five" in " ".join(
                        re.findall(r"\w+", assistant_messages[0]["content"].casefold())
                    )
                    assert runtime_state["session_status"] in {
                        "running",
                        "listening",
                        "speaking",
                    }

                    await browser.disconnect()
                    ended_deadline = asyncio.get_running_loop().time() + 20
                    while asyncio.get_running_loop().time() < ended_deadline:
                        persisted = await platform.get(f"/voice/sessions/{session_id}")
                        state_response = await platform.get(
                            f"/conversations/{conversation_id}/runtime-state"
                        )
                        runtime_state = state_response.json()
                        if persisted.json()["status"] == "ended":
                            break
                        await asyncio.sleep(0.1)
                    assert persisted.json()["status"] == "ended"
                    assert "SessionEnded" in {
                        event["event_type"] for event in runtime_state["events"]
                    }
    finally:
        with suppress(Exception):
            await asyncio.wait_for(browser.disconnect(), timeout=5)
        for task in output_tasks:
            task.cancel()
        if output_tasks:
            await asyncio.gather(*output_tasks, return_exceptions=True)
        with suppress(Exception):
            await asyncio.wait_for(source.aclose(), timeout=5)
