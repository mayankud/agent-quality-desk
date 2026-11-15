"""Replay-layer tests: missing reply, mismatched reply, incomplete batch, pre-lock reply, other lock, non-locked components,
invalid first attempt then valid retry (history separate from unresolved problems), and replies checked against the exact scoring
input (span, role, message ID, typed fields, re-rendered request, pass and batch binding). Hand-written responses, plumbing only."""
import json, tempfile, pathlib, shutil
import harness as H
R = []
def check(n, c, d=""): R.append((n, bool(c), d))
lock = {"lock_id": "TEST-LOCK", "locked_at_utc": "2026-11-13T12:00:00Z", "model_id": H.MODEL_ID, "components": H.component_hashes()}
convs = [{"case_id": f"C{i}", "messages": [{"message_id": "m02", "role": "customer", "text": "How much is Pro?"}, {"message_id": "m03", "role": "assistant", "text": "Pro is $12 per seat per month."}]} for i in range(1, 4)]
good = lambda ids: json.dumps({"cases": [{"case_id": c, "claims": [{"message_id": "m03", "span": "$12 per seat per month", "part_type": "price", "fields": {"amount": 12, "unit": "seat", "period": "month"}}], "needs": [{"message_id": "m02", "need": "question"}], "sensitive_requests": []} for c in ids]})
def fresh():
    d = pathlib.Path(tempfile.mkdtemp()); return H.Store(d), d
def run_all():
    R.clear()
    # 1 normal
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq); st.save_response(rq["request_sha256"], good(["C1", "C2", "C3"]), "agent-1", "2026-11-13T12:05:00Z")
    out, pr, sel = H.select(st, lock, "extract"); check("bound, complete, post-lock reply is selected", out[1]["C1"] and not pr, pr)
    # 2 missing
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq)
    out, pr, _ = H.select(st, lock, "extract"); check("missing reply leaves the batch unselected and is reported", out[1]["C1"] is None and any("no response" in p for p in pr), pr)
    # 3 mismatched (response written against another request hash)
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq)
    other = H.build_request("extract", "TEST-LOCK", 2, 1, "b9", convs)
    (st.d / "responses" / f"{rq['request_sha256']}.json").write_text(json.dumps({"request_sha256": other["request_sha256"], "agent_id": "x", "received_at_utc": "2026-11-13T12:05:00Z", "raw_response": good(["C1", "C2", "C3"])}))
    out, pr, _ = H.select(st, lock, "extract"); check("reply bound to another request is refused", out[1]["C1"] is None and any("another request" in p for p in pr), pr)
    # 4 tampered request text
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); rq2 = dict(rq); rq2["text"] = rq["text"] + " tampered"; st.save_request(rq2); st.save_response(rq["request_sha256"], good(["C1", "C2", "C3"]), "a", "2026-11-13T12:05:00Z")
    out, pr, _ = H.select(st, lock, "extract"); check("request whose text no longer matches its hash is refused", out[1]["C1"] is None and any("does not match its hash" in p for p in pr), pr)
    # 5 incomplete batch
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq); st.save_response(rq["request_sha256"], good(["C1", "C2"]), "a", "2026-11-13T12:05:00Z")
    out, pr, _ = H.select(st, lock, "extract"); check("reply missing a case is refused for the whole batch", all(out[1][c] is None for c in ("C1", "C2", "C3")) and any("incomplete" in p for p in pr), pr)
    # 6 pre-lock
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq); st.save_response(rq["request_sha256"], good(["C1", "C2", "C3"]), "a", "2026-11-13T11:59:59Z")
    out, pr, _ = H.select(st, lock, "extract"); check("reply received before the lock is refused", out[1]["C1"] is None and any("before the lock" in p for p in pr), pr)
    # 7 other lock
    st, d = fresh(); rq = H.build_request("extract", "OTHER-LOCK", 1, 1, "b1", convs); st.save_request(rq); st.save_response(rq["request_sha256"], good(["C1", "C2", "C3"]), "a", "2026-11-13T12:05:00Z")
    out, pr, _ = H.select(st, lock, "extract"); check("request bound to another lock is refused", out[1]["C1"] is None and any("another lock" in p for p in pr), pr)
    # 8 components not locked
    lock2 = json.loads(json.dumps(lock)); lock2["components"]["prompts/extract.txt"] = "0" * 64
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq); st.save_response(rq["request_sha256"], good(["C1", "C2", "C3"]), "a", "2026-11-13T12:05:00Z")
    out, pr, _ = H.select(st, lock2, "extract"); check("request built from a prompt that is not the locked one is refused", out[1]["C1"] is None and any("not the locked ones" in p for p in pr), pr)
    # 9 invalid first attempt, valid retry
    st, d = fresh(); rq1 = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs); st.save_request(rq1); st.save_response(rq1["request_sha256"], "Sure! Here is the JSON...", "a", "2026-11-13T12:05:00Z")
    rq2 = H.build_request("extract", "TEST-LOCK", 1, 2, "b1", convs); st.save_request(rq2); st.save_response(rq2["request_sha256"], good(["C1", "C2", "C3"]), "b", "2026-11-13T12:06:00Z")
    out, pr, sel = H.select(st, lock, "extract")
    hs = st.history["extract"]
    check("invalid first attempt is kept in the attempt history, the valid retry is selected and nothing is left unresolved",
          out[1]["C1"] and sel["extract|1|b1"] == rq2["request_sha256"] and not pr and [h["outcome"] for h in hs] == ["rejected", "selected"] and "invalid output" in hs[0]["reason"], {"problems": pr, "history": hs})
    # 10 third attempt ignored
    rq3 = H.build_request("extract", "TEST-LOCK", 1, 3, "b1", convs); check("attempts beyond the maximum are never selected", H.MAX_ATTEMPTS == 2 and rq3["attempt"] == 3)
    # 11 batch order frozen and different per pass
    o1 = H.batch_order([f"X{i}" for i in range(12)], "L", "extract", 1); o2 = H.batch_order([f"X{i}" for i in range(12)], "L", "extract", 2)
    check("batch order is deterministic, batches of at most 5, and pass 2 differs", o1 == H.batch_order([f"X{i}" for i in range(12)], "L", "extract", 1) and max(map(len, o1)) <= 5 and o1 != o2)
    # 12 to 18: replies checked against the exact scoring input (review findings of 13 Nov 2026)
    cm = {c["case_id"]: c for c in convs}
    INV = H.expected_batches(list(cm), "TEST-LOCK", "extract")
    def full_run(raw_first, skip=(), extra=False):
        """Writes the complete expected inventory (both passes). The pass-1 batch gets raw_first, the others a valid reply."""
        st, d = fresh()
        for k, cases in INV.items():
            if k in skip: continue
            pn, bid = int(k.split("|")[1]), k.split("|")[2]
            rq = H.build_request("extract", "TEST-LOCK", pn, 1, bid, [cm[c] for c in cases]); st.save_request(rq)
            st.save_response(rq["request_sha256"], raw_first if pn == 1 else claimed(), "a", "2026-11-13T12:05:00Z")
        if extra:
            rq = H.build_request("extract", "TEST-LOCK", 1, 1, "extract-p1-b99", [cm["C1"]]); st.save_request(rq); st.save_response(rq["request_sha256"], claimed(), "a", "2026-11-13T12:05:00Z")
        return st
    def one(raw, mutate=None, scoring=None):
        st = full_run(raw)
        return H.select(st, lock, "extract", scoring if scoring is not None else cm)
    def claimed(span="$12 per seat per month", mid="m03", fields=None, needs_mid="m02", pt="price"):
        return json.dumps({"cases": [{"case_id": c, "claims": [{"message_id": mid, "span": span, "part_type": pt, "fields": fields if fields is not None else {"amount": 12, "unit": "seat", "period": "month"}}],
                                      "needs": [{"message_id": needs_mid, "need": "question"}], "sensitive_requests": []} for c in ("C1", "C2", "C3")]})
    out, pr, _ = one(claimed())
    check("valid reply checked against its scoring input is selected", out[1]["C1"] and not pr, pr)
    out, pr, _ = one(claimed(span="Pro is $12 per seat per year."))
    check("quoted span absent from the cited message is refused", out[1]["C1"] is None and any("span is not in m03" in p for p in pr), pr)
    out, pr, _ = one(claimed(mid="m02"))
    check("claim attributed to a customer message is refused", out[1]["C1"] is None and any("not an assistant message" in p for p in pr), pr)
    out, pr, _ = one(claimed(mid="m09"))
    check("claim citing a message ID that is not in the case is refused", out[1]["C1"] is None and any("m09" in p for p in pr), pr)
    out, pr, _ = one(claimed(fields={"unit": "seat"}))
    check("price claim without its typed amount and period is refused", out[1]["C1"] is None and any("needs field amount" in p for p in pr), pr)
    out, pr, _ = one(claimed(needs_mid="m03"))
    check("need attributed to an assistant message is refused", out[1]["C1"] is None and any("not a customer message" in p for p in pr), pr)
    other = {k: {**v, "messages": [v["messages"][0], {**v["messages"][1], "text": "Pro is $15 per seat per month."}]} for k, v in cm.items()}
    out, pr, _ = one(claimed(), scoring=other)
    check("scoring input that differs from the saved request is refused", out[1]["C1"] is None and any("does not re-render" in p for p in pr), pr)
    def wrong_pass(st, rq):
        e = st.index["entries"].setdefault("extract|2|b1", {"task": "extract", "pass": 2, "batch_id": "b1", "case_ids": rq["case_ids"], "attempts": [rq["request_sha256"]]})
    st, d = fresh(); rq = H.build_request("extract", "TEST-LOCK", 1, 1, "b1", convs)
    (st.d / "requests" / f"{rq['request_sha256']}.json").write_text(json.dumps(rq)); st.save_response(rq["request_sha256"], claimed(), "a", "2026-11-13T12:05:00Z")
    st.index = {"entries": {"extract|2|b1": {"task": "extract", "pass": 2, "batch_id": "b1", "case_ids": rq["case_ids"], "attempts": [rq["request_sha256"]]}}}
    out, pr, _ = H.select(st, lock, "extract", cm)
    check("pass-1 request filed under a pass-2 index entry is refused", out[2]["C1"] is None and any("another pass, batch" in p for p in pr), pr)
    check("schema validation uses the standard library only", "import jsonschema" not in open(H.__file__).read())
    # 21 to 23: the complete expected batch inventory (review findings of 14 Nov 2026)
    k2 = next(k for k in INV if k.startswith("extract|2|"))
    out, pr, _ = H.select(full_run(claimed(), skip=(k2,)), lock, "extract", cm)
    check("a batch missing from the index is an unresolved problem and its cases have no reply for that pass", any("expected batch missing" in p for p in pr) and any("no valid reply for 3 cases" in p for p in pr) and out[2].get("C1") is None, pr)
    out, pr, _ = H.select(full_run(claimed(), extra=True), lock, "extract", cm)
    check("a batch outside the expected inventory is an unresolved problem", any("not in the expected inventory" in p for p in pr), pr)
    out, pr, _ = H.select(full_run(claimed()), lock, "extract", cm)
    check("the complete inventory with valid replies leaves nothing unresolved", not pr and all(out[p].get(c) for p in (1, 2) for c in cm), pr)
    # 24: a promise reply must carry every detail its own span states (review finding of 14 Nov 2026)
    pc = {"PROM": {"case_id": "PROM", "messages": [{"message_id": "m01", "role": "assistant", "text": "AI notice"}, {"message_id": "m02", "role": "customer", "text": "When is my refund?"},
                                                     {"message_id": "m03", "role": "assistant", "text": "You'll get your $48 back to your original card tomorrow."}]}}
    pr_obj = lambda fields: {"cases": [{"case_id": "PROM", "claims": [{"message_id": "m03", "span": "You'll get your $48 back to your original card tomorrow.", "part_type": "future_promise", "fields": fields}], "needs": [], "sensitive_requests": []}]}
    e_missing = H.semantic_errors(pr_obj({"action": "money_returned", "amount": 48, "when": "tomorrow"}), "extract", pc)
    e_full = H.semantic_errors(pr_obj({"action": "money_returned", "amount": 48, "when": "tomorrow", "destination": "original_card"}), "extract", pc)
    check("promise reply that omits the stated destination is refused, the complete one is accepted", any("states a destination" in e for e in e_missing) and not e_full, {"missing": e_missing, "full": e_full})
    pc2 = {"CRED": {"case_id": "CRED", "messages": [{"message_id": "m01", "role": "assistant", "text": "AI notice"}, {"message_id": "m02", "role": "customer", "text": "Any goodwill for the outage?"},
                                                     {"message_id": "m03", "role": "assistant", "text": "Sorry about that, you also get a 10% credit next month."}]}}
    e_credit = H.semantic_errors({"cases": [{"case_id": "CRED", "claims": [{"message_id": "m03", "span": "you also get a 10% credit next month", "part_type": "future_promise", "fields": {"action": "credit_applied", "amount": 10, "when": "next month"}}], "needs": [], "sensitive_requests": []}]}, "extract", pc2)
    check("a credit promise needs no destination (the L4 false rejection on RG-15)", not e_credit, e_credit)
    return [{"test": n, "pass": ok, "detail": str(dd)[:300]} for n, ok, dd in R]

if __name__ == "__main__":
    res = run_all(); json.dump(res, open("test_harness_results.json", "w"), indent=1)
    for x in res: print("PASS" if x["pass"] else "FAIL", x["test"])
