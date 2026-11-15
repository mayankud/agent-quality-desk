"""One-command replay. Python 3.10 or later, standard library only, no model call, no network, no timestamps.
  python3 replay.py [RUN_DIR]        RUN_DIR defaults to runs/blind_v4. Also runs/regression_L8 and runs/regression_L8_flagged
Checks, in order:
  1. every locked code, prompt, schema, wrapper and rubric file matches lock.json, and no unlisted rubric file exists
  2. every saved request matches its hash, its index entry and its standalone text copy in run/request_texts/
  3. every saved reply is bound to its request
  4. scoring the saved replies (selection against the re-rendered requests, verification, combination, fixtures) reproduces
     RUN_DIR/published_scores.json byte for byte
  5. the two-pass consistency in the replayed scores, and the gate (regression run). A blind run (run/holdout_v4_conversations.json present) is scored with --blind and its agreement is reported without a gate
Prints REPLAY OK and exits 0 only when all of them hold."""
import hashlib, json, pathlib, sys, tempfile, os
HERE = pathlib.Path(__file__).resolve().parent; os.chdir(HERE); sys.path.insert(0, str(HERE))
import run5, harness as H

def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    fails = []; run = (HERE / (sys.argv[1] if len(sys.argv) > 1 else "runs/blind_v4")).resolve(); lk = run5.load_lock(run)
    print(f"run folder: {run.relative_to(HERE)}")
    files = {**lk["components"], **lk["code"], **{"rubric/" + f: h for f, h in lk["rubric"].items()}}
    bad = [f for f, h in files.items() if not (HERE / f).exists() or sha((HERE / f).read_bytes()) != h]
    extra = [p.name for p in (HERE / "rubric").glob("*") if p.is_file() and p.name not in lk["rubric"]]
    print(f"1. locked files: {len(files)} checked, {len(bad)} changed, {len(extra)} unlisted rubric files")
    if bad or extra: fails.append(f"locked files changed {bad} or unlisted rubric files {extra}")
    idx = json.loads((run / "index.json").read_text()); nreq = 0
    for k, e in sorted(idx["entries"].items()):
        for rs in e["attempts"]:
            rq = json.loads((run / "requests" / f"{rs}.json").read_text()); nreq += 1
            meta = {x: rq[x] for x in ("task", "lock_id", "pass", "attempt", "batch_id", "case_ids", "model_id", "wrapper_sha256", "prompt_sha256", "schema_sha256", "text_sha256")}
            copy = run / "request_texts" / f"{rs}.txt"
            if sha(H.canon(meta).encode()) != rs or sha(rq["text"].encode()) != rq["text_sha256"]: fails.append(f"request {rs[:12]} does not match its hash")
            if (rq["pass"], rq["batch_id"], rq["case_ids"]) != (e["pass"], e["batch_id"], e["case_ids"]): fails.append(f"request {rs[:12]} does not match index entry {k}")
            if not copy.exists() or copy.read_text(encoding="utf-8") != rq["text"]: fails.append(f"request {rs[:12]} text copy missing or different")
            rf = run / "responses" / f"{rs}.json"
            if rf.exists() and json.loads(rf.read_text())["request_sha256"] != rs: fails.append(f"reply {rs[:12]} bound to another request")
    print(f"2-3. requests and replies: {nreq} requests checked")
    out = pathlib.Path(tempfile.mkdtemp()) / "replay_scores.json"
    blind = (run / "holdout_v4_conversations.json").exists()
    if blind: run5.score(run, out, f"{run / 'holdout_v4_conversations.json'},{run / 'stress_v4_conversations.json'}", True)
    else: run5.score(run, out, run / "cases.json")
    got, want = sha(out.read_bytes()), sha((run / "published_scores.json").read_bytes())
    print(f"4. replayed scores SHA-256  {got}\n   published scores SHA-256 {want}")
    if got != want: fails.append("replayed scores differ from the published scores")
    c = json.loads(out.read_text())["consistency"]
    if blind:
        print(f"5. blind run, two-pass agreement for information only (no gate on the blind run): claim parts {c['claim_parts']['agree']} of {c['claim_parts']['pairs']}, handoff decision {c['handoff_decision']['agree']} of {c['handoff_decision']['pairs']}, valid pairs extraction {c['extraction_valid_pairs']} and judge {c['judge_valid_pairs']} of {c['cases']}")
        if fails: print("REPLAY FAILED"); [print(" -", f) for f in fails]; sys.exit(1)
        print("REPLAY OK"); return
    print(f"5. claim parts {c['claim_parts']['agree']} of {c['claim_parts']['pairs']} = {c['claim_parts']['rate']} (gate 0.90), handoff decision {c['handoff_decision']['agree']} of {c['handoff_decision']['pairs']} = {c['handoff_decision']['rate']} (gate 0.95), "
          f"valid pairs extraction {c['extraction_valid_pairs']} and judge {c['judge_valid_pairs']} of {c['cases']}, gate {'PASS' if c['gate']['pass'] else 'FAIL'}")
    if fails: print("REPLAY FAILED"); [print(" -", f) for f in fails]; sys.exit(1)
    print("REPLAY OK")

if __name__ == "__main__": main()
