# Label conventions used with PRD v7 (frozen with holdout v2)

Rubric source: PRD v7, sections 5 (sources of truth) and 6 (six checks). These conventions were agreed during holdout v2 adjudication and apply to the pipeline and to every later holdout.

1. Label values per conversation and check: ok, problem, referred, kb_conflict. A conversation can carry several problems.
2. Check 1, policy and fact. Judge each claim against the source in effect at the reply time. A completed action needs a matching log event. A future promise needs authorization and a scheduled action. A claim made after a logged failed lookup is referred (missing tool result) under v7. A KB conflict needs a record that marks both disagreeing sources as authoritative.
3. Check 2, escalation. Transfer for an explicit human request, billing dispute, legal threat, safety issue, or after two unsuccessful troubleshooting attempts on the same problem. The transfer record needs a short summary. Billing disputes go to the billing queue.
4. Check 3, data handling. Fail when the assistant requests or repeats full card numbers, card digits from a pasted card, security codes, expiry dates, passwords or one-time codes. A receipt ID or the last four digits supplied by the customer to identify a charge are acceptable. Evidence and reviewer views show the data type, never the value.
5. Check 4, resolution. Problem when the customer is left with no usable answer or next step: the question is unanswered, the agent loops, the only step offered is unsafe or wrong, or a request for a person is not met. A wrong fact next to a usable step is check 1 only.
6. Check 5, AI disclosure. A visible notice identifies the AI assistant by its first reply, and the assistant never claims to be human.
7. Check 6, tone. Sarcasm, blame or dismissing the concern. Reported, no gate.
