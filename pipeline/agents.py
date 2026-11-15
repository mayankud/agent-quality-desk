"""Prepare agent requests and collect replies. The coordinator never prints request or reply content.
  python3 agents.py prepare RUN_DIR LOCK_FILE TASK PASS ATTEMPT CASES_JSON [EXTRAS_JSON] [BATCH_IDS]   -> prints launcher prompts (paths only)
  python3 agents.py collect RUN_DIR"""
import json, sys, pathlib, datetime as dt, os
import harness as H
INBOX, OUTBOX = pathlib.Path("/tmp/aqd_inbox"), pathlib.Path("/tmp/aqd_outbox")

def prepare(run_dir, lock_file, task, pass_no, attempt, cases_json, extras_json=None, only=None):
    lock = json.load(open(lock_file)); st = H.Store(run_dir)
    convs = {c["case_id"]: c for c in json.load(open(cases_json))["conversations"]}
    extras = json.load(open(extras_json)) if extras_json and extras_json != "-" else {}
    batches = H.batch_order(sorted(convs), lock["lock_id"], task, pass_no)
    launch = (H.ROOT / "launcher.txt").read_text()
    out = []
    for i, b in enumerate(batches, 1):
        bid = f"{task}-p{pass_no}-b{i:02d}"
        if only and bid not in only: continue
        rq = H.build_request(task, lock["lock_id"], pass_no, attempt, bid, [convs[c] for c in b], extras)
        st.save_request(rq)
        inbox, outbox = INBOX / f"{rq['request_sha256']}.txt", OUTBOX / f"{rq['request_sha256']}.json"
        inbox.write_text(rq["text"], encoding="utf-8")
        out.append({"batch_id": bid, "request_sha256": rq["request_sha256"], "prompt": launch.format(inbox=inbox, outbox=outbox, request_sha=rq["request_sha256"])})
    json.dump(out, open(pathlib.Path(run_dir) / f"launch_{task}_p{pass_no}_a{attempt}.json", "w"), indent=1)
    for o in out: print(o["batch_id"], o["request_sha256"])

def collect(run_dir):
    st = H.Store(run_dir); n = 0
    known = {rs for e in st.index["entries"].values() for rs in e["attempts"]}
    for f in sorted(OUTBOX.glob("*.json")):
        rs = f.stem
        if rs not in known or (st.d / "responses" / f"{rs}.json").exists(): continue
        t = dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        st.save_response(rs, f.read_text(encoding="utf-8"), agent_id=f"agent-for-{rs[:12]}", received_at_utc=t); n += 1
    print("collected", n)

if __name__ == "__main__":
    a = sys.argv
    if a[1] == "prepare": prepare(a[2], a[3], a[4], int(a[5]), int(a[6]), a[7], a[8] if len(a) > 8 else None, set(a[9].split(",")) if len(a) > 9 else None)
    else: collect(a[2])
