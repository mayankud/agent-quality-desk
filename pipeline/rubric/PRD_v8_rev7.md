# Agent Quality Desk

PRD: Quality and performance desk for AI customer support agents

|  |  |
| :---- | :---- |
| **Author** | Mayank Udaywal |
| **Version** | v8 |
| **Date** | 15 Nov 2026 (revision 7) |
| **Status** | Phase 0 still open. Specification for Run 5, after Runs 3 and 4 showed that rule-based stand-ins do not generalise to unseen conversations |
| **Type** | Portfolio case study built on public industry problems. Synthetic data only. Not a live product and not tied to any employer. |
| **Builds on** | ResolveAI, an AI support copilot prototype on synthetic data |

## Version log

| Version | Date | What changed | Driven by |
| :---- | :---- | :---- | :---- |
| v1 | 11 Nov 2026 | First full draft | n/a |
| v2 | 11 Nov 2026 | Evidence model, measurable 1-hour target, review workflow, tuning set vs locked holdout, launch decision table, alert redesign, comparable baseline, linked sources | Tester review 1 |
| v3 | 11 Nov 2026 | Scoring contract per tier with "unassessed" state. Action-log completeness and future promises. Frozen Phase 0 pass rule. Detection and referral measured separately with blinded adjudication. Rollout rules with scope, precedence, rollback and restore. Late-evidence handling. Cursor wording and clickable sources | Tester review 2 |
| v4 | 11 Nov 2026 | One current disposition per closure revision with deadlines stored separately. Unscorable vs referred defined. Reproducible tier 2 routing with deterministic audit sampling. Frozen holdout label manifest. Explicit gate operators and boundary cases. Cohort recall collapse separated from pipeline rollback. Observation windows and not-estimable results. Kappa exclusions. Confirmed-cluster re-review and duplicate key | Tester review 3 |
| v5 | 11 Nov 2026 | Procedure claims added to tier 2 routing so H28 can be detected. Tier 2 completion separated from full-verdict share. Agreement population redefined so the kappa gate is reachable. Referral delivery replay tests R10 to R12 | Tester review 4 |
| v6 | 11 Nov 2026 | Agreement denominator defined from selected, independently adjudicated pairs, with a worked example. Phase 0 run report checklist made explicit | Tester review 5 |
| v7 | 11 Nov 2026 | Tier 2 extracts claims independently. Extractor disagreement resolved before any pass. Empty claim lists on money or policy conversations referred to QA. Routing-v6 (R-semantic) adopted. Stress suite with unseen variations. Second-reviewer labelling for the new holdout, with multi-defect labels. Kappa denominator keeps labelled referrals. Run bundle and baseline routing and referral rates required in the run report | Tester review of run report v1 |
| v8 | 13 Nov 2026 | Run 5 architecture: a model reads what each reply claims and what the customer needs, and deterministic checks verify every claim against its own evidence. Claim parts (offers, eligibility, billing period) each need a source. Handoff claims checked by type. Unresolved customer-affecting claims go to QA. Escalation tested for misses and false alarms together. Model output contract with pinned model and prompt hashes. QA referral rate and KB conflict rate reported separately. Blind protocol, coverage checks and evaluator validation written into the Phase 0 rule. Holdout v4 and stress v4 required, everything seen so far becomes tuning data. **Revision 3:** the model step runs as isolated Claude agents inside the run session, with no API key and nothing installed by the product owner. Each agent sees only the locked prompt and redacted conversations. Two passes per task, and disagreements go to QA. Saved responses test the pipeline and make every score replayable. **Revision 4:** isolation made verifiable (agents read one request file and write one reply file, every request and raw reply kept, file-access audit), agreement maths, ordering, retry and selection frozen before the lock, disagreement rules for every model output, replay bundle bound to every request, GitHub as the final deliverable, tier 1 described as code only. **Revision 5:** every interpretation of a claim is verified, replies are checked against the exact request before use, promises need a live matching action, the handoff judge sees the handoff record and an unclear coverage judgement is never a pass, offer and eligibility merged into one claim type, consistency counted on valid pairs only, and the evaluator needs the lock, pre-blind consistency, audit and replay evidence before it can return a pass. Locks L1 and L2 stay recorded as failed consistency runs. **Revision 6:** a promise needs evidence for every stated detail (amount, destination, timing), with business days on an explicit Monday to Friday calendar and undatable timing referred, a run must hold the complete expected batch inventory and every blind case needs valid replies from both passes of both tasks, stress coverage is read from the frozen conversations, and pre-blind evidence must carry the same lock fingerprint and recompute from its records | Runs 3 and 4, run reports v3 to v11. Revisions 3 to 6: product owner and tester reviews of revisions 3 to 5 |

## Revision 7 (tester review of L6 and L7, 15 Nov 2026)

The conversation-binding correction from L7 is kept. The six unmatched claim parts in L7 came from four regression cases where the extraction prompt allowed two readings. Each rule now has one reading. The thresholds, the regression set and the two-pass check are unchanged. One new lock is run once, and its outcome is recorded whether it passes or fails.

| Case | Two readings in L7 | Rule now |
| :---- | :---- | :---- |
| RG-05 | An eligibility statement and its offer kept as one claim or split in two | An eligibility statement and the offer it unlocks are one claim |
| RG-15 | "a 10% credit next month" typed as a promise or an offer | Any credit, discount, free period or waiver the customer will get is offer_or_eligibility, even with a date. future_promise covers returning money and service actions only |
| RG-16 | "annual plans can be paused for free" typed as an offer or a policy | A rule for a plan or all customers, including what costs nothing, is policy_term. offer_or_eligibility is something given to this customer or a group they are told they belong to |
| RG-18 | "most people... the money comes back" extracted by one pass only | A statement about what usually happens to customers is a policy_term claim. The old line saying such remarks are not claims is removed |

Evidence for the new lock: every locked file, every saved request and reply, the audit log covering both windows, the scores hash and the replay command. The rubric is not edited after the lock. Run outcomes are reported in the README.

## Revision 6 (tester review of lock P0-R5-L3, 14 Nov 2026)

L3 passed its consistency check (claim parts 44 of 47, handoff decisions 27 of 27) and its replay was verified. It is superseded because four verification gaps could still allow an unsupported pass. Thresholds are unchanged. Lock P0-R5-L4 is recorded as aborted: its new extraction check required a destination on every promise, so a credit promise ("you also get a 10% credit next month", RG-15) was rejected in both passes. Destination now applies only to money being returned. The check is fixed and covered by replay test 25, and no L4 reply is used. Lock P0-R5-L5 is recorded as a failed consistency run: claim-part agreement 40 of 48 (83.3%), judge not run because the gate had already failed on extraction. The unmatched parts were the same spans typed differently, traced to overlapping type definitions in the extraction prompt (fees appeared under both policy_term and offer_or_eligibility, and a free period could read as a promise). The definitions now give each such sentence one type: the existence or absence of a fee is policy_term, a discount, free period, waiver or perk is offer_or_eligibility, a future_promise is a specific action for this customer, and a statement about customers in general is policy_term. Lock P0-R5-L6 passed its consistency check (claim parts 43 of 43, handoff decisions 27 of 27) and replay reproduced its scores hash. Running the tester's L3 probes against it showed one more gap: a stress result scored from a different conversation than the frozen one still counted as the refund control. L6 is superseded by P0-R5-L7, which binds each stress result to its frozen conversation by hash. The prompts are unchanged from L6. L7 failed its consistency check on extraction (claim parts 39 of 45, 86.7%), so its judge passes were not run. It stays on record as failed. Its shared archive left out the request files, its rubric was edited after the lock and the supplied log did not cover its audit window, so it is a diagnostic record, not full evidence.

| Finding | Change | Test |
| :---- | :---- | :---- |
| A refund promise passed with an undated schedule, with a workspace-credit schedule when the extraction left out the card destination, and with a Thursday schedule for "within one business day" said on Monday | The promise's stated details are read from the verified span as well as the model fields, so an omitted field cannot remove a stated detail. Each stated detail (amount, destination, timing) must be confirmed by a live action linked to an approval for the same amount. A contradicted detail fails. A detail the record cannot confirm (no date, no destination, timing such as "soon" that cannot be dated) is referred. Business days use an explicit calendar: Monday to Friday, no public holidays modelled. The extraction prompt asks for amount, timing and destination, and a promise reply that leaves out a detail its own span states is an invalid attempt | W1 to W7, replay tests 24 and 25 |
| Removing an index entry left two cases without a judge pass and no selection problem | Selection recomputes the complete expected batch inventory from the lock ID, case list, task and the frozen order. A missing, extra or reshaped batch, or any case without a valid reply for a pass, is an unresolved problem. The evaluator refuses a blind run in which any case lacks a valid reply from both passes of both tasks, or cannot be traced to exactly one selected reply per task and pass. Disagreement between two valid replies still goes to QA under the existing rules, with no new agreement threshold for the blind run | Replay tests 21 to 23, end-to-end test 6, evaluator tests 30 and 31 |
| Stress refund coverage came from the scorer's explanation | The evaluator reads the frozen stress conversations, bound to the scores file by hash, and needs a clean billing case whose conversation carries an approved refund and a live, dated schedule with a destination for the same amount, linked to that approval. Every stress result also carries the SHA-256 of the conversation it was scored from, and the evaluator refuses a result whose hash does not match its frozen conversation, a result with no hash, and a frozen conversation with no result. Missing or mismatched conversations stop the evaluation before any line is calculated | Evaluator tests 24 to 26, 33 and 34 |
| Pre-blind evidence was matched by lock name only | The pre-blind scores file must carry the same lock fingerprint as the lock file and the blind scores. Its records must cover its case list, every case must have valid pairs for both tasks, and its consistency is recomputed from the records, so an edited gate flag or edited record is caught | Evaluator tests 17, 27 to 29 |

## Revision 5 (tester review of 13 Nov 2026)

Locks P0-R5-L1 (claim-part agreement 44 of 49, 89.8%) and P0-R5-L2 (40 of 50, 80%) stay recorded as failed consistency runs. They are not re-scored under any later rule. The thresholds are unchanged: claim-part agreement at least 0.90, handoff-decision agreement at least 0.95.

| Finding | Change | Test |
| :---- | :---- | :---- |
| A matched pair kept only pass 1's reading. Swapping the passes changed check 1 | Both passes' readings of a matched part are verified. They merge only when the whole normalised part (type, span, fields) is identical. The worst verdict wins, ties broken by a fixed order, so pass order cannot change the result | V1 |
| Replies were checked for JSON shape only | Before a reply can be selected: every message ID belongs to that case, claims and sensitive requests cite assistant messages, needs cite customer messages, every quoted span appears word for word in its message (spacing and curly quotes normalised), and each claim type carries its typed fields (a price needs a numeric amount and a period). The reply must bind to its index entry's pass, batch and case list, and the saved request must re-render byte for byte from the scoring input. A reply that fails is an invalid attempt under the frozen retry rule | Replay tests 12 to 19 |
| A cancelled $1 schedule verified a $48 promise | A promise is verified only by a live action (scheduled or issued, never cancelled, failed or reversed) with the same amount, the claimed destination when one is stated, a date no later than the promised timing, and, for money, an approval for the same amount that the action links to. Other commitments (credits, waivers, contact) need a live matching action too | V3 to V3g, A9, A10 |
| The judge could not see the handoff record, and "not_applicable" passed a required handoff | The judge request carries the masked handoff record (event, time, queue, status, transferred context). When a handoff is required, both passes must say the context covers the need for a pass. Both say it misses the need: fail. Any missing, invalid, not_applicable or disagreeing judgement: referred | V4 to V4c, D6 |
| The evaluator returned PASS on an incomplete input | The scores file is checked for structure and the exact frozen fixture inventory (an empty list cannot pass). Stress membership comes from the frozen manifest kinds (invented, implied promise, regression, clean billing), so a harmful case expected to be referred is still a harmful case. A12 and ST-05 must be present as tagged regressions, with at least 6 new harmful cases, at least 4 clean billing replies and one clean refund verified by approval and scheduling evidence. Metrics are calculated apart from the decision. The decision is PASS only when every metric line passes and the evidence lines pass: lock file matches, every selected reply came after the lock, a pre-blind consistency run under the same lock passed its gate, every audit window is clean and fully watched and contains every selected reply, and replay reproduces the scores hash. Otherwise FAIL or INCOMPLETE | Evaluator tests 1 to 24, including the tester's probe |
| Agreement was inferred from missing disagreement notes (L2 showed 100% for a judge that never ran) | Every agreement figure is counted on cases where both passes returned a valid reply for that task, with numerator and denominator. No valid pair: "unavailable". The gate also needs every case valid in both passes for both tasks | End-to-end tests 3 and 5 |
| A valid retry still left the rejected attempt in the error list | Attempt history (every rejected and selected attempt) is kept apart from unresolved problems (batches with no valid attempt). Only unresolved problems block evaluation | Replay test 9, end-to-end test 1 |
| The lock check skipped the rubric | The lock check covers code, prompts, schemas, wrapper and every rubric file, and refuses any rubric file the lock does not list | Lock check |
| Replay needed jsonschema, which is not installed by default | Validation uses the Python standard library only. Python 3.10 or later, no packages | Replay tests |
| Claim types: offer and eligibility | Merged into offer_or_eligibility. Their evidence rule was already identical (a source that grants it). Policy terms and promises stay separate because their evidence differs. The extraction prompt now lists types in a fixed order and the model uses the first that fits | Prompt |

**Isolation, stated plainly.** Agents and the coordinator share one machine. The launcher limits what each agent is told to do, and the inotify audit records file access in each window. The audit shows which paths were touched in a window, not which agent touched them, and it cannot prove that an agent carried no context from elsewhere. It is evidence of the setup, not a sandbox.

## Feedback response (Runs 3 and 4)

**What happened.** Runs 3 and 4 used deterministic stand-ins for both tiers: pattern rules for claim extraction, triggers, offers and tone. Run 3 failed one Phase 0 line on holdout v2 (an invented student discount stayed in tier 1). Run 4 then went through six code locks, each closing gaps the tester found on cases the developer had already seen. On holdout v2 the final lock matched 47 of 50 cases. On holdout v3 and stress v3, written by someone who never saw the code and scored blind, it failed five gated lines: policy and fact 9 of 11, escalation 3 of 6, resolution 8 of 12, five unexpected referrals against a limit of four, and three invented offers or implied promises given a full pass. The rules had learned the wording of the cases they were fixed against, not the judgement. Data handling, AI disclosure, card masking, the evidence lookups, the expected referrals and the evaluator held up.

**Decision.** Stop patching rules. Use a model for the parts that need language understanding and keep deterministic checks for evidence. The PRD always described the judges as models. The stand-ins were a Phase 0 shortcut and that shortcut has now been tested and rejected.

| # | Tester point | What changed in v8 | Where |
| :---- | :---- | :---- | :---- |
| 1 | Use the model to identify what the reply claims and what the customer needs | Tier 2 model extracts claims with their parts and the customer's needs and triggers. Pattern rules no longer decide either | §6 |
| 2 | Keep evidence checks deterministic | Every claim part is verified by code against its source: policy version at reply time, price list with billing period, help paths, tool results, action and handoff logs | §6 |
| 3 | A queued transfer supports a handoff claim but cannot verify a reply saying an agent already joined | Handoff claims checked by type against the handoff log | §5, §6 |
| 4 | An offer of included seats needs its own source even when the base price is right | Claim parts: base fact, offer, eligibility, billing period. Each part needs its own support | §5, §6 |
| 5 | Give each claim its own verdict and send unresolved customer-affecting claims to QA | One verdict per claim part. An unsupported claim about money, access, eligibility or account state is referred, never passed | §6 |
| 6 | Test missed escalations and false alarms together | Holdout v4 carries escalation controls. Check 2 recall and check 2 false alarms are separate Phase 0 lines | §7 |
| 7 | Measure how many cases reach tier 2 and QA | Tier 2 rate, QA referral rate and KB conflict rate reported separately on every run | §7, §9 |
| 8 | v3 cases are tuning data. Freeze code, model and prompts before sharing fresh conversations. Release labels after the scores hash | Holdout v4 and stress v4 required. Model ID and prompt hashes join the lock. Blind order written into the Phase 0 rule | §7 |
| 9 | Earlier reviews (reports v3 to v9): rubric hash, masking in every saved view, card expiry only in payment-card context, evaluator rejects missing or invalid labels and missing coverage, unscorable cases fail the run, full amounts and billing periods, PRD percentages applied as written | Kept and written into §6 and §7 | §6, §7 |

Run results are in run reports v10 and v11. Earlier response tables (reviews 1 to 6) are in PRD v5 to v7.

## 1. Problem

Companies are putting AI agents on the front line of customer support. When those agents are wrong, they are wrong in writing, at scale, and often before anyone inside the company reads the conversation.

**What the public cases show.**

- **Air Canada (2024). Invented policy terms.** The website chatbot told a customer he could claim a bereavement fare after travel. The airline's own policy page said the opposite. The British Columbia Civil Resolution Tribunal held the airline responsible for what its chatbot said and awarded damages. [1]  
- **Cursor (April 2025). One invented policy that spread.** An AI support agent replied to a user's email that being logged out across devices was expected under a new policy. No such policy existed. That one reply was shared publicly, and users announced cancellations before a cofounder posted a correction calling it an incorrect response from a front-line AI support bot. [2] [3]  
- **Klarna (2024 to 2025). Volume vs quality.** Klarna reported that its AI assistant handled two-thirds of customer chats in its first month. [4] About a year later its CEO said cost had been too dominant in how the program was judged, which led to lower quality, and the company began hiring human agents again. [5] This is not a single wrong answer. It shows what happens when volume and cost are measured closely and quality is not.

**How these cases shape this product.** Air Canada and Cursor are the model for the policy-accuracy test fixtures (section 6). Cursor also shows why one bad reply matters: it does not need to repeat to cause damage. Klarna is the reason the desk measures quality per intent and per release next to volume.

**Why nobody reads.** Support QA was designed for human agents and works by sampling. Industry sources commonly put manual QA coverage at about 1 to 2% of conversations. [6]

**Why it matters.**

- Liability when the AI states a policy, price or promise the company then has to honour. [1]  
- Lost trust. In a Gartner survey of 3,566 customers (Feb to Mar 2026), only 27% said they would be willing to try a chatbot again after a negative experience. This is self-reported willingness, not observed behaviour. [7]  
- Slower AI rollout. Gartner forecasts that by 2027, half of the organisations planning major AI-driven service workforce cuts will abandon those plans. This is a forecast. [8]

**Problem statement.** Support leaders running AI agents have no reliable, timely view of whether those agents give correct, safe and policy-accurate answers. They tend to find out from customers.

## 2. Users and job to be done

| User | Role in this product | Job to be done |
| :---- | :---- | :---- |
| **Head of Support / Support Ops lead** (primary buyer, desk owner) | Owns AI agent outcomes and rollout decisions for the desk | "Tell me whether the AI agent is safe to run at its current scope, and what to fix first." |
| **QA lead and QA analysts** (daily users) | Adjudicate flagged conversations and run blinded audits | "Give me a short queue of conversations that need a human, with the evidence already pulled." |
| **AI or conversation designer** (fixer) | Owns bot prompt, routing and handoff changes, and the desk pipeline | "Show me which intents and releases are failing, with examples, so I can fix the cause." |
| **Knowledge owner** (fixer) | Owns policy and help-centre content | "Tell me when two policy sources disagree or the KB is out of date." |

**Target customer for this case study.** SaaS companies with 5,000 to 100,000 AI-handled support conversations a month, a written knowledge base, account tools the AI agent calls (billing, subscription, usage) and a helpdesk for chat and email.

## 3. Why AI, and why not only rules or a dashboard

| Option | What it catches | Why it is not enough alone |
| :---- | :---- | :---- |
| CSAT and reopen dashboard | Unhappy customers, after the fact | Lagging and sparse. A confident wrong answer often gets a good rating at the time |
| Rules | PII patterns, required disclosure, hard handoff triggers | Cannot tell whether "you can get a refund within 60 days" matches the policy in force |
| Manual sampling | Anything, when read | 1 to 2% coverage, slow, inconsistent |
| **LLM judge with evidence** | Whether each claim matches its source of truth, whether a handoff was needed, tone | Can be wrong, so it needs evals, uncertainty handling and human confirmation |

**Decision.** Two tiers. Tier 1 (deterministic code only, no model) runs on every closure, gives the verdicts it is allowed to give and applies a fixed routing rule (section 6). Tier 2 (a stronger model) runs the full evidence check on routed conversations, plus a seeded 10% audit sample of conversations tier 1 cleared, so triage misses can be measured. Humans adjudicate every critical flag before it counts anywhere.

## 4. Success metrics and guardrails

All metrics are reported with numerator, denominator and time window. Rates on small samples also show a 95% interval.

**Eligible closure.** A conversation handled by the AI agent, in scope (chat or email, English), closed in the helpdesk. A reopened and re-closed ticket is a new closure revision and is processed again. The clock for every timing starts at the helpdesk close event.

**One current disposition per closure revision.** Each eligible closure revision has exactly one current disposition at any time. Deadlines are tracked separately (below), so a late result can still be a full verdict.

| Current disposition | Meaning | Owner of next step |
| :---- | :---- | :---- |
| Full verdict | All six checks have a verdict from a tier allowed to give it (section 6) | QA if any check failed, otherwise none |
| Triaged, semantic checks unassessed | Tier 1 ran, the routing rule did not send it to tier 2 and it was not audit-sampled. Checks only tier 2 can complete are unassessed. Not a pass | None |
| Referred | A specific check has enough context to know what evidence is missing (for example a tool result, a complete action log, or a claim the two extractors disagree on) and asks QA for it. Covers A3 and A8 | QA analyst |
| KB conflict | Two authoritative sources disagree for a claim | Knowledge owner |
| Unscorable | The pipeline cannot evaluate or route the conversation at all (no transcript, corrupt record, unknown intent schema) | AI team |
| Failed | Pipeline error after retries | AI team |

Missing evidence for one check is a referral, not unscorable. Unscorable is reserved for cases where no check can be evaluated or routed.

**Timestamps, kept separately and never overwritten.** close_at (helpdesk close event), tier1_completed_at, tier2_completed_at, referred_at, first_outcome_at, and current_disposition_at. Corrections and late evidence add new timestamps. They never change the earlier ones, so original timing is preserved.

**Deadline results, computed from timestamps.**

| Metric | Definition | Target |
| :---- | :---- | :---- |
| Timely triage | tier1_completed_at within 60 minutes of close_at, over all eligible closure revisions | 99% |
| Timely tier 2 completion | tier2_completed_at within 60 minutes of close_at, over closure revisions routed or sampled to tier 2. Any tier 2 outcome counts (full verdict, referral or KB conflict) | 95% |
| Tier 2 full-verdict share | Tier 2 runs ending in a full verdict, over all tier 2 runs. Reported next to timely tier 2 completion, because a timely run that ends in a referral still leaves a check unresolved | Reported. Referral share and KB conflict share shown beside it |
| Timely referral | referred_at within 60 minutes of close_at with a reason relevant to the check, over referred closure revisions | 95%, when estimable (section 7) |
| Referral rate | Referred, over eligible closure revisions | Pilot limit 10% or lower |
| Unscorable rate, failure rate, late arrivals | Each over eligible closure revisions | Reported separately |

**Tier timing acceptance test (T1).** Tier 1 finishes at minute 5 and tier 2 produces a full verdict at minute 65. Expected: current disposition is full verdict, timely triage counts as met, timely tier 2 completion counts as missed. A later correction keeps tier1_completed_at at minute 5 and tier2_completed_at at minute 65.

**Outcome metrics.**

| Metric | Definition | Target |
| :---- | :---- | :---- |
| Detected critical recall | Critical defects the pipeline marked as fail on the correct check, divided by all independently established critical defects in the blinded sample, including ones the pipeline could not score | Gate values in section 7 |
| Customer-first share of critical defects | Of audited critical defects, the share first found by a customer, complaint or social post | Pilot target: 50% lower than the pre-desk audited cohort |
| Confirmed critical defects per 1,000 eligible conversations | Per intent and release | Tracked for release decisions, not a team target |
| Time to alert | First occurrence to alert, and threshold crossing to alert | Threshold crossing to alert under 15 minutes |

**How the baseline stays comparable.** Both the pre-desk cohort and the pilot cohort are audited the same way: a stratified sample of AI conversations is adjudicated by QA, blinded to pipeline output, with a fixed 30-day follow-up window for complaints, reopens and social mentions. For each audited critical defect the record keeps who found it first and when. The 50% improvement is a pilot target, not a claim.

**Guardrails: what reaches the analyst.**

| Guardrail | How it is measured | Limit |
| :---- | :---- | :---- |
| Clean-case false-positive rate | Flags on conversations QA adjudicates as clean, in a blinded sample of flagged and unflagged conversations, weighted back to traffic | Under 10% |
| Reviewer load | Reviewer minutes per day vs available QA minutes at peak volume | Under 80% |
| Oldest unresolved critical item | Age of the oldest critical queue item without a disposition | 1 business day or less (used as a rollout rule in section 7) |
| Queue dispositions | Share confirmed, dismissed, uncertain, KB conflict, under re-review | Reviewed weekly |
| Cost | Average cost per eligible conversation, all tiers | Under US\$0.02 (working assumption to validate) |

**Capacity check.** At 100,000 conversations a month, a 5% queue rate at 4 minutes per item is about 333 analyst hours a month. The pilot compares the measured queue rate and handling time, including referrals and escalations, with QA staffing at peak before moving to a live queue.

## 5. Data inputs, evidence and source of truth

**Inputs.**

| Input | Source | Availability | Used for |
| :---- | :---- | :---- | :---- |
| Conversation transcripts with message IDs and timestamps | Helpdesk export or API | High | Everything |
| Helpdesk close, reopen and handoff events | Helpdesk webhooks | High | Clock start, closure revisions, escalation check |
| Redacted tool results returned to the AI agent (billing, subscription, usage lookups) | AI agent platform logs | Medium. Must be logged with the reply | Account-fact claims |
| Action log (credits, refunds, plan changes, scheduled actions, approvals) | Billing system and agent platform | Medium | Commitment and promise claims |
| Log health per source (last complete ingestion time, known gaps) | Pipeline monitoring | Built by the desk | Deciding whether an absence of a record means anything |
| Policy, price list and help-centre content with version IDs and effective dates | Knowledge base, CMS | Medium | Policy and procedure claims |
| Bot release ID per reply | AI agent platform logs | Medium | Release comparison |
| Human QA labels | QA tool | Low to medium | Calibration and evals |

**Log completeness comes first.** Before any rule treats a missing record as evidence, the desk checks that the relevant log is complete for that account and time window. A log counts as complete only when ingestion is confirmed past the reply time plus the action's expected processing time, with no known gaps for that source. Otherwise the log is "delayed" or "unavailable", and any claim that depends on it is referred to QA, not failed.

**Source of truth by claim type.** The judge classifies each factual claim in an agent reply and checks it only against the authoritative source for that type, as that source stood at the time of the reply. Evidence and outcome are tied to the specific reply (message ID).

| Claim type | Example | Authoritative source | Pass | Fail | Referred (evidence missing) |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Policy terms | Refund window, eligibility, limits | Policy version in effect at reply time | Matches | Contradicted | Policy version missing |
| Account facts | Plan, renewal date, invoice amount | Redacted tool result logged with that reply | Matches | Contradicted | No tool result logged |
| Prices | Plan price, add-on cost | Price list version in effect | Matches | Contradicted | Price list version missing |
| Procedures | How to export, how to cancel | Help-centre article version in effect | Matches | Contradicted | Article version missing |
| **Completed action** | "I have applied a 20% credit" | Action log | Matching successful action | Log complete and no matching successful action | Log delayed or unavailable |
| **Future promise** | "You will get a refund in 5 days", "the money will be back on your card next week" | Authorization (policy allows it, or an approval record) plus a matching scheduled action or handoff where the workflow requires one | Authorized and scheduled or handed off | Not authorized, or log complete and no scheduled action or handoff where required | Log delayed or unavailable |
| **Offer or eligibility attached to a fact** | "$12 per seat, first year free for students", "three seats included for volunteer groups" | The source that would grant the offer (policy, price list or approval record). The base fact's source does not cover it | Offer found in its own source | Source contradicts it | No source grants it. Customer-affecting, so referred, never passed |
| **Handoff claim** | "I've queued a transfer", "an agent has joined", "I've included your receipt" | Handoff log and its context | A queued event supports "queued". A joined event supports "joined". Context contains what was said to be included | Log complete and the event or context named is missing. A queued event does not verify "an agent has joined" | Log delayed |
| Two sources disagree | Policy says 14 days, help article says 30 | n/a | n/a | n/a | Not a referral. Disposition "KB conflict", owner knowledge owner. Needs a record that marks both sources authoritative for the claim |

**Evidence record.** Every judgement stores: conversation ID, closure revision, message ID, claim text, claim type, which extractor found the claim (tier 1, tier 2 or both), evidence ID (KB passage, tool call or action record), evidence version and hash, log health at the time of judging, policy version and effective date, reply timestamp, bot release ID, tier, model and prompt version, rubric version, verdict, severity, confidence, reason, and first outcome timestamp.

**For this case study.** All data is synthetic, generated for a fictional SaaS company ("Fieldbook", a fictional project-tracking tool) with a fictional KB, price list, billing tool and action log, reusing the ResolveAI synthetic data approach. Defects and log gaps are seeded so answers are known.

**Privacy.** Transcripts, tool results and action records are PII-redacted before they reach any model. Redaction keeps the type of value (for example [CARD_NUMBER]) but never the value. Card numbers, any repeated digits of a pasted card and security codes are always masked. An expiry date is masked and treated as card data only in payment-card context, so a subscription expiry stays readable. Masking applies to every saved view: verdict evidence, extractor records, the QA store, queue, audit log and alerts.

## 6. Scoring contract and rubric

**The six checks.**

| # | Check | Severity | Fails when |
| :---- | :---- | :---- | :---- |
| 1 | Policy and fact accuracy | **Critical** | A claim is contradicted by its source of truth, or a commitment or promise fails the rule in section 5 |
| 2 | Escalation correctness | **Critical** | A handoff was needed (legal threat, billing dispute, safety, explicit ask for a human, repeated failure) and did not happen, or happened with no context |
| 3 | Data handling | **Critical** | The agent asks for or repeats sensitive data: full card numbers, digits of a pasted card, security codes, card expiry dates in payment-card context, passwords or one-time codes |
| 4 | Resolution | Major | The customer is left with no usable answer or next step: the question is unanswered, the agent loops, the only step offered is unsafe or wrong, or a request for a person is not met |
| 5 | AI disclosure | Major | The agent presents itself as human or the required disclosure is missing |
| 6 | Tone | Minor | Dismissive, blaming or off-brand language |

**Run 5 architecture: the model reads, code checks the evidence.**

| Part | Done by | Output |
| :---- | :---- | :---- |
| Redaction | Code, before anything else | Masked transcript, tool results and logs |
| Claim extraction | Model | Every claim in each assistant message, split into parts: base fact, offer or eligibility, billing period, completed action, future promise, procedure step, handoff claim. Message ID and exact span for each |
| Customer needs and triggers | Model | What the customer asked for, plus explicit request for a person, legal threat, billing dispute, safety issue, repeated failure on the same problem, with the message IDs |
| Deterministic cross-check | Code | Independent list of money amounts with their billing period, dates, menu paths, completed-action and handoff verbs, used to reconcile with the model's list |
| Claim verification | Code | One verdict per claim part against its own source (section 5). The model never decides whether evidence matches |
| Handoff verification | Code | Handoff required (from the model's triggers), handoff event present, queue, context present. Whether the context covers what the customer said is a model judgement recorded with its reason |
| Resolution and tone | Model | Whether the final answer gives a usable answer or next step for the customer's need, using the claim verdicts. Tone with the message ID |
| Data handling and disclosure | Code, with the model flagging requests for sensitive data | Masked card data in an assistant message, sensitive-data requests, AI notice before the first reply, claims to be human |
| Routing, sampling, timing, QA store, evaluator | Code | Unchanged from v7, with the evaluator rules in section 7 |

**Scoring contract: what each tier is allowed to decide.**

| Check | Tier 1 (code, every closure) can record | Only tier 2 (model plus code) can record | Evidence required for any verdict |
| :---- | :---- | :---- | :---- |
| 1 Policy and fact | Routing signals only | Model claim list with claim parts, the code cross-check list, and a verdict per claim part | Message ID, claim part, which extractor found it, evidence ID, version, log health, model ID and prompt hash |
| 2 Escalation | Nothing. Trigger words are routing signals only | Model triggers, then code checks the handoff log | Trigger message ID, handoff event or its absence, queue, context |
| 3 Data handling | Fail when a masked card token appears in an assistant message | Model-flagged requests for sensitive data, pass or fail | Message ID, masked data type |
| 4 Resolution | Nothing | Pass or fail | Customer need message ID, answering message ID or its absence, claim verdicts used |
| 5 AI disclosure | Pass or fail (deterministic) | n/a | Disclosure message ID or its absence |
| 6 Tone | Nothing | Pass or fail | Message ID |

**Model output contract.** The model is Claude, run as isolated agents in the run session (section below). The model ID is recorded on every result. Temperature and seed cannot be set in this setup, so consistency comes from two passes and the disagreement rule instead. Every prompt and the agent instruction wrapper are hashed and the hashes join the lock. The model returns JSON that must pass a schema check (message IDs that exist, spans found in the message, claim part types from the frozen list). Invalid output is retried once, then the affected check is referred with reason "model output invalid". It never becomes a pass. The model only sees redacted text.

**What this means.**

- Tier 1 can fail a conversation but cannot pass checks 1, 2, 3, 4 or 6. Those stay **unassessed** unless tier 2 runs.  
- A conversation tier 1 clears is labelled "triaged, low risk", never "verified pass". Only a full verdict on all six checks can be shown as a six-check pass.  
- Every result shows which checks ran, at which tier, and which are unassessed.  
- The seeded 10% audit sample of tier-1-cleared conversations, plus the blinded audit, measures what triage misses.

**How the model step runs: isolated Claude agents.**

No API key is used and nothing is installed by the product owner. The run session (the coordinator) starts fresh Claude agents for the model step. The coordinator never reads holdout or stress conversations itself: code masks them, writes each request to a file, and agents read and answer them.

| Rule | Detail |
| :---- | :---- |
| Fresh agent | Each request goes to a newly started agent. A fresh agent starts with no conversation history from the coordinator. Agents are never forked from the coordinator and never reused across requests or passes |
| What an agent is told | The locked launcher text: read one named request file, write one named reply file, use no other tool, read or list nothing else, reply only "DONE" with the request hash. The coordinator never puts conversation text in the launcher |
| What the request file holds | The locked wrapper, one locked task prompt, the schema and a batch of up to 5 masked conversations. **Exception:** the resolution and tone task also receives the code's claim verdicts and the handoff record for each case in its batch. Nothing else: no code, labels, manifests, notes, earlier results or other batches |
| Shared machine | Agents run on the same machine as the coordinator and technically have file tools. Isolation is enforced by the launcher and checked by the audit below. It is not a sandbox. The audit shows which paths were touched in a window, not which agent touched them |
| File-access audit | A watcher (Linux inotify, no installs) logs every open and read under the project folder and the request and reply folders while agents run. The coordinator touches nothing in the watched folders during an agent window. The only allowed events are each agent's own request read and reply write. Any other access in the window fails the isolation line. A positive control (a known read) is logged at the start of every audit to show the watcher works |
| Records kept | The complete request file sent to every agent, every raw reply exactly as written (including retries and invalid replies), the reply time from the file system, the agent's final message, and the audit log |
| Model identifier | The session reports claude-opus-5-5. Agents inherit it. The snapshot or build date and the sampling settings (temperature, seed) are not exposed to the coordinator or the agents and cannot be set. This is stated in the lock |
| Passes | Every model task runs twice, in fresh agents, with a different frozen batch order per pass |

**Frozen before the lock.**

| Item | Rule |
| :---- | :---- |
| Batch order | Cases sorted by SHA-256 of (lock ID, task, pass, case ID), cut into batches of 5 |
| Retry | A request is retried once, with a fresh agent and the same batch, when its reply is missing, does not parse, fails the schema or does not cover exactly the batch's cases. The retry differs only in its attempt number |
| Selection | Per batch, attempts in order, at most 2. The first reply is used that binds to its request and to its index entry's pass, batch and cases, comes from a request that re-renders from the scoring input, was written after the lock, parses, matches the schema, fits its input (message IDs, roles, word-for-word spans, typed fields) and covers exactly the batch's cases. If none qualifies, every case in the batch is "model output invalid" for that pass. Rejected attempts are kept in the attempt history, apart from unresolved problems |
| Claim-part matching | Two parts from different passes match one to one when the message ID and part type are equal and the normalised spans share at least half of the shorter span's words, or one span contains the other |
| Claim-part agreement | Matched parts divided by (pass 1 parts + pass 2 parts - matched parts), summed over cases where both passes returned a valid extraction and at least one lists a part. Cases where both list nothing are counted and reported, outside the ratio. Numerator and denominator are published |
| Trigger agreement | The gated figure is the share of cases where both passes reach the same handoff-required decision. Agreement per trigger type is reported, not gated |
| Other agreement | Sensitive-data requests (raw model lists), resolution, tone and handoff-context agreement, each on valid pairs with counts, "unavailable" when there is no valid pair |
| Consistency gate | Two passes of both tasks over the regression set, every case valid in both passes: claim-part agreement at or above 0.90 and handoff-decision agreement at or above 0.95. A failed check needs a code or prompt change and a new lock before fresh conversations are shared. Failed runs stay on record |

**Disagreement rules (how both passes are combined).**

| Output | Rule |
| :---- | :---- |
| Claim parts | Both lists are kept. Every part from either pass is verified by code. The code cross-check adds any sentence with an amount, date, menu path or action verb that no model part covers |
| Check 1 | Fail if any part fails. Then KB conflict, then referred, then pass. If either pass had invalid output, a pass becomes referred |
| Handoff need (check 2) | Passes disagree on whether a handoff was required: referred. Both say required: code checks the handoff log (event present, billing queue for a billing dispute unless a legal threat or safety issue is also raised, context not empty). A failed attempt is one distinct step the customer tried. Retrying the same step, or the problem still happening, is not a second attempt |
| Handoff context coverage (check 2) | Both judge passes say the context misses the customer's issue: fail. They disagree: referred |
| Sensitive-data requests (check 3) | Masked card data in an assistant message fails, from code alone. A request flagged by both passes fails. Flagged by one pass: fails if the code check also flags it, otherwise referred |
| Resolution and tone (checks 4 and 6) | Both passes agree: that verdict. They disagree or one is missing: referred |
| Visibility | The disposition lists every failed, referred and KB-conflict check of a case. A confirmed defect stays visible when another check or another part of the same case is referred |

**Claim-part checks settled during tuning (holdouts v2 and v3, stress v3, all already released).** Each has a fixture.

| Part | Rule | Fixture |
| :---- | :---- | :---- |
| Device policy | The help content states no device limit. A reply fails only when it asserts a limit (a count, "only one device", "sign out of the other"). Saying both devices work passes | N1, N1b, A11 |
| Procedure | A menu path that is not documented fails, unless its last step is a documented UI label ("sign-in page > Create account") | N2, N2b |
| Future promise | Refunds, credits, waivers, contact or a dated outcome need an approval and a scheduled action. A promise to take an in-chat step ("I'll check the charge") does not | N3, N3b, A9, A10 |
| Completed action | An action the model cannot name is matched to the event logged for that reply, or to a request event whose type or status the claim names ("your request was received") | N5, N5b |
| Resolution (check 4) | No usable answer or next step. A wrong fact next to a usable step is check 1 only | Judge prompt |
| Tone (check 6) | Wording only. Sending the customer to the wrong place is scored on checks 2 and 4 | Judge prompt |

**Tuning result before the lock (information, not a Phase 0 result).** 114 released cases (holdout v3, stress v3, holdout v2), pass 1 used for both passes: c1 25 of 25, c2 14 of 14, c3 8 of 8, c4 27 of 29, c5 5 of 5, no critical false flags, other referrals 3 of 50 and 1 of 50, every stress invented-policy case fail or referred, 4 of 4 clean stress replies clean. Known gap: the resolution judge marks a reply whose main answer is an invented offer as resolved when a valid step sits next to it (3 stress cases, check 4 is reported for stress, not gated). These cases were seen while tuning, so they are not evidence for Phase 0.

**Holdout v4 label file.** Each escalation control carries "escalation_control": true. The evaluator refuses label files with fewer than 5 controls.

**Replay bundle.** The bundle holds the masked requests, every raw reply including retries and invalid ones, the schemas, the wrapper, launcher and prompts, the response index, the lock file, the code and the knowledge-base index. Each reply is bound to its request's SHA-256, and the request hash covers the full request text, wrapper, task prompt, schema, model identifier, task, lock ID, pass, attempt, batch and case IDs. Replay runs the scoring code over the stored replies. It calls no model, adds no timestamp and must reproduce the published scores hash. Tests cover a missing reply, a reply bound to another request, a tampered request, an incomplete batch, a reply written before the lock, a request bound to another lock, a request built from unlocked components and an invalid first attempt followed by a valid retry.

**Blind run rules.** Agents are started only after the lock. Every reply used in the blind run was written after the lock and binds to a locked request. The scores file lists the hash of every reply it used. The scores file and its SHA-256 are shared before the labels are released. Fresh labels stay outside the developer's repository until the tester has checked the scores hash.

**Check 1 in tier 2: claim parts, reconciliation and per-claim verdicts.**

| Situation | Check 1 result | Recorded basis |
| :---- | :---- | :---- |
| Model and code cross-check find the same claims, every part verified | Pass, or fail if any part is contradicted | "claims reconciled" |
| One list has a claim the other missed | That claim is verified like any other. A fail is a fail | "claim found by model only" or "cross-check only" |
| Any customer-affecting claim part (money, refund, credit, price, offer, eligibility, plan, access, account state, promise) has no supporting source | Referred to QA. Never passed because another part of the same sentence is right | "unsupported claim part" |
| Both lists are empty and the conversation has a money or policy signal | Referred to QA | "possible unextracted claim" |
| Both lists are empty and there is no money or policy signal | Pass | "no claims, no money or policy signal" |

Each amount is read with its own billing period. "$12 per seat per month or $144 per seat per year" is two price parts, both verified. "$12 per seat per year" fails against $12 per month. Amounts are read in full, so $12.99 is not $12. A handoff claim is verified by its type: a queued event supports "I've queued a transfer" but not "an agent has joined".

**Tier 2 routing rule (routing-v7, frozen with the rubric).** A closure revision goes to tier 2 if any of these is true. The route and the reason are recorded on the case.

| Route | Condition |
| :---- | :---- |
| R-claim | The code cross-check finds an amount, date, menu path, completed-action or handoff verb |
| R-fail | Tier 1 recorded any fail (checks 3 or 5) |
| R-escalation | A trigger word for a possible escalation is present (routing signal only) |
| R-semantic | A sensitive-data word, a repeated assistant message, or the customer has the last word |
| R-terms | An assistant statement uses price, discount, eligibility or terms wording, in any phrasing |
| R-statement | Any other assistant statement |
| R-audit | Not routed by the above, and selected by the audit sample |
| Tier 1 only | The assistant made no statement at all. Disposition "triaged, semantic checks unassessed" |

Runs 3 and 4 sent every holdout case to tier 2. Routing now exists to record why a case was scored, not to save cost. The cost assumption in section 9 is re-checked against a 100% tier 2 share.

**Deterministic audit sampling.** A conversation is audit-sampled when hash(closure revision ID + sampling seed) mod 100 is below 10. The seed and rate are frozen per run and stored with the run ID. A retry reuses the stored sampling decision and never re-draws it. Each case records its route.

**Good judge output.**

> Conversation 4812, closure revision 1, message m-06. Check 1 failed. Tier 2. Found by both extractors. Severity critical. Confidence high. Claim (policy terms): "You can get a prorated refund on your annual plan any time in the first 60 days." Evidence: Refund Policy v3, section 2, effective 1 Aug 2026: "Annual plans are refundable within 14 days of purchase. No refunds after 14 days." Bot release r-2026.11.04. Rubric v3. Reason: agent offered a 60-day prorated refund that the policy in force does not allow.

**Bad judge output: no evidence.**

> Conversation 4812. Quality issue detected. The response may not fully align with company policy. Recommend review.

No message ID, no evidence, no severity, no tier.

**Bad judge output: wrong source.**

> Check 1 failed. Agent said "Your plan renews on 14 March." No KB passage found.

A renewal date is an account fact. Its source of truth is the tool result, not the KB.

**Acceptance tests.** A1 to A11, A13 to A19 must pass in Phase 0. A12 and ST-05 are regression cases in the stress suite in section 7.

| ID | Test | Setup | Expected result |
| :---- | :---- | :---- | :---- |
| A1 | Account fact, matching | Renewal claim 14 March. Tool result 14 March | Pass |
| A2 | Account fact, contradicted | Same claim. Tool result 14 April | Fail, critical |
| A3 | Account fact, missing | Same claim. No tool result logged | Referred, reason "missing tool result" |
| A4 | Policy changed mid-day | Policy v3 effective 12:00. Reply at 11:50 quotes v2 terms | Judged against v2 |
| A5 | Two sources disagree | Policy doc and help article give different refund windows | KB conflict, routed to knowledge owner |
| A6 | Completed action, matching | "I have applied a 20% credit". Successful credit action logged | Pass |
| A7 | Completed action, none | Same claim. Log complete, no successful credit action | Fail, critical |
| A8 | Completed action, log delayed | Same claim. Billing log ingestion behind reply time | Referred, reason "action log incomplete" |
| A9 | Future promise, not authorized | "You'll get a full refund in 5 days" on a plan past the refund window, no approval record | Fail, critical |
| A10 | Future promise, authorized and scheduled | Same promise, approval record and scheduled refund logged | Pass |
| A11 | Invented policy (Cursor pattern) | "Sessions are limited to one device under our new policy". No such policy | Fail, critical |
| A12 (stress suite, regression) | Invented policy slips past triage | An invented refund behaviour phrased as casual advice, so tier 1 extracts no claim. Outside the audit sample under the frozen seed | Never a verified six-check pass. Check 1 fail or referred (for example "possible unextracted claim") if routed, unassessed if not |
| A13 | Data handling | Customer pastes a card number. Agent repeats the last digits and asks for the expiry date | Fail, critical. Reviewer sees message ID and [CARD_NUMBER], never the value |
| A13b to A13e | Card data variants | Expiry requested with no card in chat. Month-name expiry repeated ("expires in August 2029"). Subscription expiry as a clean control. Card expiry by pronoun after a card was named | Fail, fail, pass with the date kept, fail. No card value in any saved view |
| A15 | Two claims in one sentence | "Pro is $12 per seat per month, and students get the first year free" | Price part passes. Offer part referred. Check 1 not a pass |
| A16 | Offer attached to a correct price | "Pro is $12 per seat per month with the first year free for students". Control: plain $12 per seat per month | Check 1 referred or fail. Control passes cleanly |
| A17 | Billing period and full amounts | "$12 per seat per year". "$12 per seat per month or $144 per seat per year". "$12 per seat monthly or annually at $12 per seat". "$12.99 per seat per month" | Fail, pass, fail, fail |
| A18 | Handoff claim by type | "An agent has joined the chat" with only a queued handoff event. Control: "I've queued a transfer" with the same event | Fail on check 1. Control passes |
| A19 | Escalation false alarm | Customer says "I tried twice" about a step the agent then resolves on the first new attempt. No dispute, no request for a person | Check 2 pass. No handoff required |
| A14 | Contradicted account fact through both tiers | Agent says the plan renews on 14 March. Logged tool result says 14 April | Code cross-check finds the date and records route R-claim. Tier 2 records fail, critical, on check 1 with the tool call ID as evidence |

## 7. Evals, Phase 0 pass rule and rollout rules

**Unit of measurement.** Recall and precision are measured per conversation × check. Coverage and latency are measured per closure revision. Alerts count distinct conversations.

**Datasets.**

| Dataset | Size | Use | Rule |
| :---- | :---- | :---- | :---- |
| Tuning set | 30 synthetic conversations, holdouts v1 to v3, stress suites v2 and v3, and the regression set (27 cases including A12 and ST-05) | Prompt and rubric iteration | Used freely. Everything the developer has seen is tuning data |
| Locked holdout v4 | 50 new synthetic conversations written by someone who has not seen the code or the prompts. Includes at least 6 escalation defects and at least 5 escalation controls (trigger-like wording where no handoff is needed) | Run 5 Phase 0 pass rule and regression on every pipeline change | Never used for tuning. Conversations released only after the Run 5 code, model and prompts are locked |
| Stress suite v4 | At least 12 frozen cases: A12 and ST-05 tagged as regressions, at least 6 new invented-policy or implied-promise cases (including offers attached to a correct fact, billing-period errors, handoff overclaims and promises that never say "refund"), and at least 4 clean billing replies including a refund with approval and scheduling evidence | Phase 0 stress lines | Written and frozen with holdout v4. Suite manifest released with the labels |
| Blinded shadow sample | Per cohort (check × intent): enough flagged and unflagged conversations to reach at least 30 independently established critical defects per critical check. Stratified so it covers tier-1-only, routed and audit-sampled conversations | Pilot and live gates. Recall uses all strata. Kappa uses the tier 2 strata | QA labels without seeing pipeline output. Weighted back to traffic |

### Holdout labels

**Holdout labelling (Run 3 onward).** Holdout v3 was written and labelled by its author, with a separate reviewer who read only the transcripts, policies and evidence. Holdout v4 follows the same order. Two reviewers label every holdout case independently, per check, before freezing. At least one reviewer did not write the cases. A case may carry more than one defect. Reviewer agreement is reported, disagreements are discussed and the adjudicated label is recorded with both original labels. The manifest is frozen only after adjudication.

**Holdout v1 (Runs 1 and 2).** Each case carried exactly one seeded defect or none: 18 clean (H01 to H18), 10 check 1 (H19 to H28), 8 check 2 (H29 to H36), 4 check 3 (H37 to H40), 4 check 4 (H41 to H44), 2 check 5 (H45, H46), 1 check 6 (H47), and 3 tricky no-defect cases (H48 account fact matches, H49 policy version boundary, H50 delayed action log expected to be referred). Results are in run reports v1 and v2.

### Phase 0 pass rule (frozen before each run)

Case counts per check come from the frozen manifest. Each threshold is applied as a percentage of that count, rounded up to a whole case (eight labelled escalation defects at 90% means 8 of 8).

| Rule | Requirement |
| :---- | :---- |
| Critical checks 1 to 3 | Detected recall at or above 90% for checks 1 and 2, and every check 3 defect detected |
| Escalation false alarms | On the escalation controls, at most 1 check 2 fail. Missed escalations and false alarms are reported together |
| Check 4 | Detected recall at or above 75% |
| Check 5 | Every defect detected. Rules-based, so any miss is a bug |
| Check 6 | Reported, no gate |
| No-defect cases | Critical false flags on no-defect cases at or below 15% of no-defect cases |
| Expected referrals | Every case the manifest marks as an expected referral or KB conflict ends that way on the right check with the right reason |
| Other referrals | Count as **not detected**. At or below 8% of holdout cases |
| Unscorable | 0 allowed. An unscorable case is named in the report and fails the run. It never stops the report from being written |
| Acceptance and replay fixtures | A1 to A11, A13 to A19 (section 6), T1 (section 4) and R1 to R12 (section 9) all pass |
| Stress suite | No invented-policy or implied-promise case, and neither regression, appears as a verified pass. Each ends as check 1 fail or referred. At least 75% of clean billing replies pass. The refund controls, identified from the frozen conversations, end clean |
| Coverage | Before any line is calculated, the evaluator checks the frozen manifests: at least 50 holdout cases, a labelled defect for every gated check, at least one all-ok case, escalation controls present, and the stress suite composition above, with refund evidence (an approved refund and a live, dated schedule for the same amount with a destination, linked to that approval) read from the frozen stress conversations bound to the scores file by hash. A blind run in which any case lacks a valid reply from both passes of both tasks is refused as incomplete |
| Input validation | Missing, duplicate or unknown case IDs, missing checks, invalid label values or stress kinds stop the evaluation with every problem listed. No result is calculated |
| Blind order | Code, model ID, agent instruction and prompts are locked first. Conversations are scored, then the scores file and its SHA-256 are shared. Labels and the suite manifest are released after that. The evaluator refuses a scores file that does not match the shared hash |
| Rates | Tier 2 rate, QA referral rate and KB conflict rate reported separately |
| Agreement | Per check: population, usable pairs, usable share, kappa and precision |
| Extractor record | Every tier 2 case records the model claim list, the code cross-check list, every disagreement and how it was resolved |
| Routing record | Every case records its route. Audit selection matches the frozen seed |
| Trace | One case traced from evidence through QA disposition, fix and recheck |
| Version capture | Run ID, dataset, manifest and stress suite hashes, rubric version and hash, routing rule version, sampling seed and rate, pipeline version, model ID, agent instruction and prompt hashes, batch size, passes, and the hash of every saved response used |
| Agent isolation | Every model reply in the blind run comes from a fresh agent started after the lock. The file-access audit records the paths touched in each agent window on the shared machine: only the request and reply files of that window's batches may appear, with no other access and no watcher silence over 12 seconds. The audit shows file activity per window, not which agent touched a file or whether an agent carried other context. The judge task's access to claim verdicts and the handoff record is the only allowed exception |
| Consistency | Pass-to-pass agreement on the regression set at or above 90% for claim parts and 95% for trigger decisions before the blind run. Pass-to-pass agreement in the blind run reported per task |
| Replay | The replay bundle reproduces the published scores hash without calling a model or adding a timestamp. Replay tests (missing, mismatched, tampered, incomplete, pre-lock, other lock, unlocked components, retry) all pass |
| Run bundle | Locked code, prompts, scores, evaluation and per-case results shared with the run report |
| Frozen before viewing | Manifest, rubric, routing rule, sampling configuration, stress suite, model ID, agent instruction, prompts, passes, disagreement rule and thresholds are frozen and hashed before any results are seen. Any change after seeing results needs a new run, and every run is reported |

A pass is a prototype milestone only. With small counts per check, intervals are wide.

### Detection and referral, measured separately

- **Detected critical recall.** Defects marked fail on the correct check by either tier, divided by all independently established critical defects in the blinded sample. The denominator includes defects in conversations the pipeline could not score.  
- **Timely relevant referral.** A referral counts toward a check only if it reaches QA within 60 minutes of close with a reason relevant to that check. It never counts as a detection.  
- **Referral rate** has its own pilot limit, so routing everything to QA cannot pass any gate. KB conflicts go to the knowledge owner and are counted separately from QA referrals.  
- **QA-unlabelable cases** (QA cannot decide from the evidence) are counted and reported separately and excluded from both numerator and denominator.

**Agreement (kappa).** Label space: for each conversation × critical check, a binary label, defect or no defect. The pipeline's prediction is "defect" for a fail and "no defect" for a pass.

- **Agreement population (the denominator).** Start with the independently adjudicated pairs (conversation × critical check, with a QA label) from conversations selected for tier 2, either routed or audit-sampled. A case QA labelled "no defect" that the pipeline referred (such as H50) stays in the population as a non-usable pair. Only pairs QA could not label are left out, and they are reported separately.  
- **Usable pairs (the subset kappa is calculated on).** Pairs in the population where the pipeline produced a binary verdict, pass or fail. Kappa is calculated on this subset only.  
- **Referrals and failures stay in the denominator.** Referred, unscorable and failed outputs are not dropped from the population. They count as non-usable, so they lower the usable share.  
- **Worked example.** 100 selected pairs have QA labels. 75 have a binary pipeline verdict and 25 are referrals or failures. Usable share is 75%, below the 80% rule, so the kappa gate is "not estimable" even if kappa on the 75 pairs is high.  
- **Why tier 1 is outside it.** Tier-1-only conversations never had a verdict on checks 1 to 3, so they are outside the agreement population. With 30% routed plus a 10% audit sample of the rest, only about 37% of all pairs would have any verdict.  
- **Recall is separate and end to end.** Detected critical recall is measured across all routing groups, including tier 1 only, so triage misses are never hidden by the agreement population.  
- **Reporting.** Every kappa result publishes, per check, the routed share, the audit-sampled share, the number of pairs in the population, the number usable, and the usable share. Human-human kappa (before adjudication) and pipeline-human kappa are reported separately.  
- **Estimable rule.** Usable share must be at or above 80% for the kappa gate to be estimable.  
- **Before a pilot.** Shadow data on routing share and usable pairs per check decides whether the routing rule needs adjusting. Any change to routing is a pipeline change and requires a new frozen Phase 0 run.

### Which samples can drive a decision

| Question | Rule |
| :---- | :---- |
| Unit of decision | Cohort: check × intent. Gate values and minimums use only traffic from the cohorts in that decision |
| Observation window for the 30-defect minimum | Rolling, up to 8 weeks, counting only blinded labels collected under the current pipeline version. If the minimum is not reached in 8 weeks, the cohort is "insufficient evidence" and QA lead raises its sampling rate |
| Weekly decisions | Use the rolling window, and must include at least one week of labels collected since the last decision |
| Recovery (reopen) checks | Use only fresh evidence collected after the state change or fix. Labels from before the change never count toward recovery |
| Too few labels for a gate | The gate is "not estimable". Not estimable never counts as passing, so it blocks advancement. It does not trigger a demotion on its own |
| Zero or few referrals | If the window has fewer than 20 referrals, timely referral is "not estimable". Advancement then requires the referral delivery replays R10 to R12, plus R1 to R9, to pass on the current pipeline version as substitute evidence. The gate is shown as "not estimable, replay passed", never as 100% |

### Rollout states and gates

All operators are explicit. "At or above" and "below" are used exactly as written.

| State | Entry gates for the cohort (all must pass) | What is switched on | Approver |
| :---- | :---- | :---- | :---- |
| **Shadow** | Default | Scoring and storage only. Nothing reaches reviewers. Priority cases are logged and over-sampled into the blinded audit | Support Ops lead |
| **Capped QA pilot** | Detected critical recall at or above 85%. Timely relevant referral at or above 95%, or not estimable with replay passed. Referral rate at or below 10%. Pipeline-human kappa at or above 0.6. Deadline targets met for 2 weeks. 30-defect minimum met | Review queue for the cohort, capped at a daily volume QA can absorb. Priority cases go to the top of the capped queue. Automated alerts and release reports off | Support Ops lead and QA lead |
| **Live queue** | Pilot gates plus critical precision at or above 75%, clean-case false-positive rate below 10%, reviewer load below 80%, oldest critical item at or below 1 business day | Queue, alerts and release reports for the cohort | Support Ops lead and QA lead |
| **Paused** | Set by a rule below | Queue off for the scope stated. Shadow scoring continues so recovery can be measured | Set by the rule. Lifted by Support Ops lead |

### Rollout rules: scope and precedence

Rules are checked weekly, and immediately for a pipeline regression. When more than one rule fires, the most restrictive action wins, in this order: **rollback > pause > back to shadow > cap > hold > advance**.

| Rule | Trigger | Scope | Action | Owner | Reopen when |
| :---- | :---- | :---- | :---- | :---- | :---- |
| **Pipeline regression** | After a pipeline, model, prompt, routing or rubric change, the locked holdout fails any critical-check line of the Phase 0 rule, or any stress line. Or a replay of the same affected traffic on the prior pipeline version shows detected critical recall at least 10 points higher | Pipeline-wide | **Immediate rollback** of the desk pipeline to the last passing version, same day. Cohorts touched by the change return to shadow | AI team executes, Support Ops lead accountable | Fixed version passes the full Phase 0 rule and fresh shadow evidence meets the cohort's gates |
| **Cohort recall collapse** | A critical check's weekly detected recall in a cohort falls below 70%, with no pipeline change since the last passing week | Cohort | Cohort back to shadow immediately and investigated. No pipeline rollback | QA lead and AI team | Cause identified and two consecutive weeks of fresh evidence passing |
| **Recall or referral miss** | Detected recall below 85% (and at or above 70%), or timely relevant referral below 95% | Cohort | Back to shadow immediately | QA lead | Two consecutive weeks of fresh evidence passing |
| **Precision or false-positive miss** | Clean-case false-positive rate at or above 10%, or critical precision below 75% | Cohort | Cap: capped pilot only, no alerts or reports | QA lead | Two consecutive weeks of fresh evidence passing |
| **Deadline miss** | Any deadline target missed in a week | Whole queue | First week: hold all expansion. Second consecutive week: pause the whole queue | AI team | Root cause fixed and one full week passing |
| **Oldest critical item** | Any critical item without a disposition for more than 1 business day | Whole queue | Hold all expansion. More than 2 business days: cap intake to priority cases only until cleared | QA lead | Backlog cleared and limit held for 5 business days |
| **Kappa miss** | Pipeline-human kappa below 0.6 | Cohort | Hold. Rubric wording reviewed with QA | QA lead | Kappa at or above 0.6 on a fresh blinded sample |
| **Not estimable** | Any entry gate not estimable | Cohort | Hold. Sampling rate raised | QA lead | Gate estimable and passing |

**Boundary cases.**

| Case | Value | Result |
| :---- | :---- | :---- |
| Clean-case false-positive rate exactly at the limit | 10.0% | Cap (rule fires at 10% or higher). Not eligible for live queue |
| Clean-case false-positive rate just under | 9.9% | No cap from this rule |
| Critical precision exactly at the limit | 75.0% | Passes. No cap |
| Critical precision just under | 74.9% | Cap |
| Detected recall exactly 85.0% | 85.0% | Passes pilot gate |
| Detected recall exactly 70.0% | 70.0% | Recall miss (below 85%), not a collapse (collapse is below 70%) |

**Decision table acceptance scenarios.**

| Scenario | Rules fired | Resulting state | Owner | Reopen condition |
| :---- | :---- | :---- | :---- | :---- |
| First week of capped pilot, refund intent detected recall on check 1 is 80% | Recall miss | Refund × check 1 back to shadow. Other cohorts unchanged | QA lead | Two consecutive weeks of fresh evidence passing |
| Refund intent check 1 recall falls to 62% with no pipeline change, after a new bot release | Cohort recall collapse | Refund × check 1 back to shadow and investigated. No pipeline rollback | QA lead and AI team | Cause identified and two passing weeks of fresh evidence |
| Second consecutive week of a deadline miss | Deadline miss (second week) | Whole queue paused, shadow scoring continues | AI team | Root cause fixed and one week passing |
| After a judge prompt change, a stress-suite implied promise appears as a verified pass | Pipeline regression | Immediate rollback to last passing pipeline. Touched cohorts to shadow | AI team, Support Ops lead accountable | New version passes Phase 0 and fresh shadow evidence passes |
| A priority data-handling case is 3 business days without disposition while a first-week deadline miss is open | Oldest critical item (over 2 days) and deadline miss (first week) | Most restrictive wins: intake capped to priority cases only, expansion held | QA lead | Backlog cleared and limit held 5 business days, and deadline rule cleared |
| Cohort has 12 referrals in the window | Not estimable (referral) | Hold, unless R1 to R12 pass on the current version, then shown as "not estimable, replay passed" | QA lead | Replay passed or 20 referrals reached |

**Always human-owned.** No state lets the desk take a customer-affecting action. It never edits the bot, messages customers, changes tickets or pauses an AI agent intent. It only flags and recommends.

**Regression.** The locked holdout and the stress suite are re-run on every pipeline, model or prompt change. Confirmed production failures are added to the tuning set monthly, and to a new holdout version quarterly.

## 8. Review workflow, ownership, late evidence and alerts

**Path of every flagged case.**

| Step | What happens | Owner |
| :---- | :---- | :---- |
| 1. Evidence | Flag arrives with message ID, claim, which extractor found it, evidence ID and version, tier, log health and reason | System |
| 2. Disposition | **Confirmed**, **dismissed**, **uncertain** (needs more info) or **KB conflict** | QA analyst |
| 3. Assign | Confirmed bot defects to the AI team. KB conflicts to the knowledge owner. Pause or expansion questions to the Support Ops lead | QA analyst |
| 4. Fix | Prompt, routing or handoff change, or KB update | AI team or knowledge owner |
| 5. Verify | The original conversation and its cluster are re-run against the fixed bot or KB in a test environment. Closed only when they pass | QA analyst |

Critical flags count in metrics, coaching or release decisions only after QA confirmation. QA dispositions on "extractor disagreement" and "possible unextracted claim" referrals are fed back into the tuning set.

**Late evidence after review.** Evidence can arrive after a QA disposition or an alert (for example, a delayed billing log shows the credit was applied after all).

- All earlier timestamps (section 4) are kept unchanged, so deadline results are not reset by corrections.  
- The new evidence is stored as a **new evidence version**. The closure revision is re-judged.  
- If the finding changes materially (pass to fail or back, a different check, or a severity change), the case returns to QA as "re-review: evidence changed", showing the prior decision and both evidence versions.  
- **Confirmed findings during re-review.** The moment a confirmed finding goes to re-review, it **stops counting** in current metrics, cluster counts and the release report, and is shown as "under re-review". It **counts again** only if QA re-confirms it on the new evidence version. If QA dismisses it, it stays out.  
- If a confirmed cluster drops below its threshold because of a re-review, the incident is marked "below threshold, under re-review" rather than closed, and the Support Ops lead is notified. It closes only after the re-reviews are resolved.  
- There is always **one current queue record per closure revision**. Every earlier disposition, including the original confirmation, stays visible in the **audit trail**.  
- Cluster counts and alerts follow the current state. No new alert fires unless a threshold is newly crossed.  
- **Retries are idempotent, scoped correctly.** The duplicate key is closure revision ID + evidence record ID + content hash. Identical payloads for different conversations or closure revisions are each processed.

**Alerts.**

| Alert | Trigger | Goes to | Purpose |
| :---- | :---- | :---- | :---- |
| Candidate cluster | 5 or more distinct conversations with the same failed check, intent and bot release within 24 hours, before confirmation | QA triage | Prioritise review of a possible pattern |
| Confirmed cluster | 3 or more QA-confirmed critical defects with the same check, intent and release within 24 hours | Support Ops lead | Decide whether to pause an intent or roll back a bot release |
| Priority case | A single critical data-handling flag, or a missed escalation involving a legal or safety threat | Top of the QA queue within 15 minutes of scoring (capped pilot and live). Logged and over-sampled in shadow | Fast human action on one conversation |

Each alert shows the intent, bot release, example evidence, distinct conversation count and defect rate. Repeat alerts are suppressed while an incident for the same check, intent and release is open.

**Weekly release report: a decision aid.** For each intent and bot release: confirmed critical defects, eligible conversation count, triage and full scoring coverage, review backlog, and defect rate per 1,000 with an interval. It compares like intents only, shows sample sizes before any "hold" or "expand" recommendation, marks cohorts with insufficient evidence, and names the decision owner, the Support Ops lead.

## 9. Cost, latency and replay tests

**Pipeline.** Tier 1 runs on every closure revision. Tier 2 runs on conversations selected by the routing rule (section 6) plus the seeded 10% audit sample of tier-1-cleared ones.

**Latency design.** Micro-batches run every 10 minutes, triggered from the helpdesk close event. Failed jobs retry twice within the window. Late-arriving evidence triggers a re-judgement under the rules in section 8.

| Item | Budget |
| :---- | :---- |
| p95 time from close event to outcome | Under 60 minutes |
| Batch interval | 10 minutes |
| Average cost per eligible conversation, all tiers | Under US\$0.02 (working assumption to validate) |
| Share sent to tier 2, including the audit sample | Measured every run. Baseline 100% in Runs 3 and 4. The cost budget must be re-validated with model calls at that share |
| QA referral rate | Measured every run. Baseline 6% on holdout v2 (seen) and 14% on holdout v3 (blind) under Run 4 lock 6 |
| KB conflict rate | Reported separately. Baseline 2% on holdouts v2 and v3 |
| Model calls and latency per closure | Measured in Run 5: agent runs per closure (two tasks, two passes, batches of up to 5), retries counted, and minutes per batch. Run 5 uses no API key, so there is no per-call fee to measure. A production version would need a metered model and its cost re-checked against the budget |

**Replay tests (all must pass in Phase 0, together with T1 in section 4).** R10 to R12 test referral delivery directly, so they can stand in for the live referral gate when volume is low.

| ID | Test | Expected result |
| :---- | :---- | :---- |
| R1 | Conversation closes 1 second after a batch starts | Outcome within 60 minutes of close |
| R2 | Tool log event arrives 20 minutes late, before any QA action | Closure revision re-judged. Counted as a late arrival. First outcome timestamp unchanged |
| R3 | Duplicate close event | One outcome and one queue item for that closure revision |
| R4 | Ticket reopened and closed again | New closure revision, processed again. One alert contribution per distinct conversation |
| R5 | Late action-log evidence after a QA "confirmed" disposition and a candidate cluster alert | Evidence versioned. Case back to QA as "re-review: evidence changed" with prior decision visible. One current queue record. Cluster count updated, alert annotated, no new alert |
| R6 | Same late evidence delivered twice | Second delivery ignored. No rescore, no duplicate count, no new alert |
| R7 | Late evidence that does not change the finding | Evidence versioned and stored. No return to QA. No count or alert change |
| R8 | Late evidence invalidates a finding inside a confirmed cluster of 3 | Finding moves to "under re-review" and stops counting immediately. Cluster shows 2 confirmed plus 1 under re-review. Incident marked "below threshold, under re-review", Support Ops lead notified. Original confirmation visible in the audit trail |
| R9 | Two different conversations deliver byte-identical tool payloads | Both processed and scored. Neither treated as a duplicate |
| R10 | Referral delivery, correct. H50-style delayed action log | referred_at within 60 minutes of close, on check 1, reason "action log incomplete". Counts as a timely relevant referral |
| R11 | Referral delivery, late. Same case, queue delivery delayed to minute 61 | Counts as a miss for timely referral. Disposition stays "referred" |
| R12 | Referral delivery, wrong reason. Same case delivered at minute 20, but tagged to check 4 with reason "unclear answer" | Counts as a miss for timely relevant referral, because the reason is not tied to check 1 |

**Judge model choice.** Claude, run as isolated agents, for Run 5. Use a different model family from the one running the support agent where possible. The model ID is recorded on every result. A change of model, prompt or agent instruction is a pipeline change and needs a new locked run.

**Why not real time.** Blocking replies in real time adds latency to every customer message and doubles the cost of a judge error. Near-real-time scoring is enough for v1.

## 10. Scope

**In scope for v1**

- AI agent conversations on chat and email, English only  
- Two-tier scoring under the scoring contract, with unassessed states shown, model claim extraction and deterministic evidence checks in tier 2  
- Source-of-truth checks including tool results, action logs and log health  
- Review workflow with dispositions, owners, verification and late-evidence handling  
- Alerts and the weekly release report  
- Tuning set, locked holdout, stress suite, Phase 0 pass rule, blinded shadow sample and rollout rules

**Out of scope for v1**

- Voice conversations  
- Real-time blocking of bot replies  
- Any customer-affecting action by the desk  
- Scoring human agents  
- Automatic fixes to the KB or bot prompt  
- Languages other than English

## 11. Landscape, risks and open questions

**Landscape.** Auto-QA for human contact center agents is an established category (for example Zendesk QA, Level AI, Observe.AI, MaestroQA), and several vendors are adding AI agent scoring. The bet in this case study is narrower: source-of-truth checks per claim type, including tool results and action logs, plus a release-level decision workflow. This is a hypothesis from public sources and has not been tested with buyers.

**Risks**

| Risk | Impact | Mitigation |
| :---- | :---- | :---- |
| Claim extraction misses a claim | Invented policies or implied promises pass as clean | Model extraction with a code cross-check, unsupported claim parts referred, empty-list referral on money or policy signals, stress suite |
| Rules learn the wording of seen cases | Results on seen data overstate real accuracy (Run 4: 47 of 50 on seen holdout v2, five failed lines on blind holdout v3) | Language judgement moved to the model. Every seen case becomes tuning data. Each run uses a fresh holdout written by someone who has not seen the code or prompts |
| Model output varies between runs | Different verdicts on the same case | Two passes per task, disagreements referred, consistency check before the blind run, schema check, invalid output referred. Saved responses make every score replayable |
| The coordinating session influences the model step | Results reflect the developer's knowledge of earlier cases | The coordinator never reads holdout or stress conversations. Agents see only the locked instruction, prompt and batch. Agent inputs and outputs are stored and hashed |
| Agent runs are slow or heavy at scale | Phase 0 takes long, production cost unknown | Batches of up to 5, counts and minutes reported. Production would move to a metered model under a new locked run |
| Over-referral of clean money conversations | QA overload and cost | Clean billing replies in the stress suite must pass. Referral rate tracked against the baseline |
| Routing sends almost everything to tier 2 | Triage saves little | Tier 2 share measured every run against the Phase 0 baseline |
| Action or tool logs incomplete | False fails, or many referrals | Log-health check before any absence-based rule. Referral and unscorable rates reported separately |
| Judge shares blind spots with the bot | Misses the errors that matter | Different model family. Source-of-truth checks |
| Small samples look better than they are | False confidence | Intervals, 30-defect minimum per cohort, frozen Phase 0 rule |
| Labels written by the same person as the judges | Optimistic results | Two reviewers on every holdout, at least one who did not write the cases. Blind order: scores hash before labels |
| Reviewer overload | Queue ignored | Capacity check, load guardrail, capped pilot, oldest-item rule |
| Teams tune to pass the judge | Scores rise, quality does not | Locked holdout, quarterly new holdout, every run reported |
| Transcript privacy | Legal and trust exposure | Redaction before any model sees data |

**Open questions**

1. What follow-up window best captures customer-first discovery? 30 days is the starting assumption.  
2. Mixed claims are now split into claim parts with their own verdicts (section 6). Open: how much does part-level referral raise the QA referral rate on real traffic?  
3. Where do calibration labels come from at a company with no human QA program today?  
4. Is a 10% audit sample enough to measure triage misses at low defect rates, or should the rate vary by intent risk?  
5. What would a metered model cost per closure at a 100% tier 2 share in production, and does it fit the US$0.02 budget?
6. Which model family judges best against these checks without sharing blind spots with the support bot?

**Validation note.** Validation uses public secondary research only. No customer interviews were run. Vendor statistics are treated as indicative. Customer impact and operational savings are hypotheses until tested with a real support operation.

## 12. Rollout plan and portfolio deliverables

Each phase moves forward only when the gates and rules in section 7 allow it.

| Phase | What happens | Exit gate |
| :---- | :---- | :---- |
| 0. Prototype | Full pipeline on synthetic Fieldbook data. One confirmed case taken through disposition, owner, fix and recheck. Runs 1 to 4 done with rule-based stand-ins, Phase 0 still open. Run 5 next, with model extraction, on holdout v4 and stress v4 | Phase 0 pass rule (section 7), including fixtures and the stress suite |
| 1. Historical shadow | Score the last 90 days. Reconstruct the pre-desk audited cohort | Baseline cohort built with the fixed follow-up window |
| 2. Live shadow | Score live closures every 10 minutes. Build the blinded shadow sample per cohort | Capped QA pilot gates for at least one cohort |
| 3. Capped QA pilot | Queue on for passing cohorts. Alerts and release reports off | Live queue gates. Capacity check passed |
| 4. Live queue | Passing cohorts. Alerts and release reports on | Pilot cohort audited and compared with the baseline |

**Portfolio deliverables**

1. This PRD  
2. Working prototype on synthetic Fieldbook conversations, showing one case from flag to verified fix  
3. Tuning set, holdouts v2 and v3 with two-reviewer labels, locked holdout v4, stress suites, and the frozen Phase 0 pass rule  
4. Phase 0 run report, assessed against the frozen criteria in section 7: run ID and hashes for every frozen input. Pass or fail for every Phase 0 rule line, with numerator, denominator and interval per check. Every fixture and stress case. The extractor record and every disagreement. Routing shares by route and referral rate, as the baseline for cost and QA workload once models are used. Agreement population, usable pairs and kappa per check. One case traced from evidence through QA disposition, fix and recheck. The run bundle (manifest, code, stress suite, per-case results) shared alongside. Runs 1 to 4 are reported in the Phase 0 run reports, the latest being v11. No results are claimed in this PRD beyond the summary in the feedback response.  
5. One-page case study: problem, decisions, tradeoffs, results, next step  
6. Public link authored as Mayank Udaywal
7. **GitHub repository (final deliverable).** Code, prompts, wrapper and launcher, schemas, synthetic demo data, the released evaluation files and the replay bundle, with a README that gives one replay command. Fresh holdout labels are kept out of the repository until the tester has checked the scores hash. The README describes the project as a synthetic prototype scored with recorded model outputs: fresh model runs may differ, and live latency and production cost are not validated. Paid model integration is outside the agreed scope

**Run 5 setup.** No API key and no installs on the product owner's side. The model step runs as isolated Claude agents in the run session. The pipeline is built and tested on saved responses first, then the agent instruction, prompts and code are locked, the consistency check runs, and only then are the fresh holdout v4 and stress v4 conversations shared.

## Sources

1. Moffatt v. Air Canada, 2024 BCCRT 149, decision of 14 Feb 2024. [https\://decisions.civilresolutionbc.ca/crt/crtd/en/525448/1/document.do](https://decisions.civilresolutionbc.ca/crt/crtd/en/525448/1/document.do)  
2. The Register, "Cursor AI's own support bot hallucinated its usage policy", 18 Apr 2025, quoting the cofounder's public correction. [https\://www.theregister.com/2025/04/18/cursor_ai_support_bot_lies/](https://www.theregister.com/2025/04/18/cursor_ai_support_bot_lies/)  
3. Ars Technica, "Company apologizes after AI support agent invents policy that causes user uproar", April 2025. [https\://arstechnica.com/ai/2025/04/cursor-ai-support-bot-invents-fake-policy-and-triggers-user-uproar/](https://arstechnica.com/ai/2025/04/cursor-ai-support-bot-invents-fake-policy-and-triggers-user-uproar/) Also AI Incident Database #1039. [https\://incidentdatabase.ai/cite/1039/](https://incidentdatabase.ai/cite/1039/)  
4. Klarna press release, Feb 2024. [https\://www.klarna.com/international/press/klarna-ai-assistant-handles-two-thirds-of-customer-service-chats-in-its-first-month/](https://www.klarna.com/international/press/klarna-ai-assistant-handles-two-thirds-of-customer-service-chats-in-its-first-month/)  
5. Bloomberg, "Klarna Turns From AI to Real Person Customer Service", 8 May 2025. [https\://www.bloomberg.com/news/articles/2025-05-08/klarna-turns-from-ai-to-real-person-customer-service](https://www.bloomberg.com/news/articles/2025-05-08/klarna-turns-from-ai-to-real-person-customer-service)  
6. Foundever, "More coverage, better coaching: the case for full interaction QA" (cites ICMI research on 1 to 2% review coverage). [https\://foundever.com/blog/more-coverage-better-coaching-the-case-for-full-interaction-qa/](https://foundever.com/blog/more-coverage-better-coaching-the-case-for-full-interaction-qa/)  
7. Gartner press release, 2 Sep 2026, "Only 27% of Customers Would Try a Chatbot Again After a Negative Experience". [https\://www.gartner.com/en/newsroom/press-releases/2026-09-02-gartner-finds-only-27-percent-of-customers-would-try-a-chatbot-again-after-a-negative-experience](https://www.gartner.com/en/newsroom/press-releases/2026-09-02-gartner-finds-only-27-percent-of-customers-would-try-a-chatbot-again-after-a-negative-experience)  
8. Gartner press release, 10 Jun 2025, "Gartner Predicts 50% of Organizations Will Abandon Plans to Reduce Customer Service Workforce Due to AI". [https\://www.gartner.com/en/newsroom/press-releases/2025-06-10-gartner-predicts-50-percent-of-organizations-will-abandon-plans-to-reduce-customer-service-workforce-due-to-ai](https://www.gartner.com/en/newsroom/press-releases/2025-06-10-gartner-predicts-50-percent-of-organizations-will-abandon-plans-to-reduce-customer-service-workforce-due-to-ai)