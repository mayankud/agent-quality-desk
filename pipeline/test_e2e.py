"""End-to-end replay test (review finding of 13 Nov 2026): a run folder with both tasks and both passes, where the first extraction
attempt of pass 1 quotes a span that is not in the message and the second attempt is valid. Scoring must select the retry, leave no
unresolved selection problem, keep the rejected attempt in the history, compute the two-pass consistency from valid pairs, and
produce byte-identical scores when run twice. Synthetic fixture conversations and hand-written replies, no model call."""
import json, tempfile, pathlib, hashlib
import harness as H, run5, desk7
from fixture_builder import mk

T0 = "2026-11-20T10:00:00Z"
CONVS = [mk("E2E-1", T0, [("c", "How much is Pro?"), ("a", "Pro is $12 per seat per month.")]),
         mk("E2E-2", T0, [("c", "Can I talk to a person?"), ("a", "I've queued a transfer to our support team.")],
            events=[("m03", "handoff", {"queue": "support", "context": "Customer asks for a person about billing access.", "status": "queued"})]),
         mk("E2E-3", T0, [("c", "Hello"), ("a", "Hi, how can I help?")])]

def ext(span_ok=True):
    return json.dumps({"cases": [
        {"case_id": "E2E-1", "claims": [{"message_id": "m03", "span": "Pro is $12 per seat per month." if span_ok else "Pro is $12 per seat per year.", "part_type": "price", "fields": {"amount": 12, "unit": "seat", "period": "month"}}],
         "needs": [{"message_id": "m02", "need": "question"}], "sensitive_requests": []},
        {"case_id": "E2E-2", "claims": [{"message_id": "m03", "span": "I've queued a transfer to our support team.", "part_type": "handoff_claim", "fields": {"kind": "queued", "queue": "support"}}],
         "needs": [{"message_id": "m02", "need": "explicit_request_for_person"}], "sensitive_requests": []},
        {"case_id": "E2E-3", "claims": [], "needs": [{"message_id": "m02", "need": "other"}], "sensitive_requests": []}]})
def jud():
    one = lambda cid, ctx: {"case_id": cid, "resolution": {"value": "yes", "message_id": "m03", "reason": "answered"}, "tone": {"value": "ok", "message_id": "m03", "reason": "polite"}, "handoff_context": ctx}
    return json.dumps({"cases": [one("E2E-1", "not_applicable"), one("E2E-2", "covers"), one("E2E-3", "not_applicable")]})

def run_all():
    R = []; d = pathlib.Path(tempfile.mkdtemp()); cp = d / "cases.json"; cp.write_text(json.dumps({"conversations": CONVS}))
    lk = {"lock_id": "E2E-LOCK", "locked_at_utc": "2026-11-01T00:00:00Z", "model_id": H.MODEL_ID, "components": H.component_hashes(),
          "code": {f: hashlib.sha256((run5.ROOT / f).read_bytes()).hexdigest() for f in run5.CODE},
          "rubric": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((run5.ROOT / "rubric").glob("*"))}}
    (d / "lock.json").write_text(json.dumps(lk)); st = H.Store(d); red = {c["case_id"]: desk7.R.redact(c) for c in CONVS}
    for k, cases in H.expected_batches(list(red), "E2E-LOCK", "extract").items():
        p, bid = int(k.split("|")[1]), k.split("|")[2]
        for a, raw in ([(1, ext(False)), (2, ext())] if p == 1 else [(1, ext())]):
            rq = H.build_request("extract", "E2E-LOCK", p, a, bid, [red[c] for c in cases]); st.save_request(rq); st.save_response(rq["request_sha256"], raw, f"agent-x{p}{a}", "2026-11-20T10:05:00Z")
    res, _, _, _ = run5.stage_results(d, {c["case_id"]: c for c in CONVS}, lk, False)
    extras = {cid: desk7.judge_extras(r, next(c for c in CONVS if c["case_id"] == cid)) for cid, r in res.items()}
    for k, cases in H.expected_batches(list(red), "E2E-LOCK", "judge").items():
        p, bid = int(k.split("|")[1]), k.split("|")[2]
        rq = H.build_request("judge", "E2E-LOCK", p, 1, bid, [red[c] for c in cases], extras); st.save_request(rq); st.save_response(rq["request_sha256"], jud(), f"agent-j{p}", "2026-11-20T10:06:00Z")
    o1, o2 = d / "s1.json", d / "s2.json"; run5.score(d, o1, cp); run5.score(d, o2, cp)
    S = json.loads(o1.read_text()); hist = S["attempt_history"]["extract"]; cons = S["consistency"]
    R.append({"test": "invalid first attempt rejected, valid retry selected, no unresolved selection problem", "pass": not S["selection_problems"] and [h["outcome"] for h in hist if h["batch"].startswith("extract|1|")] == ["rejected", "selected"] and "span is not in m03" in hist[0]["reason"], "detail": {"problems": S["selection_problems"], "history": hist}})
    R.append({"test": "two scoring runs of the same folder give byte-identical scores", "pass": o1.read_bytes() == o2.read_bytes(), "detail": [hashlib.sha256(o.read_bytes()).hexdigest() for o in (o1, o2)]})
    R.append({"test": "consistency is computed from valid pairs with counts", "pass": cons["extraction_valid_pairs"] == 3 and cons["judge_valid_pairs"] == 3 and cons["claim_parts"]["pairs"] == 2 and cons["claim_parts"]["rate"] == 1.0 and cons["gate"]["pass"] is True, "detail": cons})
    r2 = next(r for r in S["datasets"]["holdout"]["results"] if r["conversation_id"] == "E2E-2")
    R.append({"test": "required handoff with covering context from both passes passes check 2", "pass": r2["verdicts"]["c2"] == "pass", "detail": r2["evidence"]["c2"]})
    # judge missing for pass 2: consistency reports unavailable judge pairs and the gate does not pass
    jk = next(k for k in st.index["entries"] if k.startswith("judge|2|"))
    (d / "responses" / f"{st.index['entries'][jk]['attempts'][0]}.json").unlink(); o3 = d / "s3.json"; run5.score(d, o3, cp); S3 = json.loads(o3.read_text())
    R.append({"test": "with no pass-2 judge reply, judge agreement is unavailable, the gate fails and the batch is listed unresolved", "pass": S3["consistency"]["judge"]["resolution"]["rate"] == "unavailable" and S3["consistency"]["gate"]["pass"] is False and any(jk in p for p in S3["selection_problems"]), "detail": S3["consistency"]})
    # the tester's probe of 14 Nov 2026: an index entry removed altogether must not escape the missing-reply path
    idx = json.loads((d / "index.json").read_text()); idx["entries"].pop(jk); (d / "index.json").write_text(json.dumps(idx)); o4 = d / "s4.json"; run5.score(d, o4, cp); S4 = json.loads(o4.read_text())
    R.append({"test": "an index entry removed altogether is reported as an expected batch missing, with its cases listed", "pass": any("expected batch missing" in p for p in S4["selection_problems"]) and any("no valid reply for 3 cases" in p for p in S4["selection_problems"]), "detail": S4["selection_problems"]})
    return R

if __name__ == "__main__":
    res = run_all(); json.dump(res, open("test_e2e_results.json", "w"), indent=1, default=str)
    for x in res: print("PASS" if x["pass"] else "FAIL", x["test"]) if (not x["pass"] or True) else None
