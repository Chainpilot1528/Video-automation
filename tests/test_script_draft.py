import io
import json
import urllib.error

import pytest
from conftest import edit_json

from reckoning_pipeline.project import validate_project
from reckoning_pipeline.providers.llm import ProviderUnavailableError
from reckoning_pipeline.providers.llm.voicebox_llm import VoiceboxLLM, strip_thinking
from reckoning_pipeline.script.draft import (
    SECTIONS, DraftError, check_draft, claims_block, clean_section, draft_script,
)

REPLIES = [
    "<think>plan the hook</think>What has to be true before a scene is allowed into a film?",
    "## Stakes and context\nClaims stay unverified until a person reviews them [Claim: claim-review-required].",
    "Every asset carries a checksum [claim:claim-checksum-catches-changes]. Studies show 73% of edits go unnoticed.",
    "Nothing publishes itself [claim:claim-no-auto-publish]. Experts call it \"the gold standard\" [claim:ghost-claim].",
    "We still don't know how well this scales [NEEDS SOURCE: survey of newsroom adoption].",
]


class ScriptedLLM:
    name = "scripted"
    sends_data_externally = False

    def __init__(self, replies=REPLIES):
        self.replies, self.calls = list(replies), []

    def version(self):
        return "scripted 1.0"

    def complete(self, prompt, *, system="", max_tokens=1024):
        self.calls.append((prompt, system, max_tokens))
        return self.replies[len(self.calls) - 1]


def test_claims_block_marks_status_and_skips_rejected(demo):
    claims = validate_project(demo).ledger.claims
    block = claims_block(claims)
    assert "[claim:claim-review-required] (UNVERIFIED - hedge it" in block
    edit_json(demo / "research/ledger.json", lambda d: d["claims"][0].update(
        verification_status="rejected", reviewer="R", review_date="2026-10-18"))
    assert "claim-review-required" not in claims_block(validate_project(demo).ledger.claims)


def test_clean_section_strips_headings_and_normalises_markers():
    assert clean_section("## Investigation\nText [ Claim : ABC ].", "Investigation") == "Text [claim:abc]."
    assert clean_section("Investigation: the text", "Investigation") == "the text"


def test_strip_thinking():
    assert strip_thinking("<think>x\ny</think>\nAnswer") == "Answer"
    assert strip_thinking("Answer <think>unfinished") == "Answer"


def test_draft_writes_file_with_flags_and_never_touches_script(demo):
    before = (demo / "script/script.md").read_text(), (demo / "scenes.json").read_text()
    llm = ScriptedLLM()
    out = draft_script(validate_project(demo), llm, minutes=1)
    assert len(llm.calls) == len(SECTIONS)
    prompt, system, _ = llm.calls[1]
    assert "CLAIMS (the only facts you may state)" in prompt and "/no_think" in prompt
    assert "Never invent numbers" in system
    assert ((demo / "script/script.md").read_text(), (demo / "scenes.json").read_text()) == before

    text = out.path.read_text()
    assert out.path.parent.name == "drafts" and text.startswith("<!-- AI DRAFT, NOT APPROVED. scripted 1.0")
    assert "<think>" not in text and "[claim:claim-review-required]" in text
    kinds = {(f.kind, f.detail.split()[0]) for f in out.flags}
    assert ("unknown_claim", "[claim:ghost-claim]") in kinds
    assert any(f.kind == "unsourced_fact" and "73%" in f.detail for f in out.flags)
    assert any(f.kind == "needs_source" and "newsroom" in f.detail for f in out.flags)
    assert any(f.kind == "unverified_claim" for f in out.flags)
    assert set(out.claims_used) == {"claim-review-required", "claim-checksum-catches-changes", "claim-no-auto-publish"}
    assert "## Source and visual notes" in text and "## Review flags" in text


def test_check_draft_rejected_and_no_claims(demo):
    edit_json(demo / "research/ledger.json", lambda d: d["claims"][0].update(
        verification_status="rejected", reviewer="R", review_date="2026-10-18"))
    claims = {c.claim_id: c for c in validate_project(demo).ledger.claims}
    flags, _ = check_draft({"Investigation": "It was so [claim:claim-review-required].",
                            "Stakes and context": "A plain sentence with no facts."}, claims)
    assert {f.kind for f in flags} >= {"rejected_claim", "no_claims"}


def test_draft_refuses_empty_brief_and_empty_reply(demo):
    (demo / "brief.md").write_text("# Brief\n")
    with pytest.raises(DraftError, match="brief"):
        draft_script(validate_project(demo), ScriptedLLM())
    (demo / "brief.md").write_text("# Brief\n" + "word " * 30)
    with pytest.raises(DraftError, match="returned nothing"):
        draft_script(validate_project(demo), ScriptedLLM(["## Cold open / question\n"] * 5))


# --- Voicebox LLM adapter ----------------------------------------------------

class FakeVB:
    def __init__(self, endpoint=None, downloaded=True, reply_size="1.7B", status=200):
        self.endpoint, self.downloaded, self.reply_size, self.status = endpoint, downloaded, reply_size, status
        self.posts = []

    def __call__(self, req, timeout=None):
        path = req.full_url.split("17493", 1)[1]
        if path == "/settings/captures":
            return _resp({"custom_llm_endpoint": self.endpoint})
        if path == "/models/status":
            return _resp({"models": [{"model_name": "qwen3-1.7b", "downloaded": self.downloaded}]})
        if path == "/":
            return _resp({"version": "0.5.0"})
        if path == "/llm/generate":
            self.posts.append(json.loads(req.data))
            if self.status == 500:
                raise urllib.error.HTTPError(req.full_url, 500, "x", {}, io.BytesIO(b'{"detail": "LLM generation failed"}'))
            return _resp({"text": "<think>hmm</think>Hello.", "model_size": self.reply_size}, self.status)
        raise AssertionError(path)


class _R(io.BytesIO):
    def __init__(self, body, status):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _resp(data, status=200):
    return _R(json.dumps(data).encode(), status)


def test_voicebox_llm_happy_path():
    fake = FakeVB()
    llm = VoiceboxLLM("http://127.0.0.1:17493", opener=fake)
    assert llm.complete("Say hi", system="Be brief", max_tokens=99999) == "Hello."
    assert fake.posts[0]["model_size"] == "1.7B" and fake.posts[0]["max_tokens"] == 4096
    assert llm.version() == "voicebox 0.5.0 / qwen3-1.7B"


@pytest.mark.parametrize("fake,match", [
    (FakeVB(endpoint="https://api.example.com/v1"), "custom endpoint"),
    (FakeVB(downloaded=False), "isn't downloaded"),
    (FakeVB(reply_size="gpt-4o"), "not a local Qwen3"),
    (FakeVB(status=202), "still downloading"),
    (FakeVB(status=500), "500"),
])
def test_voicebox_llm_refusals(fake, match):
    with pytest.raises(ProviderUnavailableError, match=match):
        VoiceboxLLM("http://127.0.0.1:17493", opener=fake).complete("x")
    if match in ("custom endpoint", "isn't downloaded"):
        assert fake.posts == []  # refused before any text was sent


def test_voicebox_llm_local_custom_endpoint_ok_and_config_checks():
    VoiceboxLLM("http://127.0.0.1:17493", opener=FakeVB(endpoint="http://127.0.0.1:11434/v1")).complete("x")
    with pytest.raises(ProviderUnavailableError, match="not on this machine"):
        VoiceboxLLM("http://10.0.0.5:17493")
    with pytest.raises(ProviderUnavailableError, match="model size"):
        VoiceboxLLM(model_size="70B")
    with pytest.raises(ProviderUnavailableError, match="system prompt"):
        VoiceboxLLM("http://127.0.0.1:17493", opener=FakeVB()).complete("x", system="s" * 5000)


def test_cli_draft_without_provider(runner_env, demo):
    runner, app, cli = runner_env
    r = runner.invoke(app, ["script", "draft", str(demo)])
    assert r.exit_code == cli.EXIT_FAILED and "no LLM provider" in r.output


def test_repetition_and_cut_off_are_flagged(demo):
    claims = {c.claim_id: c for c in validate_project(demo).ledger.claims}
    same = "A scene must follow a strict chain of review before it is allowed in [claim:claim-review-required]."
    flags, _ = check_draft({"Stakes and context": same,
                            "Investigation": same.replace("[claim:claim-review-required]", "") + " Then the",
                            "Resolution or honest uncertainty": "We know a little more now."}, claims)
    kinds = [f.kind for f in flags]
    assert kinds.count("repeated") == 1
    assert ("cut_off", "Investigation") in [(f.kind, f.section) for f in flags]
    assert ("cut_off", "Resolution or honest uncertainty") not in [(f.kind, f.section) for f in flags]


def test_system_prompt_has_no_copyable_example_marker():
    from reckoning_pipeline.script.draft import CLAIM_MARKER, SYSTEM_PROMPT
    assert not CLAIM_MARKER.search(SYSTEM_PROMPT)


# --- Ollama adapter ----------------------------------------------------------

class FakeOllama:
    def __init__(self, models=("qwen3:4b-instruct-2507-q4_K_M",), status=200):
        self.models, self.status, self.chats = list(models), status, []

    def __call__(self, req, timeout=None):
        path = req.full_url.split("11434", 1)[1]
        if path == "/api/tags":
            return _resp({"models": [{"name": m, "model": m} for m in self.models]})
        if path == "/api/version":
            return _resp({"version": "0.40.6"})
        if path == "/api/chat":
            if self.status != 200:
                raise urllib.error.HTTPError(req.full_url, self.status, "x", {}, io.BytesIO(b'{"error": "model failed to load"}'))
            self.chats.append(json.loads(req.data))
            return _resp({"message": {"role": "assistant", "content": "<think>x</think>A clear sentence."}, "done": True})
        raise AssertionError(path)


def test_ollama_chat_request_and_reply():
    from reckoning_pipeline.providers.llm.ollama import OllamaLLM
    fake = FakeOllama()
    llm = OllamaLLM(opener=fake)
    assert llm.complete("Write.", system="Rules.", max_tokens=200) == "A clear sentence."
    body = fake.chats[0]
    assert body["model"] == "qwen3:4b-instruct-2507-q4_K_M" and body["stream"] is False and body["think"] is False
    assert body["messages"][0] == {"role": "system", "content": "Rules."}
    assert body["options"]["num_predict"] == 200 and body["options"]["num_ctx"] == 8192
    assert llm.version() == "ollama 0.40.6 / qwen3:4b-instruct-2507-q4_K_M"


def test_ollama_refusals():
    from reckoning_pipeline.providers.llm.ollama import OllamaLLM
    with pytest.raises(ProviderUnavailableError, match="ollama pull"):
        OllamaLLM(opener=FakeOllama(models=[])).complete("x")
    with pytest.raises(ProviderUnavailableError, match="failed to load"):
        OllamaLLM(opener=FakeOllama(status=500)).complete("x")
    with pytest.raises(ProviderUnavailableError, match="not on this machine"):
        OllamaLLM("http://192.168.1.10:11434")


def test_ollama_selected_from_config():
    from reckoning_pipeline.config import load_config
    from reckoning_pipeline.providers.llm import get_llm_provider
    p = get_llm_provider(load_config({"PIPELINE_OLLAMA_MODEL": "qwen3:1.7b"}), "ollama")
    assert p.name == "ollama" and p.model == "qwen3:1.7b"
