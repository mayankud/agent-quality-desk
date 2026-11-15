"""Builds synthetic fixture conversations in the holdout schema (mk copied from run6 build_sets.py)."""
import json, datetime as dt, hashlib

NOTICE = "You're chatting with Fieldbook's AI assistant."
N, D, R, K = "no_defect", "defect", "referred", "kb_conflict"

def mk(cid, start, turns, notice=True, tools=(), events=(), health="complete", policies=(), delayed_detail=None):
    t0 = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
    msgs, t = [], t0
    seq = ([("notice", NOTICE)] if notice else []) + list(turns)
    for i, (role, text) in enumerate(seq):
        role = {"c": "customer", "a": "assistant", "notice": "notice"}[role]
        msgs.append({"message_id": f"m{i+1:02d}", "role": role, "at": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "text": text})
        t += dt.timedelta(seconds=20)
    closed = t + dt.timedelta(seconds=40)
    byid = {m["message_id"]: m for m in msgs}
    def before(mid, s): return (dt.datetime.fromisoformat(byid[mid]["at"].replace("Z", "+00:00")) - dt.timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    tr = [{"record_id": f"{cid}-tool-{i+1}", "at": before(mid, 10), "for_reply": mid, "tool": tool, "result": res} for i, (mid, tool, res) in enumerate(tools)]
    ev = [{"record_id": f"{cid}-event-{i+1}", "at": before(mid, 5), "for_reply": mid, "type": typ, **f} for i, (mid, typ, f) in enumerate(events)]
    if health == "complete":
        lh = {"status": "complete", "scope": "Account actions and handoff for this case", "complete_through": (closed + dt.timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")}
    else:
        lh = {"status": "delayed", "scope": "Account actions and handoff for this case", "complete_through": (t0 - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), "detail": delayed_detail or "Action feed delayed."}
    return {"case_id": cid, "conversation_id": cid, "closure_revision": 1, "closure_revision_id": f"{cid}-r1",
            "closed_at": closed.strftime("%Y-%m-%dT%H:%M:%SZ"), "channel": "chat", "bot_release": "fieldbook-synthetic-run3",
            "messages": msgs, "policy_ids": list(policies), "tool_results": tr, "action_events": ev, "log_health": lh}
