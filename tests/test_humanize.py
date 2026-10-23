import pytest
from test_narration import HAVE_FFMPEG, FakeTTS, tools  # noqa: F401
from test_voicebox import fake  # noqa: F401  (fixture: fake Voicebox server)

from reckoning_pipeline.media.audio import detect_silence, probe_audio
from reckoning_pipeline.narration import BuildOptions, build_narration
from reckoning_pipeline.narration.humanize import (
    BEFORE_SHORT_EXTRA, ELLIPSIS_GAP, PARAGRAPH_GAPS, QUESTION_EXTRA, SENTENCE_GAPS, plan_pieces,
    split_sentences,
)
from reckoning_pipeline.narration.styles import get_preset, style_filters
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.tts import TTSOptions, VoiceboxProvider

SID = "s01-cold-open"


def test_split_sentences_keeps_abbreviations_and_ellipses():
    assert split_sentences("Dr. Smith arrived. Was he late? No… he wasn't!") == [
        "Dr. Smith arrived.", "Was he late?", "No…", "he wasn't!"]
    assert split_sentences("One clause, no end") == ["One clause, no end"]
    assert split_sentences("   ") == []


def test_plan_pieces_pauses():
    pieces = plan_pieces("What is death? Some people called it a door. Others disagreed with that idea entirely.\n\nThe Stoics practised it every single morning. Daily.")
    assert [p.text for p in pieces] == ["What is death?", "Some people called it a door.", "Others disagreed with that idea entirely.",
                                        "The Stoics practised it every single morning.", "Daily."]
    assert pieces[0].gap_after == pytest.approx(SENTENCE_GAPS[0] + QUESTION_EXTRA)  # a question lands
    assert pieces[1].gap_after == SENTENCE_GAPS[1]
    assert pieces[2].gap_after == PARAGRAPH_GAPS[0]                                 # end of paragraph
    assert pieces[3].gap_after == pytest.approx(SENTENCE_GAPS[3] + BEFORE_SHORT_EXTRA)  # a beat before "Daily."
    assert pieces[-1].gap_after == 0.0                                             # the scene hold follows
    assert plan_pieces("Same text. Same plan.") == plan_pieces("Same text. Same plan.")  # deterministic
    assert len({p.tempo for p in plan_pieces("A. B. C. D.")}) > 1                 # gentle drift


def test_short_statements_are_spoken_with_the_next_sentence():
    pieces = plan_pieces("Here's the situation. For three years you believed one thing. Why? Because.\n\nHard work wins.")
    assert [p.text for p in pieces] == ["Here's the situation. For three years you believed one thing.", "Why?", "Because.",
                                        "Hard work wins."]   # questions and a paragraph's last line stay alone


def test_even_pace_lifts_only_drawn_out_pieces():
    from reckoning_pipeline.narration.humanize import EVEN_PACE_MAX, pace_boosts, syllables
    assert syllables("Here's the situation.") == 6 and syllables("One.") == 1
    pieces = plan_pieces("This sentence is long enough to set the pace for the scene. Okay?\n\nAnother long sentence sets a steady pace here.")
    boosts = pace_boosts(pieces, [4.2, 1.5, 4.0])
    assert boosts[0] == 1.0 and boosts[2] == 1.0 and boosts[1] == EVEN_PACE_MAX   # capped
    assert pace_boosts(pieces, [4.2, 3.6, 4.0])[1] == pytest.approx(4.2 * 0.95 / 3.6)  # lifted to 95% of the pace


def test_talking_rhythm_breathes_after_an_ellipsis_and_varies_paragraphs():
    pieces = plan_pieces("He broke every rule… and won anyway.\n\nOne.\n\nTwo.\n\nThree.")
    assert [p.text for p in pieces][:2] == ["He broke every rule…", "and won anyway."]
    assert pieces[0].gap_after == ELLIPSIS_GAP
    assert len({p.gap_after for p in pieces[1:-1]}) > 1                            # paragraph gaps vary


@pytest.mark.skipif(not HAVE_FFMPEG, reason="FFmpeg not installed")
def test_humanized_build_reads_each_sentence_and_adds_pauses(demo, tools):
    tts = FakeTTS(tools)
    plain = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=tts, voice="v", scene_ids=[SID])).report.chunks[0]
    calls_before = len(tts.calls)
    human = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=tts, voice="v", humanize=True, scene_ids=[SID])).report.chunks[0]
    text = next(s.narration_text for s in validate_project(demo).scenes.scenes if s.scene_id == SID)
    sentences = split_sentences(text)
    assert len(tts.calls) - calls_before == len(sentences) > 1     # one request per sentence
    assert tts.calls[calls_before:] == sentences
    assert not human.cached and human.fingerprint != plain.fingerprint
    path = demo / human.path
    info = probe_audio(tools, path)
    pauses = detect_silence(tools, path, info.duration_seconds, noise_db=-50, min_seconds=0.25).internal_gaps
    assert len(pauses) >= len(sentences) - 1                       # a real pause between sentences
    again = build_narration(validate_project(demo), tools,
                            BuildOptions(provider=tts, voice="v", humanize=True, scene_ids=[SID]))
    assert again.report.chunks[0].cached
    a = next(x for x in validate_project(demo).registry.assets if x.asset_id == f"narr-{SID}")
    assert a.generation.settings["humanize"] is True


def test_sage_preset_and_style():
    p = get_preset("sage")
    assert (p.provider, p.voice, p.style, p.humanize) == ("voicebox", "qwen_custom_voice:Ryan", "sage", True)
    assert "narrator" in p.instruct and "not a clone" in p.description
    chain = style_filters("sage")
    assert chain.startswith("highpass=f=60,lowshelf=f=170:g=7") and chain.index("lowshelf") < chain.index("deesser")
    assert not get_preset("reckoner").humanize and get_preset("reckoner").instruct == ""


# --- Qwen3 CustomVoice through Voicebox -------------------------------------------

def add_qwen(fake):
    fake.engine_presets = {"qwen_custom_voice": [{"voice_id": "Ryan", "name": "Ryan", "gender": "male",
                                                  "language": "en"}]}


def test_qwen_voice_uses_native_endpoint_with_size_and_instruction(fake, tmp_path):
    add_qwen(fake)
    p = VoiceboxProvider(fake.url)  # default engine kokoro; the voice name picks qwen
    assert p.engine_for("qwen_custom_voice:Ryan") == "qwen_custom_voice" and p.engine_for("kokoro:x") == "kokoro"
    out = tmp_path / "q.wav"
    p.synthesize("A calm line.", "qwen_custom_voice:Ryan", out, TTSOptions(extra={"instruct": "calm, deep"}))
    assert out.read_bytes()[:4] == b"RIFF" and fake.speech_requests == []
    req = fake.stream_requests[-1]
    assert (req["engine"], req["model_size"], req["instruct"]) == ("qwen_custom_voice", "0.6B", "calm, deep")
    created = fake.profiles[-1]
    assert (created["preset_engine"], created["preset_voice_id"]) == ("qwen_custom_voice", "Ryan")
    c = p.voice_clearance("qwen_custom_voice:Ryan")
    assert c.cleared and "Apache-2.0" in c.note and "Qwen3-TTS" in c.terms_url


def test_voice_listing_includes_qwen_and_tolerates_older_voicebox(fake):
    names = [v.name for v in VoiceboxProvider(fake.url).list_voices()]
    assert "kokoro:af_heart" in names and not any(n.startswith("qwen") for n in names)  # no qwen route: skipped
    add_qwen(fake)
    assert "qwen_custom_voice:Ryan" in [v.name for v in VoiceboxProvider(fake.url).list_voices()]


def test_cli_sage_preset_dry_run(runner_env, demo, fake, monkeypatch):
    add_qwen(fake)
    runner, app, cli = runner_env
    monkeypatch.setenv("PIPELINE_VOICEBOX_URL", fake.url)
    r = runner.invoke(app, ["narration", "build", str(demo), "--preset", "sage", "--dry-run"])
    assert r.exit_code == cli.EXIT_OK, r.output
    assert "preset sage: qwen_custom_voice:Ryan" in r.output and "humanized" in r.output
