"""Voicebox adapter tests against a fake local server that mirrors Voicebox's REST API."""

import io
import json
import math
import struct
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_narration import HAVE_FFMPEG, tools  # noqa: F401

from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.tts import TTSError, TTSOptions, VoiceboxProvider, get_tts_provider


def wav_bytes(seconds: float = 0.6, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / rate)))
                          for i in range(int(seconds * rate)))
        w.writeframes(frames)
    return buf.getvalue()


class FakeVoicebox:
    """Minimal stand-in for the Voicebox backend (routes as in backend/routes/*.py)."""

    def __init__(self):
        self.profiles = [{"id": "p-clone", "name": "My Voice", "language": "en", "voice_type": "cloned",
                          "preset_engine": None, "preset_voice_id": None}]
        self.presets = [{"voice_id": "af_heart", "name": "Heart", "gender": "female", "language": "en"},
                        {"voice_id": "hf_alpha", "name": "Alpha", "gender": "female", "language": "hi"}]
        self.speech_requests = []
        self.stream_requests = []
        self.downloaded = True
        self.has_openai_route = True  # False mimics Voicebox 0.5.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _json(self, code, data):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/":
                    return self._json(200, {"message": "voicebox API", "version": "9.9.9"})
                if self.path == "/openapi.json":
                    paths = {"/profiles": {}, "/generate/stream": {}}
                    if fake.has_openai_route:
                        paths["/v1/audio/speech"] = {}
                    return self._json(200, {"paths": paths})
                if self.path == "/profiles":
                    return self._json(200, fake.profiles)
                if self.path == "/profiles/presets/kokoro":
                    return self._json(200, {"engine": "kokoro", "voices": fake.presets})
                self._json(404, {"detail": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/profiles":
                    profile = {"id": f"p-{len(fake.profiles)}", **body}
                    fake.profiles.append(profile)
                    return self._json(200, profile)
                if self.path == "/v1/audio/speech":
                    fake.speech_requests.append(body)
                    if not any(p["id"] == body.get("voice") for p in fake.profiles):
                        return self._json(400, {"error": {"message": f"Voice '{body.get('voice')}' is not a "
                                                                     "Voicebox voice profile.", "code": "voice_not_found"}})
                    if not fake.downloaded:
                        return self._json(400, {"error": {"message": "The model for 'kokoro' (engine 'kokoro') is "
                                                                     "not downloaded yet.", "code": "model_not_downloaded"}})
                    audio = wav_bytes(max(len(body["input"].split()) / 2.5, 0.5))
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(audio)))
                    self.end_headers()
                    self.wfile.write(audio)
                    return
                if self.path == "/generate/stream":
                    fake.stream_requests.append(body)
                    audio = wav_bytes(0.5)
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(audio)))
                    self.end_headers()
                    self.wfile.write(audio)
                    return
                self._json(404, {"detail": "not found"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake():
    server = FakeVoicebox()
    yield server
    server.close()


def test_refuses_remote_urls_and_bad_urls():
    with pytest.raises(TTSError, match="not on this machine"):
        VoiceboxProvider("http://voice.example.com:17493")
    with pytest.raises(TTSError, match="invalid"):
        VoiceboxProvider("ftp://127.0.0.1")
    remote = VoiceboxProvider("http://voice.example.com", allow_remote=True)
    assert remote.sends_data_externally
    assert not VoiceboxProvider().sends_data_externally


def test_unreachable_app_has_a_clear_error():
    with pytest.raises(TTSError, match="is the Voicebox app open"):
        VoiceboxProvider("http://127.0.0.1:9").version()


def test_version_and_voice_listing(fake):
    p = VoiceboxProvider(fake.url)
    assert p.version() == "voicebox 9.9.9 / kokoro"
    names = [v.name for v in p.list_voices()]
    assert names == ["My Voice", "kokoro:af_heart", "kokoro:hf_alpha"]


def test_kokoro_preset_profile_is_created_once_and_cleared(fake):
    p = VoiceboxProvider(fake.url)
    c = p.voice_clearance("kokoro:af_heart")
    assert c.cleared and "Apache-2.0" in c.note
    assert len(fake.profiles) == 2
    created = fake.profiles[-1]
    assert (created["voice_type"], created["preset_engine"], created["preset_voice_id"]) == ("preset", "kokoro", "af_heart")
    p.resolve_profile("kokoro:af_heart")
    assert len(fake.profiles) == 2  # reused, not duplicated
    with pytest.raises(TTSError, match="no preset voice"):
        p.resolve_profile("kokoro:nope")


def test_cloned_and_unreviewed_engines_are_not_cleared(fake):
    assert not VoiceboxProvider(fake.url).voice_clearance("my voice").cleared  # name match is case-insensitive
    assert "consent" in VoiceboxProvider(fake.url).voice_clearance("My Voice").note
    other = VoiceboxProvider(fake.url, engine="chatterbox")
    assert not other.commercial_use_cleared and "no reviewed model licence" in other.license_note
    with pytest.raises(TTSError, match="no voice profile"):
        VoiceboxProvider(fake.url).resolve_profile("Nobody")


def test_synthesize_posts_openai_style_request_and_writes_wav(fake, tmp_path):
    out = tmp_path / "o.wav"
    VoiceboxProvider(fake.url).synthesize("Hello there, this is a test.", "kokoro:af_heart", out, TTSOptions())
    assert out.read_bytes()[:4] == b"RIFF"
    req = fake.speech_requests[-1]
    assert req["model"] == "kokoro" and req["response_format"] == "wav" and req["voice"] == fake.profiles[-1]["id"]
    assert req["input"] == "Hello there, this is a test."


def test_synthesize_surfaces_voicebox_errors(fake, tmp_path):
    fake.downloaded = False
    with pytest.raises(TTSError, match="not downloaded yet"):
        VoiceboxProvider(fake.url).synthesize("Hi.", "kokoro:af_heart", tmp_path / "o.wav", TTSOptions())
    with pytest.raises(TTSError, match="empty"):
        VoiceboxProvider(fake.url).synthesize("  ", "kokoro:af_heart", tmp_path / "o.wav", TTSOptions())
    with pytest.raises(TTSError, match="at most"):
        VoiceboxProvider(fake.url).synthesize("x" * 10_001, "kokoro:af_heart", tmp_path / "o.wav", TTSOptions())


def test_registry_uses_config(fake):
    from reckoning_pipeline.config import load_config
    p = get_tts_provider("voicebox", load_config({"PIPELINE_VOICEBOX_URL": fake.url}))
    assert p.base_url == fake.url and p.engine == "kokoro"
    with pytest.raises(TTSError, match="not on this machine"):
        get_tts_provider("voicebox", load_config({"PIPELINE_VOICEBOX_URL": "http://1.2.3.4:17493"}))


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_narration_build_with_kokoro_preset_is_publishable_after_review(demo, tools, fake):
    p = VoiceboxProvider(fake.url)
    built = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=p, voice="kokoro:af_heart", scene_ids=["s04-review-gates"]))
    chunk = built.report.chunks[0]
    assert chunk.route == "tts" and chunk.sample_rate == 48000  # 24 kHz Kokoro output normalized
    result = validate_project(demo)
    assert result.ok
    a = next(x for x in result.registry.assets if x.asset_id == "narr-s04-review-gates")
    assert (a.commercial_use, a.publication_status) == ("allowed", "pending_review")
    assert a.generation.provider == "voicebox" and a.generation.model == "kokoro:af_heart"
    assert a.generation.model_version == "voicebox 9.9.9 / kokoro"
    assert "Apache-2.0" in a.rights_evidence and a.generation.terms_url.endswith("Kokoro-82M")


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_narration_build_with_cloned_voice_is_blocked(demo, tools, fake):
    build_narration(validate_project(demo), tools,
                    BuildOptions(provider=VoiceboxProvider(fake.url), voice="My Voice", scene_ids=["s04-review-gates"]))
    a = next(x for x in validate_project(demo).registry.assets if x.asset_id == "narr-s04-review-gates")
    assert (a.commercial_use, a.publication_status) == ("not_allowed", "blocked")
    assert "consent" in a.notes


def test_cli_voices_with_fake_server(runner_env, fake, monkeypatch):
    runner, app, cli = runner_env
    monkeypatch.setenv("PIPELINE_VOICEBOX_URL", fake.url)
    r = runner.invoke(app, ["narration", "voices", "--provider", "voicebox", "--locale", "hi"])
    assert r.exit_code == cli.EXIT_OK and "kokoro:hf_alpha" in r.output and "af_heart" not in r.output


def test_voicebox_050_uses_generate_stream(fake, tmp_path):
    fake.has_openai_route = False
    out = tmp_path / "o.wav"
    VoiceboxProvider(fake.url).synthesize("Hello from an older Voicebox.", "kokoro:af_heart", out, TTSOptions())
    assert out.read_bytes()[:4] == b"RIFF" and fake.speech_requests == []
    req = fake.stream_requests[-1]
    assert req["engine"] == "kokoro" and req["text"] == "Hello from an older Voicebox." and req["seed"] == 0
    assert req["profile_id"] == fake.profiles[-1]["id"] and req["language"] == "en"
