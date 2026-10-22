"""Kinetic quotes: finding the quote in the narration, word timing, phrase steps, fonts and honesty rules."""

import json

import pytest
from conftest import edit_json
from test_compose import PROFILE, make_composition
from test_narration import HAVE_FFMPEG, FakeTTS, tools  # noqa: F401
from test_render import short_demo, tiny_profiles  # noqa: F401

from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.narration.build import timing_path
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.render.compose import (
    FONT_DIR, PHRASE_FADE, composition_command, expand_reveals, font_env, text_svg,
)
from reckoning_pipeline.schemas.narration import ChunkReport, SentenceTiming
from reckoning_pipeline.schemas.timeline import TimelineLayer
from reckoning_pipeline.timeline.quotes import EVEN_WORDS_PER_SECOND, audio_time, find_quote, word_times

NARRATION = "Epicurus taught one thing. In his words: pleasure is the beginning and end of the blessed life."
QUOTE = "“Pleasure is the beginning and end of the blessed life.”"


def chunk(**kw):
    base = dict(scene_id="s", asset_id="a", route="tts", path="p", sha256="a" * 64, fingerprint="b" * 64,
                cached=False, duration_seconds=10.0, sample_rate=48000, channels=1,
                leading_silence_seconds=0.5, trailing_silence_seconds=0.5)
    return ChunkReport(**{**base, **kw})


def test_find_quote_ignores_case_and_punctuation():
    offsets = find_quote(QUOTE, NARRATION)
    assert offsets is not None and len(offsets) == 10
    assert NARRATION[offsets[0]:].startswith("pleasure") and NARRATION[offsets[-1]:].startswith("life")
    assert find_quote("Not in there at all", NARRATION) is None
    assert find_quote("“ — ”", NARRATION) is None


def test_audio_time_uses_sentence_timings_when_recorded():
    timed = chunk(sentences=[SentenceTiming(text="Epicurus taught one thing.", start=0.2, end=1.8),
                             SentenceTiming(text="In his words: …", start=2.4, end=8.0)])
    second = NARRATION.index("In his")
    assert audio_time(second, NARRATION, timed) == pytest.approx(2.4)
    assert audio_time(len(NARRATION) - 1, NARRATION, timed) == pytest.approx(8.0, abs=0.1)
    # Without sentences: proportional over the measured speech span (0.5 .. 9.5 s).
    assert audio_time(0, NARRATION, chunk()) == pytest.approx(0.5)
    assert audio_time(len(NARRATION), NARRATION, chunk()) == pytest.approx(9.5)


def test_word_times_follow_narration_or_pace_evenly():
    times, warning = word_times(QUOTE, NARRATION, chunk(), lead_in=0.25, beat_start=1.0, layer_start=0.0)
    assert warning is None and len(times) == len(QUOTE.split())
    assert times == sorted(times) and times[0] > 3.0  # the quote is late in the narration
    even, warning = word_times("Know thyself, said the oracle", NARRATION, chunk(), lead_in=0.25, beat_start=0,
                               layer_start=2.0)
    assert warning and "isn't read" in warning
    assert even == [round(2.0 + i / EVEN_WORDS_PER_SECOND, 3) for i in range(5)]
    _, warning = word_times(QUOTE, NARRATION, None, lead_in=0, beat_start=0, layer_start=0)
    assert "no measured narration" in warning


def test_expand_reveals_makes_phrase_steps_on_one_motion_clock():
    text = "One two, three four five six seven. Eight"
    layer = TimelineLayer(kind="text", text=text, text_style="quote", reveal="words", start=1.0, end=12.0,
                          drift_y=-0.02, word_times=[1, 1.4, 2, 2.3, 2.6, 2.9, 3.2, 4.0])
    steps = expand_reveals([layer])
    assert [s.visible_words for s in steps] == [[0, 1], [2, 3, 4, 5], [6], [7]]  # punctuation or 4 words
    assert [s.start for s in steps] == [1.0, 2.0, 3.2, 4.0]
    assert all(s.motion_start == 1.0 and s.motion_end == 12.0 and s.fade_in == PHRASE_FADE for s in steps)
    plain = TimelineLayer(kind="text", text="fade only")
    assert expand_reveals([plain]) == [plain]


def test_hidden_words_keep_their_place():
    layer = TimelineLayer(kind="text", text="a b c d", text_style="quote", width=0.9, visible_words=[1, 2])
    svg = text_svg(layer, PROFILE)
    assert svg.count('fill-opacity="0"') == 2 and ">b <" in svg and ">d<" in svg
    cmd = composition_command("ffmpeg", [layer.model_copy(update={"start": 3, "motion_start": 1, "motion_end": 9,
                                                                  "drift_x": 0.1})],
                              ["l.png"], PROFILE, 10, "o.mp4")
    assert "clip((t-1)/8,0,1)" in cmd[cmd.index("-filter_complex") + 1]  # parent clock, not the step's


def test_bundled_fonts_and_private_font_config(tmp_path):
    assert {p.name for p in FONT_DIR.iterdir()} >= {"CormorantGaramond[wght].ttf",
                                                    "CormorantGaramond-Italic[wght].ttf", "OFL.txt"}
    assert "SIL Open Font License" in (FONT_DIR / "OFL.txt").read_text()
    env = font_env(tmp_path)
    conf = (tmp_path / "fonts.conf").read_text()
    assert env["PANGOCAIRO_BACKEND"] == "fc" and str(FONT_DIR) in conf and env["FONTCONFIG_FILE"].endswith("fonts.conf")


def test_reveal_and_claim_only_on_text_layers():
    from pydantic import ValidationError

    from reckoning_pipeline.schemas.visual import Layer
    with pytest.raises(ValidationError, match="for text layers"):
        Layer(kind="image", asset_id="a", reveal="words")


def quote_layer(demo, **kw):
    make_composition(demo)
    edit_json(demo / "visuals.json", lambda d: next(b for b in d["beats"] if b["beat_id"] == "v01-comp")
              ["layers"][2].update(**kw))


def test_validation_and_qa_require_a_verified_quotation_claim(demo, tools):
    from reckoning_pipeline.qa import run_qa
    quote_layer(demo)
    codes = [i.code for i in validate_project(demo).warnings]
    assert "visual.quote_unsourced" in codes
    quote_layer(demo, claim_id="nope")
    assert "ref.missing_claim" in [i.code for i in validate_project(demo).errors]
    claim = validate_project(demo).ledger.claims[0].claim_id
    quote_layer(demo, claim_id=claim)
    result = validate_project(demo)
    assert "visual.quote_claim_type" in [i.code for i in result.warnings]  # demo claims aren't quotations
    report = run_qa(result, tools, "preview", analyse_media=False)
    assert "visual.quote_unverified" in [k.code for k in report.checks if k.severity == "blocker"]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_humanized_build_records_sentence_timings(demo, tools):
    sid = "s01-cold-open"
    built = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=FakeTTS(tools), voice="v", humanize=True, scene_ids=[sid]))
    c = built.report.chunks[0]
    assert len(c.sentences) >= 2 and all(s.end > s.start for s in c.sentences)
    assert c.sentences[1].start > c.sentences[0].end  # a pause between sentences
    assert timing_path(demo / c.path).is_file()
    again = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=FakeTTS(tools), voice="v", humanize=True, scene_ids=[sid]))
    assert again.report.chunks[0].cached and again.report.chunks[0].sentences == c.sentences  # kept when cached


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_word_reveal_renders_phrase_layers(short_demo, tools):  # noqa: F811
    from reckoning_pipeline.render import render
    quote_layer(short_demo, reveal="words", text="One two, three four five six. Seven", highlight="")
    out = render(validate_project(short_demo, verify_checksums=True), tools, "preview")
    seg = out.plan.scenes[0].segments[0]
    assert len(seg.layers[2].word_times) == 7
    assert any("quote reveal" in w for w in out.plan.warnings)  # silent demo scene: paced evenly
    work = short_demo / "renders/preview/build/s01-cold-open"
    svgs = [json.dumps(p.read_text()) for p in work.glob("layer-*.svg")]
    assert sum("fill-opacity" in s for s in svgs) == 3  # three phrase steps
