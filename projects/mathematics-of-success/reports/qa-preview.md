# QA report: mathematics-of-success (preview)

**Verdict: NOT READY**: 25 blocker(s), 4 open warning(s).

- Generated: 2026-10-19T22:03:13+00:00 (pipeline 0.1.0)
- Render report: `reports/render-preview-20261018T203234Z.json`
- Video: `/Users/nikhiltalla/Desktop/Video/projects/mathematics-of-success/renders/preview/mathematics-of-success-preview-a9a843ef5767.mp4`
- Duration 131.79 s; loudness -20.5 LUFS; true peak -5.2 dBTP; range 3.4 LU

## Blockers (must be fixed)

- `render.stale` **mathematics-of-success-preview-a9a843ef5767.mp4**: the project changed since this render; render again
- `research.claim.critical_unreviewed` **c-identical-start**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-matthew**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-power-law**: critical claim used in narration is unverified
- `research.claim.critical_unreviewed` **c-superstars**: critical claim used in narration is unverified
- `rights.asset.unapproved_in_use` **g-close**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **g-compounding**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **g-luck**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **g-power-law**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **g-songs**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **g-title**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **music-pad**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s01-cold-open**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s02-same-start**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s03-compounding**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s04-superstars**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s05-luck**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s06-strategy**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **narr-s07-close**: rights recorded; ready for human review
- `rights.asset.unapproved_in_use` **stock-city**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **stock-crowd**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **stock-dice**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **stock-music**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `rights.asset.unapproved_in_use` **stock-notebook**: missing: identifiable_people is unknown; trademarks_visible is unknown
- `script.not_approved` **script**: script is not approved; run 'pipeline script approve'

## Warnings (fix, or waive with a written reason)

- `captions.readability` **mathematics-of-success-preview-a9a843ef5767.srt**: 2 readability note(s): cue 9: 3 lines (max 2); cue 34: 3 lines (max 2)  
  waive: `pipeline qa waive <project> "captions.readability@mathematics-of-success-preview-a9a843ef5767.srt" --by NAME --rationale "..."`
- `picture.frozen` **18.6s**: 4.9 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@18.6s" --by NAME --rationale "..."`
- `picture.frozen` **63.0s**: 4.6 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@63.0s" --by NAME --rationale "..."`
- `picture.frozen` **85.4s**: 5.0 s with no visible change (may be a deliberate still shot)  
  waive: `pipeline qa waive <project> "picture.frozen@85.4s" --by NAME --rationale "..."`

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
