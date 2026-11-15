"""One case from flag to verified fix, built only from recorded outputs. No model call, no network.
  python3 trace_case.py
Case FB-H4-035 (holdout v4). The bot told a customer a password reset link stays valid for two hours. The policy in force says 30 minutes.

Steps
  1. Flag: the blind run's check 1 verdict, claim and evidence, read from the frozen scores file.
  2. QA disposition: the released holdout v4 label for this case (QA is simulated by the frozen label, applied after the blind scores hash was verified).
  3. Owner and reason.
  4. Fix: the reply text is corrected.
  5. Recheck: the locked check 1 verifier (desk7.verify_part) runs on the corrected conversation.
     The corrected claim is entered by hand with the same fields the extraction agents recorded, only the value changed.
     It is not a model output. In production the recheck would rerun the locked extraction agents on the new closure revision.
Writes trace_FB-H4-035.json next to this file."""
import copy, json, pathlib, os, sys
HERE = pathlib.Path(__file__).resolve().parent; os.chdir(HERE); sys.path.insert(0, str(HERE))
import desk7, run5

CASE = "FB-H4-035"
RUN = HERE / "runs" / "blind_v4"
DATA = HERE.parent / "data" / "holdout_v4"

def main():
    conv = run5.cases(RUN / "holdout_v4_conversations.json")[CASE]
    scores = json.loads((RUN / "published_scores.json").read_text())
    res = next(r for r in scores["datasets"]["holdout"]["results"] if r["conversation_id"] == CASE)
    flagged = next(c for c in res["claim_verdicts"] if c["verdict"] == "fail")
    labels = json.loads((DATA / "holdout_v4_labels.json").read_text())
    label = next(c for c in labels["cases"] if c["case_id"] == CASE)["labels"]["c1"]
    kb = run5.kb()
    original = {"message_id": flagged["message_id"], "part_type": flagged["part_type"], "span": flagged["span"], "fields": flagged["fields"]}
    steps = []
    steps.append({"step": "1. Flag (blind run P0-R5-ef80449a, scores SHA-256 " + run5.sha((RUN / "published_scores.json").read_bytes())[:16] + ")",
                  "check1": res["verdicts"]["c1"], "claim": flagged["span"], "reason": flagged["reason"], "evidence_id": flagged["evidence_id"],
                  "verifier_rerun_on_recorded_claim": desk7.verify_part(conv, kb, original)})
    steps.append({"step": "2. QA disposition", "released_label_c1": label["final"], "disposition": "confirmed" if label["final"] == "problem" else "rejected"})
    steps.append({"step": "3. Owner", "owner": "AI team (password reset intent)", "reason": "bot stated a link lifetime the policy in force does not allow"})
    fixed = copy.deepcopy(conv); fixed["closure_revision_id"] = CASE + "-recheck"
    m = next(x for x in fixed["messages"] if x["message_id"] == flagged["message_id"])
    m["text"] = m["text"].replace("two hours", "30 minutes")
    steps.append({"step": "4. Fix", "change": "password reset answer grounded on the policy in force (" + str(flagged["evidence_id"]) + ")", "new_reply": m["text"]})
    corrected = copy.deepcopy(original); corrected["span"] = corrected["span"].replace("two hours", "30 minutes"); corrected["fields"]["value"] = "30 minutes"
    v = desk7.verify_part(fixed, kb, corrected)
    steps.append({"step": "5. Recheck with the locked verifier", "claim_entered_by_hand": corrected, "result": v, "closed": v["verdict"] == "pass"})
    out = HERE / f"trace_{CASE}.json"
    out.write_text(json.dumps({"case": CASE, "steps": steps}, indent=1))
    for s in steps: print(json.dumps(s))
    print("TRACE CLOSED" if steps[-1]["closed"] else "TRACE NOT CLOSED")

if __name__ == "__main__": main()
