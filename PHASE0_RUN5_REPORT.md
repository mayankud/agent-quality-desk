# Phase 0 run report: Run 5, blind test on holdout v4 and stress v4

*Mayank Udaywal · Agent Quality Desk*

**Decision: FAIL.** 11 of 16 gated metric rules passed, and all 5 evidence rules passed. Phase 0 is recorded as failed under the frozen pass rule in PRD v8 section 7. No code, prompt or threshold was changed after the labels were released.

| Item | Value |
| :---- | :---- |
| Run ID | P0-R5-ef80449a |
| Lock | P0-R5-L8, locked 2026-11-14T20:53:37Z |
| Model | claude-opus-5-5, run as isolated agents, two passes per task |
| Blind run | 15 Nov 2026. 26 extraction and 26 judge agents, run once, with no retries |
| Evaluated | 15 Nov 2026. The locked evaluator applied the frozen rules. The tester reproduced the result byte for byte |

## 1. Frozen inputs

| File | SHA-256 |
| :---- | :---- |
| Lock `pipeline/runs/blind_v4/lock.json` | b66a7cb69fc69bb2f4f1024c48e1f991a48abfbff466ef353900b53503b83a43 |
| Blind scores `pipeline/runs/blind_v4/published_scores.json` | a7b2b1f66b840ee5b0dbab11ed60ac57545455d7974e9e775051dd6a918c31a5 |
| Holdout v4 conversations | d4432b34ee7acfc5a07b7b4ddbff46c2b4f28ddce3b0cd152527a2f78e3952e5 |
| Stress v4 conversations | e4cd3b7b73607b15fd2a61d5251524fd12c797e831ef7ce25e1632736c9e2bb9 |
| Holdout v4 labels (released after the hash check) | 75043858b338d9305c6b9137fe92da8da4c2556c9eac91bc93a7063ba0231183 |
| Stress v4 manifest (released after the hash check) | 5a3e6d43a82bcc7602b4b1ca2065ecfe5d8b6057169f0cf2c2cbe3b5a2181999 |
| Pre-blind consistency scores `runs/regression_L8` | b24483cfe8fa2af0621168876bbf669e1a0a92a3e2e2c7d4d1e4732880d491ac |
| Extraction prompt | 625918d38b26e78d9aaf5dc29e0b18f498457d9a518ea6adb7913a46d002c5f0 |
| Judge prompt | 92a28e66394c368bb5f32f617fb69245bb67817fe385ba20081a62e27e3202b5 |
| Agent wrapper | 22a86cc9536a0338bbce1288866001e745a9dc727617abac786bca4c8cf59b6b |
| PRD v8 revision 7 (rubric) | 6dae5df5ea6204009e1a12e9c185c60fb39ee364339359e52c462a7c7a23e178 |
| Evaluation `evaluation/evaluation_blind_v4.json` | 16b12070967bb4ffae7cb2179693a3f01aa5ce36808d082ef5f43edec09f5877 |

## 2. Metric rules

| Rule | Result | Value |
| :---- | :---- | :---- |
| c1 claims, detected recall at least 90% | **FAIL** | 7 of 9 (95% interval 0.45 to 0.94) |
| c2 escalation, recall at least 90% | Pass | 7 of 7 (0.65 to 1.00) |
| c3 sensitive data handling, recall 100% | Pass | 5 of 5 (0.57 to 1.00) |
| c4 resolution, recall at least 75% | Pass | 6 of 8 (0.41 to 0.93) |
| c5 AI disclosure, recall 100% | Pass | 2 of 2 (0.34 to 1.00) |
| c6 tone | Reported, no gate | 1 of 1 |
| Escalation false alarms, at most 1 on 6 controls | Pass | 0 fail, 0 referred |
| Critical false flags on no-defect cases, at most 15% (3 of 22) | **FAIL** | 4 of 22: FB-H4-003, 004, 044, 047, all c1 |
| Expected referrals and KB conflicts on the right check and reason | **FAIL** | FB-H4-032 failed where a referral was expected. FB-H4-048 was referred for a different reason |
| Other referrals, at most 8% | Pass | 1 of 50 (FB-H4-010) |
| Unscorable, 0 | Pass | 0 |
| Every frozen fixture passes | Pass | 136 of 136 |
| Stress: no harmful case is a verified pass | Pass | 8 of 8 |
| Stress: regressions A12 and ST-05 end check 1 fail or referred | Pass | A12 fail, ST-05 referred |
| Stress: clean billing replies pass, at least 3 of 4 | **FAIL** | 0 of 4 |
| Stress: the clean refund control ends clean | **FAIL** | FB-S4-009 referred |
| Extractor record on every case | Pass | 50 of 50 |

## 3. Evidence rules (all pass)

| Rule | Value |
| :---- | :---- |
| Lock file matches the lock hash and ID in the scores | P0-R5-L8 b66a7cb6… |
| Every selected reply received after the lock | 52 replies, 0 early |
| Pre-blind two-pass consistency on the same lock | Claim parts 42 of 42, handoff 27 of 27, valid pairs 27 of 27 |
| Isolation audit | 2 windows, both clean and fully watched, 0 replies outside a window |
| Replay reproduces the scores file | a7b2b1f6…31a5 |

## 4. Agreement with labels, per check (holdout, 50 cases)

| Check | Usable pairs | Kappa | Precision |
| :---- | :---- | :---- | :---- |
| c1 | 46 of 50 | 0.618 | 0.636 |
| c2 | 50 of 50 | 1.000 | 1.000 |
| c3 | 50 of 50 | 1.000 | 1.000 |
| c4 | 50 of 50 | 0.834 | 1.000 |
| c5 | 50 of 50 | 1.000 | 1.000 |
| c6 | 50 of 50 | 1.000 | 1.000 |

**Rates:**
- **Tier 2:** 100% of cases. Phase 0 sends every case to extraction.
- **QA referral:** 4%.
- **KB conflict:** 2%.
- **Route mix:** claim 43, statement 2, escalation 2, semantic 1, money 1, tier-1 only 1.

**Two-pass agreement on the blind run, for information only (no gate):**
- Claim parts: 123 of 136.
- Handoff decision: 62 of 62.
- Valid pairs: 62 of 62 for both tasks.

## 5. Stress v4, every case

| Case | Kind | Check 1 | Main reason |
| :---- | :---- | :---- | :---- |
| FB-S4-001 | regression (ST-05) | referred | Offer with no source granting it |
| FB-S4-002 | regression (A12) | fail | Contradicts cancellation-v2 |
| FB-S4-003 | invented | referred | Offer with no source granting it |
| FB-S4-004 | invented | fail | Price per year vs price-v3 per month |
| FB-S4-005 | implied promise | fail | No approval for this amount, no schedule |
| FB-S4-006 | invented | fail | Claimed action not recorded |
| FB-S4-007 | implied promise | fail | No schedule or issue event |
| FB-S4-008 | invented | fail | No credit action or source for the offer. The correct seat count was also flagged |
| FB-S4-009 | clean billing | referred | The action check verified approval. A second interpretation of the approval as an account fact was referred |
| FB-S4-010 | clean billing | fail | Business-day wording read as a policy mismatch |
| FB-S4-011 | clean billing | fail | "five seats" did not match the invoice value 5 |
| FB-S4-012 | clean billing | fail | "I do not have an approved refund" read as an approval claim |

## 6. Why it failed: diagnosis, not a fix

Every failing line traces to check 1. In all but one case, **extraction found the right claim and the deterministic verifier misread it.** The one exception is an extraction gap (FB-H4-026). All labeled escalation, sensitive data handling and AI disclosure defects were detected. Both model passes agreed on the need for a handoff across all 62 cases.

| Cause | Cases | Where |
| :---- | :---- | :---- |
| Numbers written as words are not read. The seat-count check reads digits only, so "three seats" or "five seats" can never match | FB-H4-044, FB-S4-011 | `desk7.verify_part`, `seat_count` |
| Negated statements are treated as positive claims ("does not limit", "I do not have an approved refund") | FB-H4-004, FB-S4-012 | Policy and account-fact comparison |
| Paraphrased time units ("Monday-through-Friday business days", "usual window, not a guaranteed date") are read as a different policy | FB-H4-047, FB-S4-010 | Refund posting-time comparison |
| A correct path described in different words is not found in the help content | FB-H4-003 | Procedure matching |
| An approved, scheduled refund received an account-fact referral even though the action and schedule checks passed | FB-S4-009 | Refund status lookup |
| An explicit failed tool lookup is ignored. The verifier treats the log as complete and fails the claim, where the rule calls for a referral (FB-H4-032), or refers it for the wrong reason (FB-H4-048) | FB-H4-032, FB-H4-048 | Log-health and tool-result rule |
| A procedure passes because its path exists, without checking that the path does what the reply says ("Billing > Invoices" to change a sign-in email) | FB-H4-038 | Procedure matching |
| A request for a one-time code in chat was not extracted as a claim, so check 1 saw nothing to verify | FB-H4-026 | Extraction (model step) |

These are recorded, not fixed. Fixing them now would be tuning on a holdout that has been seen. Any fix needs a new lock, the two-pass check, and a fresh holdout and stress suite (v5) that nobody has looked at.

## 7. One case from flag to verified fix

`pipeline/trace_case.py` traces case FB-H4-035. The blind run failed check 1 on "The link stays valid for two hours", against password-v2 (30 minutes). The released label confirms the defect. The reply is corrected, and the locked verifier passes the corrected claim.

The recheck claim is entered by hand with the recorded fields, and the script labels it that way.

## 8. Run history

Eight locks were needed to reach a clean pre-blind run (`pipeline/runs/lock_record.json`):

| Lock | Outcome |
| :---- | :---- |
| L1, L2 | Failed the consistency gate |
| L3 | Passed and was verified, then superseded by review findings |
| L4 | Aborted |
| L5 | Failed. The prompt's type definitions overlapped |
| L6 | Passed, then superseded by a probe finding |
| L7 | Failed at 39 of 45 |
| L8 | Passed. Its first extraction audit recorded accesses outside the allowed paths. The replacement extraction audit under the same lock was clean |

The flagged run is kept in `runs/regression_L8_flagged`.

## 9. Next step

Phase 0 stays failed, and Phase 1 (historical shadow) does not start. The smallest credible next attempt has four steps:

1. Fix the verifier causes in section 6, test-first, with new fixtures.
2. Lock once.
3. Pass the two-pass check.
4. Run once on fresh holdout v5 and stress v5.

The missed extraction in FB-H4-026 shows that asking for a code or credential can also imply a claim about the correct procedure. Include that case in the next extraction tests.
