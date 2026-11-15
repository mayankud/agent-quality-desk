"""Phase 0 Run 5 runner (PRD v8 revision 4).
  python3 run5.py lock LOCK_ID                                        lock code, wrapper, launcher, prompts, schemas and rules
  python3 run5.py prepare RUN_DIR extract|judge PASS ATTEMPT CASES [BATCH_IDS]   write agent requests (judge needs extraction selected first)
  python3 run5.py collect RUN_DIR                                     store agent replies from the outbox
  python3 run5.py score RUN_DIR OUT HOLDOUT[,STRESS] [--blind]         select replies, verify claims, combine, run fixtures, write scores (no model call)
  python3 evaluate5.py SCORES SHARED_SHA LABELS STRESS_MANIFEST OUT    Phase 0 evaluation, after the labels are released
  python3 run5.py consistency SCORES                                  pass-to-pass agreement, as defined before the lock
Replay = score on a bundle: same stored requests and replies give the same scores file, byte for byte."""
import json, sys, pathlib, hashlib, datetime as dt
import harness as H, desk7
ROOT = pathlib.Path(__file__).resolve().parent
CODE = ["desk7.py", "rules6.py", "qa_store.py", "harness.py", "agents.py", "run5.py", "evaluate5.py", "audit.py", "fixtures7.py", "fixtures_store.py", "fixture_builder.py", "test_harness.py", "test_evaluate5.py", "test_e2e.py", "fixtures_inventory.json", "kb_index.json", "launcher.txt"]
SAMP = {"seed": "phase0-seed-2026-11-11", "rate_pct": 10}
RULES = {
 "selection": "Per batch, attempts in order, at most 2. First reply that parses, matches the schema, binds to its request (hash, task, lock, pass, attempt, locked components), was received after the lock and covers exactly the batch's case IDs. Otherwise every case in the batch is 'model output invalid' for that pass.",
 "retry": "An attempt is retried once, with a fresh agent and the same batch, when its reply is missing, does not parse, fails the schema or does not cover the batch. The retry request differs only in its attempt number.",
 "batch_order": "Cases sorted by sha256(lock ID | task | pass | case ID), cut into batches of 5. Each pass has its own order.",
 "claims": "Union of both passes. Parts are matched one to one when message ID and part type are equal and the normalised spans overlap by at least half of the shorter span's words, or one contains the other. Every part, matched or not, is verified by code. The code cross-check adds sentences with amounts, dates, menu paths or action verbs that no model part covers.",
 "check1": "fail if any part fails, else kb_conflict, else referred, else pass. A model pass with invalid output turns a pass into referred.",
 "check2": "Handoff required = explicit request for a person, billing dispute, duplicate or unrecognised charge, legal threat, safety issue, or two or more failed attempts. If the passes disagree on required, referred. If required: no handoff event fails, billing dispute outside the billing queue fails unless a legal threat or safety issue is also present, empty context fails. A failed attempt is one distinct step the customer tried, a retry of the same step is not a second attempt. If both judge passes say the context misses the need, fail. If they disagree, referred.",
 "check3": "Masked card data in an assistant message fails (code). A sensitive-data request flagged by both passes fails. Flagged by one pass, fails if the code check also flags it, otherwise referred.",
 "check4_6": "Both judge passes agree: that verdict. Disagree: referred. Missing: referred (model output invalid).",
 "visibility": "Disposition lists every failed, referred and KB-conflict check. A failed check stays visible when another check of the same case is referred.",
 "agreement": "Claim parts: sum of matched parts divided by sum of (pass 1 parts + pass 2 parts - matched) over cases where at least one pass has parts. Cases where both passes list no parts are counted and reported, not in the ratio. Triggers: share of cases where both passes reach the same handoff-required decision (the gated figure). Per-trigger agreement is reported, not gated. Sensitive-data, resolution and tone agreement reported.",
 "consistency_gate": "Regression set, two passes: claim-part agreement at or above 0.90 and handoff-decision agreement at or above 0.95. A failed check needs a new lock before fresh conversations are shared.",
}
def sha(b): return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()
def conv_sha(c): return sha(json.dumps(c, sort_keys=True, ensure_ascii=False))
def now(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def lock(lock_id):
    rec = {"lock_id": lock_id, "locked_at_utc": now(), "model_id": H.MODEL_ID,
           "model_note": "Identifier reported by the session. Snapshot, build date and sampling settings (temperature, seed) are not exposed to agents or the coordinator and cannot be set.",
           "components": H.component_hashes(), "code": {f: sha((ROOT / f).read_bytes()) for f in CODE},
           "rubric": {f: sha((ROOT / "rubric" / f).read_bytes()) for f in sorted(p.name for p in (ROOT / "rubric").glob("*"))},
           "batch_size": H.BATCH_SIZE, "passes": list(H.PASSES), "max_attempts": H.MAX_ATTEMPTS, "rules": RULES, "sampling": SAMP}
    (ROOT / f"lock_{lock_id}.json").write_text(json.dumps(rec, indent=1, sort_keys=True)); print(lock_id, rec["locked_at_utc"], sha((ROOT / f"lock_{lock_id}.json").read_bytes()))

def load_lock(run_dir):
    p = pathlib.Path(run_dir) / "lock.json"; return json.loads(p.read_text())

def check_lock(lk):
    files = {**lk["components"], **lk["code"], **{"rubric/" + f: h for f, h in lk["rubric"].items()}}
    bad = [f for f, h in files.items() if not (ROOT / f).exists() or sha((ROOT / f).read_bytes()) != h]
    extra = sorted(str(x.relative_to(ROOT)) for x in (ROOT / "rubric").glob("*") if x.is_file() and x.name not in lk["rubric"])
    if extra: bad += [f"unlocked rubric file {x}" for x in extra]
    if bad: sys.exit(f"LOCK BROKEN: {bad}")

def cases(paths):
    out = {}
    for path in str(paths).split(","):
        for c in json.load(open(path))["conversations"]:
            if c["case_id"] in out: sys.exit(f"duplicate case ID {c['case_id']}")
            out[c["case_id"]] = c
    return out
KB = None
def kb():
    global KB
    if KB is None: KB = desk7.KB2(json.load(open(ROOT / "kb_index.json")))
    return KB

def stage_results(run_dir, convs, lk, with_judge):
    """Selects replies against the exact scoring input: extraction first, then the judge, whose requests carried extras computed
    from the extraction results, so the judge requests are re-rendered from those same extras."""
    red = {cid: desk7.R.redact(c) for cid, c in convs.items()}
    st = H.Store(run_dir); ex, pr_e, sel_e = H.select(st, lk, "extract", red); jd, pr_j, sel_j = ({}, [], {})
    res = {cid: desk7.combine(c, kb(), {p: ex.get(p, {}).get(cid) for p in H.PASSES}, None, SAMP) for cid, c in sorted(convs.items())}
    if with_judge:
        extras = {cid: desk7.judge_extras(r, convs[cid]) for cid, r in res.items()}
        jd, pr_j, sel_j = H.select(st, lk, "judge", red, extras)
        res = {cid: desk7.combine(c, kb(), {p: ex.get(p, {}).get(cid) for p in H.PASSES}, {p: jd.get(p, {}).get(cid) for p in H.PASSES}, SAMP) for cid, c in sorted(convs.items())}
        for cid in res: res[cid]["judge_record"] = {f"pass_{p}": jd.get(p, {}).get(cid) for p in H.PASSES}
    return res, pr_e + pr_j, {**sel_e, **sel_j}, st

def prepare(run_dir, task, pass_no, attempt, cases_path, only=None):
    import agents
    lk = load_lock(run_dir); check_lock(lk); convs = cases(cases_path)
    extras = None
    if task == "judge":
        res, _, _, _ = stage_results(run_dir, convs, lk, False)  # extras from the selected extraction replies
        extras = {cid: desk7.judge_extras(r, convs[cid]) for cid, r in res.items()}
        ep = pathlib.Path(run_dir) / "judge_extras.json"; ep.write_text(json.dumps(extras, indent=1, sort_keys=True))
    rd = pathlib.Path(run_dir); tmp = rd / "_cases_redacted.json"
    tmp.write_text(json.dumps({"conversations": [desk7.R.redact(c) for c in convs.values()]}))
    agents.prepare(run_dir, str(rd / "lock.json"), task, pass_no, attempt, str(tmp), str(rd / "judge_extras.json") if extras else None, only)

def score(run_dir, out, cases_paths, blind=False):
    lk = load_lock(run_dir); check_lock(lk); paths = str(cases_paths).split(",")
    sets = {name: cases(p) for name, p in zip(("holdout", "stress"), paths)}; allc = {k: v for d in sets.values() for k, v in d.items()}
    unscorable = []
    try: res, problems, sel, st = stage_results(run_dir, allc, lk, True)
    except Exception as e: sys.exit(f"SCORING STOPPED: {type(e).__name__}: {e}")
    for k in res: res[k]["conversation_sha256"] = conv_sha(allc[k])
    used = {}
    for k, rs in sorted(sel.items()):
        f = st.d / "responses" / f"{rs}.json"; used[k] = {"request_sha256": rs, "response_file_sha256": sha(f.read_bytes()), "received_at_utc": json.loads(f.read_text())["received_at_utc"], "case_ids": st.index["entries"][k]["case_ids"]}
    if blind:
        early = [k for k, u in used.items() if u["received_at_utc"] < lk["locked_at_utc"]]
        if early: problems.append(f"blind run used replies received before the lock: {early}")
    import fixtures7, fixtures_store, test_harness
    fx = fixtures7.run_all(); fs = fixtures_store.run_all(); th = test_harness.run_all()
    body = {"run_id": f"P0-R5-{sha(json.dumps(lk, sort_keys=True) + ''.join(sha(open(p, 'rb').read()) for p in paths))[:8]}", "lock_id": lk["lock_id"],
            "lock_sha256": sha((pathlib.Path(run_dir) / "lock.json").read_bytes()), "blind": blind, "model_id": lk["model_id"], "pipeline_version": desk7.PIPELINE_VERSION,
            "datasets": {name: {"cases_sha256": sha(open(p, "rb").read()), "case_ids": sorted(sets[name]), "results": [res[k] for k in sorted(sets[name]) if k in res]} for name, p in zip(sets, paths)},
            "unscorable": unscorable, "selected_responses": used, "selection_problems": problems, "attempt_history": {t: st.history.get(t, []) for t in ("extract", "judge")},
            "fixtures": {"run5": [{k: x[k] for k in ("id", "test", "pass")} for x in fx], "store_and_timing": [{k: x[k] for k in ("id", "test", "pass")} for x in fs],
                         "replay_tests": [{k: x[k] for k in ("test", "pass")} for x in th]},
            "consistency": consistency({k: v for k, v in res.items()})}
    b = json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False).encode("utf-8"); pathlib.Path(out).write_bytes(b)
    print(body["run_id"], "scores sha256", sha(b), "cases", len(res), "unscorable", len(unscorable), "problems", len(problems))

def consistency(res):
    """Two-pass agreement on actual paired valid replies. Each figure carries its numerator and denominator, and is "unavailable" when
    there is no valid pair. A case counts in a statistic only when both passes produced a valid reply for that task."""
    def stat(k, n): return {"agree": k, "pairs": n, "rate": round(k / n, 4) if n else "unavailable"}
    m = tot = both_empty = 0; ex_pairs = 0; ex_invalid = []; dec = [0, 0]; trig = {}; sens = [0, 0]; jstats = {"resolution": [0, 0], "tone": [0, 0], "handoff_context": [0, 0]}; jd_invalid = []
    for cid, r in sorted(res.items()):
        e = r["extractor_record"]
        if e["invalid_passes"]: ex_invalid.append(cid)
        else:
            ex_pairs += 1; a, b = len(e["model_pass_1"]), len(e["model_pass_2"])
            if a + b == 0: both_empty += 1
            else: m += e["matched"]; tot += a + b - e["matched"]
            h = r["needs"]["handoff_required"]; dec[0] += h[0] == h[1]; dec[1] += 1
            for kind in ("explicit_request_for_person", "billing_dispute", "duplicate_or_unrecognised_charge", "legal_threat", "safety_issue", "failed_attempt"):
                x = sum(1 for n in r["needs"]["pass_1"] if n["need"] == kind); y = sum(1 for n in r["needs"]["pass_2"] if n["need"] == kind)
                t = trig.setdefault(kind, [0, 0]); t[0] += (min(x, 1) == min(y, 1)) if kind != "failed_attempt" else ((x >= 2) == (y >= 2)); t[1] += 1
            s1 = {(x["message_id"], x["data_type"]) for x in r["sensitive"]["pass_1"]}; s2 = {(x["message_id"], x["data_type"]) for x in r["sensitive"]["pass_2"]}
            sens[0] += s1 == s2; sens[1] += 1
        j = r.get("judge_record") or {}
        if not (j.get("pass_1") and j.get("pass_2")): jd_invalid.append(cid); continue
        for k in ("resolution", "tone"):
            jstats[k][0] += j["pass_1"][k]["value"] == j["pass_2"][k]["value"]; jstats[k][1] += 1
        jstats["handoff_context"][0] += j["pass_1"]["handoff_context"] == j["pass_2"]["handoff_context"]; jstats["handoff_context"][1] += 1
    claim = stat(m, tot); hand = stat(*dec)
    gate_ok = (not ex_invalid and not jd_invalid and isinstance(claim["rate"], float) and claim["rate"] >= 0.90 and isinstance(hand["rate"], float) and hand["rate"] >= 0.95)
    return {"cases": len(res), "extraction_valid_pairs": ex_pairs, "extraction_invalid_cases": ex_invalid, "judge_valid_pairs": len(res) - len(jd_invalid), "judge_invalid_cases": jd_invalid,
            "claim_parts": {**claim, "union": tot, "matched": m}, "cases_both_passes_empty": both_empty,
            "handoff_decision": hand, "per_trigger": {k: stat(*v) for k, v in trig.items()}, "sensitive_requests_raw": stat(*sens),
            "judge": {k: stat(*v) for k, v in jstats.items()},
            "gate": {"claim_parts_min": 0.90, "handoff_decision_min": 0.95, "requires_every_case_valid_in_both_passes_for_both_tasks": True, "pass": gate_ok}}

if __name__ == "__main__":
    a = sys.argv
    if a[1] == "lock": lock(a[2])
    elif a[1] == "prepare": prepare(a[2], a[3], int(a[4]), int(a[5]), a[6], set(a[7].split(",")) if len(a) > 7 else None)
    elif a[1] == "collect":
        import agents; agents.collect(a[2])
    elif a[1] == "score": score(a[2], a[3], a[4], "--blind" in a)
    elif a[1] == "consistency": print(json.dumps(json.load(open(a[2]))["consistency"], indent=1))
