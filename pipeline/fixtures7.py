"""Run 5 fixtures. Synthetic conversations plus hand-written FIXTURE model outputs (not recorded model replies) run through the real
code path (desk7.combine). Covers claim checks, the disagreement rules, the tuning fixes and the QA store hand-off.
The store and timing tests R1-R12 and T1 run unchanged against the lock 6 layer in fixtures_store.py."""
import json, sys, datetime as dt
import desk7, run5
from fixture_builder import mk
from qa_store import Desk

KB = run5.kb(); SAMP = run5.SAMP; RESULTS = []
def check(fid, desc, cond, detail): RESULTS.append({"id": fid, "test": desc, "pass": bool(cond), "detail": detail})
def C(mid, span, pt, **f): return {"message_id": mid, "span": span, "part_type": pt, "fields": f}
def X(claims=(), needs=(), sens=(), cid="F"): return {"case_id": cid, "claims": list(claims), "needs": [{"message_id": m, "need": n} for m, n in needs], "sensitive_requests": [{"message_id": m, "data_type": d} for m, d in sens]}
def J(res="yes", tone="ok", ctx="not_applicable"): return {"case_id": "F", "resolution": {"value": res, "message_id": "m03", "reason": "fixture"}, "tone": {"value": tone, "message_id": None, "reason": "fixture"}, "handoff_context": ctx}
def S(conv, x1, x2=None, j1=None, j2=None):
    x2 = x1 if x2 is None else x2; j1 = j1 or J(); j2 = j1 if j2 is None else j2
    return desk7.combine(conv, KB, {1: x1, 2: x2}, {1: j1, 2: j2}, SAMP)
T0 = "2026-11-20T10:00:00Z"
def inv(cid, total=None, err=False):
    tools = [("m03", "invoice_lookup", {"error": "gateway_timeout", "invoice_record": None} if err else {"month": "2026-10", "total_before_tax_usd": total, "pro_seats": 7, "per_seat_usd": 12})] if (total or err) else []
    return mk(cid, T0, [("c", "what was october's invoice"), ("a", "October came to $84 before tax.")], tools=tools)
INVX = X([C("m03", "October came to $84 before tax.", "account_fact", topic="invoice_total", value="$84")], [("m02", "question")])
REFUND_SENT = [("c", "where is my money"), ("a", "I've issued your $48 refund to your card.")]
RSX = X([C("m03", "I've issued your $48 refund to your card.", "completed_action", action="refund_issued", amount=48)], [("m02", "question")])
def appr(): return ("m03", "refund_approval", {"status": "approved", "amount_usd": 48, "approved_by": "billing_manager"})
def issue(): return ("m03", "refund_issue", {"status": "issued", "amount_usd": 48, "issued_on": "2026-11-20", "destination": "original_card"})
def sched(): return ("m03", "refund_schedule", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "original_card"})
def one(cid, a, claims, c="question?", needs=(("m02", "question"),), **kw): conv = mk(cid, T0, [("c", c), ("a", a)], **kw); return conv, X(claims, needs)

def run_all():
    RESULTS.clear()
    # ---------------- A: claim checks, both passes agree
    r = S(inv("FA1", 84), INVX); check("A1", "Account fact matches the invoice tool", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(inv("FA2", 96), INVX); check("A2", "Account fact contradicted by the invoice tool", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(inv("FA3", err=True), INVX); check("A3", "Account fact, tool lookup failed", r["verdicts"]["c1"] == "referred" and "missing tool result" in r["evidence"]["c1"]["reason"], r["evidence"]["c1"])
    r = S(mk("FA6", T0, REFUND_SENT, events=[appr(), issue()]), RSX); check("A6", "Completed action with a matching issue event", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(mk("FA7", T0, REFUND_SENT, events=[appr()]), RSX); check("A7", "Completed action, log complete, no issue event", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(mk("FA8", T0, REFUND_SENT, events=[appr()], health="delayed"), RSX); check("A8", "Completed action, action log delayed", r["verdicts"]["c1"] == "referred" and "action log incomplete" in r["evidence"]["c1"]["reason"], r["evidence"]["c1"])
    pt = [("c", "when do i get my money"), ("a", "You'll get your $48 back tomorrow.")]
    px = X([C("m03", "You'll get your $48 back tomorrow.", "future_promise", action="money_returned", amount=48, when="tomorrow")], [("m02", "question")])
    r = S(mk("FA9", T0, pt), px); check("A9", "Refund promise without approval or schedule", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(mk("FA10", T0, pt, events=[appr(), sched()]), px); check("A10", "Refund promise, approved and scheduled", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    c, x = one("FA11", "Accounts are limited to one device under our new policy.", [C("m03", "Accounts are limited to one device under our new policy.", "policy_term", topic="device_limit", value="limited to one device", negated=False)])
    r = S(c, x); check("A11", "Invented device limit", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    c = mk("FA13b", T0, [("c", "payment failed"), ("a", "Can you confirm the expiry date on your card?")])
    r = S(c, X([C("m03", "Can you confirm the expiry date on your card?", "other")], [("m02", "other")], [("m03", "card_expiry")])); check("A13b", "Expiry date requested in chat", r["verdicts"]["c3"] == "fail", r["evidence"]["c3"])
    a = "Pro is $12 per seat per month, and students get the first year free."
    c, x = one("FA15", a, [C("m03", "Pro is $12 per seat per month", "price", amount=12, unit="seat", period="month"), C("m03", "students get the first year free", "offer_or_eligibility", description="first year free for students")])
    r = S(c, x); check("A15", "A verified price cannot cover an offer in the same sentence", r["verdicts"]["c1"] in ("fail", "referred") and any(k["part_type"] == "price" and k["verdict"] == "pass" for k in r["claim_verdicts"]), [(k["part_type"], k["verdict"]) for k in r["claim_verdicts"]])
    # ---------------- A (continued): PRD section 6 fixtures not covered above
    c = mk("FA4", "2026-11-12T11:58:00Z", [("c", "refund window on annual?"), ("a", "New annual plans get a full refund within 14 days.")])
    r = S(c, X([C("m03", "New annual plans get a full refund within 14 days.", "policy_term", topic="refund_window", value="14 days", negated=False)], [("m02", "question")]))
    check("A4", "Policy changed at noon, reply at 11:58 judged against refund-v3", r["verdicts"]["c1"] == "pass" and any(k.get("evidence_id") == "refund-v3" for k in r["claim_verdicts"]), r["evidence"]["c1"])
    c = mk("FA5", "2026-11-13T10:00:00Z", [("c", "refund window?"), ("a", "The Help Center page says annual plans can be refunded within 30 days.")],
           tools=[("m03", "kb_lookup", {"document_ids": ["refund-v4", "refund-help-v5"], "finding": "Both documents are active and marked authoritative for annual refund terms."})])
    r = S(c, X([C("m03", "annual plans can be refunded within 30 days", "policy_term", topic="refund_window", value="30 days", negated=False)], [("m02", "question")]))
    check("A5", "Two authoritative sources disagree: KB conflict", r["verdicts"]["c1"] == "kb_conflict" and r["disposition"]["kb_conflict"] == ["c1"], r["disposition"])
    import harness as H, rules6 as R6
    def leaks(conv, r, vals, desk=True):
        d = Desk(); d.ingest(desk7.store_view(r), "billing")
        saved = json.dumps({"result": r, "records": d.records, "queue": d.queue_items(), "audit": d.audit, "request": H.render_case(R6.redact(conv))}, default=str)
        return [v for v in vals if v in saved]
    c = mk("FA13", T0, [("c", "here is my new card 4242 4242 4242 4242, expires 08/29"), ("a", "Thanks, I can see the card ending 4242. What's the expiry date on it?")])
    r = S(c, X([], [("m02", "other")], [("m03", "card_digits"), ("m03", "card_expiry")])); lk = leaks(c, r, ("4242 4242 4242 4242", "4242424242424242", "4242", "08/29"))
    check("A13", "Card digits repeated and expiry asked: fail, nothing leaks into the result, store, audit or agent request", r["verdicts"]["c3"] == "fail" and r["evidence"]["c3"].get("msg_id") == "m03" and not lk, {"c3": r["evidence"]["c3"], "leaked": lk})
    c = mk("FA13c", T0, [("c", "updated my card, it's valid until August 2029"), ("a", "Got it. Your card expires in August 2029.")])
    r = S(c, X([], [("m02", "other")], [("m03", "card_expiry")])); lk = leaks(c, r, ("August 2029", "august 2029"))
    check("A13c", "Month-name card expiry repeated: fail and masked everywhere", r["verdicts"]["c3"] == "fail" and not lk, {"c3": r["evidence"]["c3"], "leaked": lk})
    c = mk("FA13d", T0, [("c", "when does my plan end"), ("a", "Your subscription expires in August 2029.")])
    r = S(c, X([C("m03", "Your subscription expires in August 2029.", "account_fact", topic="other", value="August 2029")], [("m02", "question")]))
    check("A13d", "Control: subscription expiry is not card data and the date is kept", r["verdicts"]["c3"] == "pass" and "August 2029" in json.dumps(r["extractor_record"]), r["evidence"]["c3"])
    c = mk("FA13e", T0, [("c", "I just added a new Visa"), ("a", "Thanks. It expires in August 2029, right?")])
    r = S(c, X([], [("m02", "other")], [("m03", "card_expiry")])); lk = leaks(c, r, ("August 2029",))
    check("A13e", "Card expiry by pronoun after a card was named: fail and masked", r["verdicts"]["c3"] == "fail" and not lk, {"c3": r["evidence"]["c3"], "leaked": lk})
    r = S(inv("FA14", 96), INVX)
    check("A14", "Contradicted account fact through both tiers: routed R-claim, check 1 fail with the tool record as evidence", r["route"] == "R-claim" and r["verdicts"]["c1"] == "fail" and r["evidence"]["c1"].get("evidence_id") == "FA14-tool-1", {"route": r["route"], "c1": r["evidence"]["c1"]})
    a = "Pro is $12 per seat per month with the first year free for students."
    c, x = one("FA16", a, [C("m03", "Pro is $12 per seat per month", "price", amount=12, unit="seat", period="month"), C("m03", "with the first year free for students", "offer_or_eligibility", description="first year free for students")]); r = S(c, x)
    check("A16", "Offer attached to a correct price: not a pass", r["verdicts"]["c1"] in ("fail", "referred"), [(k["part_type"], k["verdict"]) for k in r["claim_verdicts"]])
    a = "Pro is $12 per seat per month."
    c, x = one("FA16c", a, [C("m03", a, "price", amount=12, unit="seat", period="month")]); r = S(c, x)
    check("A16c", "Control: plain price passes cleanly", r["verdicts"]["c1"] == "pass" and not any(r["disposition"].values()), r["disposition"])
    for fid, a, parts, want in (
        ("A17a", "Pro is $12 per seat per year.", [(12, "year")], "fail"),
        ("A17b", "Pro is $12 per seat per month or $144 per seat per year.", [(12, "month"), (144, "year")], "pass"),
        ("A17c", "Pro is $12 per seat monthly or annually at $12 per seat.", [(12, "month"), (12, "year")], "fail"),
        ("A17d", "Pro is $12.99 per seat per month.", [(12.99, "month")], "fail")):
        c, x = one("F" + fid, a, [C("m03", a, "price", amount=amt, unit="seat", period=per) for amt, per in parts]); r = S(c, x)
        check(fid, f"Billing period and full amount: {a}", r["verdicts"]["c1"] == want, [(k["fields"], k["verdict"]) for k in r["claim_verdicts"] if k["part_type"] == "price"])
    qh = ("m03", "handoff", {"queue": "support", "context": "Customer asks for a person about an export bug.", "status": "queued"})
    a = "An agent has joined the chat."
    r = S(mk("FA18", T0, [("c", "can I talk to a person"), ("a", a)], events=[qh]), X([C("m03", a, "handoff_claim", kind="agent_joined")], [("m02", "explicit_request_for_person")]), j1=J(ctx="covers"))
    check("A18", "Agent-joined claim with only a queued handoff: check 1 fail", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    a = "I've queued a transfer to our support team."
    r = S(mk("FA18b", T0, [("c", "can I talk to a person"), ("a", a)], events=[qh]), X([C("m03", a, "handoff_claim", kind="queued", queue="support")], [("m02", "explicit_request_for_person")]), j1=J(ctx="covers"))
    check("A18b", "Control: queued-transfer claim with the same event passes", r["verdicts"]["c1"] == "pass" and r["verdicts"]["c2"] == "pass", {k: r["evidence"][k] for k in ("c1", "c2")})
    c = mk("FA19", T0, [("c", "I tried exporting twice and it failed"), ("a", "Open Export, choose CSV and press Start."), ("c", "That worked, thanks")])
    r = S(c, X([C("m03", "Open Export, choose CSV and press Start.", "procedure", path="Export", purpose="export data")], [("m02", "failed_attempt")]))
    check("A19", "Escalation false alarm: one step tried twice, resolved in chat, no handoff required", r["verdicts"]["c2"] == "pass", r["evidence"]["c2"])
    # ---------------- N: rules added during tuning
    a = "Yes. You can stay signed in on both devices at once."
    c, x = one("FN1", a, [C("m03", "You can stay signed in on both devices at once.", "policy_term", topic="device_limit", value="both devices at once", negated=False)]); r = S(c, x)
    check("N1", "Device policy: no limit stated, no limit asserted, passes", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    a = "Fieldbook allows only one active device per account."
    c, x = one("FN1b", a, [C("m03", a, "policy_term", topic="device_limit", value="one active device per account", negated=False)]); r = S(c, x)
    check("N1b", "Device policy: asserted limit fails", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    a = "On the sign-in page, choose Create account and follow the verification link in your email."
    c, x = one("FN2", a, [C("m03", "On the sign-in page, choose Create account", "procedure", path="sign-in page > Create account", purpose="create a new account")]); r = S(c, x)
    check("N2", "Procedure written as a path ending in a documented UI label passes", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    a = "Open Workspace settings > Billing > Secret refunds."
    c, x = one("FN2b", a, [C("m03", a, "procedure", path="Workspace settings > Billing > Secret refunds", purpose="get a refund")]); r = S(c, x)
    check("N2b", "Undocumented menu path still fails", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    a = "I'll check the charge for you here."
    c, x = one("FN3", a, [C("m03", a, "future_promise", action="other")]); r = S(c, x)
    check("N3", "In-chat step promise needs no approval record", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    a = "I'll get back to you with a credit by Friday."
    c, x = one("FN3b", a, [C("m03", a, "future_promise", action="other", when="by Friday")]); r = S(c, x)
    check("N3b", "Outcome promise marked other still needs approval", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    ho = lambda q: ("m03", "handoff", {"queue": q, "context": "Customer disputes renewal charge and asks for a person.", "status": "queued"})
    hx = X([C("m03", "I've passed this to the team.", "handoff_claim", kind="sent_to_team")], [("m02", "legal_threat"), ("m02", "billing_dispute")])
    r = S(mk("FN4", T0, [("c", "I'm suing over this renewal charge"), ("a", "I've passed this to the team.")], events=[ho("support")]), hx, j1=J(ctx="covers"))
    check("N4", "Legal threat with a billing dispute, handed to support, passes", r["verdicts"]["c2"] == "pass", r["evidence"]["c2"])
    hx2 = X(hx["claims"], [("m02", "billing_dispute")])
    r = S(mk("FN4b", T0, [("c", "this renewal charge is wrong"), ("a", "I've passed this to the team.")], events=[ho("support")]), hx2, j1=J(ctx="covers"))
    check("N4b", "Billing dispute alone, handed to support, fails", r["verdicts"]["c2"] == "fail", r["evidence"]["c2"])
    a = "Yes, your request was received."
    rx = X([C("m03", a, "completed_action", action="other")])
    r = S(mk("FN5", T0, [("c", "did you submit my refund request?"), ("a", a)], events=[("m03", "refund_request", {"status": "received", "amount_usd": 33})]), rx)
    check("N5", "Request-received claim matches the request event", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(mk("FN5b", T0, [("c", "did you submit my refund request?"), ("a", a)]), rx)
    check("N5b", "Request-received claim with no event and a complete log fails", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    c = mk("FN6", T0, [("c", "I checked the postal code and checkout still fails"), ("a", "Try clearing the browser cache.")])
    r = S(c, X([C("m03", "Try clearing the browser cache.", "procedure", path="browser cache", purpose="fix checkout")], [("m02", "failed_attempt")]))
    check("N6", "One failed attempt does not require a handoff", r["verdicts"]["c2"] == "pass", r["evidence"]["c2"])
    r = S(c, X([], [("m02", "failed_attempt"), ("m02", "failed_attempt")]))
    check("N6b", "Two failed attempts require a handoff", r["verdicts"]["c2"] == "fail" and "repeated_failure" in r["evidence"]["c2"]["reason"], r["evidence"]["c2"])
    # ---------------- D: disagreement rules and visibility
    c = mk("FD1", T0, [("c", "how much is pro"), ("a", "Pro is $12 per seat per month. Students get the first year free.")])
    p1 = X([C("m03", "Pro is $12 per seat per month.", "price", amount=12, unit="seat", period="month"), C("m03", "Students get the first year free.", "offer_or_eligibility", description="first year free")])
    p2 = X([C("m03", "Pro is $12 per seat per month.", "price", amount=12, unit="seat", period="month")])
    r = S(c, p1, p2); off = [k for k in r["claim_verdicts"] if k["part_type"] == "offer_or_eligibility"]
    check("D1", "Claim part found by one pass only is still checked and recorded", off and off[0]["found_by"] == "pass 1 only" and r["verdicts"]["c1"] in ("fail", "referred") and r["extractor_record"]["disagreements"], {"offer": off, "c1": r["verdicts"]["c1"]})
    c = mk("FD2", T0, [("c", "my payment failed"), ("a", "Could you share a bit more about the card so I can look?")])
    r = S(c, X([], [("m02", "question")], [("m03", "card_digits")]), X([], [("m02", "question")]))
    check("D2", "Sensitive-data request in one pass, code does not flag it: referred", r["verdicts"]["c3"] == "referred", r["evidence"]["c3"])
    c = mk("FD3", T0, [("c", "my payment failed"), ("a", "Please send me your full card number.")])
    r = S(c, X([], [("m02", "question")], [("m03", "full_card_number")]), X([], [("m02", "question")]))
    check("D3", "Sensitive-data request in one pass, code flags it too: fail", r["verdicts"]["c3"] == "fail", r["evidence"]["c3"])
    c = mk("FD4", T0, [("c", "can I talk to someone?"), ("a", "Here is our help page.")])
    r = S(c, X([], [("m02", "explicit_request_for_person")]), X([], [("m02", "question")]))
    check("D4", "Passes disagree on whether a handoff was required: referred", r["verdicts"]["c2"] == "referred", r["evidence"]["c2"])
    c = mk("FD5", T0, [("c", "how do I export?"), ("a", "Use the export button.")])
    r = S(c, X([], [("m02", "question")]), j1=J("yes", "ok"), j2=J("no", "problem"))
    check("D5", "Passes disagree on resolution and tone: both referred", r["verdicts"]["c4"] == "referred" and r["verdicts"]["c6"] == "referred", {k: r["evidence"][k] for k in ("c4", "c6")})
    r = S(mk("FD6", T0, [("c", "I want a person"), ("a", "I've passed this to the team.")], events=[("m03", "handoff", {"queue": "support", "context": "wants a person", "status": "queued"})]),
          X([], [("m02", "explicit_request_for_person")]), j1=J(ctx="covers"), j2=J(ctx="missing"))
    check("D6", "Passes disagree on handoff context coverage: referred", r["verdicts"]["c2"] == "referred", r["evidence"]["c2"])
    r = S(inv("FD7", 96), INVX, j1=J("yes"), j2=J("no"))
    check("D7", "A confirmed defect stays visible next to a referral", r["disposition"]["fails"] == ["c1"] and "c4" in r["disposition"]["referred"], r["disposition"])
    r = desk7.combine(inv("FD8", 84), KB, {1: INVX, 2: None}, {1: J(), 2: J()}, SAMP)
    check("D8", "One pass invalid: a passing claim and the handoff check are referred", r["verdicts"]["c1"] == "referred" and r["verdicts"]["c2"] == "referred", {k: r["evidence"][k] for k in ("c1", "c2")})
    r = S(mk("FD9", T0, [("c", "hello"), ("a", "Hi, how can I help?")]), X())
    check("D9", "Both passes empty, no money or policy signal: pass", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(mk("FD9b", T0, [("c", "how much will I be charged?"), ("a", "You will be charged $60 on renewal.")]), X())
    check("D9b", "Both passes empty but the reply states an amount: referred", r["verdicts"]["c1"] in ("referred", "fail"), r["evidence"]["c1"])
    # ---------------- V: review findings of 13 Nov 2026 (development checks from the tester's probes, not holdout cases)
    c = mk("FV1", T0, [("c", "What is the yearly price?"), ("a", "Pro is $12 per seat per year.")])
    a = X([C("m03", "Pro is $12 per seat per year.", "price", amount=12, unit="seat", period="month")]); b = X([C("m03", "Pro is $12 per seat per year.", "price", amount=12, unit="seat", period="year")])
    f, rv = S(c, a, b), S(c, b, a)
    check("V1", "Both interpretations of a matched part are verified, and swapping the passes gives the same conservative result", f["verdicts"]["c1"] == "fail" and rv["verdicts"]["c1"] == "fail" and f["evidence"]["c1"] == rv["evidence"]["c1"], {"forward": f["evidence"]["c1"], "reversed": rv["evidence"]["c1"]})
    ev0 = [("m03", "refund_approval", {"status": "approved", "amount_usd": 48})]
    pt2 = [("c", "When will I get the approved refund?"), ("a", "You'll get your $48 back tomorrow.")]
    px2 = X([C("m03", "You'll get your $48 back tomorrow.", "future_promise", action="money_returned", amount=48, when="tomorrow")])
    for fid, sch, want, desc in (
        ("V3", {"status": "cancelled", "amount_usd": 1, "issue_date": "2027-12-31", "destination": "other_account"}, "fail", "cancelled $1 schedule for another date and destination"),
        ("V3b", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "original_card"}, "pass", "control: live $48 schedule for tomorrow"),
        ("V3c", {"status": "scheduled", "amount_usd": 30, "issue_date": "2026-11-21", "destination": "original_card"}, "fail", "live schedule for a different amount"),
        ("V3d", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-12-15", "destination": "original_card"}, "fail", "live schedule later than the promised timing"),
        ("V3e", {"status": "cancelled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "original_card"}, "fail", "matching schedule that was cancelled")):
        r = S(mk("F" + fid, T0, pt2, events=ev0 + [("m03", "refund_schedule", sch)]), px2)
        check(fid, f"Refund promise with a {desc}", r["verdicts"]["c1"] == want, r["evidence"]["c1"])
    px3 = X([C("m03", "You'll get your $48 back to your original card tomorrow.", "future_promise", action="money_returned", amount=48, when="tomorrow", destination="original_card")])
    r = S(mk("FV3f", T0, [("c", "When will I get the approved refund?"), ("a", "You'll get your $48 back to your original card tomorrow.")], events=ev0 + [("m03", "refund_schedule", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "workspace_credit"})]), px3)
    check("V3f", "Refund promise to the card, schedule goes to workspace credit", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(mk("FV3g", T0, [("c", "Can you credit me for the outage?"), ("a", "I'll apply a $20 credit to your account by Friday.")], events=[("m03", "credit", {"status": "cancelled", "amount_usd": 20})]),
          X([C("m03", "I'll apply a $20 credit to your account by Friday.", "future_promise", action="credit_applied", amount=20, when="by Friday")]))
    check("V3g", "Non-refund promise backed only by a cancelled action fails", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    hov = [("m03", "handoff", {"queue": "support", "context": "Customer wants instructions for changing their avatar.", "status": "queued"})]
    hc = mk("FV4", T0, [("c", "Please connect me with a person about my missing invoice."), ("a", "I've queued a transfer to support.")], events=hov)
    hx4 = X([C("m03", "I've queued a transfer to support.", "handoff_claim", kind="queued", queue="support")], [("m02", "explicit_request_for_person")])
    r = S(hc, hx4); ex_txt = desk7.judge_extras(r, hc)
    check("V4", "Required handoff with not_applicable coverage from both passes stays unresolved, and the judge request carries the handoff context", r["verdicts"]["c2"] == "referred" and "avatar" in ex_txt and "queue support" in ex_txt, {"c2": r["evidence"]["c2"], "extras": ex_txt})
    r = S(hc, hx4, j1=J(ctx="missing"))
    check("V4b", "Both passes say the context misses the need: fail", r["verdicts"]["c2"] == "fail", r["evidence"]["c2"])
    r = desk7.combine(hc, KB, {1: hx4, 2: hx4}, None, SAMP)
    check("V4c", "No judge output at all: a required handoff is not passed", r["verdicts"]["c2"] == "referred", r["evidence"]["c2"])
    # ---------------- W: review findings of 14 Nov 2026 (the tester's development probes, not holdout cases)
    MON = "2026-11-23T10:00:00Z"; card = "You'll get your $48 back to your original card tomorrow."
    apw = ("m03", "refund_approval", {"status": "approved", "amount_usd": 48})
    def wsched(**kw): return ("m03", "refund_schedule", {"status": "scheduled", "amount_usd": 48, **kw})
    for fid, span, start, schedule, fields, want, desc in (
        ("W1", card, T0, wsched(destination="original_card"), dict(action="money_returned", amount=48, when="tomorrow", destination="original_card"), "referred", "schedule has no date, timing stays unresolved"),
        ("W2", card, T0, wsched(issue_date="2026-11-21", destination="workspace_credit"), dict(action="money_returned", amount=48, when="tomorrow"), "fail", "destination left out of the fields, span names the card, schedule sends workspace credit"),
        ("W3", "We'll issue your $48 refund to your original card within one business day.", MON, wsched(issue_date="2026-11-26", destination="original_card"), dict(action="money_returned", amount=48, when="within one business day", destination="original_card"), "fail", "Monday promise of one business day, Thursday schedule"),
        ("W3b", "We'll issue your $48 refund to your original card within one business day.", MON, wsched(issue_date="2026-11-24", destination="original_card"), dict(action="money_returned", amount=48, when="within one business day", destination="original_card"), "pass", "control: Monday promise of one business day, Tuesday schedule"),
        ("W3c", "We'll issue your $48 refund to your original card within one business day.", "2026-11-27T10:00:00Z", wsched(issue_date="2026-11-30", destination="original_card"), dict(action="money_returned", amount=48, when="within one business day", destination="original_card"), "pass", "control: Friday promise of one business day, Monday schedule"),
        ("W4", card, T0, wsched(issue_date="2026-11-21", destination="original_card"), dict(action="money_returned", amount=48, when="tomorrow", destination="original_card"), "pass", "control: matching dated original-card schedule"),
        ("W5", "Your $48 refund will reach your original card soon.", T0, wsched(issue_date="2026-11-21", destination="original_card"), dict(action="money_returned", amount=48, when="soon", destination="original_card"), "referred", "timing stated but not datable"),
        ("W6", card, T0, wsched(issue_date="2026-11-21"), dict(action="money_returned", amount=48, when="tomorrow", destination="original_card"), "referred", "schedule has no destination")):
        r = S(mk("F" + fid, start, [("c", "When will I get the approved refund?"), ("a", span)], events=[apw, schedule]), X([C("m03", span, "future_promise", **fields)]))
        check(fid, f"Refund promise: {desc}", r["verdicts"]["c1"] == want, r["evidence"]["c1"])
    check("W7", "Business-day calendar: Monday + 1 is Tuesday, Friday + 1 is Monday, Wednesday + 3 is Monday",
          desk7.add_business_days(dt.date(2026, 11, 23), 1) == dt.date(2026, 11, 24) and desk7.add_business_days(dt.date(2026, 11, 27), 1) == dt.date(2026, 11, 30) and desk7.add_business_days(dt.date(2026, 11, 25), 3) == dt.date(2026, 11, 30), "")
    # ---------------- S: hand-off to the QA store
    for fid, conv, x, j2, queued in (("S1", inv("FS1", 96), INVX, None, True), ("S2", inv("FS2", err=True), INVX, None, True), ("S3", inv("FS3", 84), INVX, None, False)):
        r = S(conv, x, j2=j2); d = Desk(); rec = d.ingest(desk7.store_view(r), "billing")
        check(fid, f"QA store queues the case: {queued}", rec["in_queue"] == queued and rec["result"]["disposition_detail"] == r["disposition"], {"in_queue": rec["in_queue"], "disposition": r["disposition"]})
    return RESULTS

if __name__ == "__main__":
    res = run_all(); json.dump(res, open(sys.argv[1] if len(sys.argv) > 1 else "fixtures7_results.json", "w"), indent=1, default=str)
    for x in res: print("PASS" if x["pass"] else "FAIL", x["id"], x["test"]) if not x["pass"] or "-v" in sys.argv else None
    print(f"{sum(x['pass'] for x in res)}/{len(res)} pass")
