import json
import re

import pytest
from conftest import DEMO, edit_json
from pydantic import ValidationError

from reckoning_pipeline.graphics import GraphicError, render_graphic, render_spec
from reckoning_pipeline.project import validate_project
from reckoning_pipeline.schemas import GraphicSpec, ResearchLedger, VisualBeat
from reckoning_pipeline.visuals import build_sheet, build_visual_report, placeholder_svg, write_placeholders

LEDGER = ResearchLedger.model_validate({"sources": [{
    "source_id": "s1", "title": "Survey & Results <2023>", "authors": ["A. Author"], "publisher": "Inst",
    "url": "https://example.org/s", "source_type": "report", "classification": "primary"}], "claims": []})


def beat(**kw):
    base = {"beat_id": "b1", "scene_id": "s01-cold-open", "order": 1, "takeaway": "t",
            "visual_type": "original_graphic", "graphic_kind": "diagram", "asset_ids": ["s01-title"]}
    return VisualBeat(**{**base, **kw})


def report_for(demo):
    r = validate_project(demo)
    assert r.ok, [str(i) for i in r.issues]
    return build_visual_report(r.visuals, r.scenes, r.ledger, r.registry, r.approvals)


def add_beat(demo, **kw):
    edit_json(demo / "visuals.json", lambda d: d["beats"].append(kw))


# --- schema rules ------------------------------------------------------------

@pytest.mark.parametrize("kw,reason", [
    ({"graphic_kind": None}, "graphic_kind"),
    ({"visual_type": "licensed_stock"}, "graphic_kind is only"),
    ({"visual_type": "primary_evidence", "graphic_kind": None}, "source_ids or claim_ids"),
    ({"graphic_kind": "chart"}, "never invent data"),
    ({"visual_type": "generated", "graphic_kind": None, "asset_ids": [], "requirements": "x"}, "generation request"),
    ({"visual_type": "generated", "graphic_kind": None, "generation": {"prompt": "p"}}, "label"),
    ({"is_reconstruction": True}, "labelled"),
    ({"motion": "pan"}, "motion_purpose"),
    ({"asset_ids": []}, "requirements"),
    ({"generation": {"prompt": "p"}}, "only for generated"),
])
def test_beat_rules(kw, reason):
    with pytest.raises(ValidationError, match=reason):
        beat(**kw)


def test_valid_generated_and_evidence_beats():
    g = beat(visual_type="generated", graphic_kind=None, asset_ids=[], requirements="concept art",
             generation={"prompt": "an empty waiting room, dusk"}, label="AI illustration")
    assert g.generation.status == "requested"
    e = beat(visual_type="primary_evidence", graphic_kind=None, source_ids=["src-readme"])
    assert e.source_ids == ["src-readme"]


@pytest.mark.parametrize("kw,reason", [
    ({"kind": "bar_chart", "bars": [{"label": "a", "value": 1}], "data_locator": "T1"}, "source_ids"),
    ({"kind": "bar_chart", "source_ids": ["s1"], "bars": [{"label": "a", "value": 1}]}, "data_locator"),
    ({"kind": "bar_chart", "source_ids": ["s1"], "data_locator": "T", "bars": []}, "1-8 bars"),
    ({"kind": "bar_chart", "source_ids": ["s1"], "data_locator": "T", "bars": [{"label": "a", "value": -1}]}, "greater"),
    ({"kind": "timeline", "source_ids": ["s1"], "events": [{"when": "1", "text": "x"}]}, "2-6"),
    ({"kind": "title", "bars": [{"label": "a", "value": 1}]}, "no data"),
])
def test_graphic_spec_rules(kw, reason):
    with pytest.raises(ValidationError, match=reason):
        GraphicSpec(**{"asset_id": "g1", "title": "T", **kw})


# --- validation --------------------------------------------------------------

def test_visual_plan_references_are_checked(demo):
    def bad(d):
        d["beats"][0].update(asset_ids=["ghost"], claim_ids=["ghost-claim"], source_ids=["ghost-src"])
        d["beats"].append({**d["beats"][1], "scene_id": "ghost-scene"})
        d["beats"].append({**d["beats"][2]})
    edit_json(demo / "visuals.json", bad)
    codes = {i.code for i in validate_project(demo).errors}
    assert {"ref.missing_asset", "ref.missing_claim", "ref.missing_source", "ref.missing_scene",
            "id.duplicate", "visual.order_duplicate"} <= codes


def test_missing_visual_plan_is_allowed(demo):
    (demo / "visuals.json").unlink()
    r = validate_project(demo)
    assert r.ok and r.visuals.beats == []
    rep = build_visual_report(r.visuals, r.scenes, r.ledger, r.registry, r.approvals)
    assert [f.code for f in rep.gaps] == ["scene.no_visual_plan"] * 4


# --- report ------------------------------------------------------------------

def test_demo_plan_has_no_gaps_or_warnings():
    rep = report_for(DEMO)
    assert rep.gaps == [] and not [f for f in rep.findings if f.severity == "warning"]
    assert rep.type_counts["original_graphic"] == 4


def test_unresolved_beat_and_long_text(demo):
    add_beat(demo, beat_id="v-extra", scene_id="s03-asset-record", order=2, takeaway="t",
             visual_type="licensed_stock", requirements="Archive photo of a ledger",
             on_screen_text=["x " * 30])
    codes = [f.code for f in report_for(demo).findings]
    assert "visual.unresolved" in codes and "visual.text_too_long" in codes


def test_precise_claim_with_only_generic_visuals(demo):
    def swap(d):
        b = d["beats"][1]  # s02, critical claim
        b.update(visual_type="licensed_stock", graphic_kind=None)
    edit_json(demo / "visuals.json", swap)
    codes = [f.code for f in report_for(demo).findings]
    assert "visual.generic_for_precise_claim" in codes
    assert "visual.type_mismatch" in codes  # stock beat using an original graphic


def test_too_many_generated_beats(demo):
    def gen(d):
        for b in d["beats"][:2]:
            b.update(visual_type="generated", graphic_kind=None, asset_ids=[], requirements="concept",
                     generation={"prompt": "p"}, label="AI illustration", motion="none", motion_purpose="")
    edit_json(demo / "visuals.json", gen)
    assert "visual.too_many_generated" in [f.code for f in report_for(demo).findings]


def test_scene_without_strategy(demo):
    edit_json(demo / "scenes.json", lambda d: d["scenes"][0].update(visual_strategy=""))
    assert "scene.no_visual_strategy" in [f.code for f in report_for(demo).findings]


# --- graphics ----------------------------------------------------------------

BAR = {"asset_id": "g-bar", "kind": "bar_chart", "title": "Hours & minutes <test>", "source_ids": ["s1"],
       "data_locator": "Table 2", "units": "h", "bars": [{"label": "A", "value": 4}, {"label": "B", "value": 2},
                                                          {"label": "C", "value": 0}]}


def test_bar_chart_is_zero_based_cited_escaped_and_deterministic():
    spec = GraphicSpec(**BAR)
    svg = render_spec(spec, LEDGER)
    assert svg == render_spec(spec, LEDGER)
    widths = [float(w) for w in re.findall(r'<rect x="\d+" y="[\d.]+" width="([\d.]+)"', svg)]
    assert widths[0] == pytest.approx(2 * widths[1]) and widths[2] == 0  # proportional from zero
    assert "Source: A. Author. Survey &amp; Results &lt;2023&gt;" in svg and "(Table 2)" in svg
    assert "Hours &amp; minutes &lt;test&gt;" in svg and "<test>" not in svg


def test_timeline_and_title_render():
    tl = GraphicSpec(asset_id="t", kind="timeline", title="T", source_ids=["s1"],
                     events=[{"when": "1990", "text": "a"}, {"when": "2000", "text": "b"}])
    assert svg_count(render_spec(tl, LEDGER), "<circle") == 2
    title = render_spec(GraphicSpec(asset_id="x", kind="title", title="Why Boredom Disappeared"), LEDGER)
    assert "Why Boredom Disappeared" in title and "Source:" not in title


def svg_count(svg, token):
    return svg.count(token)


def test_unknown_source_refused():
    with pytest.raises(GraphicError, match="not in the ledger"):
        render_spec(GraphicSpec(**{**BAR, "source_ids": ["nope"]}), LEDGER)


def test_render_graphic_registers_and_never_overwrites(demo):
    r = validate_project(demo)
    spec = GraphicSpec(asset_id="g-timeline", kind="timeline", title="Demo phases",
                       source_ids=["src-readme"], events=[{"when": "Phase 1", "text": "CLI"},
                                                          {"when": "Phase 2", "text": "Schemas"}],
                       intended_scene_ids=["s04-review-gates"])
    out = render_graphic(demo, r.manifest, r.registry, r.ledger, spec, spec_name="t.json")
    assert out.path.is_file() and not out.unchanged
    r = validate_project(demo)
    assert r.ok
    a = next(x for x in r.registry.assets if x.asset_id == "g-timeline")
    assert (a.creation_method, a.publication_status) == ("original_graphic", "pending_review")
    assert "src-readme" in a.rights_evidence

    again = render_graphic(demo, r.manifest, r.registry, r.ledger, spec)
    assert again.unchanged
    changed = spec.model_copy(update={"title": "Different"})
    with pytest.raises(GraphicError, match="never overwritten"):
        render_graphic(demo, r.manifest, r.registry, r.ledger, changed)


# --- placeholders and sheet --------------------------------------------------

def test_placeholders_only_for_unresolved(demo):
    add_beat(demo, beat_id="v-gap", scene_id="s01-cold-open", order=2, takeaway="t",
             visual_type="typography", requirements="Quote card <b>needs</b> sourcing")
    r = validate_project(demo)
    written = write_placeholders(demo, r.visuals.beats)
    assert [p.name for p in written] == ["v-gap.svg"]
    svg = written[0].read_text()
    assert "NOT FOR PUBLICATION" in svg and "&lt;b&gt;needs&lt;/b&gt;" in svg
    assert placeholder_svg(r.visuals.beats[-1]) == svg


def test_sheet_escapes_text_and_links_assets(demo):
    edit_json(demo / "visuals.json", lambda d: d["beats"][0].update(takeaway="<script>alert(1)</script>"))
    add_beat(demo, beat_id="v-gap", scene_id="s01-cold-open", order=2, takeaway="t",
             visual_type="licensed_stock", requirements="Archive photo")
    r = validate_project(demo)
    rep = build_visual_report(r.visuals, r.scenes, r.ledger, r.registry, r.approvals)
    html = build_sheet(r, rep)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert 'src="../assets/graphics/s01_title.svg"' in html
    assert "UNRESOLVED" in html and "1 gap(s)" in html
    assert "<meta name=\"viewport\"" in html


def test_cli_visuals_and_graphics(runner_env, demo, tmp_path):
    runner, app, codes = runner_env
    r = runner.invoke(app, ["visuals", "report", str(demo)])
    assert r.exit_code == codes.EXIT_OK and "0 gap(s)" in r.output
    add_beat(demo, beat_id="v-gap", scene_id="s01-cold-open", order=2, takeaway="t",
             visual_type="licensed_stock", requirements="Archive photo")
    assert runner.invoke(app, ["visuals", "report", str(demo), "--strict"]).exit_code == codes.EXIT_FAILED
    assert json.loads(runner.invoke(app, ["visuals", "report", str(demo), "--json"]).output)["gap_count"] == 1
    assert runner.invoke(app, ["visuals", "placeholders", str(demo)]).exit_code == codes.EXIT_OK
    assert (demo / "visuals/placeholders/v-gap.svg").is_file()
    assert runner.invoke(app, ["visuals", "sheet", str(demo)]).exit_code == codes.EXIT_OK
    assert (demo / "reports/visuals.html").is_file()
    r = runner.invoke(app, ["visuals", "generate", str(demo)])
    assert r.exit_code == codes.EXIT_NOT_IMPLEMENTED and "Phase 9" in r.output

    spec = tmp_path / "title.json"
    spec.write_text(json.dumps({"asset_id": "g-title", "kind": "title", "title": "Hello"}))
    r = runner.invoke(app, ["graphics", "render", str(demo), str(spec), "--dry-run"])
    assert r.exit_code == codes.EXIT_OK and "[dry-run]" in r.output
    assert not (demo / "assets/graphics/g-title.svg").exists()
    assert runner.invoke(app, ["graphics", "render", str(demo), str(spec)]).exit_code == codes.EXIT_OK
    assert "unchanged" in runner.invoke(app, ["graphics", "render", str(demo), str(spec)]).output
    spec.write_text(json.dumps({"asset_id": "g-bad", "kind": "bar_chart", "title": "x", "bars": []}))
    r = runner.invoke(app, ["graphics", "render", str(demo), str(spec)])
    assert r.exit_code == codes.EXIT_FAILED and "source_ids" in r.output
