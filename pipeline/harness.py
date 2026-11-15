"""Run 5 request, response and replay layer (PRD v8 revision 4).

Every agent request is a file. Its SHA-256 binds: task, lock ID, pass, attempt, batch ID, case IDs, model ID,
wrapper hash, prompt hash, schema hash and the exact text sent to the agent. Every raw response, including
retries, is stored against the hash of the request it answers. Scoring reads only stored responses, so replay
needs no model call and adds no timestamp."""
import json, hashlib, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parent
MODEL_ID = "claude-opus-5-5"  # identifier the session reports. Snapshot, build and sampling settings are not exposed
PASSES = (1, 2)
BATCH_SIZE = 5
MAX_ATTEMPTS = 2
TASKS = {"extract": ("prompts/extract.txt", "schemas/extract.schema.json"), "judge": ("prompts/judge.txt", "schemas/judge.schema.json")}

def sha(b): return hashlib.sha256(b if isinstance(b, bytes) else b.encode("utf-8")).hexdigest()
def canon(o): return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
def read(p): return (ROOT / p).read_text(encoding="utf-8")

def component_hashes():
    h = {"wrapper.txt": sha(read("wrapper.txt"))}
    for t, (p, sc) in TASKS.items(): h[p] = sha(read(p)); h[sc] = sha(read(sc))
    return h

def batch_order(case_ids, lock_id, task, pass_no):
    """Frozen ordering: cases sorted by sha256(lock, task, pass, case), then cut into batches of BATCH_SIZE. Pass 2 sees a different order."""
    order = sorted(case_ids, key=lambda c: sha(f"{lock_id}|{task}|{pass_no}|{c}"))
    return [order[i:i + BATCH_SIZE] for i in range(0, len(order), BATCH_SIZE)]

def expected_batches(case_ids, lock_id, task):
    """The complete batch inventory a run must have for one task: every pass, every batch, in the frozen order."""
    return {f"{task}|{p}|{task}-p{p}-b{i:02d}": b for p in PASSES for i, b in enumerate(batch_order(sorted(case_ids), lock_id, task, p), 1)}

def render_case(conv, extra=None):
    lines = [f"CASE {conv['case_id']}"]
    for m in conv["messages"]: lines.append(f"{m['message_id']} {m['role']}: {m['text']}")
    if extra: lines.append(extra)
    return "\n".join(lines)

def build_request(task, lock_id, pass_no, attempt, batch_id, convs, extras=None):
    p, sc = TASKS[task]
    body = "\n\n".join(render_case(c, (extras or {}).get(c["case_id"])) for c in convs)
    text = read("wrapper.txt").format(instructions=read(p).strip(), schema=read(sc).strip(), input=body)
    meta = {"task": task, "lock_id": lock_id, "pass": pass_no, "attempt": attempt, "batch_id": batch_id, "case_ids": [c["case_id"] for c in convs],
            "model_id": MODEL_ID, "wrapper_sha256": sha(read("wrapper.txt")), "prompt_sha256": sha(read(p)), "schema_sha256": sha(read(sc)), "text_sha256": sha(text)}
    return {**meta, "request_sha256": sha(canon(meta)), "text": text}

class Store:
    """requests/<sha>.json, responses/<request sha>.json, index.json. One directory per run."""
    def __init__(self, run_dir):
        self.d = pathlib.Path(run_dir); (self.d / "requests").mkdir(parents=True, exist_ok=True); (self.d / "responses").mkdir(exist_ok=True)
        self.index_path = self.d / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {"entries": {}}

    def save_request(self, req):
        (self.d / "requests" / f"{req['request_sha256']}.json").write_text(json.dumps(req, indent=1, ensure_ascii=False))
        k = f"{req['task']}|{req['pass']}|{req['batch_id']}"
        e = self.index["entries"].setdefault(k, {"task": req["task"], "pass": req["pass"], "batch_id": req["batch_id"], "case_ids": req["case_ids"], "attempts": []})
        if req["request_sha256"] not in e["attempts"]: e["attempts"].append(req["request_sha256"])
        self._save_index()

    def save_response(self, request_sha, raw_text, agent_id, received_at_utc):
        (self.d / "responses" / f"{request_sha}.json").write_text(json.dumps(
            {"request_sha256": request_sha, "agent_id": agent_id, "received_at_utc": received_at_utc, "raw_response": raw_text}, indent=1, ensure_ascii=False))

    def _save_index(self): self.index_path.write_text(json.dumps(self.index, indent=1, sort_keys=True))

def parse_json(raw):
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    return json.loads(t)

# ---------- validation with the standard library only (no jsonschema): the schema subset these schemas use
def schema_errors(obj, sch, path="$"):
    t = sch.get("type"); errs = []
    if isinstance(t, list):
        if not any(schema_errors(obj, {**sch, "type": x}, path) == [] for x in t): return [f"{path}: expected one of {t}"]
        return []
    ok = {"object": dict, "array": list, "string": str, "boolean": bool}.get(t)
    if t in ("number", "integer"):
        if isinstance(obj, bool) or not isinstance(obj, (int, float)) or (t == "integer" and not isinstance(obj, int)): return [f"{path}: expected {t}"]
    elif t == "null":
        if obj is not None: return [f"{path}: expected null"]
    elif ok and not isinstance(obj, ok): return [f"{path}: expected {t}"]
    if "enum" in sch and obj not in sch["enum"]: errs.append(f"{path}: {obj!r} not in {sch['enum']}")
    if isinstance(obj, dict):
        for k in sch.get("required", []):
            if k not in obj: errs.append(f"{path}: missing {k}")
        props = sch.get("properties", {})
        for k, v in obj.items():
            if k in props: errs += schema_errors(v, props[k], f"{path}.{k}")
            elif sch.get("additionalProperties") is False: errs.append(f"{path}: unexpected {k}")
    if isinstance(obj, list) and "items" in sch:
        for n, x in enumerate(obj): errs += schema_errors(x, sch["items"], f"{path}[{n}]")
    return errs

REQUIRED_FIELDS = {"price": {"amount": (int, float), "period": str}, "policy_term": {"topic": str, "value": str}, "account_fact": {"topic": str, "value": str},
                   "completed_action": {"action": str}, "future_promise": {"action": str}, "procedure": {"path": str}, "handoff_claim": {"kind": str},
                   "offer_or_eligibility": {"description": str}}
MONEY_ACTIONS = {"money_returned", "refund", "refund_issued", "refund_sent", "refund_scheduled"}
PROMISE_DETAILS = {"amount": r"\$\s?\d", "when": r"\b(today|tonight|tomorrow|soon|shortly|within|in \w+ (business |working )?days?|next week|this week|end of|by (monday|tuesday|wednesday|thursday|friday)|20\d\d-\d\d-\d\d|business days?|working days?)\b",
                   "destination": r"\b(card|credit|bank|payment method)\b"}
def squash(t): return re.sub(r"\s+", " ", (t or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')).strip()

def semantic_errors(obj, task, convs):
    """Checks a schema-valid reply against the exact input it answers: message IDs belong to that case, roles fit, quoted spans appear
    word for word (whitespace and curly quotes normalised) in the cited message, and each claim type carries its required typed fields."""
    errs = []
    for c in obj["cases"]:
        conv = convs.get(c["case_id"])
        if conv is None: errs.append(f"{c['case_id']}: not in this batch"); continue
        msgs = {m["message_id"]: m for m in conv["messages"]}
        def role_of(mid): return msgs[mid]["role"] if mid in msgs else None
        if task == "extract":
            for n, x in enumerate(c["claims"]):
                where = f"{c['case_id']} claim {n}"
                if role_of(x["message_id"]) != "assistant": errs.append(f"{where}: {x['message_id']} is not an assistant message of this case"); continue
                if not squash(x["span"]) or squash(x["span"]) not in squash(msgs[x["message_id"]]["text"]): errs.append(f"{where}: span is not in {x['message_id']}")
                for k, typ in REQUIRED_FIELDS.get(x["part_type"], {}).items():
                    v = (x.get("fields") or {}).get(k)
                    if not isinstance(v, typ) or isinstance(v, bool) or v == "": errs.append(f"{where}: {x['part_type']} needs field {k}")
                if x["part_type"] == "future_promise":  # every detail the quoted promise states must be extracted
                    sp, fl = squash(x["span"]).lower(), x.get("fields") or {}
                    money = fl.get("action") in MONEY_ACTIONS or re.search(r"refund|money back|your \$", sp)
                    for k, pat in PROMISE_DETAILS.items():
                        if k == "destination" and not money: continue  # destination applies to money being returned, not to a credit or a call being promised
                        if re.search(pat, sp) and fl.get(k) in (None, ""): errs.append(f"{where}: future_promise states a {k} but the field {k} is empty")
            for x in c["needs"]:
                if role_of(x["message_id"]) != "customer": errs.append(f"{c['case_id']} need: {x['message_id']} is not a customer message")
            for x in c["sensitive_requests"]:
                if role_of(x["message_id"]) != "assistant": errs.append(f"{c['case_id']} sensitive request: {x['message_id']} is not an assistant message")
        else:
            for k in ("resolution", "tone"):
                mid = c[k].get("message_id")
                if mid is not None and role_of(mid) != "assistant": errs.append(f"{c['case_id']} {k}: {mid} is not an assistant message")
    return errs

def select(store, lock, task, convs=None, extras=None):
    """Frozen selection rule: for each batch, attempts in order (at most MAX_ATTEMPTS). The first response is selected that
    binds to its request (same hash, task, lock, pass, batch, case IDs and attempt), whose request was built from the locked components
    and, when the scoring input is given, re-renders byte for byte from that input, that was received after the lock, parses,
    matches the schema, passes the semantic checks against the input, and covers exactly the batch's case IDs.
    Returns ({pass: {case_id: output or None}}, unresolved problems, {batch key: selected request hash}).
    Every attempt's outcome, including rejected attempts before a valid retry, is in store.history[task]. Pure: writes nothing."""
    schema = json.loads(read(TASKS[task][1])); out = {p: {} for p in PASSES}; problems = []; selected = {}; hist = []
    if convs is not None:  # the run must hold exactly the expected batch inventory for this task: no missing, extra or reshaped batch
        exp = expected_batches(list(convs), lock["lock_id"], task); have = {k: e for k, e in store.index["entries"].items() if e["task"] == task}
        for k in sorted(set(exp) - set(have)): problems.append(f"{k}: expected batch missing from the run (cases {exp[k]}), those cases have no reply for this pass")
        for k in sorted(set(have) - set(exp)): problems.append(f"{k}: batch not in the expected inventory for this lock and case list")
        for k in sorted(set(exp) & set(have)):
            if have[k]["case_ids"] != exp[k] or have[k]["pass"] != int(k.split("|")[1]): problems.append(f"{k}: batch cases or pass differ from the frozen order")
    for k, e in sorted(store.index["entries"].items()):
        if e["task"] != task: continue
        chosen, why = None, []
        for n, rs in enumerate(e["attempts"][:MAX_ATTEMPTS], 1):
            def reject(msg): why.append(f"{k} attempt {n}: {msg}"); hist.append({"batch": k, "attempt": n, "request_sha256": rs, "outcome": "rejected", "reason": msg})
            rq_f, rs_f = store.d / "requests" / f"{rs}.json", store.d / "responses" / f"{rs}.json"
            if not rq_f.exists(): reject("request file missing"); continue
            rq = json.loads(rq_f.read_text())
            meta = {x: rq[x] for x in ("task", "lock_id", "pass", "attempt", "batch_id", "case_ids", "model_id", "wrapper_sha256", "prompt_sha256", "schema_sha256", "text_sha256")}
            if sha(canon(meta)) != rs or sha(rq["text"]) != rq["text_sha256"]: reject("request does not match its hash"); continue
            if rq["lock_id"] != lock["lock_id"] or rq["attempt"] != n or rq["task"] != task: reject("request bound to another lock, task or attempt"); continue
            if rq["pass"] != e["pass"] or rq["batch_id"] != e["batch_id"] or rq["case_ids"] != e["case_ids"]: reject("request bound to another pass, batch or case list than its index entry"); continue
            comp = lock["components"]
            if (rq["wrapper_sha256"], rq["prompt_sha256"], rq["schema_sha256"], rq["model_id"]) != (comp["wrapper.txt"], comp[TASKS[task][0]], comp[TASKS[task][1]], lock["model_id"]):
                reject("request built from components that are not the locked ones"); continue
            if convs is not None:
                missing = [c for c in rq["case_ids"] if c not in convs]
                if missing: reject(f"scoring input lacks {missing}"); continue
                again = build_request(task, rq["lock_id"], rq["pass"], rq["attempt"], rq["batch_id"], [convs[c] for c in rq["case_ids"]], extras)
                if again["text_sha256"] != rq["text_sha256"]: reject("scoring input does not re-render to the saved request"); continue
            if not rs_f.exists(): reject("no response"); continue
            r = json.loads(rs_f.read_text())
            if r["request_sha256"] != rs: reject("response bound to another request"); continue
            if r["received_at_utc"] < lock["locked_at_utc"]: reject("response received before the lock"); continue
            try: obj = parse_json(r["raw_response"])
            except Exception as ex: reject(f"invalid output ({type(ex).__name__})"); continue
            se = schema_errors(obj, schema)
            if se: reject(f"invalid output (schema: {'; '.join(se[:3])})".replace(";", ",")); continue
            got = [c["case_id"] for c in obj["cases"]]
            if sorted(got) != sorted(e["case_ids"]) or len(set(got)) != len(got): reject(f"incomplete or extra cases {sorted(set(got) ^ set(e['case_ids']))}"); continue
            if convs is not None:
                me = semantic_errors(obj, task, {c: convs[c] for c in e["case_ids"]})
                if me: reject("output does not fit its input: " + ", ".join(me[:4])); continue
            chosen = {c["case_id"]: c for c in obj["cases"]}; selected[k] = rs
            hist.append({"batch": k, "attempt": n, "request_sha256": rs, "outcome": "selected", "reason": ""}); break
        if chosen is None: problems.append(f"{k}: no valid attempt ({' | '.join(why) or 'no attempts'})")
        for cid in e["case_ids"]: out[e["pass"]][cid] = (chosen or {}).get(cid)
    if convs is not None:
        for p in PASSES:
            gone = sorted(c for c in convs if out[p].get(c) is None)
            if gone: problems.append(f"{task} pass {p}: no valid reply for {len(gone)} cases {gone[:8]}")
    if not hasattr(store, "history"): store.history = {}
    store.history[task] = hist
    return out, problems, selected
