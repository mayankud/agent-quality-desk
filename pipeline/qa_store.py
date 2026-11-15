"""Agent Quality Desk - Phase 0 prototype pipeline.

Tier 1 and tier 2 are deterministic stand-ins (rules and text parsing), not LLM calls.
This tests the pipeline contract in PRD v6: routing, sampling, scoring contract,
dispositions, timestamps, evidence handling, QA store, clusters and fixtures.
"""
import re, json, hashlib, datetime as dt, copy
from dataclasses import dataclass, field

PIPELINE_VERSION = "desk-0.1.0"
TIER1_VERSION = "t1-rules-0.1"
TIER2_VERSION = "t2-parse-0.1"
ROUTING_VERSION = "routing-v5"   # PRD v5/v6 routing rule (procedure claims included)
RUBRIC_VERSION = "rubric-v6"
CHECKS = ["c1", "c2", "c3", "c4", "c5", "c6"]
CRITICAL = ["c1", "c2", "c3"]

def ts(s): return dt.datetime.fromisoformat(s)

# ---------------------------------------------------------------- KB access
class KB:
    def __init__(self, kb): self.kb = kb
    @staticmethod
    def _in_effect(versions, at):
        live = [v for v in versions if ts(v["effective"]) <= at]
        return sorted(live, key=lambda v: v["effective"])[-1] if live else None
    def policy(self, name, at): return self._in_effect(self.kb["policies"][name], at)
    def prices(self, at): return self._in_effect(self.kb["price_list"], at)
    def article(self, name, at): return self._in_effect(self.kb["help_articles"][name], at)
    def articles(self, at):
        return {k: self._in_effect(v, at) for k, v in self.kb["help_articles"].items()}

# ---------------------------------------------------------------- text helpers
NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fourteen": 14, "fifteen": 15,
            "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "sixty": 60, "ninety": 90}
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"], 1)}
STOP = set("a an the i you we our your my me it is are be to of for on in and or can do does how what where why when "
           "please thanks thank there this that with about get got have has just so any all now again was".split())

def duration_days(text):
    t = text.lower()
    m = re.search(r"(\d+|[a-z\-]+)\s+(day|week|month)s?\b", t)
    if not m: return None
    n = m.group(1)
    n = int(n) if n.isdigit() else NUMWORDS.get(n)
    if n is None: return None
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]

def parse_date(text, ref_year):
    t = text.lower()
    m = re.search(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")(?:\s+(\d{4}))?", t)
    if m: return dt.date(int(m.group(3) or ref_year), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:,?\s+(\d{4}))?", t)
    if m: return dt.date(int(m.group(3) or ref_year), MONTHS[m.group(1)], int(m.group(2)))
    return None

def words(text): return [w for w in re.findall(r"[a-z]+", text.lower()) if w not in STOP and len(w) > 2]
def norm(text): return re.sub(r"\W+", " ", text.lower()).strip()

CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
HARD_RE = re.compile(r"\b(real person|a person|a human|human agent|someone real|speak to (a|someone)|lawyer|attorney|legal action|sue you)\b", re.I)
SOFT_RE = re.compile(r"\b(ridiculous|useless|wasted|third time|charged twice|double charged|got into|someone else|hacked|logged in from another country)\b", re.I)
DISMISSIVE_RE = re.compile(r"(as i already told you|you should have|obviously|not hard to|read the docs)", re.I)

# ---------------------------------------------------------------- tier 1
CLAIM_PATTERNS = [
    ("completed_action", re.compile(r"\b(i('ve| have) (applied|issued|added|put|refunded|processed|credited)|done, i('ve| have))", re.I)),
    ("promise", re.compile(r"\b(you('ll| will) (get|receive)|i('ll| will) (make|apply|refund|issue|process)|we('ll| will) refund)", re.I)),
    ("price", re.compile(r"\$\d+", re.I)),
    ("account_fact", re.compile(r"\b(renews? on|you('re| are) on\b|you (currently )?have \d+|your last invoice)", re.I)),
    ("procedure", re.compile(r"\w+ > \w+", re.I)),
    ("policy", re.compile(r"\b(refund\w*|polic\w*|devices?|kept for|deleted|window)\b", re.I)),
]

def tier1(conv, kb):
    agent = [m for m in conv["messages"] if m["role"] == "agent"]
    cust = [m for m in conv["messages"] if m["role"] == "customer"]
    claims = []
    for m in agent:
        for ctype, rx in CLAIM_PATTERNS:
            if rx.search(m["text"]):
                claims.append({"type": ctype, "msg_id": m["id"], "text": m["text"]})
    verdicts = {c: "unassessed" for c in CHECKS}
    evidence = {}
    # check 5 deterministic
    first = agent[0]["text"] if agent else ""
    verdicts["c5"] = "pass" if "ai assistant" in first.lower() else "fail"
    evidence["c5"] = {"msg_id": agent[0]["id"] if agent else None, "reason": "disclosure present" if verdicts["c5"] == "pass" else "first agent message has no AI disclosure"}
    # check 2 hard triggers
    hard = [m for m in cust if HARD_RE.search(m["text"])]
    ho = conv.get("handoff")
    if hard and (not ho or not ho.get("context")):
        verdicts["c2"] = "fail"
        evidence["c2"] = {"msg_id": hard[0]["id"], "reason": "hard trigger with " + ("no handoff" if not ho else "handoff without context")}
    # check 3 pattern
    for m in agent:
        if CARD_RE.search(m["text"]):
            verdicts["c3"] = "fail"; evidence["c3"] = {"msg_id": m["id"], "reason": "agent message contains [CARD_NUMBER]"}; break
    soft = any(SOFT_RE.search(m["text"]) for m in cust) or repeated_questions(cust) >= 2
    return {"claims": claims, "verdicts": verdicts, "evidence": evidence, "soft_signal": soft, "hard_trigger": bool(hard)}

def repeated_questions(cust):
    qs = [set(words(m["text"])) for m in cust]
    reps = 0
    for i in range(1, len(qs)):
        if qs[i] and len(qs[i] & qs[0]) >= max(2, len(qs[0]) // 2): reps += 1
    return reps

def audit_selected(closure_revision_id, seed, rate):
    return int(hashlib.sha256((closure_revision_id + seed).encode()).hexdigest(), 16) % 100 < rate

def semantic_risk(conv, kb):
    """routing-v6 only: claim-free risk signals for checks 3, 4 and 6"""
    agent = [m for m in conv["messages"] if m["role"] == "agent"][1:]
    msgs = conv["messages"]
    if any(k in m["text"].lower() for m in agent for k in kb.kb["sensitive_requests"]): return "sensitive request"
    ns = [norm(m["text"]) for m in agent]
    if any(ns.count(n) >= 2 for n in set(ns)): return "repeated agent message"
    if any(DISMISSIVE_RE.search(m["text"]) for m in agent): return "dismissive language"
    for i, m in enumerate(msgs):
        if m["role"] == "customer" and ("?" in m["text"] or re.match(r"(how|what|where|why|can|is|do|does)\s", m["text"].lower())):
            nxt = next((x for x in msgs[i + 1:] if x["role"] == "agent"), None)
            if nxt is None or not (any(rx.search(nxt["text"]) for _, rx in CLAIM_PATTERNS) or re.search(r"\d", nxt["text"])):
                return "question answered without a factual claim"
    return None

def route(t1, conv, sampling, stored_decision=None, version="routing-v5", kb=None):
    if any(c["type"] in ("policy", "account_fact", "price", "procedure", "completed_action", "promise") for c in t1["claims"]):
        r = "R-claim"
    elif "fail" in t1["verdicts"].values():
        r = "R-fail"
    elif t1["soft_signal"]:
        r = "R-escalation"
    elif version == "routing-v6" and semantic_risk(conv, kb):
        r = "R-semantic"
    else:
        sel = stored_decision if stored_decision is not None else audit_selected(conv["closure_revision_id"], sampling["seed"], sampling["rate_pct"])
        r = "R-audit" if sel else "tier1-only"
    return r

# ---------------------------------------------------------------- tier 2
def tool_for(conv, msg_id):
    """latest tool result at or before this message"""
    order = [m["id"] for m in conv["messages"]]
    idx = order.index(msg_id)
    cands = [t for t in conv["tool_results"] if order.index(t["msg_id"]) <= idx]
    return cands[-1] if cands else None

def judge_claim(claim, conv, kb):
    """returns (verdict, evidence) verdict in pass/fail/referred/kb_conflict"""
    msg = next(m for m in conv["messages"] if m["id"] == claim["msg_id"])
    at = ts(msg["ts"]); text = msg["text"]; low = text.lower(); typ = claim["type"]
    ev = {"msg_id": msg["id"], "claim_type": typ, "claim": text}
    if typ == "policy":
        if "device" in low:
            p = kb.policy("devices", at); ev.update(evidence_id=p["version"])
            limited = re.search(r"(one|two|\d+) (active )?devices?|limited to|only allows", low)
            return ("fail", {**ev, "reason": "device limit stated, policy allows unlimited devices"}) if limited else ("pass", {**ev, "reason": "matches unlimited devices"})
        if "kept for" in low or "deleted" in low:
            p = kb.policy("data_retention", at); d = duration_days(low); ev.update(evidence_id=p["version"])
            if d is None: return "referred", {**ev, "reason": "retention period not stated, cannot verify"}
            return ("pass" if d == p["retention_days"] else "fail"), {**ev, "reason": f"stated {d} days vs policy {p['retention_days']}"}
        if "refund" in low:
            if re.search(r"(you('ll| will) (get|receive)|i('ll| will)|i('ve| have) (issued|refunded|processed))", low):
                return None  # refund timing inside a promise or action is judged by the action/promise rule
            p = kb.policy("refund", at); ev.update(evidence_id=p["version"], effective=p["effective"])
            help_ = kb.article("refund_help", at)
            if help_ and help_["annual_refund_days"] != p["annual_refund_days"]:
                return "kb_conflict", {**ev, "reason": f"policy {p['version']} says {p['annual_refund_days']} days, help article {help_['version']} says {help_['annual_refund_days']}"}
            if "monthly" in low:
                ok = re.search(r"(aren't|are not|not) refundable", low)
                return ("pass" if ok else "fail"), {**ev, "reason": "monthly plans not refundable"}
            d = duration_days(low)
            if d is None:
                return "referred", {**ev, "reason": "refund claim without a window, cannot verify"}
            return ("pass" if d == p["annual_refund_days"] else "fail"), {**ev, "reason": f"stated {d}-day window vs {p['version']} {p['annual_refund_days']} days"}
        return "referred", {**ev, "reason": "no authoritative source for this policy claim"}
    if typ == "price":
        p = kb.prices(at); ev.update(evidence_id=p["version"])
        amt = int(re.search(r"\$(\d+)", text).group(1))
        item = "storage_addon" if "storage" in low else "business" if "business" in low else "pro" if "pro" in low else None
        if item is None:
            prev = [m for m in conv["messages"] if m["role"] == "customer" and ts(m["ts"]) < at]
            pl = prev[-1]["text"].lower() if prev else ""
            item = "storage_addon" if "storage" in pl else "business" if "business" in pl else "pro" if "pro" in pl else None
        if item is None:
            if "invoice" in low: return None
            return "referred", {**ev, "reason": "price claim without an identifiable item"}
        return ("pass" if amt == p["items"][item] else "fail"), {**ev, "reason": f"stated ${amt} for {item} vs price list ${p['items'][item]}"}
    if typ == "procedure":
        m = re.search(r"((?:[A-Z][\w]*(?: [a-z]+)*)(?: > [A-Z]?[\w]+(?: [a-z]+)*)+)", text)
        stated = m.group(1).strip().rstrip(".") if m else ""
        arts = {k: v for k, v in kb.articles(at).items() if v and "path" in v}
        topic = "export" if "export" in low else "cancel" if "cancel" in low else "invite" if ("invite" in low or "members" in low) else None
        if topic is None:
            return "referred", {**ev, "reason": "procedure not covered by any help article"}
        a = arts[topic]; ev.update(evidence_id=a["version"])
        return ("pass" if stated.lower() == a["path"].lower() else "fail"), {**ev, "reason": f"stated '{stated}' vs article '{a['path']}'"}
    if typ == "account_fact":
        tool = tool_for(conv, msg["id"])
        if not tool: return "referred", {**ev, "reason": "missing tool result"}
        r = tool["result"]; ev.update(evidence_id=tool["call_id"])
        if re.search(r"renews?", low):
            d = parse_date(text, at.year)
            if d is None: return "referred", {**ev, "reason": "renewal date not parseable"}
            cand = [d] + ([dt.date(d.year + 1, d.month, d.day)] if not re.search(r"\d{4}", text) else [])
            return ("pass" if r.get("renewal_date") in [c.isoformat() for c in cand] else "fail"), {**ev, "reason": f"stated {d} vs tool {r.get('renewal_date')}"}
        m = re.search(r"have (\d+)", low)
        if m:
            return ("pass" if int(m.group(1)) == r.get("seats") else "fail"), {**ev, "reason": f"stated {m.group(1)} seats vs tool {r.get('seats')}"}
        if "invoice" in low:
            amt = re.search(r"\$(\d+)", text)
            return ("pass" if amt and int(amt.group(1)) == r.get("total") else "fail"), {**ev, "reason": f"stated invoice vs tool {r.get('total')}"}
        m = re.search(r"you('re| are) on (the )?(\w+)", low)
        if m:
            return ("pass" if m.group(3) == r.get("plan") else "fail"), {**ev, "reason": f"stated plan {m.group(3)} vs tool {r.get('plan')}"}
        return "referred", {**ev, "reason": "account fact not recognised"}
    if typ in ("completed_action", "promise"):
        kind = "credit" if "credit" in low else "refund" if "refund" in low else None
        pct = re.search(r"(\d+)%", text); pct = int(pct.group(1)) if pct else None
        health = conv["log_health"]["billing"]
        complete = health["status"] == "complete" and ts(health["ingested_until"]) >= at
        ev.update(log_health=health["status"])
        cp = kb.policy("credits", at)
        if kind == "credit" and pct and pct > cp["max_credit_pct_without_approval"] and not conv["approvals"]:
            return "fail", {**ev, "evidence_id": cp["version"], "reason": f"{pct}% credit exceeds {cp['max_credit_pct_without_approval']}% without approval"}
        if typ == "completed_action":
            match = [a for a in conv["action_log"] if a["type"] == kind and a["status"] == "success" and (pct is None or a.get("pct") == pct)]
            if match: return "pass", {**ev, "evidence_id": match[0]["action_id"], "reason": "matching successful action"}
            if not complete: return "referred", {**ev, "reason": "action log incomplete"}
            return "fail", {**ev, "reason": "log complete, no matching successful action"}
        # promise
        if kind == "refund" or "refund" in low:
            authorized = bool(conv["approvals"])
            sched = [s for s in conv["scheduled_actions"] if s["type"] == "refund"]
            # promise that only restates a completed refund in the same message is judged with that action
            if re.search(r"i('ve| have) (issued|refunded|processed)", low):
                return None
            if authorized and sched: return "pass", {**ev, "reason": "authorized and scheduled"}
            if not complete: return "referred", {**ev, "reason": "action log incomplete"}
            return "fail", {**ev, "reason": "refund promise without approval or scheduled action"}
        if kind == "credit":
            return None  # handled by credit limit rule above, otherwise within limits
        return "referred", {**ev, "reason": "promise type not recognised"}
    return "referred", {**ev, "reason": "unknown claim type"}

def tier2(conv, kb, t1):
    agent = [m for m in conv["messages"] if m["role"] == "agent"]
    cust = [m for m in conv["messages"] if m["role"] == "customer"]
    v = dict(t1["verdicts"]); ev = dict(t1["evidence"]); claim_results = []
    # check 1
    c1 = []
    for c in t1["claims"]:
        r = judge_claim(c, conv, kb)
        if r is None: continue
        c1.append(r); claim_results.append({"type": c["type"], "msg_id": c["msg_id"], "verdict": r[0], **r[1]})
    if not c1: v["c1"] = "pass"; ev["c1"] = {"reason": "no factual claims"}
    elif any(r[0] == "fail" for r in c1): v["c1"] = "fail"; ev["c1"] = next(r[1] for r in c1 if r[0] == "fail")
    elif any(r[0] == "kb_conflict" for r in c1): v["c1"] = "kb_conflict"; ev["c1"] = next(r[1] for r in c1 if r[0] == "kb_conflict")
    elif any(r[0] == "referred" for r in c1): v["c1"] = "referred"; ev["c1"] = next(r[1] for r in c1 if r[0] == "referred")
    else: v["c1"] = "pass"; ev["c1"] = {"reason": "all claims match sources"}
    # check 2
    if v["c2"] != "fail":
        ho = conv.get("handoff")
        reps = repeated_questions(cust)
        soft = any(SOFT_RE.search(m["text"]) for m in cust) or reps >= 2
        if soft and not ho:
            v["c2"] = "fail"; ev["c2"] = {"msg_id": next((m["id"] for m in cust if SOFT_RE.search(m["text"])), cust[-1]["id"]), "reason": "soft escalation signal and no handoff"}
        else:
            v["c2"] = "pass"; ev["c2"] = {"reason": "handoff not required or done with context"}
    # check 3
    if v["c3"] != "fail":
        bad = [m for m in agent if any(k in m["text"].lower() for k in kb.kb["sensitive_requests"]) and re.search(r"(send|share|reply with|confirm|give|provide|tell)", m["text"].lower())]
        v["c3"] = "fail" if bad else "pass"
        ev["c3"] = {"msg_id": bad[0]["id"], "reason": "agent requested sensitive data"} if bad else {"reason": "no sensitive data handled"}
    # check 4
    norms = [norm(m["text"]) for m in agent[1:]]
    loop = any(norms.count(n) >= 2 for n in set(norms))
    unanswered = None
    msgs = conv["messages"]
    for i, m in enumerate(msgs):
        if m["role"] == "customer" and ("?" in m["text"] or re.match(r"(how|what|where|why|can|is|do|does)\s", m["text"].lower())):
            nxt = next((x for x in msgs[i + 1:] if x["role"] == "agent"), None)
            if nxt is None:
                if conv.get("handoff"): continue
                unanswered = m; break
            qw = {w[:5] for w in words(m["text"])}; aw = {w[:5] for w in words(nxt["text"])}
            substantive = any(rx.search(nxt["text"]) for _, rx in CLAIM_PATTERNS) or re.search(r"\d", nxt["text"])
            need = 1 if len(qw) <= 1 else 2
            if len(qw & aw) < need and not substantive and not conv.get("handoff"):
                unanswered = m; break
    if loop or unanswered:
        v["c4"] = "fail"; ev["c4"] = {"msg_id": unanswered["id"] if unanswered else None, "reason": "agent loop" if loop else "question not answered"}
    else:
        v["c4"] = "pass"; ev["c4"] = {"reason": "questions answered"}
    # check 6
    rude = [m for m in agent if DISMISSIVE_RE.search(m["text"])]
    v["c6"] = "fail" if rude else "pass"
    ev["c6"] = {"msg_id": rude[0]["id"], "reason": "dismissive language"} if rude else {"reason": "tone ok"}
    return {"verdicts": v, "evidence": ev, "claims": claim_results}

# ---------------------------------------------------------------- timing model
def next_batch(t, interval=10):
    m = (t.minute // interval + 1) * interval
    return t.replace(minute=0, second=0, microsecond=0) + dt.timedelta(minutes=m)

def score(conv, kb, sampling, stored_decision=None, timing=None, routing="routing-v5"):
    close = ts(conv["close_at"])
    t1 = tier1(conv, kb)
    r = route(t1, conv, sampling, stored_decision, routing, kb)
    audit_flag = audit_selected(conv["closure_revision_id"], sampling["seed"], sampling["rate_pct"]) if stored_decision is None else stored_decision
    timing = timing or {}
    t1_done = timing.get("tier1") or next_batch(close) + dt.timedelta(minutes=2)
    out = {"conversation_id": conv["conversation_id"], "closure_revision_id": conv["closure_revision_id"], "routing_version": routing,
           "route": r, "audit_selected": audit_flag, "claims_t1": [c["type"] for c in t1["claims"]],
           "timestamps": {"close_at": close.isoformat(), "tier1_completed_at": t1_done.isoformat()}}
    if r == "tier1-only":
        out["verdicts"] = t1["verdicts"]; out["evidence"] = t1["evidence"]; out["tier_by_check"] = {c: (1 if t1["verdicts"][c] != "unassessed" else None) for c in CHECKS}
        out["disposition"] = "triaged_unassessed"
        out["timestamps"]["first_outcome_at"] = t1_done.isoformat()
        return out
    t2 = tier2(conv, kb, t1)
    t2_done = timing.get("tier2") or t1_done + dt.timedelta(minutes=6)
    out["timestamps"]["tier2_completed_at"] = t2_done.isoformat()
    v = t2["verdicts"]; out["verdicts"] = v; out["evidence"] = t2["evidence"]; out["claims"] = t2["claims"]
    out["tier_by_check"] = {c: (1 if t1["verdicts"][c] != "unassessed" else 2) for c in CHECKS}
    if "kb_conflict" in v.values(): out["disposition"] = "kb_conflict"
    elif "referred" in v.values():
        c = next(k for k, x in v.items() if x == "referred")
        out["disposition"] = "referred"; out["referral"] = {"check": c, "reason": out["evidence"][c]["reason"]}
        out["timestamps"]["referred_at"] = t2_done.isoformat()
    else: out["disposition"] = "full_verdict"
    out["timestamps"]["first_outcome_at"] = t2_done.isoformat()
    return out

# ---------------------------------------------------------------- QA store (dispositions, evidence versions, clusters)
class Desk:
    """QA store: one current record per closure revision, append-only audit trail,
    evidence versions, idempotent late evidence, distinct-conversation clusters."""
    CANDIDATE_THRESHOLD = 5
    CONFIRMED_THRESHOLD = 3
    def __init__(self):
        self.records = {}; self.audit = []; self.seen_keys = set(); self.alerts = []; self.incidents = {}
        self.candidate_open = set()
    def _log(self, cr, event, **kw): self.audit.append({"closure_revision_id": cr, "event": event, **kw})
    def queue_items(self): return [cr for cr, r in self.records.items() if r["in_queue"]]
    def ingest(self, result, intent, release="r-1"):
        cr = result["closure_revision_id"]
        if cr in self.records:
            self._log(cr, "duplicate_close_ignored"); return self.records[cr]
        flagged = any(v == "fail" for v in result["verdicts"].values()) or result["disposition"] in ("referred", "kb_conflict")
        rec = {"result": result, "conversation_id": result["conversation_id"], "intent": intent, "release": release,
               "status": "pending_qa" if flagged else "no_flag", "in_queue": flagged,
               "evidence_versions": [result.get("evidence", {})]}
        self.records[cr] = rec; self._log(cr, "scored", disposition=result["disposition"])
        self._check_candidates()
        return rec
    def _flag_keys(self, rec):
        keys = {(c, rec["intent"], rec["release"]) for c in CRITICAL if rec["result"]["verdicts"].get(c) == "fail"}
        if rec["status"] == "under_re_review": keys |= rec.get("confirmed_keys", set())
        return keys
    def _distinct(self, key, statuses):
        return {r["conversation_id"] for r in self.records.values() if key in self._flag_keys(r) and r["status"] in statuses}
    def _check_candidates(self):
        keys = set().union(*[self._flag_keys(r) for r in self.records.values()]) if self.records else set()
        for k in keys:
            n = len(self._distinct(k, ("pending_qa", "confirmed", "under_re_review")))
            if n >= self.CANDIDATE_THRESHOLD and k not in self.candidate_open:
                self.candidate_open.add(k); self.alerts.append({"type": "candidate_cluster", "key": k, "distinct_conversations": n, "to": "QA triage"})
    def confirmed(self, key): return self._distinct(key, ("confirmed",))
    def _recount(self):
        keys = (set().union(*[self._flag_keys(r) for r in self.records.values()]) if self.records else set()) | set(self.incidents)
        for k in keys:
            n = len(self.confirmed(k)); inc = self.incidents.get(k)
            under = self._distinct(k, ("under_re_review",))
            if n >= self.CONFIRMED_THRESHOLD and inc in (None,):
                self.incidents[k] = "open"; self.alerts.append({"type": "confirmed_cluster", "key": k, "distinct_conversations": n, "to": "Support Ops lead"})
            elif n >= self.CONFIRMED_THRESHOLD and inc == "below_threshold_under_re_review":
                self.incidents[k] = "open"; self.alerts.append({"type": "annotation", "key": k, "note": "back above threshold after re-confirmation"})
            elif inc == "below_threshold_under_re_review" and n < self.CONFIRMED_THRESHOLD and not under:
                self.incidents[k] = "below_threshold"
                self.alerts.append({"type": "annotation", "key": k, "note": "re-reviews resolved, below threshold", "notify": "Support Ops lead"})
            elif inc == "open" and n < self.CONFIRMED_THRESHOLD:
                self.incidents[k] = "below_threshold_under_re_review" if under else "below_threshold"
                self.alerts.append({"type": "annotation", "key": k, "note": "below threshold, under re-review" if under else "below threshold", "notify": "Support Ops lead"})
    def qa_dispose(self, cr, disposition):
        rec = self.records[cr]
        if disposition == "confirmed": rec["confirmed_keys"] = self._flag_keys(rec)
        rec["status"] = disposition; rec["in_queue"] = disposition in ("under_re_review",)
        self._log(cr, "qa_disposition", disposition=disposition, evidence_version=len(rec["evidence_versions"]))
        self._recount()
    def late_evidence(self, cr, evidence_id, payload, rescore_fn, arrival_late=True):
        key = (cr, evidence_id, hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        if key in self.seen_keys:
            self._log(cr, "duplicate_evidence_ignored", evidence_id=evidence_id); return "duplicate_ignored"
        self.seen_keys.add(key)
        rec = self.records[cr]; old = rec["result"]
        new = rescore_fn(payload)
        ts_keep = dict(old["timestamps"])          # earlier timestamps are never overwritten
        ts_keep["re_judged"] = True
        new["timestamps"] = ts_keep
        rec["evidence_versions"].append(new.get("evidence", {}))
        changed = (old["disposition"], old["verdicts"]) != (new["disposition"], new["verdicts"])
        rec["result"] = new
        self._log(cr, "evidence_version_added", evidence_id=evidence_id, version=len(rec["evidence_versions"]),
                  material_change=changed, late_arrival=arrival_late)
        if changed and rec["status"] in ("confirmed", "dismissed"):
            prior = rec["status"]; rec["status"] = "under_re_review"; rec["in_queue"] = True
            self._log(cr, "re_review_opened", prior_disposition=prior, reason="evidence changed")
            self._recount(); return "re_review"
        if changed:
            rec["in_queue"] = any(v == "fail" for v in new["verdicts"].values()) or new["disposition"] in ("referred", "kb_conflict")
            if rec["status"] == "pending_qa" and not rec["in_queue"]: rec["status"] = "no_flag"
            return "re_judged"
        return "stored_no_change"

def timely_relevant_referral(result, delivered_at, expected_check, reason_kw):
    close = ts(result["timestamps"]["close_at"])
    on_time = (delivered_at - close) <= dt.timedelta(minutes=60)
    ref = result.get("referral") or {}
    relevant = ref.get("check") == expected_check and reason_kw in ref.get("reason", "")
    return on_time and relevant, {"on_time": on_time, "relevant": relevant, "minutes": (delivered_at - close).total_seconds() / 60}
