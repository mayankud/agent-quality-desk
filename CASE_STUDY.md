# Case study: Agent Quality Desk

*Mayank Udaywal. Synthetic prototype, November 2026.*

**The problem worth solving.** A support bot speaks for the company. When it states a refund rule, a price or an action it took, the company can be held to that statement. Manual QA reads a small sample of conversations, so a wrong claim can ship, repeat and erode customer trust before anyone sees it. The product question was how to make every bot reply checkable without a person reading every conversation.

**The product bet.**
- **Separate reading from judging.** A model reads each reply and lists what it claims and what the customer needs. Deterministic code verifies each claim against its own source, such as the policy in force, the invoice tool or the action log. Models are strong at language and weak at being audited. Code is the reverse, so each does the job it suits.
- **Refer instead of guessing.** When the records are incomplete, the desk sends the case to QA. A confident wrong verdict costs more trust than an honest referral.

**Decisions and tradeoffs.**
- **Two independent passes per model step.** This doubles model work. In return, instability is measured before any score is trusted.
- **Pass rule frozen and labels withheld before scoring.** This gave up the freedom to tune toward a pass. In return, the result means something.
- **Synthetic data and agents instead of a metered API.** Cost, live latency and production traffic are not validated, and the repo says so up front.

**Success criteria, set before the run.** Sixteen gated metric rules and five evidence rules, with critical checks (claim accuracy, escalation, sensitive data) weighted highest. The bar was fixed before the blind data was opened.

**Result (Run 5, blind): Phase 0 failed.**
- 11 of 16 gated metric rules passed, and all 5 evidence rules passed.
- Escalation, sensitive data handling and AI disclosure each caught every labeled defect. Resolution recall was 6 of 8. The handoff decision agreed across passes on all 62 cases.
- Claim checking, the most important check, missed 2 of 9 defects and flagged 4 of 22 clean cases. None of the four clean billing replies passed. One was referred for review and three were marked as failures.
- Most billing errors traced to the verifier, not the model. The causes were written-out numbers, negations, paraphrased time units and failed lookups. One policy defect also lacked a usable extraction.
- The result replays byte for byte from saved model replies, so anyone can audit it.

**The call I would defend.** The tempting move was to fix the verifier and rerun on the same data until it passed. That would produce a green result nobody should trust. I recorded the failure, kept the diagnosis, and moved the fix to a fresh holdout.

**What I learned.**
- The hard part was not the model. It was the evidence discipline around it: locks, isolation audits, replay, and refusing to retune after seeing labels.
- Eight locks record why each earlier run was replaced.

**Next.**
- Fix the verifier causes test-first, with a new fixture for each.
- Lock once, then run once on a fresh holdout v5.
- Start Phase 1 (historical shadow run) only after Phase 0 passes.
