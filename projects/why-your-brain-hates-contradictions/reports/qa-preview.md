# QA report: why-your-brain-hates-contradictions (preview)

**Verdict: NOT READY**: 32 blocker(s), 61 open warning(s).

- Generated: 2026-10-22T21:55:29+00:00 (pipeline 0.1.0)
- Render report: `reports/render-preview-20261022T215457Z.json`
- Video: `/Users/nikhiltalla/Desktop/Video/projects/why-your-brain-hates-contradictions/renders/preview/why-your-brain-hates-contradictions-preview-5f82f7de320a.mp4`
- Duration 627.70 s; loudness -20.2 LUFS; true peak -4.6 dBTP; range 2.0 LU

## Blockers (must be fixed)

- `research.claim.critical_unreviewed` **c-anglin-2019**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-fc-design**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-fc-results**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-vz-2026**: critical claim used in narration is unverified
- `rights.asset.unapproved_in_use` **chapter-map**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **met-brouwer-smokers**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-bruegel-harvesters**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-caraglio-diogenes**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-durer-hercules-crossroad**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-durer-melencolia**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-lahyre-narcissus**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-parmigianino-justice**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-remmelin-microcosme**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-rodin-thinker**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-rodin-thinker-cut**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-sisyphus-tantalus**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **music-pad-v2**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s01-negotiation**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s02-theory**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s03-experiment**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s04-identity**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s05-motivated**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s06-brain**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s07-everyday**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s08-dangerous**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s09-exercise**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s10-question**: rights recorded; ready for human review
- `script.not_approved` **script**: script is not approved; run 'pipeline script approve'
- `visual.quote_unverified` **v-s01-negotiation-b07**: quote claim 'q-art-preserve' is unverified; check it against the source
- `visual.quote_unverified` **v-s04-identity-b06**: quote claim 'q-art-consequences' is unverified; check it against the source
- `visual.quote_unverified` **v-s08-dangerous-b04**: quote claim 'q-art-rationalisation' is unverified; check it against the source
- `visual.quote_unverified` **v-s10-question-b05**: quote claim 'q-art-final' is unverified; check it against the source

## Warnings (fix, or waive with a written reason)

- `captions.readability` **why-your-brain-hates-contradictions-preview-5f82f7de320a.srt**: 9 readability note(s): cue 17: on screen only 0.24 s; cue 64: on screen only 0.29 s; cue 170: on screen 7.1 s (max 7); and 6 more  
  waive: `pipeline qa waive <project> "captions.readability@why-your-brain-hates-contradictions-preview-5f82f7de320a.srt" --by NAME --rationale "..."`
- `picture.black` **123.2s**: 7.3 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@123.2s" --by NAME --rationale "..."`
- `picture.black` **137.5s**: 6.1 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@137.5s" --by NAME --rationale "..."`
- `picture.black` **162.7s**: 48.5 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@162.7s" --by NAME --rationale "..."`
- `picture.black` **215.3s**: 4.7 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@215.3s" --by NAME --rationale "..."`
- `picture.black` **238.2s**: 22.0 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@238.2s" --by NAME --rationale "..."`
- `picture.black` **278.5s**: 5.8 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@278.5s" --by NAME --rationale "..."`
- `picture.black` **311.7s**: 32.4 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@311.7s" --by NAME --rationale "..."`
- `picture.black` **375.3s**: 23.1 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@375.3s" --by NAME --rationale "..."`
- `picture.black` **38.5s**: 12.1 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@38.5s" --by NAME --rationale "..."`
- `picture.black` **402.5s**: 13.5 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@402.5s" --by NAME --rationale "..."`
- `picture.black` **428.2s**: 32.4 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@428.2s" --by NAME --rationale "..."`
- `picture.black` **476.0s**: 13.2 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@476.0s" --by NAME --rationale "..."`
- `picture.black` **499.5s**: 15.0 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@499.5s" --by NAME --rationale "..."`
- `picture.black` **560.4s**: 53.8 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@560.4s" --by NAME --rationale "..."`
- `picture.black` **57.5s**: 9.9 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@57.5s" --by NAME --rationale "..."`
- `picture.black` **71.6s**: 6.4 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@71.6s" --by NAME --rationale "..."`
- `picture.black` **97.1s**: 12.6 s of near-black picture (may be a deliberate dark shot or fade)  
  waive: `pipeline qa waive <project> "picture.black@97.1s" --by NAME --rationale "..."`
- `picture.frozen` **1.0s**: 5.8 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@1.0s" --by NAME --rationale "..."`
- `picture.frozen` **123.9s**: 5.8 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@123.9s" --by NAME --rationale "..."`
- `picture.frozen` **138.4s**: 5.5 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@138.4s" --by NAME --rationale "..."`
- `picture.frozen` **148.9s**: 6.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@148.9s" --by NAME --rationale "..."`
- `picture.frozen` **154.9s**: 7.1 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@154.9s" --by NAME --rationale "..."`
- `picture.frozen` **166.0s**: 15.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@166.0s" --by NAME --rationale "..."`
- `picture.frozen` **182.0s**: 28.4 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@182.0s" --by NAME --rationale "..."`
- `picture.frozen` **215.5s**: 4.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@215.5s" --by NAME --rationale "..."`
- `picture.frozen` **239.5s**: 20.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@239.5s" --by NAME --rationale "..."`
- `picture.frozen` **278.7s**: 5.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@278.7s" --by NAME --rationale "..."`
- `picture.frozen` **285.1s**: 16.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@285.1s" --by NAME --rationale "..."`
- `picture.frozen` **311.7s**: 8.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@311.7s" --by NAME --rationale "..."`
- `picture.frozen` **319.7s**: 23.5 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@319.7s" --by NAME --rationale "..."`
- `picture.frozen` **359.1s**: 10.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@359.1s" --by NAME --rationale "..."`
- `picture.frozen` **369.1s**: 5.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@369.1s" --by NAME --rationale "..."`
- `picture.frozen` **375.2s**: 12.8 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@375.2s" --by NAME --rationale "..."`
- `picture.frozen` **38.6s**: 11.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@38.6s" --by NAME --rationale "..."`
- `picture.frozen` **388.0s**: 9.5 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@388.0s" --by NAME --rationale "..."`
- `picture.frozen` **404.0s**: 4.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@404.0s" --by NAME --rationale "..."`
- `picture.frozen` **410.0s**: 9.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@410.0s" --by NAME --rationale "..."`
- `picture.frozen` **429.1s**: 6.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@429.1s" --by NAME --rationale "..."`
- `picture.frozen` **435.8s**: 17.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@435.8s" --by NAME --rationale "..."`
- `picture.frozen` **454.1s**: 6.5 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@454.1s" --by NAME --rationale "..."`
- `picture.frozen` **461.3s**: 13.8 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@461.3s" --by NAME --rationale "..."`
- `picture.frozen` **475.9s**: 7.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@475.9s" --by NAME --rationale "..."`
- `picture.frozen` **483.4s**: 5.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@483.4s" --by NAME --rationale "..."`
- `picture.frozen` **499.6s**: 14.1 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@499.6s" --by NAME --rationale "..."`
- `picture.frozen` **524.0s**: 5.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@524.0s" --by NAME --rationale "..."`
- `picture.frozen` **529.8s**: 7.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@529.8s" --by NAME --rationale "..."`
- `picture.frozen` **537.4s**: 7.7 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@537.4s" --by NAME --rationale "..."`
- `picture.frozen` **545.1s**: 7.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@545.1s" --by NAME --rationale "..."`
- `picture.frozen` **552.1s**: 5.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@552.1s" --by NAME --rationale "..."`
- `picture.frozen` **560.5s**: 10.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@560.5s" --by NAME --rationale "..."`
- `picture.frozen` **57.6s**: 7.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@57.6s" --by NAME --rationale "..."`
- `picture.frozen` **571.8s**: 42.3 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@571.8s" --by NAME --rationale "..."`
- `picture.frozen` **6.7s**: 6.8 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@6.7s" --by NAME --rationale "..."`
- `picture.frozen` **615.2s**: 4.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@615.2s" --by NAME --rationale "..."`
- `picture.frozen` **71.7s**: 6.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@71.7s" --by NAME --rationale "..."`
- `picture.frozen` **79.7s**: 9.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@79.7s" --by NAME --rationale "..."`
- `picture.frozen` **97.3s**: 10.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@97.3s" --by NAME --rationale "..."`
- `visual.repeated` **chapter-map**: the same visual is used in 7 beats  
  waive: `pipeline qa waive <project> "visual.repeated@chapter-map" --by NAME --rationale "..."`
- `visual.repeated` **met-lahyre-narcissus**: the same visual is used in 2 beats  
  waive: `pipeline qa waive <project> "visual.repeated@met-lahyre-narcissus" --by NAME --rationale "..."`
- `visual.repeated` **met-rodin-thinker-cut**: the same visual is used in 2 beats  
  waive: `pipeline qa waive <project> "visual.repeated@met-rodin-thinker-cut" --by NAME --rationale "..."`

## Human review checklist

Automated checks can't judge these. Review the video yourself, then sign off.

**Script**

- [ ] Opens with a compelling question
- [ ] Has a clear thesis
- [ ] Every factual claim is supported by its sources
- [ ] Presents counter-evidence where it exists
- [ ] States uncertainty honestly
- [ ] Every section advances the argument

**Visuals**

- [ ] Each visual communicates the intended idea
- [ ] No visual implies evidence that doesn't exist
- [ ] Text and graphics are legible on a phone
- [ ] Reconstructions and generated images are labelled
- [ ] Rights and credits are recorded for every visual

**Final video**

- [ ] The opening is engaging but not misleading
- [ ] Narration and visuals are in sync
- [ ] Names, dates, numbers and captions are correct
- [ ] The voice is clear over the music
- [ ] No awkward gaps or repetitive visuals
- [ ] The ending resolves the question or says what remains unknown
- [ ] Credits and the source list are ready for the description

## Sign-off

When there are no blockers, every warning is fixed or waived, and the checklist is done:

```bash
pipeline qa signoff <project> --by NAME --checklist-done
```

Sign-off marks the project `publication_ready`. **Publishing is always manual.**
