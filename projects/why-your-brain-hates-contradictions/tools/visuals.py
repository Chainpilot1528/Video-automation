"""Sentence-by-sentence visual plan for why-your-brain-hates-contradictions (all ten scenes).

Writes visuals.json from the narration's measured timings, so every visual lands on its sentence.
Re-run it after any narration rebuild:

    .venv/bin/python projects/why-your-brain-hates-contradictions/tools/visuals.py projects/why-your-brain-hates-contradictions
"""
import json
import sys

P = sys.argv[1]
LEAD = 0.25
LEADS = {s["scene_id"]: (s.get("lead_in_seconds") if s.get("lead_in_seconds") is not None else LEAD)
         for s in json.load(open(f"{P}/scenes.json"))["scenes"]}
CHUNKS = {c["scene_id"]: c for c in json.load(open(f"{P}/reports/narration.json"))["chunks"]}
ART = "Reckoning Self, “Why Your Brain Hates Contradictions”"
FIG_W, FIG_H = 0.09, 0.36


def at(scene, needle, nth=0):
    """Scene time where ``needle`` is spoken (the nth spoken piece containing it). Inside a piece that
    joins two sentences, the time is placed by the needle's position, by characters."""
    hits = [s for s in CHUNKS[scene]["sentences"] if needle.lower() in s["text"].lower()]
    if len(hits) <= nth:
        raise SystemExit(f"{scene}: no phrase with {needle!r}")
    h = hits[nth]
    frac = h["text"].lower().index(needle.lower()) / max(len(h["text"]), 1)
    return round(LEADS[scene] + h["start"] + (h["end"] - h["start"]) * frac, 2)


def text(t, style, x, y, width, start, **kw):
    return {"kind": "text", "text": t, "text_style": style, "x": x, "y": y, "width": width, "start": start, **kw}


def say(t, x, y, width, start, **kw):
    """A key line in the statement style."""
    return text(t, "statement", x, y, width, start, **kw)


def cap(t, x, y, width, start, **kw):
    return text(t, "caption", x, y, width, start, **kw)


def shape(kind, x, y, width, max_height, start=0.0, **kw):
    return {"kind": "shape", "shape": kind, "x": x, "y": y, "width": width, "max_height": max_height, "start": start, **kw}


def person(x, start, **kw):
    return shape("person", x, kw.pop("y", 0.45), FIG_W, FIG_H, start, fade_in=kw.pop("fade_in", 0.8), **kw)


def img(asset, x, y, width, max_height, start=0.0, **kw):
    kw.setdefault("edge", "feather")
    kw.setdefault("feather", 0.025)
    kw.setdefault("fade_in", 1.2)
    return {"kind": "image", "asset_id": asset, "x": x, "y": y, "width": width, "max_height": max_height,
            "start": start, **kw}


def quote(t, hl, claim, start, y=0.44):
    return text(t, "quote", 0.69, y, 0.42, start, highlight=hl, reveal="words", claim_id=claim, fade_in=0.45)


MARK = {
    1: ("met-rodin-thinker", "The Thinker", [0.2, 0.05, 0.85, 0.6]),
    2: ("met-brouwer-smokers", "The Smokers", [0.25, 0.1, 0.75, 0.7]),
    4: ("met-lahyre-narcissus", "Narcissus", [0.55, 0.25, 0.9, 0.7]),
    5: ("met-caraglio-diogenes", "Diogenes", [0.3, 0.12, 0.62, 0.45]),
    6: ("met-remmelin-microcosme", "Microcosm", [0.37, 0.27, 0.65, 0.5]),
    7: ("met-sisyphus-tantalus", "Sisyphus", [0.4, 0.1, 0.95, 0.6]),
    8: ("met-parmigianino-justice", "Justice", [0.2, 0.05, 0.8, 0.5]),
}

beats = []


def add(scene, start, takeaway, layers, claims=(), sources=None):
    n = 1 + sum(1 for b in beats if b["scene_id"] == scene)
    images = list(dict.fromkeys(la["asset_id"] for la in layers if la["kind"] == "image"))
    rel = [{**la, "start": round(max(la.get("start", 0.0) - start, 0.0), 2)} for la in layers]
    beats.append({"beat_id": f"v-{scene}-b{n:02d}", "scene_id": scene, "order": n, "takeaway": takeaway,
                  "visual_type": "licensed_stock" if images else "typography", "asset_ids": images, "layers": rel,
                  "claim_ids": list(claims),
                  "source_ids": list(sources if sources is not None else (["src-article"] if claims else [])),
                  "offset_seconds": round(start, 2)})


SPOKEN = ["one", "two", "three", "four", "five", "six", "seven", "eight"]


def chapter(scene, level, takeaway, until):
    """The core map easing down one level, then the level's title card; returns when the chapter begins.
    When the scene opens with a silent lead-in and the narrator reads the level title, the map moves during
    the silence and the card holds while the title is spoken, until the chapter's first line."""
    if LEADS[scene] > 1.0:
        end = LEADS[scene]
        markers = [{"level": lv, "asset_id": a, "name": n, "crop": c} for lv, (a, n, c) in MARK.items() if lv <= level]
        view = {"asset_id": "chapter-core", "level": level, "from_level": level - 1, "pan_start": 0.3,
                "pan_seconds": round(min(2.6, end - 0.9), 2), "markers": markers}
        n = 1 + sum(1 for b in beats if b["scene_id"] == scene)
        beats.append({"beat_id": f"v-{scene}-b{n:02d}", "scene_id": scene, "order": n, "takeaway": takeaway,
                      "visual_type": "original_graphic", "graphic_kind": "chapter_map",
                      "asset_ids": list(dict.fromkeys(["chapter-core"] + [m["asset_id"] for m in markers])),
                      "chapter_map": view, "offset_seconds": 0.0})
        return title_card(scene, level, end - 0.2, until)
    end = max(until, 4.6)
    markers = [{"level": lv, "asset_id": a, "name": n, "crop": c} for lv, (a, n, c) in MARK.items() if lv <= level]
    view = {"asset_id": "chapter-core", "level": level, "from_level": level - 1, "pan_start": 0.3,
            "pan_seconds": round(min(2.6, end - 1.6), 2), "markers": markers}
    n = 1 + sum(1 for b in beats if b["scene_id"] == scene)
    beats.append({"beat_id": f"v-{scene}-b{n:02d}", "scene_id": scene, "order": n, "takeaway": takeaway,
                  "visual_type": "original_graphic", "graphic_kind": "chapter_map",
                  "asset_ids": list(dict.fromkeys(["chapter-core"] + [m["asset_id"] for m in markers])),
                  "chapter_map": view, "offset_seconds": 0.0})
    return title_card(scene, level, end)


CARD = 2.6        # seconds a chapter title card holds before the chapter begins
LEVEL_TITLES = [lv["title"] for lv in json.load(open(f"{P}/graphics/chapter-core.json"))["levels"]]
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


CARDS = False     # chapter title cards (off: the approved version has none)


def title_card(scene, level, start, end=None):
    """A chapter title card on black: "LEVEL III", then the chapter's name, glowing. Holds until ``end``
    (default CARD seconds). Returns its end."""
    if not CARDS:
        return round(start, 2)
    n = 1 + sum(1 for b in beats if b["scene_id"] == scene)
    beats.append({"beat_id": f"v-{scene}-b{n:02d}", "scene_id": scene, "order": n,
                  "takeaway": f"Level {ROMAN[level - 1]}: {LEVEL_TITLES[level - 1]}", "visual_type": "typography",
                  "asset_ids": [], "offset_seconds": round(start, 2), "layers": [
                      text(f"Level {ROMAN[level - 1]}", "chapter", 0.5, 0.43, 0.6, 0.0, fade_in=0.6, enter="none"),
                      text(LEVEL_TITLES[level - 1], "title", 0.5, 0.53, 0.9, 0.25, fade_in=0.9)]})
    return round(end if end is not None else start + CARD, 2)


# ---------------------------------------------------------------- 01 · negotiation
S = "s01-negotiation"
# the opening pull-back: close on the planet's surface, easing back to the whole planet, question in the sky
SURF_Y, Z0, Z1, AT = 120.0, 2.6, 0.92, 0.6       # overview surface y (px), start/end zoom, where the surface starts
d = SURF_Y - 540.0
y0 = (AT * 1080 - d * Z0) / 1080
pull_end = round(at(S, "and wins anyway?") + 1.6, 2)
add(S, 0.0, "A hook: someone breaks the rules and wins", [
    shape("stars", 0.5, 0.5, 1.0, 1.0, 0.0, seed=11, pulse=3.7, fade_in=1.0),
    shape("stars", 0.5, 0.5, 1.0, 1.0, 0.0, seed=23, pulse=5.3, fade_in=1.0),
    img("chapter-core-overview", 0.5, round(y0, 4), 1.0, 1.0, 0.0, edge="none", fade_in=1.2, zoom_from=Z0, zoom_to=Z1,
        drift_y=round(0.5 - y0, 4), motion_start=0.4, motion_end=pull_end, motion_ease=True),
    say("Have you ever met someone who seems to break every rule… and wins anyway?", 0.5, 0.075, 0.92, 0.0,
        highlight="and wins anyway?", reveal="words", fade_in=0.45)])
t = at(S, "Here's the situation") - 0.2
add(S, t, "Your belief: hard work wins", [
    person(0.36, t + 0.2, fade_in=1.0), cap("you", 0.36, 0.7, 0.2, t + 0.6),
    cap("three years", 0.64, 0.4, 0.3, at(S, "For three years") + 0.3),
    say("Hard work wins.", 0.64, 0.48, 0.4, at(S, "Hard work wins"), highlight="wins.", reveal="words", fade_in=0.45)])
t = at(S, "So you gave up") - 0.2
add(S, t, "Sacrifice gives the belief its meaning", [
    img("met-bruegel-harvesters", 0.5, 0.44, 0.72, 0.72, t, zoom_from=1.0, zoom_to=1.12, drift_y=-0.02),
    cap("Pieter Bruegel the Elder, The Harvesters, 1565", 0.5, 0.9, 0.6, t + 1.0)])
t = at(S, "Then you meet someone") - 0.2
arrive = t + 0.6
add(S, t, "Someone works less and earns more", [
    person(0.3, t, fade_in=0.6), cap("you", 0.3, 0.68, 0.2, t + 0.3),
    person(0.88, arrive, flip=True, drift_x=-0.22, motion_start=round(arrive - t, 2),
           motion_end=round(arrive - t + 1.4, 2), motion_ease=True, fade_in=0.5),
    cap("them", 0.66, 0.68, 0.2, arrive + 1.2),
    say("fewer hours", 0.66, 0.76, 0.32, at(S, "They work fewer hours") + 0.2),
    say("protects their evenings", 0.66, 0.83, 0.4, at(S, "They protect") + 0.2),
    say("earns more", 0.66, 0.9, 0.32, at(S, "And they earn more") + 0.6, highlight="earns more")])
t = at(S, "Now you're holding") - 0.2
add(S, t, "Two ideas that don't fit together", [
    shape("circle", 0.34, 0.45, 0.16, 0.28, t, color="stone", drift_x=0.05, motion_start=0.3, motion_end=3.0,
          motion_ease=True, fade_in=0.6),
    shape("ring", 0.66, 0.45, 0.16, 0.28, t + 0.4, drift_x=-0.05, motion_start=0.3, motion_end=3.0, motion_ease=True,
          fade_in=0.6),
    cap("Hard work wins.", 0.39, 0.66, 0.24, t + 0.8), cap("Someone works less and earns more.", 0.61, 0.66, 0.28, t + 1.2)])
t = at(S, "You could rethink") - 0.2
add(S, t, "We protect the belief instead of rethinking it", [
    say("Rethink what success really takes.", 0.5, 0.26, 0.6, t + 0.2, fade_in=0.6),
    shape("line", 0.512, 0.247, 0.37, 0.03, at(S, "Or…"), reveal="draw", color="accent", fade_in=0.7),
    say("They just got lucky.", 0.5, 0.46, 0.5, at(S, "you could decide") + 0.4),
    say("It won't last.", 0.5, 0.56, 0.5, at(S, "That it won't last")),
    say("They must know someone.", 0.5, 0.66, 0.5, at(S, "That they must know"))])
t = at(S, "Notice what just happened") - 0.2
add(S, t, "Instead of updating the belief, we protect it", [
    img("met-rodin-thinker-cut", 0.28, 0.46, 0.3, 0.76, t, feather=0.05, zoom_from=1.0, zoom_to=1.05, drift_y=-0.01),
    cap("Auguste Rodin, The Thinker, modeled c. 1880", 0.28, 0.9, 0.52, t + 0.8),
    quote("“Instead of changing your understanding of the world, you found a way to preserve it.”",
          "found a way to preserve it", "q-art-preserve", t),
    cap(ART, 0.69, 0.64, 0.42, at(S, "Instead of changing") + 2.0)], ["q-art-preserve"])
t = at(S, "And here's the strange part") - 0.2
add(S, t, "Rationalisation feels like logic from the inside", [
    say("It doesn't feel like an excuse.", 0.5, 0.42, 0.6, at(S, "From the inside") + 0.5),
    say("It feels like logic.", 0.5, 0.52, 0.6, at(S, "It feels like logic"), highlight="logic.", reveal="words",
        fade_in=0.45)])

# ---------------------------------------------------------------- 02 · dissonance
S = "s02-theory"
t = chapter(S, 2, "Level II: cognitive dissonance", at(S, "In 1957") - 0.2)
add(S, t, "Festinger named it in 1957", [
    text("Cognitive dissonance", "heading", 0.5, 0.42, 0.8, t + 0.2, fade_in=0.8),
    cap("Leon Festinger, 1957", 0.5, 0.56, 0.5, t + 1.2)], ["c-festinger-1957"], ["src-festinger-carlsmith-1959"])
t = at(S, "The idea is simple") - 0.2
add(S, t, "Two things that don't fit together feel uncomfortable", [
    shape("circle", 0.36, 0.42, 0.15, 0.27, t + 0.2, color="stone", drift_x=0.04, motion_start=0.5, motion_end=3.0,
          motion_ease=True),
    cap("what you believe", 0.4, 0.62, 0.26, t + 0.6),
    shape("ring", 0.64, 0.42, 0.15, 0.27, at(S, "or when what you do"), drift_x=-0.04, motion_start=0.3,
          motion_end=2.5, motion_ease=True),
    cap("what you do", 0.6, 0.62, 0.26, at(S, "or when what you do") + 0.4),
    say("It feels uncomfortable.", 0.5, 0.78, 0.5, at(S, "it feels uncomfortable"), highlight="uncomfortable.",
        reveal="words", fade_in=0.45)])
t = at(S, "Take a smoker") - 0.2
add(S, t, "A smoker who knows smoking is harmful", [
    img("met-brouwer-smokers", 0.3, 0.44, 0.42, 0.74, t, zoom_from=1.0, zoom_to=1.08),
    cap("Adriaen Brouwer, The Smokers, c. 1636", 0.3, 0.9, 0.52, t + 0.8),
    say("Knows smoking is harmful.", 0.72, 0.42, 0.4, at(S, "They know smoking")),
    say("Still smokes.", 0.72, 0.52, 0.4, at(S, "And they still smoke"), highlight="Still smokes.")])
t = at(S, "So what do they do?") - 0.2
add(S, t, "Several ways to ease the conflict", [
    say("So what do they do?", 0.5, 0.24, 0.6, t + 0.2),
    say("Quit.", 0.5, 0.4, 0.5, at(S, "They could quit")),
    say("Admit the clash.", 0.5, 0.5, 0.5, at(S, "They could admit")),
    say("“I don't smoke enough for it to matter.”", 0.5, 0.62, 0.7, at(S, "I don't smoke enough"),
        highlight="for it to matter.”")])
t = at(S, "That's the key") - 0.2
add(S, t, "Changing your mind is only one way out", [
    img("met-durer-hercules-crossroad", 0.28, 0.45, 0.36, 0.78, t, crop=[0.12, 0.0, 0.88, 0.62], zoom_from=1.0,
        zoom_to=1.05),
    cap("Albrecht Dürer, Hercules at the Crossroad, c. 1498", 0.28, 0.9, 0.52, t + 0.8),
    say("Change your mind", 0.7, 0.3, 0.42, at(S, "Changing your mind is only")),
    say("Change what you do", 0.7, 0.42, 0.42, at(S, "You can change what you do")),
    say("Reinterpret the evidence", 0.7, 0.54, 0.42, at(S, "You can reinterpret")),
    say("Add a new story", 0.7, 0.66, 0.42, at(S, "Or you can add"), highlight="new story")],
    ["c-festinger-1957"], ["src-festinger-carlsmith-1959"])
t = at(S, "Which way you go") - 0.2
add(S, t, "It depends on how much the belief matters", [
    say("Which way you go depends on the situation… and on how much that belief matters to you.", 0.5, 0.46, 0.66,
        t + 0.2, highlight="how much that belief matters to you.", reveal="words", fade_in=0.45)])

# ---------------------------------------------------------------- 03 · the experiment
S = "s03-experiment"
t = chapter(S, 3, "Level III: the $1 / $20 experiment", at(S, "Students came") - 0.2)
add(S, t, "An hour of deliberately boring tasks", [
    person(0.3, t + 0.2), cap("a student", 0.3, 0.68, 0.2, t + 0.6),
    cap("about an hour of boring tasks", 0.66, 0.24, 0.5, at(S, "Students came") + 2.2)] +
    [shape("ring", 0.56 + (i % 4) * 0.07, 0.38 + (i // 4) * 0.12, 0.045, 0.08, at(S, "Like turning pegs") + i * 0.12,
           fade_in=0.4) for i in range(12)] +
    [cap("a quarter turn at a time", 0.66, 0.74, 0.5, at(S, "a quarter turn"))],
    ["c-fc-design"], ["src-festinger-carlsmith-1959"])
t = at(S, "Then came the twist") - 0.2
add(S, t, "Paid $1 or $20 to call it enjoyable", [
    person(0.3, t + 0.1), person(0.7, t + 0.4, flip=True),
    cap("the next student", 0.7, 0.68, 0.24, t + 0.8),
    say("“It was enjoyable.”", 0.5, 0.22, 0.5, at(S, "Some of them were asked")),
    img("met-durand-one-dollar", 0.38, 0.82, 0.2, 0.13, at(S, "Some were paid one dollar"), crop=[0.17, 0.02, 0.98, 0.47],
        fade_in=0.6),
    text("$1", "label", 0.38, 0.92, 0.2, at(S, "Some were paid one dollar") + 0.3),
    img("met-saint-gaudens-twenty-cut", 0.62, 0.81, 0.08, 0.14, at(S, "Others were paid twenty"), edge="none", fade_in=0.6),
    text("$20", "label", 0.62, 0.92, 0.2, at(S, "Others were paid twenty") + 0.3),
    cap("control group: never asked", 0.5, 0.93, 0.5, at(S, "And a control group"))],
    ["c-fc-design"], ["src-festinger-carlsmith-1959"])
t = at(S, "Afterwards, everyone rated") - 0.2
add(S, t, "Everyone rated how enjoyable the tasks were", [
    say("How enjoyable were the tasks, really?", 0.5, 0.3, 0.7, t + 0.2),
    shape("line", 0.5, 0.52, 0.6, 0.03, t + 1.0, reveal="draw", color="dim", fade_in=1.2),
    cap("−5 extremely boring", 0.2, 0.6, 0.24, t + 1.8), cap("+5 extremely enjoyable", 0.8, 0.6, 0.24, t + 2.0)],
    ["c-fc-results"], ["src-festinger-carlsmith-1959"])
t = at(S, "You'd expect") - 0.2
add(S, t, "The expectation, and the surprise", [
    say("Expected: the $20 group likes it more.", 0.5, 0.4, 0.7, t + 0.3),
    say("The opposite happened.", 0.5, 0.54, 0.6, at(S, "But the opposite"), highlight="opposite")])
t = at(S, "The one dollar group rated") - 0.2
add(S, t, "Paid $1, people rated the boring task higher", [
    cap("How enjoyable were the tasks?  (−5 boring … +5 enjoyable)", 0.5, 0.22, 0.8, t + 0.2),
    text("Paid $1", "label", 0.36, 0.38, 0.3, t + 0.4), text("+1.35", "heading", 0.64, 0.38, 0.2, t + 0.4,
                                                              highlight="+1.35"),
    text("Paid $20", "label", 0.36, 0.52, 0.3, at(S, "The twenty dollar group landed")),
    text("−0.05", "heading", 0.64, 0.52, 0.2, at(S, "The twenty dollar group landed")),
    text("Control (not asked)", "label", 0.36, 0.66, 0.3, at(S, "The twenty dollar group landed") + 1.2),
    text("−0.45", "heading", 0.64, 0.66, 0.2, at(S, "The twenty dollar group landed") + 1.2),
    cap("Average ratings, 20 students per group · Festinger & Carlsmith (1959), J. Abnormal and Social Psychology 58",
        0.5, 0.86, 0.9, at(S, "The twenty dollar group landed") + 2.4)],
    ["c-fc-results"], ["src-festinger-carlsmith-1959"])
t = at(S, "Why?") - 0.2
add(S, t, "$20 justified the lie; $1 didn't", [
    say("Why?", 0.5, 0.2, 0.3, t + 0.2),
    img("met-saint-gaudens-twenty-cut", 0.32, 0.42, 0.13, 0.24, at(S, "Twenty dollars was reason"), edge="none",
        zoom_from=1.0, zoom_to=1.05),
    cap("$20 · reason enough to say it", 0.32, 0.6, 0.34, at(S, "Twenty dollars was reason") + 0.6),
    img("met-durand-one-dollar", 0.68, 0.42, 0.3, 0.2, at(S, "One dollar wasn't"), crop=[0.17, 0.02, 0.98, 0.47],
        zoom_from=1.0, zoom_to=1.05),
    cap("$1 · not enough", 0.68, 0.6, 0.34, at(S, "One dollar wasn't") + 0.4),
    cap("Augustus Saint-Gaudens, twenty-dollar gold piece, 1905–7 · Asher B. Durand, Bank of New York $1 proof, 1824–37",
        0.5, 0.94, 0.9, at(S, "One dollar wasn't") + 1.2),
    say("“The tasks weren't that bad.”", 0.68, 0.76, 0.42, at(S, "was to decide"), highlight="that bad.”")],
    ["i-fc-justification"], ["src-festinger-carlsmith-1959"])
t = at(S, "It doesn't prove") - 0.2
add(S, t, "What we do can shape what we believe", [
    cap("It doesn't prove we always rewrite our beliefs.", 0.5, 0.34, 0.7, t + 0.3),
    say("What we do can shape what we believe…", 0.5, 0.48, 0.7, at(S, "What we do can shape"),
        highlight="shape what we believe…", reveal="words", fade_in=0.45),
    cap("especially when we can't easily justify it to ourselves", 0.5, 0.6, 0.7, at(S, "especially when"))],
    ["i-fc-justification"], ["src-festinger-carlsmith-1959"])

# ---------------------------------------------------------------- 04 · identity
S = "s04-identity"
t = chapter(S, 4, "Level IV: beliefs as identity", at(S, "Find out you got") - 0.2)
add(S, t, "Small facts versus beliefs that matter", [
    shape("ring", 0.32, 0.44, 0.07, 0.12, t + 0.2), cap("a film's release year", 0.32, 0.6, 0.3, t + 0.4),
    shape("circle", 0.66, 0.44, 0.2, 0.36, at(S, "Find out your politics"), color="stone"),
    cap("your politics", 0.66, 0.7, 0.3, at(S, "Find out your politics") + 0.4)])
t = at(S, "The difference is what") - 0.2
add(S, t, "Some beliefs are tied to who you are", [
    img("met-lahyre-narcissus", 0.5, 0.36, 0.62, 0.52, t, zoom_from=1.0, zoom_to=1.06),
    cap("Laurent de La Hyre, Narcissus, 17th century", 0.5, 0.65, 0.6, t + 0.8),
    say("tied to who you are", 0.5, 0.78, 0.5, at(S, "Others are tied"), highlight="who you are")])
t = at(S, "Think about the career") - 0.2
add(S, t, "Career, relationship, upbringing", [
    say("the career you spent years building", 0.5, 0.34, 0.7, t + 0.2),
    say("the relationship you defended", 0.5, 0.46, 0.7, at(S, "The relationship you defended")),
    say("the beliefs you grew up with", 0.5, 0.58, 0.7, at(S, "The beliefs you grew up")),
    cap("shared with people you love", 0.5, 0.66, 0.5, at(S, "shared with people"))])
t = at(S, "Changing your mind about any") - 0.2
add(S, t, "Changing your mind can mean admitting a cost", [
    cap("Changing your mind can mean admitting…", 0.5, 0.32, 0.6, t + 0.3),
    say("a sacrifice was unnecessary", 0.5, 0.46, 0.6, at(S, "It can mean admitting"), highlight="unnecessary"),
    say("a decision was wrong", 0.5, 0.58, 0.6, at(S, "Or that a decision"), highlight="wrong")])
t = at(S, "That's why an argument") - 0.2
add(S, t, "A contradiction carries consequences", [
    img("met-lahyre-narcissus", 0.28, 0.45, 0.4, 0.5, t, crop=[0.45, 0.1, 1.0, 0.95], zoom_from=1.04, zoom_to=1.0),
    quote("“The contradiction is carrying more than information. It is carrying consequences.”",
          "It is carrying consequences.", "q-art-consequences", t),
    cap(ART, 0.69, 0.62, 0.42, at(S, "The contradiction is carrying") + 2.5)], ["q-art-consequences"])

# ---------------------------------------------------------------- 05 · motivated reasoning
S = "s05-motivated"
t = chapter(S, 5, "Level V: motivated reasoning", at(S, "It's the way our goals") - 0.2)
add(S, t, "Goals shape how we judge information", [
    text("Motivated reasoning", "heading", 0.5, 0.42, 0.8, t + 0.1),
    cap("our goals and commitments shape how we judge information", 0.5, 0.56, 0.7, t + 0.8)])
t = at(S, "Picture two smart people") - 0.2
add(S, t, "Same study, different scrutiny", [
    cap("the same study", 0.5, 0.2, 0.4, t + 0.6),
    shape("line", 0.5, 0.25, 0.16, 0.02, t + 0.8, reveal="draw", color="dim", fade_in=0.6),
    person(0.3, t + 0.2), person(0.7, t + 0.5, flip=True),
    cap("supports me", 0.3, 0.68, 0.3, at(S, "One finds it supports")),
    say("solid methods", 0.3, 0.76, 0.3, at(S, "So they notice the solid")),
    say("clear results", 0.3, 0.83, 0.3, at(S, "and the clear results")),
    cap("challenges me", 0.7, 0.68, 0.3, at(S, "The other finds")),
    say("limitations", 0.7, 0.76, 0.3, at(S, "So they notice the limitations")),
    say("what could be wrong", 0.7, 0.83, 0.34, at(S, "and everything that could"))])
t = at(S, "Now, being critical") - 0.2
add(S, t, "The problem: a moving standard", [
    img("met-caraglio-diogenes", 0.28, 0.45, 0.32, 0.78, t, crop=[0.12, 0.1, 0.9, 0.9], zoom_from=1.0, zoom_to=1.05),
    cap("Giovanni Jacopo Caraglio, Diogenes, c. 1527", 0.28, 0.91, 0.52, t + 0.8),
    say("Being critical is good science.", 0.7, 0.34, 0.42, t + 0.3),
    say("the standard changes… depending on whether we like the answer", 0.7, 0.52, 0.42,
        at(S, "The problem is when"), highlight="whether we like the answer", reveal="words", fade_in=0.45)])
t = at(S, "But here's the hopeful part") - 0.2
add(S, t, "People do update on clear evidence", [
    text("4 studies", "heading", 0.5, 0.26, 0.5, at(S, "In 2019") + 0.3),
    cap("Stephanie Anglin, 2019 · Journal of Experimental Social Psychology", 0.5, 0.37, 0.7, at(S, "In 2019") + 1.0),
    say("People often changed their beliefs.", 0.5, 0.5, 0.7, at(S, "And people often did change"),
        highlight="changed their beliefs."),
    cap("religion · politics · capital punishment", 0.5, 0.6, 0.6, at(S, "Even on religion")),
    cap("bias: sometimes… but not always", 0.5, 0.7, 0.6, at(S, "Bias showed up"))],
    ["c-anglin-2019"], ["src-anglin-2019"])
t = at(S, "So the real question") - 0.2
add(S, t, "When do we judge evidence on its merits?", [
    cap("The real question isn't whether people are rational.", 0.5, 0.32, 0.7, t + 0.3),
    say("When do we judge evidence on its merits…", 0.5, 0.46, 0.7, at(S, "When do we judge")),
    say("and when by whether we want it to be true?", 0.5, 0.56, 0.7, at(S, "and when do we judge it"),
        highlight="want it to be true?")])

# ---------------------------------------------------------------- 06 · the brain
S = "s06-brain"
t = chapter(S, 6, "Level VI: the brain", at(S, "A 2026 review") - 0.2)
add(S, t, "A 2026 review of brain studies", [
    img("met-remmelin-microcosme", 0.28, 0.44, 0.34, 0.74, t, crop=[0.37, 0.27, 0.65, 0.5], zoom_from=1.0,
        zoom_to=1.05),
    cap("Johann Remmelin, A Survey of the Microcosme (anatomical print), 1675", 0.28, 0.88, 0.52, t + 0.8),
    cap("Veiga-Zarza and colleagues, 2026 · scoping review", 0.7, 0.36, 0.42, t + 0.6),
    say("Two different jobs.", 0.7, 0.48, 0.42, at(S, "And it points to two"), highlight="Two different jobs.")],
    ["c-vz-2026"], ["src-veiga-zarza-2026"])
t = at(S, "First, noticing") - 0.2
add(S, t, "Noticing the conflict, then updating the attitude", [
    shape("circle", 0.3, 0.42, 0.14, 0.25, t + 0.2, color="stone"),
    say("noticing the conflict", 0.3, 0.62, 0.32, t + 0.4),
    cap("anterior cingulate cortex", 0.3, 0.7, 0.32, at(S, "That seems to involve")),
    shape("arrow", 0.5, 0.42, 0.14, 0.05, at(S, "Second, updating"), reveal="draw", fade_in=0.8),
    shape("ring", 0.7, 0.42, 0.14, 0.25, at(S, "Second, updating") + 0.6),
    say("updating the attitude", 0.7, 0.62, 0.32, at(S, "Second, updating") + 0.8),
    cap("dorsolateral prefrontal cortex", 0.7, 0.7, 0.34, at(S, "That seems linked"))],
    ["c-vz-2026"], ["src-veiga-zarza-2026"])
t = at(S, "In other words") - 0.2
add(S, t, "Spotting and resolving may be different steps", [
    say("spotting a contradiction and resolving it… may not be the same step", 0.5, 0.46, 0.7, t + 0.2,
        highlight="may not be the same step", reveal="words", fade_in=0.45)], ["c-vz-2026"], ["src-veiga-zarza-2026"])
t = at(S, "But be careful") - 0.2
add(S, t, "No single contradiction detector", [
    say("But be careful.", 0.5, 0.26, 0.5, t + 0.2),
    say("No single “contradiction detector”.", 0.5, 0.4, 0.7, at(S, "There's no single")),
    say("No brain scan can spot rationalising.", 0.5, 0.5, 0.7, at(S, "No brain scan")),
    cap("these regions do many jobs… the details are still being worked out", 0.5, 0.62, 0.7,
        at(S, "These regions do many"))], ["c-vz-2026"], ["src-veiga-zarza-2026"])

# ---------------------------------------------------------------- 07 · everyday life
S = "s07-everyday"
t = chapter(S, 7, "Level VII: explaining it away", at(S, "You can spot") - 0.2)
add(S, t, "Patterns to look for in yourself", [
    person(0.5, t + 0.2, y=0.4), cap("yourself", 0.5, 0.63, 0.3, at(S, "but as things to look for")),
    say("Not labels for other people.", 0.5, 0.78, 0.6, at(S, "Not as labels"))])
t = at(S, "Someone misses a promotion") - 0.2
add(S, t, "We change the meaning of success", [
    person(0.28, t + 0.2), cap("missed a promotion", 0.28, 0.68, 0.3, t + 0.5),
    say("“Promotions never really mattered.”", 0.68, 0.38, 0.44, at(S, "And decides promotions")),
    cap("honest reflection?", 0.68, 0.52, 0.4, at(S, "That could be honest")),
    cap("or protecting self-esteem?", 0.68, 0.59, 0.4, at(S, "Or a way to protect"))])
t = at(S, "Someone keeps pouring") - 0.2
add(S, t, "We defend what we have already paid for", [
    img("met-sisyphus-tantalus", 0.3, 0.45, 0.4, 0.78, t, crop=[0.0, 0.0, 1.0, 0.75], zoom_from=1.0, zoom_to=1.05),
    cap("Sisyphus and Tantalus, Italian, 16th century", 0.3, 0.9, 0.52, t + 0.8),
    say("pouring more into a failing project", 0.7, 0.4, 0.42, t + 0.4),
    cap("because quitting would make it all feel wasted", 0.7, 0.52, 0.42, at(S, "Because quitting"))])
t = at(S, "Someone who sees themselves") - 0.2
add(S, t, "We reinterpret our own behaviour", [
    person(0.28, t + 0.2), cap("“I'm honest.”", 0.28, 0.68, 0.3, t + 0.6),
    say("a small lie", 0.68, 0.38, 0.4, at(S, "tells a small lie"), highlight="small lie"),
    say("“The situation made it necessary.”", 0.68, 0.5, 0.44, at(S, "And decides the situation"))])
t = at(S, "And sometimes, when a belief") - 0.2
add(S, t, "More certain instead of more curious", [
    say("more certain", 0.5, 0.4, 0.5, at(S, "we get more certain"), highlight="more certain"),
    cap("instead of more curious", 0.5, 0.5, 0.5, at(S, "instead of more curious"))])
t = at(S, "So here's the signal") - 0.2
add(S, t, "The double standard", [
    say("The double standard.", 0.5, 0.2, 0.6, at(S, "The double standard"), highlight="double standard."),
    shape("ring", 0.34, 0.5, 0.2, 0.36, at(S, "Are we asking more"), color="accent"),
    cap("evidence against us", 0.34, 0.74, 0.3, at(S, "Are we asking more") + 0.4),
    shape("ring", 0.68, 0.53, 0.08, 0.14, at(S, "than the evidence for us")),
    cap("evidence for us", 0.68, 0.66, 0.3, at(S, "than the evidence for us") + 0.3)])

# ---------------------------------------------------------------- 08 · the dangerous contradiction
S = "s08-dangerous"
add(S, 0.0, "Not proof that people are irrational", [
    say("Proof that people are irrational?", 0.5, 0.42, 0.6, 0.3),
    shape("line", 0.5, 0.415, 0.42, 0.03, at(S, "But that misses the point"), reveal="draw", color="accent", fade_in=0.7)])
t = at(S, "Beliefs organise our lives") - 0.2
add(S, t, "Beliefs connect us to people; challenging them costs", [
    person(0.38, t + 0.2), person(0.5, t + 0.4), person(0.62, t + 0.6, flip=True),
    cap("beliefs connect us to other people", 0.5, 0.7, 0.5, at(S, "They connect us")),
    say("Sometimes the evidence against it really is weak.", 0.5, 0.82, 0.7, at(S, "Sometimes the evidence against"))])
t = at(S, "The goal isn't to accept") - 0.2
add(S, t, "Evidence-backed belief versus invested belief", [
    say("Tell the difference.", 0.5, 0.24, 0.5, at(S, "It's to tell the difference")),
    cap("a belief you hold because", 0.3, 0.42, 0.36, at(S, "A belief you hold because")),
    say("the evidence supports it", 0.3, 0.5, 0.36, at(S, "A belief you hold because") + 0.8),
    cap("a belief you hold because", 0.7, 0.42, 0.36, at(S, "and a belief you hold")),
    say("you've invested in defending it", 0.7, 0.5, 0.36, at(S, "and a belief you hold") + 0.8,
        highlight="invested in defending it")])
t = at(S, "That's hard to see") - 0.2
add(S, t, "A rationalisation arrives dressed as an explanation", [
    img("met-durer-melencolia", 0.28, 0.45, 0.36, 0.8, t, crop=[0.04, 0.02, 0.96, 0.98], zoom_from=1.0,
        zoom_to=1.06),
    cap("Albrecht Dürer, Melencolia I, 1514", 0.28, 0.92, 0.52, t + 0.8),
    quote("“A rationalisation rarely announces itself as one. It usually arrives dressed as an explanation.”",
          "arrives dressed as an explanation", "q-art-rationalisation", t),
    cap(ART, 0.69, 0.64, 0.42, at(S, "After all") + 3.0)], ["q-art-rationalisation"])
t = at(S, "So ask yourself one thing") - 0.2
add(S, t, "What evidence would change my mind?", [
    say("What evidence, specifically, would change my mind?", 0.5, 0.34, 0.66, at(S, "What evidence, specifically"),
        highlight="would change my mind?", reveal="words", fade_in=0.45),
    text("nothing", "heading", 0.5, 0.52, 0.4, at(S, "If the honest answer"), highlight="nothing"),
    say("You may be protecting a commitment.", 0.5, 0.7, 0.7, at(S, "You may be protecting"),
        highlight="protecting a commitment.")])

# ---------------------------------------------------------------- 09 · the field exercise
S = "s09-exercise"
t = chapter(S, 8, "Level VIII: a field exercise", at(S, "First, name") - 0.2)
steps = [("1 · Name the contradiction", "First, name"), ("2 · Separate fact from meaning", "Second, separate"),
         ("3 · Ask what being wrong would cost", "Third, ask"), ("4 · Decide what would change your mind", "Fourth, decide"),
         ("5 · Same standard, both directions", "And fifth")]
add(S, t, "Five steps to find the belief you are protecting", [
    img("met-parmigianino-justice", 0.26, 0.45, 0.28, 0.8, t, zoom_from=1.0, zoom_to=1.04),
    cap("Parmigianino, Justice Holding Scales, 1503–40", 0.26, 0.92, 0.46, t + 0.8)] +
    [say(s, 0.68, y, 0.56, at(S, k)) for (s, k), y in zip(steps, (0.13, 0.26, 0.47, 0.62, 0.76))] +
    [cap("“I didn't get the job” is a fact.", 0.68, 0.335, 0.56, at(S, "I didn't get the job")),
     cap("“I'm not good enough” is an interpretation.", 0.68, 0.385, 0.56, at(S, "I'm not good enough")),
     cap("pride? status? years of effort?", 0.68, 0.54, 0.56, at(S, "Your pride"))])
t = at(S, "You might still keep") - 0.2
add(S, t, "Confidence that survived an examination", [
    img("met-parmigianino-justice", 0.26, 0.45, 0.28, 0.8, t, zoom_from=1.04, zoom_to=1.0, fade_in=0.8),
    cap("Parmigianino, Justice Holding Scales, 1503–40", 0.26, 0.92, 0.46, t + 0.6),
    cap("You might still keep your belief, and that's fine.", 0.68, 0.36, 0.5, t + 0.3),
    say("your confidence survived an examination… instead of avoiding one", 0.68, 0.5, 0.5,
        at(S, "The point is that"), highlight="instead of avoiding one", reveal="words", fade_in=0.45)])

# ---------------------------------------------------------------- 10 · the final question
S = "s10-question"
add(S, 0.0, "Being smart doesn't protect you", [
    say("Being smart doesn't protect you.", 0.5, 0.36, 0.6, at(S, "Being smart"), highlight="doesn't protect you."),
    cap("the skills that examine a belief… can build a better defence for it", 0.5, 0.48, 0.7, at(S, "The same skills"))])
t = at(S, "But that's no reason") - 0.2
add(S, t, "People do change their minds", [
    cap("no reason for cynicism", 0.5, 0.34, 0.5, t + 0.3),
    say("People do change their minds.", 0.5, 0.46, 0.6, at(S, "People do change"), highlight="change their minds."),
    cap("when the evidence is clear… and there's room to look honestly", 0.5, 0.56, 0.7, at(S, "When the evidence"))],
    ["c-anglin-2019"], ["src-anglin-2019"])
t = at(S, "So the goal isn't") - 0.2
add(S, t, "Meet a contradiction without treating it as an enemy", [
    img("met-friedrich-moon", 0.3, 0.45, 0.44, 0.7, t, zoom_from=1.0, zoom_to=1.06, drift_x=0.006),
    cap("Caspar David Friedrich, Two Men Contemplating the Moon, c. 1825–30", 0.3, 0.86, 0.5, t + 0.8),
    say("meet a contradiction… without treating it as an enemy", 0.71, 0.46, 0.44, at(S, "It's to meet"),
        highlight="without treating it as an enemy", reveal="words", fade_in=0.45)])
t = at(S, "Sometimes the evidence is wrong") - 0.2
add(S, t, "Evidence, belief, or the story around it", [
    say("Sometimes the evidence is wrong.", 0.5, 0.34, 0.6, t + 0.2),
    say("Sometimes the belief is wrong.", 0.5, 0.45, 0.6, at(S, "Sometimes the belief is wrong")),
    say("Sometimes the story needs to change.", 0.5, 0.56, 0.6, at(S, "but the story we built"),
        highlight="the story needs to change.")])
t = at(S, "So the next time") - 0.2
q = at(S, "Am I trying")
add(S, t, "The final question", [
    img("met-rodin-thinker-cut", 0.28, 0.46, 0.3, 0.76, t, feather=0.05, zoom_from=1.06, zoom_to=1.0),
    cap("Auguste Rodin, The Thinker, modeled c. 1880", 0.28, 0.9, 0.52, t + 0.8),
    quote("“Am I trying to understand what is true, or am I trying to preserve the person I believe myself to be?”",
          "preserve the person I believe myself to be", "q-art-final", t),
    cap(ART, 0.69, 0.66, 0.42, q + 3.0)], ["q-art-final"])

# clearly visible, eased motion on every picture: a 10% push (or pull) over its time on screen
for b in beats:
    for la in b.get("layers", []):
        if la["kind"] != "image" or la["asset_id"] == "chapter-core-overview":
            continue
        zf, zt = la.get("zoom_from", 1.0), la.get("zoom_to", 1.0)
        la["zoom_from"], la["zoom_to"] = (1.10, 1.0) if zf > zt else (1.0, 1.10)
# the $1 bill and the $20 coin arrive from opposite sides
for b in beats:
    for la in b.get("layers", []):
        if la.get("asset_id") == "met-durand-one-dollar":
            la["enter"] = "slide_right"
        if la.get("asset_id") == "met-saint-gaudens-twenty-cut":
            la["enter"] = "slide_left"
json.dump({"schema_version": "1.0", "beats": beats}, open(f"{P}/visuals.json", "w"), indent=2, ensure_ascii=False)
print(len(beats), "beats")
