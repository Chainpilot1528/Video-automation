import json
import platform
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import edit_json

from reckoning_pipeline.assets import apply_intake, plan_intake
from reckoning_pipeline.config import load_config
from reckoning_pipeline.media.audio import (
    MediaError, Tools, detect_silence, measure_loudness, normalize_audio, probe_audio,
)
from reckoning_pipeline.media.tools import find_tool
from reckoning_pipeline.narration import (
    BuildOptions, NarrationError, build_narration, latest_take, plan_build, take_asset_id,
)
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.tts import MacSayProvider, TTSOptions
from reckoning_pipeline.schemas.narration import PronunciationList

HAVE_FFMPEG = find_tool("ffmpeg") is not None and find_tool("ffprobe") is not None
HAVE_SAY = platform.system() == "Darwin" and shutil.which("say") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
needs_say = pytest.mark.skipif(not HAVE_SAY, reason="macOS 'say' not available")


@pytest.fixture
def tools():
    if not HAVE_FFMPEG:
        pytest.skip("FFmpeg not installed")
    return Tools.from_config(load_config({}))


def tone(tools, path: Path, seconds: float, *, lead: float = 0.0, tail: float = 0.0, rate: int = 44100,
         channels: int = 2, volume: float = 0.3) -> Path:
    """A synthetic 'recording': silence, a sine tone, silence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    filt = f"volume={volume},adelay={int(lead * 1000)}:all=1,apad=pad_dur={tail}"
    subprocess.run([tools.ffmpeg, "-nostdin", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"sine=f=220:d={seconds}:sample_rate={rate}", "-af", filt, "-ac", str(channels), str(path)],
                   check=True)
    return path


def import_take(demo, tools, scene_id, seconds, take=1, tmp=None, **kw):
    src = tone(tools, (tmp or demo.parent) / f"{scene_id}-t{take}.wav", seconds, **kw)
    result = validate_project(demo)
    fields = {"asset_id": take_asset_id(scene_id, take), "type": "narration", "creation_method": "recorded",
              "creator": "Test Narrator", "rights_holder": "Test Narrator", "commercial_use": "allowed",
              "attribution_required": False, "derivatives_allowed": True, "rights_evidence": "recorded for test",
              "intended_scene_ids": [scene_id]}
    apply_intake(demo, result.manifest, result.registry, plan_intake(demo, result.registry, src, fields))
    return src


def words_seconds(demo, scene_id, wpm=150):
    text = next(s["narration_text"] for s in json.loads((demo / "scenes.json").read_text())["scenes"]
                if s["scene_id"] == scene_id)
    return len(text.split()) / wpm * 60


# --- media helpers -----------------------------------------------------------

def test_probe_normalize_measure(tools, tmp_path):
    src = tone(tools, tmp_path / "a.wav", 2.0, lead=0.5, tail=0.8)
    info = probe_audio(tools, src)
    assert (info.sample_rate, info.channels) == (44100, 2)
    assert info.duration_seconds == pytest.approx(3.3, abs=0.02)
    out = tmp_path / "n.wav"
    normalize_audio(tools, src, out, sample_rate=48000)
    n = probe_audio(tools, out)
    assert (n.sample_rate, n.channels, n.codec) == (48000, 1, "pcm_s16le")
    assert n.duration_seconds == pytest.approx(info.duration_seconds, abs=0.02)
    s = detect_silence(tools, out, n.duration_seconds)
    assert s.leading_seconds == pytest.approx(0.5, abs=0.05)
    assert s.trailing_seconds == pytest.approx(0.8, abs=0.05)
    loud = measure_loudness(tools, out)
    assert loud.integrated_lufs is not None and loud.true_peak_dbtp < 0


def test_normalize_is_deterministic(tools, tmp_path):
    src = tone(tools, tmp_path / "a.wav", 1.0)
    normalize_audio(tools, src, tmp_path / "1.wav", sample_rate=48000)
    normalize_audio(tools, src, tmp_path / "2.wav", sample_rate=48000)
    assert (tmp_path / "1.wav").read_bytes() == (tmp_path / "2.wav").read_bytes()


def test_probe_rejects_non_audio(tools, tmp_path):
    f = tmp_path / "x.wav"
    f.write_text("not audio")
    with pytest.raises(MediaError):
        probe_audio(tools, f)


# --- pronunciations ----------------------------------------------------------

def test_pronunciations_longest_first_and_word_boundaries():
    p = PronunciationList(overrides=[{"term": "Delhi", "say_as": "Delly"},
                                     {"term": "New Delhi", "say_as": "Noo Delly"},
                                     {"term": "AI", "say_as": "A. I.", "case_sensitive": True}])
    assert p.apply("New Delhi and Delhi, not Delhite; AI not ai or MAIN") == \
        "Noo Delly and Delly, not Delhite; A. I. not ai or MAIN"


def test_pronunciations_reject_duplicates():
    with pytest.raises(ValueError):
        PronunciationList(overrides=[{"term": "Ladakh", "say_as": "a"}, {"term": "ladakh", "say_as": "b"}])


# --- build: imported narration ----------------------------------------------

def test_imported_narration_is_normalized_measured_and_cached(demo, tools, tmp_path):
    sid = "s02-claim-ledger"
    import_take(demo, tools, sid, words_seconds(demo, sid), lead=0.2, tail=0.3, tmp=tmp_path)
    built = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid]))
    chunk = built.report.chunks[0]
    assert chunk.route == "imported" and not chunk.cached and chunk.sample_rate == 48000
    assert chunk.warnings == []

    result = validate_project(demo)
    assert result.ok, [str(i) for i in result.issues]
    scene = next(s for s in result.scenes.scenes if s.scene_id == sid)
    assert scene.narration_asset_id == "narr-s02-claim-ledger"
    assert scene.actual_narration_duration_seconds == chunk.duration_seconds
    asset = next(a for a in result.registry.assets if a.asset_id == "narr-s02-claim-ledger")
    assert asset.derived_from == "narr-src-s02-claim-ledger-t1"
    assert (asset.creator, asset.commercial_use, asset.publication_status) == (
        "Test Narrator", "allowed", "pending_review")
    assert (demo / "reports/narration.json").is_file()

    again = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid]))
    assert again.report.chunks[0].cached


def test_new_take_rebuilds_and_keeps_old_file(demo, tools, tmp_path):
    sid = "s03-asset-record"
    import_take(demo, tools, sid, words_seconds(demo, sid), tmp=tmp_path)
    first = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid])).report.chunks[0]
    import_take(demo, tools, sid, words_seconds(demo, sid) + 1, take=2, tmp=tmp_path)
    assert latest_take(validate_project(demo).registry, sid).asset_id.endswith("-t2")
    second = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid])).report.chunks[0]
    assert second.path != first.path and not second.cached
    assert (demo / first.path).is_file() and (demo / second.path).is_file()  # nothing overwritten or deleted
    assert second.duration_seconds > first.duration_seconds


def test_narration_change_resets_captions_and_final_duration(demo, tools, tmp_path):
    sid = "s04-review-gates"
    import_take(demo, tools, sid, words_seconds(demo, sid), tmp=tmp_path)
    build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid]))
    edit_json(demo / "scenes.json", lambda d: next(s for s in d["scenes"] if s["scene_id"] == sid).update(
        caption_status="approximate", final_duration_seconds=12.0))
    import_take(demo, tools, sid, words_seconds(demo, sid) + 2, take=2, tmp=tmp_path)
    build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid]))
    scene = next(s for s in validate_project(demo).scenes.scenes if s.scene_id == sid)
    assert scene.caption_status == "none" and scene.final_duration_seconds is None


def test_chunk_warnings(demo, tools, tmp_path):
    sid = "s01-cold-open"
    import_take(demo, tools, sid, 2.0, lead=1.5, tail=2.0, volume=7.9, channels=1,
                tmp=tmp_path)  # sine source is -18 dBFS; mono avoids the downmix gain drop
    warnings = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=[sid])).report.chunks[0].warnings
    text = " ".join(warnings)
    assert "leading silence" in text and "trailing silence" in text
    assert "words/min" in text
    assert "true peak" in text


def test_missing_narration_reported_and_dry_run_writes_nothing(demo, tools):
    before = (demo / "scenes.json").read_text()
    built = build_narration(validate_project(demo), tools, BuildOptions(dry_run=True))
    assert [c.route for c in built.plan] == ["missing"] * 4
    assert built.report.missing == [s for s in ("s01-cold-open", "s02-claim-ledger", "s03-asset-record",
                                                "s04-review-gates")]
    assert (demo / "scenes.json").read_text() == before
    assert not (demo / "reports/narration.json").exists()


def test_build_errors(demo, tools):
    with pytest.raises(NarrationError, match="unknown scene"):
        plan_build(validate_project(demo), BuildOptions(scene_ids=["nope"]))
    with pytest.raises(NarrationError, match="voice"):
        plan_build(validate_project(demo), BuildOptions(provider=MacSayProvider()))


# --- build: TTS --------------------------------------------------------------

class FakeTTS:
    """Writes a tone instead of speech, so TTS routing is testable anywhere FFmpeg exists."""
    name = "fake-tts"
    sends_data_externally = False
    commercial_use_cleared = True
    license_note = "test provider"
    terms_url = "https://example.org/terms"

    def __init__(self, tools):
        self.tools, self.calls = tools, []

    def version(self):
        return "1.0"

    def list_voices(self):
        return []

    def synthesize(self, text, voice, output_path, options):
        self.calls.append(text)
        tone(self.tools, output_path.with_suffix(".wav"), max(len(text.split()) / 150 * 60, 0.5))
        output_path.with_suffix(".wav").rename(output_path)


def test_tts_route_records_generation_and_uses_pronunciations(demo, tools):
    (demo / "narration").mkdir(exist_ok=True)
    (demo / "narration/pronunciations.json").write_text(json.dumps(
        {"schema_version": "1.0", "overrides": [{"term": "unverified", "say_as": "un-VERR-ified"}]}))
    tts = FakeTTS(tools)
    built = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v1"))
    assert len(built.report.chunks) == 4 and len(tts.calls) == 4
    assert any("un-VERR-ified" in c for c in tts.calls)
    result = validate_project(demo)
    assert result.ok
    a = next(x for x in result.registry.assets if x.asset_id == "narr-s02-claim-ledger")
    assert a.creation_method == "generated" and a.generation.model == "v1"
    assert "un-VERR-ified" in a.generation.prompt
    # Captions/narration text keep the real spelling.
    assert "un-VERR" not in next(s for s in result.scenes.scenes if s.scene_id == "s02-claim-ledger").narration_text

    built = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v1"))
    assert all(c.cached for c in built.report.chunks) and len(tts.calls) == 4
    build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v2"))
    assert len(tts.calls) == 8  # voice change invalidates every scene


def test_imported_take_wins_over_tts(demo, tools, tmp_path):
    sid = "s01-cold-open"
    import_take(demo, tools, sid, words_seconds(demo, sid), tmp=tmp_path)
    tts = FakeTTS(tools)
    built = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v1"))
    routes = {c.scene_id: c.route for c in built.report.chunks}
    assert routes[sid] == "imported" and len(tts.calls) == 3


@needs_say
def test_macos_say_output_is_blocked_from_publication(demo, tools):
    built = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=MacSayProvider(), voice="Samantha", scene_ids=["s04-review-gates"]))
    assert built.report.chunks[0].duration_seconds > 1
    a = next(x for x in validate_project(demo).registry.assets if x.asset_id == "narr-s04-review-gates")
    assert (a.commercial_use, a.publication_status) == ("not_allowed", "blocked")


@needs_say
def test_say_treats_text_as_text(tmp_path):
    out = tmp_path / "s.aiff"
    MacSayProvider().synthesize("-o /tmp/evil.aiff hello", "Samantha", out, TTSOptions())
    assert out.stat().st_size > 0
    assert not Path("/tmp/evil.aiff").exists() or Path("/tmp/evil.aiff").stat().st_mtime < out.stat().st_mtime - 60


def test_normalize_tempo_changes_duration_not_sample_rate(tools, tmp_path):
    src = tone(tools, tmp_path / "a.wav", 2.0)
    normalize_audio(tools, src, tmp_path / "slow.wav", sample_rate=48000, tempo=0.8)
    info = probe_audio(tools, tmp_path / "slow.wav")
    assert info.duration_seconds == pytest.approx(2.5, abs=0.05) and info.sample_rate == 48000
    with pytest.raises(MediaError, match="tempo"):
        normalize_audio(tools, src, tmp_path / "x.wav", sample_rate=48000, tempo=3.0)


def test_speed_is_part_of_the_tts_cache_key_and_ignored_for_takes(demo, tools, tmp_path):
    tts = FakeTTS(tools)
    sid = "s04-review-gates"
    base = build_narration(validate_project(demo), tools, BuildOptions(provider=tts, voice="v", scene_ids=[sid]))
    slow = build_narration(validate_project(demo), tools,
                           BuildOptions(provider=tts, voice="v", scene_ids=[sid], speed=0.8))
    assert not slow.report.chunks[0].cached and len(tts.calls) == 2
    assert slow.report.chunks[0].duration_seconds == pytest.approx(base.report.chunks[0].duration_seconds / 0.8, abs=0.1)
    asset = next(a for a in validate_project(demo).registry.assets if a.asset_id == f"narr-{sid}")
    assert asset.generation.settings["speed"] == 0.8

    import_take(demo, tools, "s03-asset-record", words_seconds(demo, "s03-asset-record"), tmp=tmp_path)
    take = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=["s03-asset-record"], speed=0.8))
    again = build_narration(validate_project(demo), tools, BuildOptions(scene_ids=["s03-asset-record"]))
    assert again.report.chunks[0].cached  # human recordings never change speed, so speed doesn't affect them
    assert take.report.chunks[0].duration_seconds == again.report.chunks[0].duration_seconds
