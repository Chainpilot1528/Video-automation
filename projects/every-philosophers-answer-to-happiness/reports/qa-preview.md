# QA report: every-philosophers-answer-to-happiness (preview)

**Verdict: NOT READY**: 27 blocker(s), 8 open warning(s).

- Generated: 2026-10-22T19:16:15+00:00 (pipeline 0.1.0)
- Render report: `reports/render-preview-20261022T191558Z.json`
- Video: `/Users/nikhiltalla/Desktop/Video/projects/every-philosophers-answer-to-happiness/renders/preview/every-philosophers-answer-to-happiness-preview-32b178bc048f.mp4`
- Duration 143.71 s; loudness -20.2 LUFS; true peak -4.6 dBTP; range 1.8 LU

## Blockers (must be fixed)

- `research.claim.critical_unreviewed` **q-aristotle-swallow**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **q-epictetus-ench5**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **q-epicurus-pd5**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **q-mill-ask**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **q-schopenhauer-pendulum**: critical claim used in narration is unverified
- `rights.asset.unapproved_in_use` **chapter-map**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **met-chrysippus-cut**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-chrysippus-head**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-constable-salisbury**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-epicurus-cut**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-epicurus-head**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-pendulum-clock-cut**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **met-rembrandt-aristotle**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **music-pad**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s01-cold-open**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s02-epicurus**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s03-aristotle**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s04-stoics**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s05-schopenhauer**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s06-mill**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s07-close**: rights recorded; ready for human review
- `script.not_approved` **script**: script is not approved; run 'pipeline script approve'
- `visual.quote_unverified` **v-s02-epicurus-comp**: quote claim 'q-epicurus-pd5' is unverified; check it against the source
- `visual.quote_unverified` **v-s03-aristotle-comp**: quote claim 'q-aristotle-swallow' is unverified; check it against the source
- `visual.quote_unverified` **v-s04-stoics-comp**: quote claim 'q-epictetus-ench5' is unverified; check it against the source
- `visual.quote_unverified` **v-s05-schopenhauer-comp**: quote claim 'q-schopenhauer-pendulum' is unverified; check it against the source
- `visual.quote_unverified` **v-s06-mill-comp**: quote claim 'q-mill-ask' is unverified; check it against the source

## Warnings (fix, or waive with a written reason)

- `captions.readability` **every-philosophers-answer-to-happiness-preview-32b178bc048f.srt**: 2 readability note(s): cue 1: 3 lines (max 2); cue 7: 3 lines (max 2)  
  waive: `pipeline qa waive <project> "captions.readability@every-philosophers-answer-to-happiness-preview-32b178bc048f.srt" --by NAME --rationale "..."`
- `picture.frozen` **1.0s**: 7.3 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@1.0s" --by NAME --rationale "..."`
- `picture.frozen` **138.1s**: 4.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@138.1s" --by NAME --rationale "..."`
- `picture.frozen` **18.2s**: 5.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@18.2s" --by NAME --rationale "..."`
- `picture.frozen` **48.3s**: 8.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@48.3s" --by NAME --rationale "..."`
- `picture.frozen` **56.9s**: 5.4 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@56.9s" --by NAME --rationale "..."`
- `picture.frozen` **8.3s**: 6.2 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@8.3s" --by NAME --rationale "..."`
- `visual.repeated` **chapter-map**: the same visual is used in 6 beats  
  waive: `pipeline qa waive <project> "visual.repeated@chapter-map" --by NAME --rationale "..."`

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
