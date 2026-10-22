# Pilot plan: archival-style episode

**Status:** steps 1-5 built and tested (2026-10-21/23); chapter device: stone steps; a test scene was rendered for review. Narrator switched to `reckoner` on 2026-10-22. Pilot topic: "Every Philosopher's Answer to Happiness". Written 2026-10-21.
**Goal:** make videos in the visual style of the reference below, using our own design, sources and script, and the `reckoner` voice.

---

## 1. The reference style

The reference is "Every Philosopher's Answer to Death | Iceberg Explained" by *Philosophy Is Timeless* (17:14, 720p). It was supplied by the user and analysed locally. Nothing from it is copied into this repository or used in our videos.

**What it looks like:**

- **A black canvas, like a museum at night.** Average brightness is 36/255.
- **One or two public-domain artworks float on the black**, cut out or with soft edges: marble busts, paintings, an olive branch, engravings, old book title pages.
- **Slow movement:** objects drift and gently zoom. Changes are fades and re-arrangements, not cuts. There are only about 3 hard cuts per minute, and the average shot holds about 20 s.
- **Kinetic quotes:** the quote appears word by word as the narrator reads it, in serif italics. The key phrase is in red, with a small-caps source line underneath (work and translator).
- **Portrait medallions:** a philosopher is introduced as a bust that becomes an oval medallion, with a small-caps name and a place and date ("Athens, c. 300 BC").
- **A chapter map:** a low-poly iceberg with labelled levels ("Level 1: The Surface" down to "The Bottom") returns between chapters. Medallions are placed on it as each thinker is covered.
- **Extras:** a small paper-cutout walking figure, and occasional diagrams.
- **Sound:** a calm, deep narrator over a quiet continuous music bed. We use the `reckoner` house preset with `--humanize` (sentence-by-sentence TTS, natural pauses, recorded sentence timings for quote sync). The `sage` preset (`references/sage/README.md`) remains an alternative.

**What the pipeline already has:** scenes, research ledger and claims, the `reckoner` voice, the music bed, rights tracking, per-scene cached rendering, slow push and pan, SVG graphics, captions, and QA with sign-off.

**What's missing** is the visual layer: archival images, layered compositions on black, kinetic quotes, medallions and the chapter map.

---

## 2. The six steps

### Step 1: Public-domain image source
- **Commands:** `pipeline archive search "<query>"` and `pipeline archive add <project> <ref> --id <asset>`.
- **Sources:**
  - The **Metropolitan Museum of Art** Open Access API.
  - The **Art Institute of Chicago** API.

  Both are free, need no key, and release public-domain images as CC0.
- Only items marked public domain can be added.
- The rights record is filled in automatically: licence, museum, object ID, artist, title, date and source URL.
- Title, artist and date are kept for on-screen labels.
- Downloads use the same safety as Pexels: official API hosts only, verified HTTPS, a checksum, and a read-only original.
- Every image still needs a person's rights review before publication.
- **New downloads:** none (only the images you approve).

### Step 2: Black-canvas compositor
- **A new "composition" visual type:** a beat holds several **layers** (image, text, medallion) instead of one full-screen picture.
- **Each layer has:**
  - position and size
  - a soft-edge mask
  - slow drift or zoom
  - its own fade-in and fade-out times within the scene
- **Rendering:** built on the existing per-scene renderer (FFmpeg overlay chains), cached and fingerprinted like everything else.
- **This is the engine of the style.** After this step comes a **test scene for review**: one bust, one quote, slow drift.

### Step 3: Cut-outs and medallions
- **Medallions:** oval or circle frames with a thin ring, plus a name and date label.
- **Paintings:** feathered edges, so a painting melts into the black.
- **Background removal (optional):** automatic removal for busts and objects, using **rembg** (MIT licence, model about 170 MB). Many museum photos already have plain backdrops, so this could wait.

### Step 4: Kinetic quotes and labels
- **The quote reveals word by word** in sync with the narration, with an accent-coloured key phrase and a small-caps citation line.
- **Timing:**
  - Sentence timing comes from the humanize pass, which knows where each sentence starts.
  - Word timing is estimated within each sentence.
  - Exact word timing would need a forced aligner (a later upgrade).
- **Name and date labels** for people and artworks.
- **Font:** **Cormorant Garamond** (SIL Open Font License, free, a few MB).
- **Honesty rule:** every on-screen quote must be a claim in the research ledger, with its source and a **public-domain translation**. No invented or paraphrased "quotes".

### Step 5: Chapter map
- **A reusable SVG map** with labelled levels. Markers and medallions appear as chapters progress, and the camera pans down one level at a time.
- **Our own design:** a different shape, palette and typography, not a copy of their iceberg artwork, which is their creative work. The "levels" format itself is a common internet format.
- **Options:** our own iceberg-style levels, descending stone steps, or rock strata (decision 2 below).

### Step 6: Pilot episode (about 3 minutes)
- **Research:** a ledger with real, checked sources.
- **Script:** written for the ear.
- **Narration:** `--preset reckoner --humanize`.
- **Visuals:** the chapter map plus 6–8 scenes.
- **Finish:** music bed, preview render, then the QA report.
- **Purpose:** prove the whole chain before scaling to 15-minute episodes.

---

## 3. Build order

1. **Step 1** (archive image source)
2. **Step 2** (compositor), then a **test scene for review**. If it doesn't feel right, we adjust before building on top of it.
3. **Step 4** (kinetic quotes)
4. **Step 3** (medallions and cut-outs)
5. **Step 5** (chapter map)
6. **Step 6** (pilot episode, preview, QA)

Each step gets tests, docs and a build-log entry, and is committed only when you ask.

---

## 4. Honest limits

- **Render time:** layered, animated scenes are heavier. A 3-minute preview may take several minutes on this Mac. The `reckoner` voice (Kokoro) is fast, a few seconds per scene; `sage` (Qwen3) would be about 12× slower than real time. Both are cached, so a change only rebuilds what changed.
- **Quote sync** is sentence-accurate with estimated words, not frame-perfect.
- **The paper-cutout walking figure** isn't included. It's a custom illustration; a simple silhouette could come later.
- **Black and frozen-picture QA warnings** will fire often in this style (dark, slow shots). They're expected and can be waived with a rationale.

---

## 5. Decisions needed before building

1. **Pilot topic.** It should be different from the reference's (not death). Options:
   - "Every Philosopher's Answer to Happiness"
   - "What the Stoics Actually Said About Anger"
   - "Why Boredom Disappeared" (the build plan's suggested pilot)
   - your own idea
2. **Chapter device.** Our own iceberg-style levels, or something distinct, like stone steps or rock strata.
3. **Background removal.** Download the rembg model (about 170 MB) now, or start with museum photos as they are.

## 6. Rights and ethics

- Use only **public-domain or CC0** images, and record each one's rights.
- Use only quotes with a real source and a public-domain translation, tracked in the research ledger.
- **Don't copy** the reference's graphics, script, layout or audio. We match the genre and mood, not the work.
- Narration is the `reckoner` preset: a stock voice, not a clone.
- **Publishing stays manual**, after QA sign-off.
