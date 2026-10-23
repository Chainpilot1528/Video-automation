from pathlib import Path

import pytest
from conftest import edit_json
from test_narration import import_take, needs_ffmpeg, tools, words_seconds  # noqa: F401  (fixture reuse)

from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.subtitles import CaptionError, WordTiming, build_captions, check_cues, parse_srt, to_srt
from reckoning_pipeline.subtitles.srt import (
    MAX_LINE_CHARS, Cue, SceneSpan, aligned_cues, approximate_cues, format_timestamp, layout, parse_timestamp,
    segment,
)

LONG = ("Every visual carries its paperwork: who made it, under what licence, and a checksum that flags "
        "a changed file before it reaches a render. Short one.")


def test_timestamps_round_trip():
    assert format_timestamp(3725.4567) == "01:02:05,457"
    assert parse_timestamp("01:02:05,457") == pytest.approx(3725.457)
    with pytest.raises(ValueError):
        parse_timestamp("1:2:3.4")


def test_segment_respects_sentence_and_line_limits():
    pieces = segment(LONG)
    assert pieces[-1].endswith("Short one.")   # a two-word sentence joins its neighbour instead of flashing by
    for p in pieces:
        lines = layout(p).split("\n")
        assert len(lines) <= 2 and all(len(line) <= MAX_LINE_CHARS for line in lines)
    assert " ".join(pieces) == " ".join(LONG.split())


def test_segment_long_unbroken_text():
    text = " ".join(["word"] * 60)
    pieces = segment(text)
    assert len(pieces) > 1 and " ".join(pieces) == text


def test_approximate_cues_fill_speech_span_in_order():
    span = SceneSpan("s1", LONG, offset=10.0, speech_start=0.4, speech_end=9.4)
    cues = approximate_cues(span)
    assert cues[0].start == pytest.approx(10.4) and cues[-1].end == pytest.approx(19.4)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:]))
    assert check_cues(cues)[0] == []


def test_aligned_cues_follow_word_timings():
    span = SceneSpan("s1", "One two three. Four five six.", offset=5.0, speech_start=0, speech_end=3)
    words = [WordTiming(w, i * 0.5, i * 0.5 + 0.4) for i, w in enumerate("One two three. Four five six.".split())]
    cues = aligned_cues(span, words)
    assert [(c.start, c.end) for c in cues] == [(5.0, 6.4), (6.5, 7.9)]
    with pytest.raises(ValueError, match="words"):
        aligned_cues(span, words[:-1])


def test_tiny_pieces_join_a_neighbour():
    assert segment("Or… you could decide. Why? Because it was fine.") == ["Or… you could decide.", "Why? Because it was fine."]
    assert segment("It was the longest sentence anyone had heard. Truly.")[-1].endswith("heard. Truly.")


def test_srt_round_trip_and_parse_errors():
    cues = [Cue(0.0, 1.5, "Hello\nthere"), Cue(1.5, 3.0, "Next")]
    assert parse_srt(to_srt(cues)) == cues
    with pytest.raises(ValueError, match="index"):
        parse_srt("2\n00:00:00,000 --> 00:00:01,000\nHi\n")
    with pytest.raises(ValueError, match="timing"):
        parse_srt("1\n00:00:00,000 to 00:00:01,000\nHi\n")


def test_check_cues_errors_and_warnings():
    errors, warnings = check_cues([Cue(0, 2, "ok"), Cue(1.5, 1.0, ""), Cue(3, 3.2, "x" * 50 + "\na\nb")])
    assert any("overlaps" in e for e in errors) and any("ends at or before" in e for e in errors)
    assert any("empty" in e for e in errors)
    joined = " ".join(warnings)
    assert "3 lines" in joined and "longer than" in joined and "only" in joined and "characters/second" in joined


def test_build_captions_requires_current_narration(demo):
    with pytest.raises(CaptionError, match="narration report"):
        build_captions(validate_project(demo))


@needs_ffmpeg
def test_build_captions_end_to_end(demo, tools, tmp_path):
    for sid in ("s01-cold-open", "s02-claim-ledger", "s03-asset-record", "s04-review-gates"):
        import_take(demo, tools, sid, words_seconds(demo, sid), lead=0.25, tail=0.25, tmp=tmp_path)
    report = build_narration(validate_project(demo), tools, BuildOptions()).report
    built = build_captions(validate_project(demo))
    assert built.errors == [] and built.method == "approximate"
    cues = parse_srt(built.path.read_text())
    assert built.path.name == "demo-project.en.srt"
    total = sum(c.duration_seconds for c in report.chunks)
    assert cues[0].start == pytest.approx(report.chunks[0].leading_silence_seconds, abs=0.01)
    assert cues[-1].end <= total + 0.001
    # Each scene's cues stay within that scene's audio on the narration timeline.
    assert cues[-1].end >= total - report.chunks[-1].trailing_silence_seconds - 0.05
    result = validate_project(demo)
    assert result.ok and {s.caption_status for s in result.scenes.scenes} == {"approximate"}

    # Editing narration text after the audio was built does not silently re-time old audio.
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(actual_narration_duration_seconds=99.0))
    with pytest.raises(CaptionError, match="out of date"):
        build_captions(validate_project(demo))
