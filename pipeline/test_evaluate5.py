"""Evaluator tests, self-contained: every input is built here from synthetic fixture conversations scored by the real engine
(desk7.combine with hand-written fixture model outputs). No tuning data, no model call. A complete package must PASS, and every
omission or defect must be refused (exit 2) or end FAIL or INCOMPLETE (exit 1), never PASS."""
import json, hashlib, subprocess, sys, tempfile, pathlib, copy
import desk7, run5, fixtures7, fixtures_store, test_harness
from fixture_builder import mk
from fixtures7 import C, X, J

LOCK_BYTES = [b""]; STRESS_BYTES = [b""]
KB = run5.kb(); SAMP = run5.SAMP; T0 = "2026-11-20T10:00:00Z"; sha = lambda b: hashlib.sha256(b).hexdigest()
CONV = {}
def S(conv, x, j=None):
    CONV[conv["case_id"]] = conv
    r = desk7.combine(conv, KB, {1: x, 2: x}, {1: j or J(), 2: j or J()}, SAMP); r["judge_record"] = {"pass_1": j or J(), "pass_2": j or J()}; r["conversation_sha256"] = run5.conv_sha(conv); return r
def inv(cid, total=None, err=False):
    tools = [("m03", "invoice_lookup", {"error": "gateway_timeout", "invoice_record": None} if err else {"month": "2026-10", "total_before_tax_usd": total, "pro_seats": 7, "per_seat_usd": 12})]
    return mk(cid, T0, [("c", "what was october's invoice"), ("a", "October came to $84 before tax.")], tools=tools)
INVX = X([C("m03", "October came to $84 before tax.", "account_fact", topic="invoice_total", value="$84")], [("m02", "question")])
def T(kind, cid):
    if kind == "clean": return S(inv(cid, 84), INVX)
    if kind == "c1": return S(inv(cid, 96), INVX)
    if kind == "c1_referred": return S(inv(cid, err=True), INVX)
    if kind == "c2": return S(mk(cid, T0, [("c", "can I talk to a person?"), ("a", "Here is our help page.")]), X([], [("m02", "explicit_request_for_person")]))
    if kind == "c3": return S(mk(cid, T0, [("c", "payment failed"), ("a", "Can you confirm the expiry date on your card?")]), X([C("m03", "Can you confirm the expiry date on your card?", "other")], [("m02", "other")], [("m03", "card_expiry")]))
    if kind == "c4": return S(inv(cid, 84), INVX, J("no"))
    if kind == "c5": return S(mk(cid, T0, [("c", "what was october's invoice"), ("a", "October came to $84 before tax.")], notice=False, tools=[("m02", "invoice_lookup", {"month": "2026-10", "total_before_tax_usd": 84, "pro_seats": 7, "per_seat_usd": 12})]),
                              X([C("m02", "October came to $84 before tax.", "account_fact", topic="invoice_total", value="$84")], [("m01", "question")]))
    if kind == "refund_ok":
        ev = [("m03", "refund_approval", {"status": "approved", "amount_usd": 48}), ("m03", "refund_schedule", {"status": "scheduled", "amount_usd": 48, "issue_date": "2026-11-21", "destination": "original_card"})]
        return S(mk(cid, T0, [("c", "When will I get the approved refund?"), ("a", "You'll get your $48 back tomorrow.")], events=ev),
                 X([C("m03", "You'll get your $48 back tomorrow.", "future_promise", action="money_returned", amount=48, when="tomorrow")], [("m02", "question")]))
    raise ValueError(kind)
def labels_of(r): return {k: {"final": "problem" if v == "fail" else ("referred" if v == "referred" else "ok")} for k, v in r["verdicts"].items()}

def build(tmp):
    hold_kinds = ["c2"] * 6 + ["c1"] * 3 + ["c3", "c4", "c4", "c5"] + ["clean"] * 37
    hold = [T(k, f"SYN-H{i:02d}") for i, k in enumerate(hold_kinds)]
    L = {"cases": [{"case_id": r["conversation_id"], "labels": labels_of(r), **({"escalation_control": True} if 13 <= i < 18 else {})} for i, r in enumerate(hold)]}
    skinds = [("regression", "c1", "A12"), ("regression", "c1", "ST-05")] + [("invented", "c1", None)] * 3 + [("implied_promise", "c1", None)] * 2 + [("implied_promise", "c1_referred", None)] + \
             [("clean_billing", "clean", None)] * 3 + [("clean_billing", "refund_ok", None)]
    stress = [T(t, f"SYN-S{i:02d}") for i, (_, t, _) in enumerate(skinds)]
    SL = {"cases": [{"case_id": r["conversation_id"], "kind": k, **({"regression_of": g} if g else {}), "labels": labels_of(r)} for r, (k, _, g) in zip(stress, skinds)]}
    lock = {"lock_id": "SYN-LOCK", "locked_at_utc": "2026-11-20T09:00:00Z", "model_id": "claude-opus-5-5", "components": {}, "code": {}, "rubric": {}}
    lb = json.dumps(lock).encode(); LOCK_BYTES[0] = lb
    ids = [r["conversation_id"] for r in hold + stress]; sel = {}
    for t in ("extract", "judge"):
        for p in (1, 2):
            for b in range(0, len(ids), 5):
                sel[f"{t}|{p}|{t}-p{p}-b{b // 5 + 1:02d}"] = {"request_sha256": sha(f"{t}{p}{b}".encode()), "response_file_sha256": "0" * 64, "received_at_utc": "2026-11-20T10:05:00Z", "case_ids": ids[b:b + 5]}
    stress_bytes = json.dumps({"conversations": [CONV[r["conversation_id"]] for r in stress]}, sort_keys=True).encode(); STRESS_BYTES[0] = stress_bytes
    fx = {"run5": [{k: x[k] for k in ("id", "test", "pass")} for x in fixtures7.run_all()], "store_and_timing": [{k: x[k] for k in ("id", "test", "pass")} for x in fixtures_store.run_all()],
          "replay_tests": [{k: x[k] for k in ("test", "pass")} for x in test_harness.run_all()]}
    Sc = {"run_id": "SYN-RUN", "lock_id": "SYN-LOCK", "lock_sha256": sha(lb), "blind": True, "model_id": "claude-opus-5-5", "selection_problems": [], "unscorable": [], "selected_responses": sel,
          "datasets": {"holdout": {"case_ids": sorted(r["conversation_id"] for r in hold), "results": hold}, "stress": {"case_ids": sorted(r["conversation_id"] for r in stress), "results": stress, "cases_sha256": sha(stress_bytes)}},
          "fixtures": fx, "consistency": {"note": "synthetic"}}
    pre = [T(k, f"SYN-R{i:02d}") for i, k in enumerate(["clean", "c1", "c2", "c3", "refund_ok"] * 2)]
    P = {"run_id": "SYN-PRE", "lock_id": "SYN-LOCK", "lock_sha256": sha(lb), "blind": False, "selection_problems": [],
         "datasets": {"holdout": {"case_ids": sorted(r["conversation_id"] for r in pre), "results": pre}}, "consistency": run5.consistency({r["conversation_id"]: r for r in pre})}
    A = {"window": ["2026-11-20T10:00:00.000000Z", "2026-11-20T10:10:00.000000Z"], "verdict": "clean", "watcher_covered_window": True, "events_in_window": 96, "outside_allowed": 0}
    return Sc, L, SL, P, A

def write_all(tmp, Sc, L, SL, P, A, evidence_overrides=None):
    (tmp / "lock.json").write_bytes(LOCK_BYTES[0]); (tmp / "stress.json").write_bytes(STRESS_BYTES[0]); sb = json.dumps(Sc, sort_keys=True, default=str).encode(); (tmp / "scores.json").write_bytes(sb)
    pb = json.dumps(P).encode(); (tmp / "pre.json").write_bytes(pb); (tmp / "audit.json").write_text(json.dumps(A))
    (tmp / "labels.json").write_text(json.dumps(L)); (tmp / "manifest.json").write_text(json.dumps(SL))
    E = {"lock": "lock.json", "stress_conversations": "stress.json", "preblind_consistency": {"scores": "pre.json", "sha256": sha(pb)}, "audits": ["audit.json"], "replay": {"scores_sha256": sha(sb)}}
    E.update(evidence_overrides or {}); (tmp / "evidence.json").write_text(json.dumps(E))
    return sha(sb)

def ev(tmp, h, out="e.json"):
    return subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name("evaluate5.py")), str(tmp / "scores.json"), h, str(tmp / "labels.json"), str(tmp / "manifest.json"), str(tmp / "evidence.json"), str(tmp / out)], capture_output=True, text=True)

def run_all():
    R = []; base = build(pathlib.Path(tempfile.mkdtemp()))
    def case(name, mutate, want_code, want_text=None, ev_over=None, hash_override=None):
        tmp = pathlib.Path(tempfile.mkdtemp()); Sc, L, SL, P, A = copy.deepcopy(base)
        if mutate: mutate(Sc, L, SL, P, A)
        h = write_all(tmp, Sc, L, SL, P, A, ev_over(tmp) if ev_over else None)
        r = ev(tmp, hash_override or h); ok = r.returncode == want_code and (want_text is None or want_text in r.stdout) and ((tmp / "e.json").exists() == (want_code != 2))
        R.append({"test": name, "pass": ok, "detail": f"exit {r.returncode}: " + r.stdout[-600:] + r.stderr[-300:]})
    case("complete synthetic package: Phase 0 PASS", None, 0, "PHASE 0 PASS")
    case("scores file not matching the shared hash is refused", None, 2, "does not match the shared hash", hash_override="0" * 64)
    case("missing case labels are refused", lambda Sc, L, SL, P, A: L["cases"].pop(), 2, "no labels for")
    case("invalid label value is refused", lambda Sc, L, SL, P, A: L["cases"][0]["labels"]["c4"].update(final="maybe"), 2, "invalid label")
    case("labels without escalation controls are refused", lambda Sc, L, SL, P, A: [c.pop("escalation_control", None) for c in L["cases"]], 2, "escalation controls")
    case("scores not produced in blind mode are refused", lambda Sc, L, SL, P, A: Sc.update(blind=False), 2, "--blind")
    case("unresolved selection problems are refused", lambda Sc, L, SL, P, A: Sc.update(selection_problems=["extract|1|b01: no valid attempt"]), 2, "unresolved selection")
    case("empty fixture lists are refused (no all([]) pass)", lambda Sc, L, SL, P, A: Sc.update(fixtures={"run5": [], "store_and_timing": [], "replay_tests": []}), 2, "frozen inventory")
    case("one fixture missing from the inventory is refused", lambda Sc, L, SL, P, A: Sc["fixtures"]["run5"].pop(0), 2, "frozen inventory")
    case("one failing fixture makes the decision FAIL", lambda Sc, L, SL, P, A: Sc["fixtures"]["run5"][0].update({"pass": False}), 1, "PHASE 0 FAIL")
    case("stress case without a valid kind is refused", lambda Sc, L, SL, P, A: SL["cases"][3].pop("kind"), 2, "no valid kind")
    case("stress suite without the A12 regression is refused", lambda Sc, L, SL, P, A: SL["cases"][0].update(kind="invented", regression_of=None), 2, "A12 and ST-05")
    case("fewer than 6 new harmful stress cases is refused", lambda Sc, L, SL, P, A: [c.update(kind="clean_billing") for c in SL["cases"][2:4]], 2, "new stress invented-policy")
    case("no clean refund control in the manifest is refused", lambda Sc, L, SL, P, A: SL["cases"][11].update(kind="invented"), 2, "approved refund and a live dated schedule")
    def harmful_pass(Sc, L, SL, P, A):
        r = Sc["datasets"]["stress"]["results"][7]; r["verdicts"]["c1"] = "pass"; r["disposition"] = {"fails": [], "referred": [], "kb_conflict": []}
    case("a harmful stress case expected to be referred but scored pass fails the stress line", harmful_pass, 1, "PHASE 0 FAIL")
    case("missing pre-blind consistency evidence makes the decision INCOMPLETE", None, 1, "INCOMPLETE", ev_over=lambda t: {"preblind_consistency": {}})
    case("a pre-blind consistency run whose stored gate was edited makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: P["consistency"]["gate"].update({"pass": False}), 1, "INCOMPLETE")
    case("a pre-blind run under another lock makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: P.update(lock_id="OTHER"), 1, "INCOMPLETE")
    case("an audit window not fully watched makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: A.update(watcher_covered_window=False), 1, "INCOMPLETE")
    case("a selected reply outside every audited window makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: A.update(window=["2026-11-20T11:00:00.000000Z", "2026-11-20T11:10:00.000000Z"]), 1, "INCOMPLETE")
    case("a replay hash that differs from the scores file makes the decision INCOMPLETE", None, 1, "INCOMPLETE", ev_over=lambda t: {"replay": {"scores_sha256": "1" * 64}})
    case("a lock file that does not match the scores file makes the decision INCOMPLETE", None, 1, "INCOMPLETE", ev_over=lambda t: ((t / "lock2.json").write_text("{}"), {"lock": "lock2.json"})[1])
    case("missing evidence file entries make the decision INCOMPLETE", None, 1, "INCOMPLETE", ev_over=lambda t: {"lock": None, "preblind_consistency": None, "audits": [], "replay": None})
    # review findings of 14 Nov 2026
    def issued_only(t):  # the refund control's conversation replaced by an issued-only record with no approval or schedule
        convs = json.loads(STRESS_BYTES[0])["conversations"]; c = next(x for x in convs if x["case_id"] == "SYN-S11")
        c["action_events"] = [{"record_id": "SYN-S11-ev-1", "type": "refund_issue", "status": "issued", "amount_usd": 48, "for_reply": "m03"}]
        b = json.dumps({"conversations": convs}, sort_keys=True).encode(); (t / "stress2.json").write_bytes(b); return b, c
    def issued_case(name, want_text):
        tmp = pathlib.Path(tempfile.mkdtemp()); Sc, L, SL, P, A = copy.deepcopy(base); b, c = issued_only(tmp)
        next(r for r in Sc["datasets"]["stress"]["results"] if r["conversation_id"] == "SYN-S11")["conversation_sha256"] = run5.conv_sha(c)
        Sc["datasets"]["stress"]["cases_sha256"] = sha(b); h = write_all(tmp, Sc, L, SL, P, A, {"stress_conversations": "stress2.json"})
        r = ev(tmp, h); R.append({"test": name, "pass": r.returncode == 2 and want_text in r.stdout and not (tmp / "e.json").exists(), "detail": r.stdout[-600:]})
    issued_case("a refund control with an issued-only record (no approval, no schedule) fails stress coverage", "approved refund and a live dated schedule")
    def swapped(Sc, L, SL, P, A):  # tester's L3 probe: the scored S11 result comes from an issued-only conversation, the frozen file is unchanged
        cid = "SYN-S11"; span = "I've issued your $48 refund."
        conv = mk(cid, T0, [("c", "Where is my refund?"), ("a", span)], events=[("m03", "refund_issue", {"status": "issued", "amount_usd": 48, "issued_on": "2026-11-20", "destination": "original_card"})])
        rs = Sc["datasets"]["stress"]["results"]; i = next(n for n, r in enumerate(rs) if r["conversation_id"] == cid)
        rs[i] = S(conv, X([C("m03", span, "completed_action", action="refund_issued", amount=48)], [("m02", "question")], cid=cid))
    case("a stress result scored from a conversation other than the frozen one is refused (tester probe)", swapped, 2, "not scored from the frozen conversation")
    case("a stress result with no conversation hash is refused", lambda Sc, L, SL, P, A: Sc["datasets"]["stress"]["results"][0].pop("conversation_sha256"), 2, "not scored from the frozen conversation")
    case("stress conversations that do not match the scores file's hash are refused", None, 2, "does not match the scores file's stress cases_sha256", ev_over=lambda t: ((t / "other.json").write_text('{"conversations": []}'), {"stress_conversations": "other.json"})[1])
    case("missing stress conversations are refused", None, 2, "stress conversations not supplied", ev_over=lambda t: {"stress_conversations": None})
    case("a pre-blind run with the same lock ID but a different lock hash makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: P.update(lock_sha256="0" * 64), 1, "INCOMPLETE")
    case("a pre-blind run with no lock hash makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: P.pop("lock_sha256"), 1, "INCOMPLETE")
    case("a pre-blind run whose stored gate does not match its records makes the decision INCOMPLETE", lambda Sc, L, SL, P, A: P["datasets"]["holdout"]["results"][0]["needs"]["handoff_required"].__setitem__(1, not P["datasets"]["holdout"]["results"][0]["needs"]["handoff_required"][1]), 1, "INCOMPLETE")
    def missing_judge(Sc, L, SL, P, A):
        r = Sc["datasets"]["holdout"]["results"][20]; r["judge_record"]["pass_2"] = None
        for k in ("c4", "c6"): r["verdicts"][k] = "referred"
    case("a blind case missing its second judge reply is refused as an incomplete run", missing_judge, 2, "incomplete run")
    case("a blind case with no traceable selected reply is refused as an incomplete run", lambda Sc, L, SL, P, A: Sc["selected_responses"].pop(next(iter(Sc["selected_responses"]))), 2, "incomplete run")
    # the tester's probe of 13 Nov 2026: numeric counts met, required content absent
    tmp = pathlib.Path(tempfile.mkdtemp()); hold = []; labels = []; stress = []; slabels = []
    for i in range(50):
        v = {f"c{k}": "pass" for k in range(1, 7)}
        if i < 6: v["c2"] = "fail"
        for idx, ck in ((6, "c1"), (7, "c3"), (8, "c4"), (9, "c5")):
            if i == idx: v[ck] = "fail"
        hold.append({"conversation_id": f"EV-H{i:02}", "verdicts": v, "evidence": {k: {"reason": "mock"} for k in v}, "disposition": {"fails": [k for k, x in v.items() if x == "fail"], "referred": [], "kb_conflict": []}, "extractor_record": {"present": True}, "route": "R-statement"})
        labels.append({"case_id": f"EV-H{i:02}", "labels": {k: "problem" if x == "fail" else "ok" for k, x in v.items()}, "escalation_control": i >= 45})
    for i in range(12):
        v = {f"c{k}": "pass" for k in range(1, 7)}
        if i < 6: v["c1"] = "fail"
        stress.append({"conversation_id": f"EV-S{i:02}", "verdicts": v, "disposition": {"fails": ["c1"] if i < 6 else [], "referred": [], "kb_conflict": []}})
        slabels.append({"case_id": f"EV-S{i:02}", "labels": {k: "problem" if x == "fail" else "ok" for k, x in v.items()}})
    Sp = {"run_id": "REVIEW-INVALID", "lock_id": "NO-LOCK-EVIDENCE", "blind": True, "selection_problems": [], "unscorable": [], "datasets": {"holdout": {"case_ids": [c["case_id"] for c in labels], "results": hold}, "stress": {"case_ids": [c["case_id"] for c in slabels], "results": stress}},
          "fixtures": {"run5": [], "store_and_timing": [], "replay_tests": []}, "consistency": {"claim_part_agreement": 0, "handoff_decision_agreement": 0}}
    sb = json.dumps(Sp).encode(); (tmp / "scores.json").write_bytes(sb); (tmp / "labels.json").write_text(json.dumps({"cases": labels})); (tmp / "manifest.json").write_text(json.dumps({"cases": slabels})); (tmp / "evidence.json").write_text("{}")
    r = ev(tmp, sha(sb)); R.append({"test": "the tester's incomplete evaluation probe of 13 Nov 2026 is refused, not PASS", "pass": r.returncode == 2 and "PHASE 0 PASS" not in r.stdout, "detail": r.stdout[:600]})
    return R

if __name__ == "__main__":
    res = run_all(); json.dump(res, open("test_evaluate5_results.json", "w"), indent=1)
    for x in res: print("PASS" if x["pass"] else "FAIL", x["test"]) if (not x["pass"] or "-v" in sys.argv) else None
    print(f"{sum(x['pass'] for x in res)}/{len(res)} pass")
    if not all(x["pass"] for x in res): print(next(x["detail"] for x in res if not x["pass"]))
