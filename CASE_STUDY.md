# Case study: Agent Quality Desk

*Mayank Udaywal. Synthetic prototype, November 2026.*

**Problem.** Support bots make confident claims about refunds, prices, policies and actions taken. When a claim is wrong, the company can be held to it, and customers stop trusting the bot. Manual QA samples conversations, so an incorrect claim can go unnoticed.

**Decision.**
- **Split the work.** A model reads what each reply claims and what the customer needs. Deterministic code verifies each claim against its own evidence, such as the policy in force, the invoice tool or the action log. The model is good at reading language, and code is auditable and repeatable.
- **Refer when unsure.** When the records are incomplete, the desk refers the case to QA instead of guessing.

**Tradeoffs.**
- **Two passes per model step.** This doubles the model work, but it measures how stable the model is before any result is trusted.
- **Frozen pass rule and blind holdout.** Setting the thresholds and holding back the answers before scoring made the result interpretable.
- **Synthetic data, agents instead of a metered API.** No cost, latency or live-traffic validation, which is stated up front.

**Results (Run 5, blind).**
- Phase 0 **failed**: 11 of 16 gated metric rules passed, and all 5 evidence rules passed.
- Escalation, sensitive data handling and AI disclosure each detected every labeled defect. Resolution recall was 6 of 8. The handoff decision agreed across passes on all 62 cases.
- Claim checking (check 1) missed 2 of 9 defects and flagged 4 of 22 clean cases. None of the four clean billing replies passed. One was referred for review, and three were marked as failures.
- Most billing errors traced to the verifier, including written numbers, negations, paraphrased time units and failed lookups. One policy defect also lacked a usable extraction.
- The result replays byte for byte from saved model replies.

**What I learned.**
- The hard part was not the model. It was the evidence discipline around it: locks, isolation audits, replay, and refusing to retune after seeing labels.
- The run history records eight locks and the reasons earlier runs were replaced.

**Next step.**
- Fix the verifier causes test-first, with new fixtures.
- Lock once, then run once on a fresh holdout v5.
- Phase 1 (historical shadow) starts only after Phase 0 passes.
