"""Phase 0 evaluator for Run 5 (PRD v8 revision 4, section 7). Runs only after the blind scores file and its SHA-256 were shared and the labels released.
  python3 evaluate5.py SCORES SHARED_SHA256 HOLDOUT_LABELS STRESS_MANIFEST EVIDENCE OUT
Exit 0 = Phase 0 PASS, 1 = metrics calculated but the decision is FAIL or INCOMPLETE, 2 = input refused before any calculation.

Refused (exit 2, nothing calculated): scores file not matching the shared hash, scores file failing its structure check, not blind,
unresolved selection problems, label or manifest problems (missing, duplicate or unknown case IDs, missing checks, invalid label values,
unknown stress kinds), or coverage below the frozen minimums.
Calculated but not a pass (exit 1): any metric line failing, or any evidence line failing or missing. Metrics and evidence are reported apart.

EVIDENCE is a JSON file, paths relative to it:
  {"lock": "lock.json", "stress_conversations": "stress_v4_conversations.json",
   "preblind_consistency": {"scores": "consistency_scores.json", "sha256": "..."},
   "audits": ["audit_extract.json", ...], "replay": {"scores_sha256": "..."}}
The stress conversations must hash to the scores file's stress cases_sha256. Suite coverage (the approved and scheduled refund control)
is read from those conversations, never from the scorer's explanations.
Holdout labels: {"cases": [{"case_id", "labels": {"c1".."c6": {"final": ok|problem|referred|kb_conflict, "referral_reason"?}}, "escalation_control"?: true}]}
Stress manifest: {"cases": [{"case_id", "kind": invented|implied_promise|regression|clean_billing, "regression_of"?: "A12"|"ST-05", "labels": {...}}]}"""
import json, math, sys, hashlib, pathlib
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
LV = {"ok": "no_defect", "problem": "defect", "referred": "referred", "kb_conflict": "kb_conflict"}
CH = ["c1", "c2", "c3", "c4", "c5", "c6"]
RECALL = {"c1": 0.90, "c2": 0.90, "c3": 1.0, "c4": 0.75, "c5": 1.0}
STRESS_KINDS = {"invented": "harmful", "implied_promise": "harmful", "regression": "harmful", "clean_billing": "clean"}
COVER = {"holdout_min": 50, "escalation_controls_min": 5, "escalation_defects_min": 6, "stress_min": 12, "stress_new_harmful_min": 6, "stress_clean_min": 4}
REQUIRED_REGRESSIONS = {"A12", "ST-05"}
import run5  # the locked consistency calculation, used to recompute the pre-blind evidence from its records
RESULT_KEYS = {"conversation_id", "verdicts", "evidence", "disposition", "extractor_record", "claim_verdicts", "route", "judge_record", "needs"}
need = lambda share, n: math.ceil(round(share * n, 9))
sha = lambda b: hashlib.sha256(b).hexdigest()

def wilson(k, n, z=1.96):
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]

def kappa(pairs):
    n = len(pairs)
    if not n: return None
    po = sum(a == b for a, b in pairs) / n; pa = sum(a for a, _ in pairs) / n; pb = sum(b for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None

def final(v): return v["final"] if isinstance(v, dict) else v

def scores_structure(S):
    err = []
    for k in ("run_id", "lock_id", "lock_sha256", "blind", "datasets", "selection_problems", "unscorable", "fixtures", "consistency", "selected_responses"):
        if k not in S: err.append(f"scores file: missing {k}")
    if err: return err
    for ds in ("holdout", "stress"):
        d = S["datasets"].get(ds)
        if not isinstance(d, dict) or not isinstance(d.get("results"), list) or not isinstance(d.get("case_ids"), list): err.append(f"scores file: dataset {ds} missing or malformed"); continue
        ids = [r.get("conversation_id") for r in d["results"]]
        if sorted(ids) != sorted(d["case_ids"]): err.append(f"scores file: {ds} results do not cover exactly its case IDs")
        for r in d["results"]:
            miss = RESULT_KEYS - set(r)
            if miss: err.append(f"scores file: {r.get('conversation_id')} missing {sorted(miss)}"); break
            if set(r["verdicts"]) != set(CH): err.append(f"scores file: {r['conversation_id']} does not carry all six checks"); break
    inv = json.loads((HERE / "fixtures_inventory.json").read_text())
    for part in ("run5", "store_and_timing", "replay_tests"):
        got = [x.get("id", x.get("test")) for x in S["fixtures"].get(part, [])]
        if sorted(got) != sorted(inv[part]): err.append(f"scores file: {part} fixtures are not exactly the frozen inventory ({len(got)} of {len(inv[part])}, missing {sorted(set(inv[part]) - set(got))[:6]}, unknown {sorted(set(got) - set(inv[part]))[:6]})")
    return err

def completeness(S):
    """A blind run is complete only when every case has a valid reply from both passes of both tasks, each traceable to one selected reply."""
    err = []; cover = {}
    for k, u in S["selected_responses"].items():
        task, p = k.split("|")[0], k.split("|")[1]
        for c in u.get("case_ids") or []: cover.setdefault((task, p, c), []).append(k)
    for ds in ("holdout", "stress"):
        for r in S["datasets"][ds]["results"]:
            cid = r["conversation_id"]
            for task in ("extract", "judge"):
                for p in ("1", "2"):
                    n = len(cover.get((task, p, cid), []))
                    if n != 1: err.append(f"incomplete run: {cid} has {n} selected {task} replies for pass {p} (needs exactly 1)")
            if r["extractor_record"].get("invalid_passes"): err.append(f"incomplete run: {cid} extraction pass {r['extractor_record']['invalid_passes']} has no valid reply")
            jr = r.get("judge_record") or {}
            if not (jr.get("pass_1") and jr.get("pass_2")): err.append(f"incomplete run: {cid} judge pass {[p for p in (1, 2) if not jr.get(f'pass_{p}')]} has no valid reply")
    return err

def refund_control(conv):
    """True when the conversation carries an approved refund and a live, dated schedule for the same amount with a destination, linked to that approval."""
    ev = conv.get("action_events", [])
    appr = [e for e in ev if e.get("type") == "refund_approval" and e.get("status") == "approved" and isinstance(e.get("amount_usd"), (int, float))]
    for e in ev:
        if e.get("type") == "refund_schedule" and e.get("status") == "scheduled" and e.get("issue_date") and e.get("destination"):
            if any(a["amount_usd"] == e.get("amount_usd") and (not e.get("approval_id") or e["approval_id"] == a.get("record_id")) for a in appr): return True
    return False

def validate(S, sbytes, shared, L, SL):
    err = []
    if sha(sbytes) != shared.strip().lower(): err.append(f"scores file SHA-256 {sha(sbytes)} does not match the shared hash {shared}")
    err += scores_structure(S)
    if err: return err
    err += completeness(S)
    if S.get("blind") is not True: err.append("scores file was not produced with --blind")
    if S.get("selection_problems"): err.append(f"scores file lists {len(S['selection_problems'])} unresolved selection problems")
    for name, lab, ds in (("holdout labels", L, "holdout"), ("stress manifest", SL, "stress")):
        ids = [c.get("case_id") for c in lab.get("cases", [])]; want = set(S["datasets"][ds]["case_ids"])
        dup = [k for k, n in Counter(ids).items() if n > 1]; miss = sorted(want - set(ids)); extra = sorted(set(ids) - want)
        if dup: err.append(f"{name}: duplicate case IDs {dup}")
        if miss: err.append(f"{name}: no labels for {miss}")
        if extra: err.append(f"{name}: labels for unknown cases {extra}")
        for c in lab.get("cases", []):
            labs = c.get("labels", {})
            for ck in CH:
                if ck not in labs: err.append(f"{name}: {c.get('case_id')} missing {ck}")
                elif final(labs[ck]) not in LV: err.append(f"{name}: {c.get('case_id')} {ck} invalid label {final(labs[ck])!r}")
            if ds == "stress":
                if c.get("kind") not in STRESS_KINDS: err.append(f"stress manifest: {c.get('case_id')} has no valid kind ({c.get('kind')!r})")
                if c.get("kind") == "regression" and c.get("regression_of") not in REQUIRED_REGRESSIONS: err.append(f"stress manifest: {c.get('case_id')} regression without A12 or ST-05 tag")
    return err

def stress_conversations(S, epath):
    """Returns ({case_id: conversation}, problems). Bound to the scores file by hash."""
    if not epath or not pathlib.Path(epath).exists(): return {}, ["evidence file missing, stress conversations not supplied"]
    base = pathlib.Path(epath).resolve().parent; E = json.loads(pathlib.Path(epath).read_text())
    if not E.get("stress_conversations") or not (base / E["stress_conversations"]).is_file(): return {}, ["stress conversations not supplied in the evidence file"]
    b = (base / E["stress_conversations"]).read_bytes(); want = S["datasets"]["stress"].get("cases_sha256")
    if sha(b) != want: return {}, [f"stress conversations SHA-256 {sha(b)[:16]} does not match the scores file's stress cases_sha256 {str(want)[:16]}"]
    return {c["case_id"]: c for c in json.loads(b)["conversations"]}, []

def evidence_lines(S, sbytes, epath):
    """Each line: (name, pass, value). Missing evidence is a failing line, never a pass."""
    out = []
    if not epath or not pathlib.Path(epath).exists(): return [("Evidence file present", False, "missing")]
    base = pathlib.Path(epath).resolve().parent; E = json.loads(pathlib.Path(epath).read_text())
    lk_path = base / E.get("lock", "") if E.get("lock") else None
    lb = b""
    if lk_path and lk_path.is_file():
        lb = lk_path.read_bytes()
        try: lk = json.loads(lb)
        except ValueError: lk = {}
        match = sha(lb) == S["lock_sha256"] and lk.get("lock_id") == S["lock_id"] and bool(lk.get("locked_at_utc"))
        out.append(("Lock: file matches the lock hash and ID in the scores file", match, f"{lk.get('lock_id')} {sha(lb)[:16]}"))
        if match:
            early = [k for k, u in S["selected_responses"].items() if u["received_at_utc"] < lk["locked_at_utc"]]
            out.append(("Lock: every selected reply received after the lock", not early and bool(S["selected_responses"]), f"{len(S['selected_responses'])} replies, {len(early)} early"))
        else: out.append(("Lock: every selected reply received after the lock", False, "not checkable without the matching lock"))
    else: lk = None; out.append(("Lock: file supplied", False, "missing"))
    pc = E.get("preblind_consistency") or {}; pp = base / pc["scores"] if pc.get("scores") else None
    if pp and pp.is_file():
        pb = pp.read_bytes(); P = json.loads(pb); why = []
        if sha(pb) != pc.get("sha256"): why.append("file does not match its stated SHA-256")
        lock_hashes = {"pre-blind": P.get("lock_sha256"), "blind scores": S["lock_sha256"], "lock file": sha(lb) if lk_path and lk_path.is_file() else None}
        if len(set(lock_hashes.values())) != 1 or None in lock_hashes.values(): why.append(f"lock fingerprints differ or are missing {lock_hashes}")
        if P.get("lock_id") != S["lock_id"]: why.append("lock ID differs")
        if P.get("blind") is not False: why.append("not a pre-blind run")
        if P.get("selection_problems"): why.append(f"{len(P['selection_problems'])} unresolved selection problems")
        try:
            recs = {r["conversation_id"]: r for r in P["datasets"]["holdout"]["results"]}
            if sorted(recs) != sorted(P["datasets"]["holdout"]["case_ids"]) or not recs: why.append("records do not cover the case list")
            again = run5.consistency(recs)
            if again != P.get("consistency"): why.append("stored consistency differs from the consistency recomputed from its records")
            if not (again["extraction_valid_pairs"] == again["judge_valid_pairs"] == again["cases"] == len(recs)): why.append("not every case has a valid pair for both tasks")
            if again["gate"]["pass"] is not True: why.append(f"recomputed gate fails (claim parts {again['claim_parts']['rate']}, handoff {again['handoff_decision']['rate']})")
            val = f"claim parts {again['claim_parts']['agree']} of {again['claim_parts']['pairs']}, handoff {again['handoff_decision']['agree']} of {again['handoff_decision']['pairs']}, valid pairs {again['extraction_valid_pairs']}/{again['judge_valid_pairs']} of {again['cases']}"
        except Exception as ex: why.append(f"records unreadable ({type(ex).__name__})"); val = ""
        out.append(("Pre-blind two-pass consistency: same lock fingerprint, records valid, recomputed gate passes", not why, (val + " " + "; ".join(why)).replace(";", ",").strip()))
    else: out.append(("Pre-blind two-pass consistency supplied", False, "missing"))
    auds = [base / a for a in E.get("audits", [])]
    if auds and all(a.is_file() for a in auds):
        A = [json.loads(a.read_text()) for a in auds]
        clean = all(a.get("verdict") == "clean" and a.get("watcher_covered_window") is True for a in A)
        times = [u["received_at_utc"] for u in S["selected_responses"].values()]
        unc = [t for t in times if not any(a["window"][0] <= t <= a["window"][1] for a in A)]
        out.append(("Isolation audit: every window clean and fully watched, every selected reply inside an audited window", clean and not unc and bool(times),
                    f"{len(A)} windows, {sum(1 for a in A if a.get('verdict') == 'clean' and a.get('watcher_covered_window'))} clean and covered, {len(unc)} replies outside a window"))
    else: out.append(("Isolation audit reports supplied", False, "missing"))
    rp = (E.get("replay") or {}).get("scores_sha256")
    out.append(("Replay from the saved replies reproduces the scores file", rp == sha(sbytes), rp or "missing"))
    return out

def evaluate(spath, shared, lpath, slpath, epath, out):
    sbytes = pathlib.Path(spath).read_bytes(); S = json.loads(sbytes); L = json.load(open(lpath)); SL = json.load(open(slpath))
    err = validate(S, sbytes, shared, L, SL)
    if err:
        print("EVALUATION REFUSED, nothing calculated"); [print(" -", e) for e in err]; sys.exit(2)
    M = {c["case_id"]: {k: LV[final(v)] for k, v in c["labels"].items()} for c in L["cases"]}
    RR = {c["case_id"]: {k: v.get("referral_reason") for k, v in c["labels"].items() if isinstance(v, dict) and v.get("referral_reason")} for c in L["cases"]}
    CTRL = sorted(c["case_id"] for c in L["cases"] if c.get("escalation_control"))
    KIND = {c["case_id"]: c["kind"] for c in SL["cases"]}; REG = {c["case_id"]: c.get("regression_of") for c in SL["cases"] if c["kind"] == "regression"}
    by = {r["conversation_id"]: r for r in S["datasets"]["holdout"]["results"]}; sby = {r["conversation_id"]: r for r in S["datasets"]["stress"]["results"]}
    verdict = lambda k, c: by[k]["verdicts"][c] if k in by else "unscorable"
    harmful = sorted(k for k in KIND if STRESS_KINDS[KIND[k]] == "harmful"); clean = sorted(k for k in KIND if STRESS_KINDS[KIND[k]] == "clean")
    new_harmful = [k for k in harmful if KIND[k] != "regression"]
    SC, sc_err = stress_conversations(S, epath)
    if sc_err:
        print("EVALUATION REFUSED, stress coverage cannot be established"); [print(" -", e) for e in sc_err]; sys.exit(2)
    bind = []
    for k, r in sby.items():
        if k not in SC: bind.append(f"stress result {k} has no frozen conversation")
        elif r.get("conversation_sha256") != run5.conv_sha(SC[k]): bind.append(f"stress result {k} was not scored from the frozen conversation (conversation SHA-256 {str(r.get('conversation_sha256'))[:16]} vs frozen {run5.conv_sha(SC[k])[:16]})")
    bind += [f"frozen stress conversation {k} has no scored result" for k in sorted(set(SC) - set(sby))]
    if bind:
        print("EVALUATION REFUSED, stress results are not bound to the frozen conversations"); [print(" -", e) for e in bind]; sys.exit(2)
    refund_ev = [k for k in clean if k in SC and refund_control(SC[k])]
    cov = {"holdout cases": (len(M), COVER["holdout_min"]), "escalation controls": (len(CTRL), COVER["escalation_controls_min"]),
           "escalation defects": (sum(1 for k in M if M[k]["c2"] == "defect"), COVER["escalation_defects_min"]), "stress cases": (len(KIND), COVER["stress_min"]),
           "stress regressions A12 and ST-05": (len(REQUIRED_REGRESSIONS & set(REG.values())), len(REQUIRED_REGRESSIONS)),
           "new stress invented-policy or implied-promise cases": (len(new_harmful), COVER["stress_new_harmful_min"]), "stress clean billing replies": (len(clean), COVER["stress_clean_min"]),
           "clean billing replies whose conversation carries an approved refund and a live dated schedule": (len(refund_ev), 1),
           "all-ok holdout cases": (sum(1 for k in M if all(v == "no_defect" for v in M[k].values())), 1)}
    cov.update({f"labelled {c} defects": (sum(1 for k in M if M[k][c] == "defect"), 1) for c in RECALL})
    gaps = [f"{k}: {n} (minimum {m})" for k, (n, m) in cov.items() if n < m]
    if gaps:
        print("EVALUATION REFUSED, coverage below the frozen minimums"); [print(" -", g) for g in gaps]; sys.exit(2)
    lines, per = [], {}
    for c in CH:
        cs = sorted(k for k in M if M[k][c] == "defect"); det = [k for k in cs if verdict(k, c) == "fail"]
        per[c] = {"n": len(cs), "detected": len(det), "interval95": wilson(len(det), len(cs)), "missed": {k: [verdict(k, c), by[k]["evidence"][c].get("reason") if k in by else None] for k in cs if k not in det}}
        if c in RECALL: n = need(RECALL[c], len(cs)); lines.append((f"{c} detected recall at least {round(RECALL[c] * 100)}% ({n} of {len(cs)})", len(det) >= n, f"{len(det)}/{len(cs)}"))
        else: lines.append((f"{c} reported, no gate", None, f"{len(det)}/{len(cs)}"))
    fa = {k: verdict(k, "c2") for k in CTRL if verdict(k, "c2") != "pass"}
    lines.append((f"Escalation false alarms: at most 1 check 2 fail on {len(CTRL)} controls", sum(1 for v in fa.values() if v == "fail") <= 1,
                  f"{sum(1 for v in fa.values() if v == 'fail')} fail, {sum(1 for v in fa.values() if v == 'referred')} referred {fa or ''}"))
    nod = sorted(k for k in M if all(v == "no_defect" for v in M[k].values()))
    ff = {k: [c for c in ("c1", "c2", "c3") if verdict(k, c) == "fail"] for k in nod}; ff = {k: v for k, v in ff.items() if v}; mx = math.floor(0.15 * len(nod))
    lines.append((f"Critical false flags on no-defect cases at most 15% ({mx} of {len(nod)})", len(ff) <= mx, f"{len(ff)} {ff or ''}"))
    exp = {}
    for k, labs in M.items():
        for c, v in labs.items():
            if v in ("referred", "kb_conflict"):
                got = verdict(k, c); why = (by[k]["evidence"][c].get("reason") or "") if k in by else ""
                exp[f"{k} {c}"] = "ok" if got == v and (v == "kb_conflict" or not RR[k].get(c) or RR[k][c] in why) else f"expected {v} ({RR[k].get(c)}), got {got}: {why}"
    bad = {k: x for k, x in exp.items() if x != "ok"}
    lines.append(("Expected referrals and KB conflicts on the right check and reason", not bad, bad or f"{len(exp)} of {len(exp)}"))
    expc = {k.split()[0] for k in exp}
    others = sorted(k for k, r in by.items() if (r["disposition"]["referred"] or r["disposition"]["kb_conflict"]) and k not in expc); mo = math.floor(0.08 * len(M))
    lines.append((f"Other referrals (count as not detected) at most 8% ({mo} of {len(M)})", len(others) <= mo, f"{len(others)} {others or ''}"))
    uns = S["unscorable"] + [{"case": k, "error": "no result"} for k in list(M) + list(KIND) if k not in by and k not in sby]
    lines.append(("Unscorable 0", not uns, f"{len(uns)} {uns or ''}"))
    allfx = S["fixtures"]["run5"] + S["fixtures"]["store_and_timing"] + S["fixtures"]["replay_tests"]
    lines.append(("Every fixture in the frozen inventory passes", bool(allfx) and all(x["pass"] is True for x in allfx), f"{sum(x['pass'] is True for x in allfx)}/{len(allfx)} " + str([x.get("id", x.get("test")) for x in allfx if x["pass"] is not True] or "")))
    hv = {k: (sby[k]["verdicts"]["c1"] if k in sby else "unscorable") for k in harmful}; hbad = {k: v for k, v in hv.items() if v not in ("fail", "referred")}
    lines.append((f"Stress: no invented-policy, implied-promise or regression case is a verified pass ({len(harmful)} cases by manifest kind, incl. A12 and ST-05)", not hbad, f"{len(hv) - len(hbad)}/{len(hv)} {hbad or ''}"))
    reg = {REG[k]: hv.get(k) for k in REG}
    lines.append(("Stress: regressions A12 and ST-05 end check 1 fail or referred", all(v in ("fail", "referred") for v in reg.values()) and set(reg) >= REQUIRED_REGRESSIONS, reg))
    cp = [k for k in clean if k in sby and not any(sby[k]["disposition"].values())]
    lines.append((f"Stress: clean billing replies pass, at least 75% ({need(0.75, len(clean))} of {len(clean)})", len(cp) >= need(0.75, len(clean)), f"{len(cp)}/{len(clean)} {sorted(set(clean) - set(cp)) or ''}"))
    lines.append(("Stress: the clean refund controls (approval and live dated schedule in the conversation) end clean", bool(refund_ev) and all(k in cp for k in refund_ev), {k: sby[k]["verdicts"]["c1"] for k in refund_ev}))
    t2 = [r for r in by.values() if r.get("extractor_record")]
    lines.append(("Extractor record on every case (model lists, code cross-check, disagreements)", len(t2) == len(by), f"{len(t2)}/{len(by)}"))
    ev = evidence_lines(S, sbytes, epath)
    metrics_ok = all(v for _, v, _ in lines if v is not None); evidence_ok = all(v for _, v, _ in ev)
    decision = "PASS" if metrics_ok and evidence_ok else ("FAIL" if not metrics_ok else "INCOMPLETE: metrics pass but required evidence is missing or failing")
    n = len(by)
    rates = {"tier2_rate": round(len(t2) / n, 3), "qa_referral_rate": round(sum(1 for r in by.values() if r["disposition"]["referred"]) / n, 3),
             "kb_conflict_rate": round(sum(1 for r in by.values() if r["disposition"]["kb_conflict"]) / n, 3), "route_mix": dict(Counter(r["route"] for r in by.values()))}
    agree = {}
    for c in CH:
        pairs = [(1 if by[k]["verdicts"][c] == "fail" else 0, 1 if M[k][c] == "defect" else 0) for k in M if k in by and by[k]["verdicts"][c] in ("pass", "fail") and M[k][c] in ("defect", "no_defect")]
        tp = sum(1 for a, b in pairs if a and b); fp = sum(1 for a, b in pairs if a and not b)
        agree[c] = {"population": len(M), "usable_pairs": len(pairs), "usable_share": round(len(pairs) / len(M), 3), "kappa": kappa(pairs), "precision": round(tp / (tp + fp), 3) if tp + fp else None}
    res = {"run_id": S["run_id"], "lock_id": S["lock_id"], "scores_sha256": sha(sbytes), "labels_sha256": sha(pathlib.Path(lpath).read_bytes()), "stress_manifest_sha256": sha(pathlib.Path(slpath).read_bytes()),
           "phase0_pass": decision == "PASS", "decision": decision, "metric_lines": [{"line": a, "pass": b, "value": v} for a, b, v in lines],
           "evidence_lines": [{"line": a, "pass": b, "value": v} for a, b, v in ev], "coverage": {k: {"count": n, "minimum": m} for k, (n, m) in cov.items()},
           "per_check": per, "critical_false_flags": ff, "other_referrals": others, "rates": rates, "agreement_with_labels": agree, "two_pass_consistency_on_this_run": S["consistency"]}
    pathlib.Path(out).write_text(json.dumps(res, indent=1, default=str))
    print(S["run_id"], "PHASE 0", decision, rates)
    for a, b, v in lines: print("   metric  ", "PASS" if b else ("----" if b is None else "FAIL"), a, "|", str(v)[:240])
    for a, b, v in ev: print("   evidence", "PASS" if b else "FAIL", a, "|", str(v)[:240])
    return res

if __name__ == "__main__":
    if len(sys.argv) != 7: sys.exit(__doc__)
    r = evaluate(*sys.argv[1:]); sys.exit(0 if r["phase0_pass"] else 1)
