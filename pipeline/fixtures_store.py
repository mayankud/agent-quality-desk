"""Store and timing layer tests (R1-R12, T1) plus the lock 6 rule-engine fixtures, unchanged from lock 6. Run 5 keeps this layer as is."""
import json, copy, re, datetime as dt
from rules6 import KB2, score, Desk, timely_relevant_referral, ts
from fixture_builder import mk

KBRAW = json.load(open("kb_index.json")); kb = KB2(KBRAW)
SAMP = {"seed": "phase0-seed-2026-11-11", "rate_pct": 10}
RESULTS = []
def check(fid, desc, cond, detail): RESULTS.append({"id": fid, "test": desc, "pass": bool(cond), "detail": detail})
S = lambda c, **kw: score(c, kb, SAMP, **kw)

def inv(cid, total=None, err=False, start="2026-11-20T10:00:00Z"):
    tools = [("m03", "invoice_lookup", {"error": "gateway_timeout", "invoice_record": None} if err else {"month": "2026-10", "total_before_tax_usd": total, "pro_seats": 7, "per_seat_usd": 12})] if (total or err) else []
    return mk(cid, start, [("c", "what was october's invoice"), ("a", "October came to $84 before tax.")], tools=tools)

REFUND_SENT = [("c", "where is my money"), ("a", "I've issued your $48 refund to your card.")]
def appr(): return ("m03", "refund_approval", {"status": "approved", "amount_usd": 48, "approved_by": "billing_manager"})
def issue(): return ("m03", "refund_issue", {"status": "issued", "amount_usd": 48, "issued_on": "2026-11-20", "destination": "original_card"})

def run_all():
    RESULTS.clear()
    r = S(inv("FA1", 84)); check("A1", "Account fact, matching", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(inv("FA2", 96)); check("A2", "Account fact, contradicted", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(inv("FA3", err=True)); check("A3", "Account fact, missing tool result", r["disposition"] == "referred" and "missing tool result" in r["referral"]["reason"], r.get("referral"))
    c = mk("FA4", "2026-11-12T11:58:00Z", [("c", "refund window on annual?"), ("a", "New annual plans get a full refund within 14 days.")])
    r = S(c); ev = r["evidence"]["c1"]; check("A4", "Policy changed at noon, reply at 11:58 judged against refund-v3", r["verdicts"]["c1"] == "pass" and any(x["evidence_id"] == "refund-v3" for x in r["extractor_record"]["claims"]), ev)
    c = mk("FA5", "2026-11-13T10:00:00Z", [("c", "refund window?"), ("a", "The Help Center page says annual plans can be refunded within 30 days.")],
           tools=[("m03", "kb_lookup", {"document_ids": ["refund-v4", "refund-help-v5"], "finding": "Both documents are active and marked authoritative for annual refund terms."})])
    r = S(c); check("A5", "Two authoritative sources disagree", r["disposition"] == "kb_conflict", r["disposition"])
    r = S(mk("FA6", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr(), issue()])); check("A6", "Completed action, matching", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(mk("FA7", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr()])); check("A7", "Completed action, log complete, none", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(mk("FA8", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr()], health="delayed")); check("A8", "Completed action, log delayed", r["disposition"] == "referred" and "action log incomplete" in r["referral"]["reason"], r.get("referral"))
    prom = [("c", "bought annual 60 days ago, refund please"), ("a", "You'll get the money back on your card by Friday.")]
    r = S(mk("FA9", "2026-11-20T10:00:00Z", prom)); check("A9", "Future promise, not authorized", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    r = S(mk("FA10", "2026-11-20T10:00:00Z", prom, events=[appr(), ("m03", "refund_schedule", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "original_card"})]))
    check("A10", "Future promise, authorized and scheduled", r["verdicts"]["c1"] == "pass", r["evidence"]["c1"])
    r = S(mk("FA11", "2026-11-20T10:00:00Z", [("c", "why am i logged out on my second laptop"), ("a", "Accounts are limited to one device under our new policy.")]))
    check("A11", "Invented policy (Cursor pattern)", r["verdicts"]["c1"] == "fail", r["evidence"]["c1"])
    # A13, PRD v7 scenario: customer pastes a card number, agent repeats the last digits and asks for the expiry date
    CARD = "4242 4242 4242 4242"
    c = mk("FA13", "2026-11-20T10:00:00Z", [("c", f"here is my new card {CARD}, expires 08/29"),
                                            ("a", "Thanks, I can see the card ending 4242. What's the expiry date on it?")])
    r = S(c); d13 = Desk(); d13.ingest(r, "billing")
    saved = json.dumps({"result": r, "records": d13.records, "queue": d13.queue_items(), "audit": d13.audit, "alerts": d13.alerts}, default=str)
    leaks = [v for v in ("4242 4242 4242 4242", "4242424242424242", "4242", "08/29") if v in saved]
    check("A13", "Data handling: last digits repeated and expiry asked. Every saved view masked",
          r["verdicts"]["c3"] == "fail" and "[CARD_NUMBER]" in r["evidence"]["c3"]["reason"] and r["evidence"]["c3"]["msg_id"] == "m03" and not leaks,
          {"c3": r["verdicts"]["c3"], "evidence": r["evidence"]["c3"], "leaked_values": leaks, "scanned": "result, extractor record, QA store, queue, audit, alerts"})
    c = mk("FA13b", "2026-11-20T10:00:00Z", [("c", "payment failed"), ("a", "Can you confirm the expiry date on your card?")])
    r = S(c); check("A13b", "Data handling: expiry date requested with no card in chat", r["verdicts"]["c3"] == "fail", r["evidence"]["c3"])
    c = mk("FA13c", "2026-11-20T10:00:00Z", [("c", "updated my card, it's valid until August 2029"), ("a", "Got it. Your card expires in August 2029.")])
    r = S(c); d13c = Desk(); d13c.ingest(r, "billing")
    saved = json.dumps({"result": r, "records": d13c.records, "queue": d13c.queue_items(), "audit": d13c.audit, "alerts": d13c.alerts}, default=str)
    leaks = [v for v in ("August 2029", "august 2029") if v in saved]
    check("A13c", "Data handling: month-name expiry repeated. Fails and every saved view masked", r["verdicts"]["c3"] == "fail" and not leaks, {"c3": r["evidence"]["c3"], "leaked_values": leaks})
    c = mk("FA15", "2026-11-20T10:00:00Z", [("c", "pro pricing for students?"), ("a", "Pro is $12 per seat per month, and students get the first year free.")])
    r = S(c); cls = [(x["verdict"], x["reason"]) for x in r["extractor_record"]["claims"]]
    check("A15", "One true claim cannot cover an unsupported offer in the same sentence", r["verdicts"]["c1"] in ("fail", "referred"), {"c1": r["verdicts"]["c1"], "claims": cls})
    c = mk("FA16", "2026-11-20T10:00:00Z", [("c", "student pricing?"), ("a", "Pro is $12 per seat per month with the first year free for students.")])
    r = S(c); cls = [(x["verdict"], x["reason"]) for x in r["extractor_record"]["claims"]]
    check("A16", "Offer attached to a verified price is not covered by the price source", r["verdicts"]["c1"] in ("fail", "referred"), {"c1": r["verdicts"]["c1"], "claims": cls})
    c = mk("FA16c", "2026-11-20T10:00:00Z", [("c", "how much is pro"), ("a", "Pro is $12 per seat per month before taxes and discounts.")])
    r = S(c); check("A16c", "Control: plain price reply stays a clean pass", r["disposition"] == "full_verdict" and "fail" not in r["verdicts"].values() and r["verdicts"]["c1"] == "pass", {"c1": r["verdicts"]["c1"], "disposition": r["disposition"]})
    c = mk("FA16y", "2026-11-20T10:00:00Z", [("c", "how much is pro"), ("a", "Pro is $12 per seat per year.")])
    r = S(c); check("A16y", "Wrong billing period: $12 per seat per year vs $12 per seat per month", r["verdicts"]["c1"] == "fail", {"c1": r["verdicts"]["c1"], "reason": r["evidence"]["c1"].get("reason")})
    c = mk("FA16z", "2026-11-20T10:00:00Z", [("c", "yearly cost of pro"), ("a", "Pro works out to $144 per seat per year.")])
    r = S(c); check("A16z", "Control: yearly figure equal to 12 months of the monthly price passes", r["verdicts"]["c1"] == "pass", {"c1": r["verdicts"]["c1"], "reason": r["evidence"]["c1"].get("reason")})
    c = mk("FA16m", "2026-11-20T10:00:00Z", [("c", "monthly or yearly?"), ("a", "Pro is $12 per seat per month or $144 per seat per year.")])
    r = S(c); check("A16m", "Monthly and yearly prices in one reply, each read with its own period", r["verdicts"]["c1"] == "pass" and r["disposition"] == "full_verdict", {"c1": r["verdicts"]["c1"], "claims": [x["reason"] for x in r["extractor_record"]["claims"]]})
    c = mk("FA16d", "2026-11-20T10:00:00Z", [("c", "how much is pro"), ("a", "Pro is $12.99 per seat per month.")])
    r = S(c); check("A16d", "Amount with cents read in full: $12.99 is not $12", r["verdicts"]["c1"] == "fail", {"c1": r["verdicts"]["c1"], "reason": r["evidence"]["c1"].get("reason")})
    c = mk("FA16a", "2026-11-20T10:00:00Z", [("c", "monthly or yearly?"), ("a", "Pro is $12 per seat monthly or annually at $12 per seat.")])
    r = S(c); check("A16a", "Period word before its amount: annually belongs to the second $12, which is wrong", r["verdicts"]["c1"] == "fail", {"c1": r["verdicts"]["c1"], "claims": [x["reason"] for x in r["extractor_record"]["claims"]]})
    c = mk("FA16b", "2026-11-20T10:00:00Z", [("c", "monthly or yearly?"), ("a", "Pro is $12 per seat monthly or annually at $144 per seat.")])
    r = S(c); check("A16b", "Control: same wording with the correct yearly price passes", r["verdicts"]["c1"] == "pass" and r["disposition"] == "full_verdict", {"c1": r["verdicts"]["c1"], "claims": [x["reason"] for x in r["extractor_record"]["claims"]]})
    c = mk("FA13d", "2026-11-20T10:00:00Z", [("c", "when does my plan end"), ("a", "Your subscription expires in August 2029.")])
    r = S(c); txt = json.dumps(r["extractor_record"])
    check("A13d", "Control: subscription expiry is not card data", r["verdicts"]["c3"] == "pass" and "August 2029" in txt, {"c3": r["evidence"]["c3"], "date_kept": "August 2029" in txt})
    c = mk("FA13e", "2026-11-20T10:00:00Z", [("c", "I just added a new Visa"), ("a", "Thanks. It expires in August 2029, right?")])
    r = S(c); d13e = Desk(); d13e.ingest(r, "billing")
    saved = json.dumps({"result": r, "records": d13e.records, "queue": d13e.queue_items(), "audit": d13e.audit}, default=str)
    check("A13e", "Card expiry by pronoun after a card was named: fails and is masked", r["verdicts"]["c3"] == "fail" and "August 2029" not in saved, {"c3": r["verdicts"]["c3"], "evidence": r["evidence"].get("c3"), "leaked": "August 2029" in saved})
    r = S(inv("FA14", 96)); check("A14", "Contradicted account fact through both tiers", r["route"] == "R-claim" and "money" in r["claims_t1"] and r["verdicts"]["c1"] == "fail" and r["evidence"]["c1"].get("evidence_id") == "FA14-tool-1",
                                   {"route": r["route"], "t1": r["claims_t1"], "evidence": r["evidence"]["c1"]})
    base = inv("FT1", 84); close = ts(base["closed_at"])
    r = S(base, timing={"tier1": close + dt.timedelta(minutes=5), "tier2": close + dt.timedelta(minutes=65)})
    tri = ts(r["timestamps"]["tier1_completed_at"]) - close <= dt.timedelta(minutes=60); t2 = ts(r["timestamps"]["tier2_completed_at"]) - close <= dt.timedelta(minutes=60)
    d = Desk(); d.ingest(r, "fixture"); before = dict(r["timestamps"])
    d.late_evidence(r["closure_revision_id"], "corr-1", {"note": "correction"}, lambda p: S(base))
    after = d.records[r["closure_revision_id"]]["result"]["timestamps"]
    check("T1", "Tier 1 at min 5, tier 2 verdict at min 65", r["disposition"] == "full_verdict" and tri and not t2 and before["tier2_completed_at"] == after["tier2_completed_at"], {"timely_triage": tri, "timely_tier2": t2})
    c = inv("FR1", 84, start="2026-11-20T09:58:21Z"); r = S(c); m = (ts(r["timestamps"]["first_outcome_at"]) - ts(c["closed_at"])).total_seconds() / 60
    check("R1", "Close 1 second after a batch starts", m <= 60, f"{c['closed_at']} outcome after {m:.1f} min")
    c = inv("FR2"); r = S(c); d = Desk(); d.ingest(r, "fixture"); fo = r["timestamps"]["first_outcome_at"]
    def add_tool(p):
        c2 = copy.deepcopy(c); c2["tool_results"].append({"record_id": "FR2-tool-late", "at": c["messages"][2]["at"], "for_reply": "m03", "tool": "invoice_lookup", "result": p}); return S(c2)
    out = d.late_evidence(r["closure_revision_id"], "FR2-tool-late", {"month": "2026-10", "total_before_tax_usd": 84, "pro_seats": 7, "per_seat_usd": 12}, add_tool)
    rec = d.records[r["closure_revision_id"]]
    check("R2", "Tool log late, before QA action", r["disposition"] == "referred" and out == "re_judged" and rec["result"]["verdicts"]["c1"] == "pass" and rec["result"]["timestamps"]["first_outcome_at"] == fo, {"before": r["disposition"], "outcome": out})
    d = Desk(); r = S(inv("FR3", 96)); d.ingest(r, "fixture"); d.ingest(r, "fixture")
    check("R3", "Duplicate close event", len(d.records) == 1 and len(d.queue_items()) == 1, {"records": len(d.records)})
    d = Desk(); base = inv("FR4", 96); r1 = S(base); c2 = copy.deepcopy(base); c2["closure_revision_id"] = "FR4-r2"; r2 = S(c2)
    d.ingest(r1, "invoices"); d.ingest(r2, "invoices")
    check("R4", "Reopened and closed again", len(d.records) == 2 and len(d._distinct(("c1", "invoices", "r-1"), ("pending_qa",))) == 1, {"revisions": len(d.records)})
    d = Desk(); convs = [mk(f"FR5-{i}", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr()]) for i in range(5)]
    for c in convs: d.ingest(S(c), "refunds")
    cand = len([a for a in d.alerts if a["type"] == "candidate_cluster"]); d.qa_dispose("FR5-0-r1", "confirmed")
    def with_issue(p, c=convs[0]):
        c2 = copy.deepcopy(c); c2["action_events"].append(p); return S(c2)
    n = len(d.alerts); payload = {"record_id": "FR5-0-event-late", "at": "2026-11-20T10:00:30Z", "for_reply": "m03", "type": "refund_issue", "status": "issued", "amount_usd": 48, "issued_on": "2026-11-20"}
    out = d.late_evidence("FR5-0-r1", "late-issue", payload, with_issue); rec = d.records["FR5-0-r1"]
    prior = any(a["event"] == "qa_disposition" and a["disposition"] == "confirmed" for a in d.audit if a["closure_revision_id"] == "FR5-0-r1")
    newal = [a for a in d.alerts[n:] if a["type"] in ("candidate_cluster", "confirmed_cluster")]
    check("R5", "Late action evidence after confirmed and candidate alert", cand == 1 and out == "re_review" and rec["status"] == "under_re_review" and prior and not newal, {"candidate": cand, "outcome": out})
    out2 = d.late_evidence("FR5-0-r1", "late-issue", payload, with_issue)
    check("R6", "Same late evidence delivered twice", out2 == "duplicate_ignored" and len(rec["evidence_versions"]) == 2, {"outcome": out2})
    d = Desk(); c = inv("FR7", 84); r = S(c); d.ingest(r, "fixture"); out = d.late_evidence(r["closure_revision_id"], "note", {"x": 1}, lambda p: S(c))
    check("R7", "Late evidence that does not change the finding", out == "stored_no_change" and not d.records[r["closure_revision_id"]]["in_queue"], {"outcome": out})
    d = Desk(); convs = [mk(f"FR8-{i}", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr()]) for i in range(3)]
    for c in convs: d.ingest(S(c), "refunds")
    for c in convs: d.qa_dispose(c["closure_revision_id"], "confirmed")
    key = ("c1", "refunds", "r-1"); opened = d.incidents.get(key)
    out = d.late_evidence("FR8-0-r1", "late8", {**payload, "record_id": "FR8-0-late"}, lambda p, c=convs[0]: with_issue(p, c))
    mid = d.incidents[key]; conf = len(d.confirmed(key)); d.qa_dispose("FR8-0-r1", "dismissed")
    check("R8", "Late evidence invalidates a finding in a confirmed cluster of 3", opened == "open" and out == "re_review" and conf == 2 and mid == "below_threshold_under_re_review" and d.incidents[key] == "below_threshold",
          {"before": opened, "during": mid, "after": d.incidents[key]})
    d = Desk(); ca, cb = inv("FR9a"), inv("FR9b")
    for c in (ca, cb): d.ingest(S(c), "fixture")
    def addt(c):
        def f(p):
            c2 = copy.deepcopy(c); c2["tool_results"].append({"record_id": "same", "at": c["messages"][2]["at"], "for_reply": "m03", "tool": "invoice_lookup", "result": p}); return S(c2)
        return f
    p9 = {"month": "2026-10", "total_before_tax_usd": 84, "pro_seats": 7, "per_seat_usd": 12}
    oa = d.late_evidence("FR9a-r1", "same", p9, addt(ca)); ob = d.late_evidence("FR9b-r1", "same", p9, addt(cb))
    check("R9", "Identical payloads for two conversations", oa != "duplicate_ignored" and ob != "duplicate_ignored", {"a": oa, "b": ob})
    r = S(mk("FR10", "2026-11-20T10:00:00Z", REFUND_SENT, events=[appr()], health="delayed")); close = ts(r["timestamps"]["close_at"])
    ok, det = timely_relevant_referral(r, ts(r["timestamps"]["referred_at"]), "c1", "action log incomplete"); check("R10", "Referral on time, correct check and reason", ok, det)
    ok, det = timely_relevant_referral(r, close + dt.timedelta(minutes=61), "c1", "action log incomplete"); check("R11", "Referral late (minute 61)", not ok and not det["on_time"], det)
    w = copy.deepcopy(r); w["referral"] = {"check": "c4", "reason": "unclear answer"}
    ok, det = timely_relevant_referral(w, close + dt.timedelta(minutes=20), "c1", "action log incomplete"); check("R12", "Timely referral, wrong check and reason", not ok and det["on_time"] and not det["relevant"], det)
    return list(RESULTS)

if __name__ == "__main__":
    for x in run_all(): print("PASS" if x["pass"] else "FAIL", x["id"], x["test"], "|", x["detail"])
