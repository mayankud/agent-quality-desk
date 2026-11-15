# Changelog

Prepared by Mayank Udaywal. Each entry is a frozen lock or run. Failed runs stay on record.

## 0.5.0, 15 Nov 2026: Phase 0, Run 5 (FAILED)

- Blind run P0-R5-ef80449a on holdout v4 (50 cases) and stress v4 (12 cases) under lock P0-R5-L8. 26 extraction and 26 judge agents, run once.
- Phase 0 decision: **FAIL**. 11 of 16 gated metric rules and all 5 evidence rules passed. Details in [PHASE0_RUN5_REPORT.md](PHASE0_RUN5_REPORT.md).
- Scores SHA-256 `a7b2b1f66b840ee5b0dbab11ed60ac57545455d7974e9e775051dd6a918c31a5`. It replays byte for byte with `cd pipeline && python3 replay.py`.

## Pre-blind locks, 13 to 15 Nov 2026

| Lock | Outcome |
| :---- | :---- |
| P0-R5-L1 | Failed the two-pass gate (claim parts 0.898) |
| P0-R5-L2 | Failed the two-pass gate (claim parts 0.80) |
| P0-R5-L3 | Passed and was verified, then superseded by review findings on refund promises, batch completeness, stress coverage and lock binding |
| P0-R5-L4 | Aborted. A new destination check rejected a valid credit promise |
| P0-R5-L5 | Failed. Overlapping claim-type definitions in the extraction prompt |
| P0-R5-L6 | Passed, then superseded. A probe showed stress results were not bound to their frozen conversations |
| P0-R5-L7 | Failed (claim parts 39 of 45) |
| P0-R5-L8 | Passed (42 of 42, 27 of 27). The first extraction audit window was flagged, so extraction was rerun cleanly under the same lock. Both runs are kept |

## Runs 1 to 4

Rule-based stand-ins for the model steps, on holdouts v1 to v3. Phase 0 stayed open. The history is in the PRD version log (`pipeline/rubric/PRD_v8_rev7.md`).
