"""Agent Quality Desk, Run 5 engine (PRD v8 revision 4).
The model reads (claim parts, customer needs, sensitive-data requests, resolution, tone, handoff context).
Code checks every claim part against its own evidence, applies the disagreement rules and builds the verdicts.
Input: one conversation plus the selected agent outputs for both passes. No model call happens here."""
import re, json, datetime as dt
import rules6 as R
from rules6 import KB2, ts, low, events, tools_for, log_complete, assistant_msgs, customer_msgs, durations, to_minutes, money
from qa_store import audit_selected

PIPELINE_VERSION = "desk-0.7.0"
ROUTING_VERSION = "routing-v7-statement"
CHECKS = R.CHECKS
CUSTOMER_AFFECTING = re.compile(r"refund|money|credit|charge|price|cost|fee|\$|free|discount|offer|seat|plan|eligib|qualif|access|account|waive|bill|invoice|renew|cancel", re.I)
DISALLOWED_HINT = {"paypal": "paypal", "wire": "wire", "bank wire": "wire", "gift card": "gift card", "gift cards": "gift card"}

def V(verdict, reason, evidence=None): return {"verdict": verdict, "reason": reason, "evidence_id": evidence}

# ------------------------------------------------------------------ claim part verification (deterministic)
REFUND_ACTIONS = {"money_returned", "refund", "refund_issued", "refund_sent", "refund_scheduled"}
ACTIVE = {"scheduled", "issued", "approved", "queued", "created", "pending"}
DEAD = {"cancelled", "canceled", "failed", "reversed", "rejected", "void", "expired"}

NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "fourteen": 14, "thirty": 30}
TIMING_WORDS = re.compile(r"\b(today|tomorrow|tonight|soon|shortly|within|in \w+ (business |working )?days?|next week|this week|end of|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|on (monday|tuesday|wednesday|thursday|friday)|20\d\d-\d\d-\d\d|hours?|business days?|working days?)\b")
UNKNOWN = "unknown"

def add_business_days(t0, n):
    """Explicit calendar: Monday to Friday are business days, no public holidays modelled. Day 0 is the reply date."""
    d = t0
    while n > 0:
        d += dt.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d

def promised_deadline(conv, c, f, span):
    """Latest date the promise allows, from the reply date and the stated timing. None when no timing is stated.
    UNKNOWN when timing is stated but cannot be turned into a date (for example "soon" or "in a few days")."""
    msg = next((m for m in conv["messages"] if m["message_id"] == c.get("message_id")), None)
    w = low(" ".join(str(x) for x in (f.get("when") or "", span)))
    if not TIMING_WORDS.search(w): return None
    if not msg: return UNKNOWN
    t0 = dt.date.fromisoformat(msg["at"][:10])
    if re.search(r"\b(today|tonight)\b", w): return t0
    if re.search(r"\btomorrow\b", w): return t0 + dt.timedelta(days=1)
    m = re.search(r"(?:within|in|next)\s+(\d+|" + "|".join(NUMWORDS) + r")\s+(business\s+|working\s+)?days?", w)
    if m:
        n = NUMWORDS.get(m.group(1)) or int(m.group(1))
        return add_business_days(t0, n) if m.group(2) else t0 + dt.timedelta(days=n)
    m = re.search(r"(20\d\d-\d\d-\d\d)", w)
    if m: return dt.date.fromisoformat(m.group(1))
    for k, name in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
        if re.search(r"\b(by|on|this)\s+" + name, w): return t0 + dt.timedelta(days=(k - t0.weekday()) % 7 or 7)
    return UNKNOWN

def canon_destination(x):
    x = low(str(x or "")).replace("_", " ")
    if not x: return None
    if re.search(r"workspace credit|account credit|as (a )?credit|credit (to|on) your (account|workspace)|store credit", x): return "workspace_credit"
    if re.search(r"bank|iban|transfer to your account", x): return "bank_account"
    if re.search(r"card|original payment|original method|same payment method", x): return "original_card"
    return x.replace(" ", "_")

def stated_details(f, span, act):
    """What the reply itself states, from the model fields and from the verified span, so an omitted field cannot remove a stated detail."""
    amts = [float(a.replace(",", "")) for a in re.findall(r"\$\s?(\d[\d,]*(?:\.\d+)?)", span)]
    amt = f.get("amount") if isinstance(f.get("amount"), (int, float)) and not isinstance(f.get("amount"), bool) else (amts[0] if len(set(amts)) == 1 else None)
    if f.get("destination"): dest = canon_destination(f.get("destination"))
    elif re.search(r"card|credit|bank|payment method", low(span)): dest = canon_destination(span)
    else: dest = None
    return amt, dest

def detail_status(e, amt, dest, deadline):
    """Per stated detail: 'ok', 'missing' (the action record does not say) or 'mismatch'."""
    st = {}
    if amt is not None: st["amount"] = "missing" if e.get("amount_usd") is None else ("ok" if float(e["amount_usd"]) == float(amt) else "mismatch")
    if dest is not None:
        ed = canon_destination(e.get("destination")); st["destination"] = "missing" if ed is None else ("ok" if ed == dest else "mismatch")
    if deadline is not None:
        d = e.get("issue_date") or e.get("scheduled_for") or e.get("issued_on") or e.get("due_date")
        if deadline == UNKNOWN: st["timing"] = "missing"
        elif not d: st["timing"] = "missing"
        else:
            try: st["timing"] = "ok" if dt.date.fromisoformat(str(d)[:10]) <= deadline else "mismatch"
            except ValueError: st["timing"] = "missing"
    return st

def verify_commitment(conv, c, f, act, amt, span, complete):
    """A promise is verified only by a live action that carries evidence for every detail the reply states (amount, destination, timing)
    and, for money, an approval for the same amount that the action is linked to. A contradicted detail fails. A stated detail the record
    cannot confirm (no date, no destination, timing that cannot be dated) is referred. A cancelled action never verifies a promise."""
    evs = conv["action_events"]; money = act in REFUND_ACTIONS or (act == "other" and re.search(r"refund|money back|your \$", low(span)))
    amt, dest = stated_details(f, span, act); deadline = promised_deadline(conv, c, f, span)
    stated = [k for k, v in (("amount", amt), ("destination", dest), ("timing", deadline)) if v is not None]
    def describe(e, stt): return f"{e['type']} {e['record_id']}: " + ", ".join(f"{k} {v}" for k, v in sorted(stt.items()) if v != "ok")
    if money:
        appr = [e for e in evs if e["type"] == "refund_approval" and e.get("status") == "approved" and (amt is None or e.get("amount_usd") == amt)]
        acts = [e for e in evs if e["type"] in ("refund_schedule", "refund_issue")]
        def linked(e): return any((not e.get("approval_id") or e["approval_id"] == a["record_id"]) and (a.get("amount_usd") is None or a["amount_usd"] == e.get("amount_usd"))
                                  and (not a.get("destination") or not e.get("destination") or canon_destination(a["destination"]) == canon_destination(e["destination"])) for a in appr)
        live = [(e, detail_status(e, amt, dest, deadline)) for e in acts if e.get("status") in ("scheduled", "issued") and linked(e)]
        full = [e for e, stt in live if all(v == "ok" for v in stt.values())]
        if full: return V("pass", "approved, and a live linked schedule or issue confirms every stated detail (" + (", ".join(stated) or "none stated") + ")", full[0]["record_id"])
        unresolved = [(e, stt) for e, stt in live if "mismatch" not in stt.values()]
        if appr and unresolved:
            e, stt = unresolved[0]; return V("referred", "stated detail not confirmed by the action record: " + describe(e, stt), e["record_id"])
        why = [] if appr else ["no approval for this amount"]
        why += [describe(e, stt) for e, stt in live if "mismatch" in stt.values()]
        why += [f"{e['type']} {e['record_id']} is {e.get('status')}" for e in acts if e.get("status") in DEAD]
        why += [f"{e['type']} {e['record_id']} not linked to an approval for this amount" for e in acts if e.get("status") in ("scheduled", "issued") and not linked(e)]
        if not acts: why.append("no schedule or issue event")
        bad = [e for e in acts]
        if complete: return V("fail", "promise not supported: " + ", ".join(why) + " (refund-ops-v2)", bad[0]["record_id"] if bad else None)
        return V("referred", "action log incomplete: " + ", ".join(why))
    dest = None  # destination is a money-movement detail. A credit or contact promise is checked on amount and timing
    stated = [k for k, v in (("amount", amt), ("timing", deadline)) if v is not None]
    stem = act.split("_")[0] if act != "other" else None
    cand = [e for e in evs if (stem and stem in e["type"]) or (not stem and e.get("for_reply") == c.get("message_id"))]
    live = [(e, detail_status(e, amt, dest, deadline)) for e in cand if e.get("status") in ACTIVE]
    full = [e for e, stt in live if all(v == "ok" for v in stt.values())]
    if full: return V("pass", f"live {full[0]['type']} confirms every stated detail (" + (", ".join(stated) or "none stated") + ")", full[0]["record_id"])
    unresolved = [(e, stt) for e, stt in live if "mismatch" not in stt.values()]
    if unresolved:
        e, stt = unresolved[0]; return V("referred", "stated detail not confirmed by the action record: " + describe(e, stt), e["record_id"])
    dead = [e for e in cand if e.get("status") in DEAD]
    ref = (dead or [e for e, _ in live])
    if complete: return V("fail", f"{act} promised, " + ("matching action is " + dead[0]["status"] if dead else ("live action contradicts a stated detail" if live else "no live matching action recorded")), ref[0]["record_id"] if ref else None)
    return V("referred", "action log incomplete")

def verify_part(conv, kb, c):
    """Returns a verdict dict or None (no verifiable content and not customer-affecting)."""
    msg = next((m for m in conv["messages"] if m["message_id"] == c["message_id"]), None)
    if msg is None: return V("referred", "model cited a message that does not exist")
    at = ts(msg["at"]); f = c.get("fields") or {}; pt = c["part_type"]; span = c.get("span", ""); t = low(span)
    tools = tools_for(conv, c["message_id"]) or conv["tool_results"]; complete = log_complete(conv, at)
    tool = lambda name: next((x for x in tools if x["tool"] == name), None)
    unit = kb.kb["price_pro_per_seat_usd"]["value"]

    if pt == "price":
        amt = f.get("amount"); period = f.get("period", "none"); per = f.get("unit", "none")
        if not isinstance(amt, (int, float)):
            am = money(span); amt = am[0] if am else None
        if amt is None: return V("referred", "price with no amount")
        if per in ("seat", "user"):
            want = unit * 12 if period == "year" else unit
            return V("pass" if amt == want else "fail", f"${R.fmt(amt)} per seat per {period if period != 'none' else 'month (no period stated)'} vs price-v3 ${unit} per seat per month", "price-v3")
        inv = tool("invoice_lookup")
        if inv and inv["result"].get("total_before_tax_usd") is not None:
            return V("pass" if amt == inv["result"]["total_before_tax_usd"] else "fail", f"${R.fmt(amt)} vs invoice tool total {inv['result']['total_before_tax_usd']}", inv["record_id"])
        m = re.search(r"(\d+)\s+(?:pro\s+)?seats?", t)
        if m: return V("pass" if amt == int(m.group(1)) * unit else "fail", f"{m.group(1)} seats at ${unit} vs ${R.fmt(amt)}", "price-v3")
        return V("referred", "missing tool result" if inv else "price with no unit or supporting record")

    if pt in ("offer_or_eligibility", "offer", "eligibility"):
        d = low(f.get("description", "") + " " + span)
        if re.search(r"refund", d) and durations(d):
            return verify_part(conv, kb, {**c, "part_type": "policy_term", "fields": {"topic": "refund_window", "value": d}})
        return V("referred", "unsupported claim part: no source grants this offer or eligibility")

    if pt == "policy_term":
        topic = f.get("topic", "other"); val = low(str(f.get("value", "")) + " " + span); neg = bool(f.get("negated"))
        if topic == "refund_window":
            days = [R.to_days(v, u) for v, u in durations(val) if u not in ("minute", "hour", "business day")]
            if not days: return V("referred", "refund window with no duration")
            pol, hlp = kb.refund_policy(at), kb.refund_help(at)
            kbc = next((x for x in conv["tool_results"] if x["tool"] == "kb_lookup" and "authoritative" in low(x["result"].get("finding", "")) and len(x["result"].get("document_ids", [])) >= 2), None)
            if kbc and hlp and hlp["annual_full_refund_days"] != pol["annual_full_refund_days"]:
                return V("kb_conflict", f"{pol['version']} says {pol['annual_full_refund_days']} days, {hlp['version']} says {hlp['annual_full_refund_days']}, both marked authoritative", kbc["record_id"])
            if re.search(r"\b(page|help center|help centre|article)\b|it says", val) and hlp:
                return V("pass" if days[0] == hlp["annual_full_refund_days"] else "fail", f"quotes {hlp['version']} ({hlp['annual_full_refund_days']} days)", hlp["version"])
            return V("pass" if days[0] == pol["annual_full_refund_days"] else "fail", f"{days[0]} days vs {pol['version']} {pol['annual_full_refund_days']} days", pol["version"])
        if topic == "monthly_refund":
            ok = re.search(r"approv|billing manager|request", val) and not re.search(r"automatic|comes back|without", val)
            return V("pass" if ok else "fail", "monthly charges need a billing manager's approval (refund-v4)", "refund-v4")
        if topic == "cancellation_fee":
            ok = re.search(r"\bno\b|none|free|\$0|isn't|is not|there's no", val) and not money(val.replace("$0", ""))
            return V("pass" if ok else "fail", "cancellation-v2: no early termination fee", "cancellation-v2")
        if topic == "cancellation_effect":
            bad = re.search(r"refund|money back|balance|returned|comes back|show up|credited", val) and not re.search(r"(doesn't|does not|won't|will not|no|not)\b[^.]{0,30}(refund|money)", val)
            return V("fail" if bad else "pass", "cancellation-v2: access continues to the end of the paid period, cancellation alone does not refund", "cancellation-v2")
        if topic in ("payment_methods_accepted", "payment_methods_not_accepted"):
            pm = kb.kb["payment_methods"]; named_ok = [b for b in pm["allowed"] if b in val]
            named_bad = sorted({v for k, v in DISALLOWED_HINT.items() if re.search(r"\b" + k + r"\b", val)})
            if topic == "payment_methods_accepted" and not neg:
                return V("fail" if named_bad else "pass", ("offers unavailable methods: " + ", ".join(named_bad)) if named_bad else "accepted methods match billing-v3", "billing-v3")
            return V("fail" if named_ok else "pass", ("says an accepted method is unavailable: " + ", ".join(named_ok)) if named_ok else "unavailable methods match billing-v3", "billing-v3")
        if topic == "link_validity":
            mins = [to_minutes(v, u) for v, u in durations(val) if u in ("minute", "hour", "day")]
            if not mins: return V("referred", "link validity with no duration")
            kind = "verification" if re.search(r"verif|sign-?up|create", val) else "password"
            want = kb.kb["link_validity_minutes"][kind]["value"]
            return V("pass" if mins[0] == want else "fail", f"{mins[0]} minutes vs {want} minutes", kb.kb["link_validity_minutes"][kind]["version"])
        if topic == "device_limit":
            lim = DEVICE_LIMIT_CLAIM.search(val) or (f.get("negated") and re.search(r"two|both|more than one|multiple|another", val))
            return V("fail" if lim else "pass", "profile-v2: no device limit", "profile-v2")
        if topic == "refund_posting_time":
            ok = re.search(r"(5|five)\s*(to|-|–)\s*(10|ten) business days", val)
            return V("pass" if ok else "fail", "refund-ops-v2: 5 to 10 business days once issued", "refund-ops-v2")
        if topic == "deletion_rule":
            bad = re.search(r"ignore|skip|no need|bypass|without confirm", val)
            return V("fail" if bad else "pass", "delete-v2: confirmation required, sole owner transfers ownership first", "delete-v2")
        return V("referred", "no authoritative source for this policy statement") if CUSTOMER_AFFECTING.search(val) else None

    if pt == "account_fact":
        topic = f.get("topic", "other"); val = low(str(f.get("value", "")) + " " + span)
        inv = tool("invoice_lookup")
        if topic in ("invoice_total", "seat_count", "per_seat_billed"):
            if not inv or inv["result"].get("error") or inv["result"].get("total_before_tax_usd") is None:
                return V("referred", "missing tool result", inv["record_id"] if inv else None)
            r = inv["result"]
            if topic == "seat_count":
                n = re.findall(r"\d+", val); return V("pass" if n and int(n[0]) == r["pro_seats"] else "fail", f"seat count vs invoice tool {r['pro_seats']}", inv["record_id"])
            a = money(val) or [float(x) for x in re.findall(r"\d+(?:\.\d+)?", val)][:1]
            want = r["total_before_tax_usd"] if topic == "invoice_total" else r.get("per_seat_usd", unit)
            return V("pass" if a and a[0] == want else "fail", f"stated {a[0] if a else '?'} vs invoice tool {want}", inv["record_id"])
        if topic == "role":
            role = next((x["result"].get("role") for x in conv["tool_results"] if "role" in x["result"]), None)
            if role is None: return V("referred", "missing tool result")
            said = "sole_workspace_owner" if re.search(r"only owner|sole owner|only .*owner", val) else "workspace_owner" if "owner" in val else "workspace_member" if "member" in val else None
            ok = said == role or (said == "workspace_owner" and role == "sole_workspace_owner")
            return V("pass" if ok else "fail", f"stated {said} vs tool {role}", None)
        if topic == "email_status":
            acc = next((x for x in conv["tool_results"] if "email_change_status" in x["result"]), None)
            if not acc: return V("referred", "missing tool result")
            st = acc["result"]["email_change_status"]; said_done = bool(re.search(r"verified|active|done|changed|updated", val)) and not re.search(r"pending|not yet|once you|after you", val)
            return V("pass" if said_done == (st in ("verified", "active")) else "fail", f"email change status {st}", acc["record_id"])
        if topic == "registration_status":
            reg = tool("registration_lookup") or next((x for x in conv["tool_results"] if x["tool"] == "registration_lookup"), None)
            if not reg: return V("referred", "missing tool result")
            err = reg["result"].get("error", ""); key = "expired" if "expired" in val else "registered" if re.search(r"already|registered|has an account", val) else None
            return V("pass" if key and key in err else "fail", f"registration state vs tool ({err})", reg["record_id"])
        if topic == "charge_count":
            ch = next((x for x in conv["tool_results"] if x["tool"] == "charge_lookup"), None)
            if not ch: return V("referred", "missing tool result")
            n = len(ch["result"].get("posted_charge_amounts_usd", [])); said_one = bool(re.search(r"once|one charge|single|only one|went through once", val)); said_none = bool(re.search(r"no charge|nothing was charged|not charged", val))
            ok = (said_one and n == 1) or (said_none and n == 0) or (not said_one and not said_none and re.search(r"two|twice|both|duplicate", val) and n >= 2)
            return V("pass" if ok else "fail", f"charge_lookup shows {n} posted charges", ch["record_id"])
        if topic in ("refund_status", "refund_amount", "refund_date"):
            evs = conv["action_events"]; rl = next((x for x in conv["tool_results"] if x["tool"] == "refund_lookup"), None)
            status = (rl or {}).get("result", {}).get("status")
            if "approved" in val or "signed off" in val:
                appr = [e for e in evs if e["type"] == "refund_approval" and e.get("status") == "approved"]
                denied = [e for e in evs if e.get("status") in ("denied", "declined")] or status in ("declined", "requested")
                if appr and not denied: return V("pass", "approval event", appr[0]["record_id"])
                return V("fail" if (denied or complete) else "referred", "approval claimed, records show " + (status or "no approval"), (rl or {}).get("record_id"))
            if re.search(r"issued|sent|on its way", val):
                d = R.parse_date(val); iss = [e for e in evs if e["type"] == "refund_issue" and (d is None or e.get("issued_on") == d)]
                if iss: return V("pass", "issue event matches", iss[0]["record_id"])
                return V("fail" if complete else "referred", "issue claimed, no matching issue event" if complete else "action log incomplete")
            if "scheduled" in val:
                d = R.parse_date(val); sch = [e for e in evs if e["type"] == "refund_schedule" and (d is None or e.get("issue_date") == d)]
                if sch: return V("pass", "schedule event matches", sch[0]["record_id"])
                return V("fail" if complete else "referred", "schedule claimed, none recorded" if complete else "action log incomplete")
            if re.search(r"declin|denied", val): return V("pass" if status == "declined" or any(e.get("status") in ("denied", "declined") for e in evs) else "fail", "decline vs records", (rl or {}).get("record_id"))
            if re.search(r"received|requested|submitted|logged", val):
                ok = any(e["type"] == "refund_request" for e in evs) or status == "requested"
                return V("pass" if ok else ("fail" if complete else "referred"), "request receipt vs records")
            return V("referred", "refund status not verifiable from the records")
        if topic == "lookup_failed":
            ok = any("unavailable" in json.dumps(x["result"]) or "error" in x["result"] for x in conv["tool_results"])
            return V("pass" if ok else "fail", "lookup failure vs tool record")
        return V("referred", "account fact with no supporting record") if CUSTOMER_AFFECTING.search(val) else None

    if pt == "completed_action":
        act = f.get("action", "other"); evs = conv["action_events"]; amt = f.get("amount")
        if act in ("refund_issued", "refund_sent"):
            iss = [e for e in evs if e["type"] == "refund_issue" and e.get("status") == "issued" and (not isinstance(amt, (int, float)) or e.get("amount_usd") == amt)]
            if iss: return V("pass", "matching refund issue event", iss[0]["record_id"])
            return V("fail" if complete else "referred", "refund issue claimed, log complete, no issue event" if complete else "action log incomplete")
        if act == "refund_approved":
            ap = [e for e in evs if e["type"] == "refund_approval" and e.get("status") == "approved"]
            return V("pass", "approval event", ap[0]["record_id"]) if ap else V("fail" if complete else "referred", "approval claimed, none recorded" if complete else "action log incomplete")
        if act == "account_deleted":
            dn = [e for e in evs if e["type"] in ("deletion", "deletion_request") and e.get("status") in ("deleted", "completed")]
            return V("pass", "deletion recorded", dn[0]["record_id"]) if dn else V("fail" if complete else "referred", "deletion claimed, no completed deletion" if complete else "action log incomplete")
        if act == "email_changed":
            return verify_part(conv, kb, {**c, "part_type": "account_fact", "fields": {"topic": "email_status", "value": "changed"}})
        ev = [e for e in evs if act != "other" and act.split("_")[0] in e["type"]]
        if act == "other":  # match on the event recorded for this reply, or an event whose type or status words appear in the claim
            sp = low(span); words = lambda e: set(e["type"].split("_")) | {str(e.get("status", ""))}
            ev = [e for e in evs if e.get("for_reply") == c.get("message_id") and (words(e) & set(re.findall(r"[a-z]+", sp)))] or \
                 [e for e in evs if {"request", "received"} & words(e) and re.search(r"request|received|submitted", sp) and e["type"].split("_")[0] in sp + " refund" * ("refund" in sp)]
        return V("pass", "matching event", ev[0]["record_id"]) if ev else V("fail" if complete else "referred", f"{act} claimed, none recorded" if complete else "action log incomplete")

    if pt == "future_promise":
        evs = conv["action_events"]; amt = f.get("amount"); act = f.get("action", "other")
        if act == "other" and not isinstance(amt, (int, float)) and not OUTCOME_PROMISE.search(low(span)):
            return V("pass", "commitment to an in-chat step, no customer outcome promised", None)
        return verify_commitment(conv, c, f, act, amt, span, complete)

    if pt == "procedure":
        path = (f.get("path") or "").strip(); purpose = f.get("purpose", "")
        if ">" in path:
            known = [k for k in kb.kb["paths"] if k["path"].lower().startswith(path.lower().rstrip(".")) or path.lower().startswith(k["path"].lower())]
            extra = [x for x in conv["tool_results"] if path.lower() in low(json.dumps(x["result"]))]
            ptop = set(R.topics_of(purpose, kb)) - {"payment", "human", "price"}
            if known:
                kt = set(sum([k["topics"] for k in known], []))
                if ptop and not (ptop & kt) and not ({"refund", "refund_status"} & ptop and {"refund", "refund_status"} & kt):
                    return V("fail", f"'{path}' is documented for {sorted(kt)}, not {sorted(ptop)}", known[0]["version"])
                return V("pass", f"'{path}' matches help content", known[0]["version"])
            if extra: return V("pass", f"'{path}' from tool record", extra[0]["record_id"])
            last = low(path.split(">")[-1]).strip(" .")
            if last in kb.kb["ui_labels"]: return V("pass", f"UI step '{last}' exists", None)
            return V("fail", f"'{path}' is not in the help content")
        lbl = low(path or span)
        if "picker" in lbl and re.search(r"(another|different|separate|other)\s+(account|login)", low(purpose + " " + span)):
            return V("fail", "the workspace picker switches workspaces within one account. A different account needs Sign out (profile-v2)", "profile-v2")
        if re.search(r"(ignore|skip|bypass)\s+(the\s+)?confirm|no need to (verify|confirm)|(delete|ignore) the verification", low(span)):
            return V("fail", "contradicts a required confirmation or verification step (delete-v2, profile-v2)")
        for k in kb.kb["ui_labels"]:
            if k in lbl: return V("pass", f"UI step '{k}' exists", None)
        return None  # a troubleshooting suggestion with no documented step to check

    if pt == "handoff_claim":
        kind = f.get("kind", "queued"); ho = events(conv, "handoff"); joined = [e for e in conv["action_events"] if e["type"] in ("agent_joined", "handoff_accepted")]
        if not ho: return V("fail" if complete else "referred", "handoff claimed, no handoff event" if complete else "action log incomplete")
        if kind == "agent_joined":
            return V("pass", "agent joined event", joined[0]["record_id"]) if joined else V("fail" if complete else "referred", "a queued transfer does not verify that an agent has joined" if complete else "action log incomplete")
        q = low(f.get("queue", "") or "")
        if "billing" in q and ho[0].get("queue") != "billing": return V("fail", f"said billing, handoff queue is {ho[0].get('queue')}", ho[0]["record_id"])
        if kind == "context_included" and not ho[0].get("context"): return V("fail", "said context was included, handoff context is empty", ho[0]["record_id"])
        return V("pass", f"handoff event ({ho[0].get('queue')})", ho[0]["record_id"])

    # capability or other
    return V("referred", "customer-affecting statement with no verifiable type") if pt == "other" and re.search(r"refund|money|credit|free|discount|waive|charge|\$", t) else None

# ------------------------------------------------------------------ combining both passes
def norm(s): return re.sub(r"\W+", " ", low(s)).strip()

def match_parts(a, b):
    """Greedy one-to-one match between two passes' claim parts: same message ID and part type, and the normalised spans overlap
    by at least half of the shorter span's words (or one contains the other). Returns matched pairs and unmatched indices."""
    used, pairs = set(), []
    for i, x in enumerate(a):
        wx = set(norm(x.get("span", "")).split())
        best = None
        for j, y in enumerate(b):
            if j in used or x["message_id"] != y["message_id"] or x["part_type"] != y["part_type"]: continue
            wy = set(norm(y.get("span", "")).split())
            if not wx or not wy: continue
            ov = len(wx & wy) / min(len(wx), len(wy))
            if ov >= 0.5 or norm(x["span"]) in norm(y["span"]) or norm(y["span"]) in norm(x["span"]):
                if best is None or ov > best[1]: best = (j, ov)
        if best: used.add(best[0]); pairs.append((i, best[0]))
    ua = [i for i in range(len(a)) if i not in {p[0] for p in pairs}]; ub = [j for j in range(len(b)) if j not in used]
    return pairs, ua, ub

OUTCOME_PROMISE = re.compile(r"refund|credit|money|waive|cancel|reverse|remove the charge|fix|resolve|send you|email you|call you|contact you|get back to you|follow up|by (monday|tuesday|wednesday|thursday|friday|tomorrow|end of)|within \d")
DEVICE_LIMIT_CLAIM = re.compile(r"(limit\w*|restrict\w*|only|just|max\w*|at most|up to|no more than)\b[^.]{0,25}\b(one|1|two|2|three|3|four|4|five|5|a single|\d+)\b[^.]{0,20}\bdevices?|one (active |signed-in )?device (per|at a time)|(sign|log) out (of|on) the other|(can't|cannot|can not|won't) (stay |be )?(signed|logged) in on (two|both|more|multiple)")

def handoff_required(needs):
    kinds = [n["need"] for n in needs]
    trig = sorted({k for k in kinds if k in ("explicit_request_for_person", "billing_dispute", "duplicate_or_unrecognised_charge", "legal_threat", "safety_issue")})
    if kinds.count("failed_attempt") >= 2: trig.append("repeated_failure")
    return bool(trig), trig

def combine(conv, kb, ex, jd=None, sampling=None):
    """ex, jd: {1: case output or None, 2: ...}. Returns the result dict. Deterministic."""
    red = R.redact(conv); kb2 = kb
    t1 = R.tier1(red, kb2)
    route = R.route(t1, red, kb2, sampling)
    out = {"conversation_id": conv["case_id"], "closure_revision_id": conv["closure_revision_id"], "routing_version": ROUTING_VERSION, "route": route,
           "audit_selected": audit_selected(conv["closure_revision_id"], sampling["seed"], sampling["rate_pct"]), "pipeline_version": PIPELINE_VERSION}
    v, ev = {}, {}
    invalid = [p for p in (1, 2) if ex.get(p) is None]
    # ---------- claims: union of both passes plus the code cross-check
    p1, p2 = (ex.get(1) or {}).get("claims", []), (ex.get(2) or {}).get("claims", [])
    pairs, u1, u2 = match_parts(p1, p2)
    # every interpretation is verified: a matched pair contributes both passes' parts, merged only when the normalised part is identical
    key = lambda c: (c["message_id"], c["part_type"], norm(c.get("span", "")), json.dumps(c.get("fields") or {}, sort_keys=True))
    parts = []
    for i, j in pairs:
        a, b = dict(p1[i], found_by="both passes"), dict(p2[j], found_by="both passes")
        if key(a) == key(b): parts.append(a)
        else: parts += [dict(a, found_by="both passes, interpretations differ"), dict(b, found_by="both passes, interpretations differ")]
    parts += [dict(p1[i], found_by="pass 1 only") for i in u1] + [dict(p2[j], found_by="pass 2 only") for j in u2]
    parts.sort(key=key)
    claims = []
    for c in parts:
        r = verify_part(red, kb2, c)
        if r: claims.append({**{k: c.get(k) for k in ("message_id", "part_type", "span", "fields", "found_by")}, **r})
    cross = R.extract_a(red); covered = set()
    for (mid, i), info in cross.items():
        sent = info["text"]
        if any(c["message_id"] == mid and (norm(c.get("span", "")) in norm(sent) or norm(sent) in norm(c.get("span", "")) or len(set(norm(c.get("span", "")).split()) & set(norm(sent).split())) >= 3) for c in parts): covered.add((mid, i)); continue
        rr = R.judge_sentence(red, kb2, mid, sent)
        for verdict, reason, eid, _ in rr:
            claims.append({"message_id": mid, "part_type": "cross_check", "span": sent, "found_by": "code cross-check only", "verdict": verdict, "reason": reason, "evidence_id": eid})
        if not rr and R.POLICY_WORDS.search(sent):
            claims.append({"message_id": mid, "part_type": "cross_check", "span": sent, "found_by": "code cross-check only", "verdict": "referred", "reason": "claim found only by the code cross-check could not be verified", "evidence_id": None})
    out["extractor_record"] = {"model_pass_1": p1, "model_pass_2": p2, "matched": len(pairs), "pass_1_only": len(u1), "pass_2_only": len(u2),
                               "cross_check": [{"msg_id": k[0], "sentence": x["text"], "covered_by_model": k in covered} for k, x in sorted(cross.items())],
                               "disagreements": [{"msg_id": c["message_id"], "sentence": c["span"], "found_by": c["found_by"], "resolution": "verified: " + c["verdict"]} for c in claims if c["found_by"] != "both passes"],
                               "claims": claims, "invalid_passes": invalid}
    order = {"fail": 0, "kb_conflict": 1, "referred": 2, "pass": 3}
    if invalid and not claims:
        v["c1"] = "referred"; ev["c1"] = {"reason": "model output invalid"}
    elif not claims:
        sig = t1["money_signal"] and any(R.declarative(m["text"]) for m in assistant_msgs(red))
        v["c1"] = "referred" if sig else "pass"; ev["c1"] = {"reason": "possible unextracted claim" if sig else "no claims, no money or policy signal"}
    else:
        top = min(claims, key=lambda c: (order[c["verdict"]], c["message_id"], c["part_type"], norm(c.get("span", "")), json.dumps(c.get("fields") or {}, sort_keys=True), c["reason"]))
        v["c1"] = top["verdict"]; ev["c1"] = {"msg_id": top["message_id"], "reason": top["reason"], "evidence_id": top.get("evidence_id"), "span": top["span"]}
        if invalid and v["c1"] == "pass": v["c1"] = "referred"; ev["c1"] = {"reason": "model output invalid on one pass"}
    out["claim_verdicts"] = claims
    # ---------- check 2: handoff need from both passes, handoff record from code
    n1, n2 = (ex.get(1) or {}).get("needs", []), (ex.get(2) or {}).get("needs", [])
    r1, tr1 = handoff_required(n1); r2, tr2 = handoff_required(n2)
    ho = events(red, "handoff"); req_dispute = any(t in ("billing_dispute", "duplicate_or_unrecognised_charge") for t in tr1 + tr2)
    req_legal_safety = any(t in ("legal_threat", "safety_issue") for t in tr1 + tr2)  # legal and safety outrank the billing-queue rule
    jctx = [(jd or {}).get(p, {}) and (jd or {}).get(p, {}).get("handoff_context") for p in (1, 2)]
    if t1["verdicts"]["c2"] == "fail" and False: pass
    if invalid: v["c2"] = "referred"; ev["c2"] = {"reason": "model output invalid"}
    elif r1 != r2: v["c2"] = "referred"; ev["c2"] = {"reason": f"model disagreement on whether a handoff was required (pass 1 {tr1 or 'none'}, pass 2 {tr2 or 'none'})"}
    elif not r1: v["c2"] = "pass"; ev["c2"] = {"reason": "no handoff required"}
    elif not ho: v["c2"] = "fail"; ev["c2"] = {"reason": f"handoff required ({', '.join(sorted(set(tr1)))}) and no handoff event"}
    elif req_dispute and not req_legal_safety and ho[0].get("queue") != "billing": v["c2"] = "fail"; ev["c2"] = {"reason": "billing dispute not sent to the billing queue", "evidence_id": ho[0]["record_id"]}
    elif not ho[0].get("context"): v["c2"] = "fail"; ev["c2"] = {"reason": "handoff with empty context", "evidence_id": ho[0]["record_id"]}
    elif any(x not in ("covers", "missing") for x in jctx): v["c2"] = "referred"; ev["c2"] = {"reason": f"handoff required, context coverage judgement missing or invalid (pass 1 {jctx[0]}, pass 2 {jctx[1]})", "evidence_id": ho[0]["record_id"]}
    elif jctx[0] != jctx[1]: v["c2"] = "referred"; ev["c2"] = {"reason": "model disagreement on whether the handoff context covers the need", "evidence_id": ho[0]["record_id"]}
    elif jctx[0] == "missing": v["c2"] = "fail"; ev["c2"] = {"reason": "handoff context leaves out the customer's issue", "evidence_id": ho[0]["record_id"]}
    else: v["c2"] = "pass"; ev["c2"] = {"reason": "handoff required and done, both passes say the context covers the need", "evidence_id": ho[0]["record_id"]}
    # ---------- check 3: masked card data (code), sensitive requests (model, with code as tie-break)
    s1 = {(x["message_id"], x["data_type"]) for x in (ex.get(1) or {}).get("sensitive_requests", [])}
    s2 = {(x["message_id"], x["data_type"]) for x in (ex.get(2) or {}).get("sensitive_requests", [])}
    code_flag = next((m for m in assistant_msgs(red) if R.sensitive_request(m["text"], kb2)), None)
    if t1["verdicts"]["c3"] == "fail": v["c3"] = "fail"; ev["c3"] = t1["evidence"]["c3"]
    elif s1 and s2: x = sorted(s1 | s2)[0]; v["c3"] = "fail"; ev["c3"] = {"msg_id": x[0], "reason": f"assistant requested sensitive data ({x[1]}), both passes"}
    elif (s1 or s2) and code_flag: x = sorted(s1 | s2)[0]; v["c3"] = "fail"; ev["c3"] = {"msg_id": x[0], "reason": f"assistant requested sensitive data ({x[1]}), one pass plus code check"}
    elif s1 or s2: v["c3"] = "referred"; ev["c3"] = {"reason": "model disagreement on a sensitive-data request"}
    elif invalid: v["c3"] = "referred"; ev["c3"] = {"reason": "model output invalid"}
    else: v["c3"] = "pass"; ev["c3"] = {"reason": "no sensitive data requested or repeated"}
    # ---------- check 5: deterministic
    v["c5"] = t1["verdicts"]["c5"]; ev["c5"] = t1["evidence"]["c5"]
    # ---------- checks 4 and 6: judge passes
    for ck, key, bad in (("c4", "resolution", "no"), ("c6", "tone", "problem")):
        if not jd: v[ck] = "unassessed"; ev[ck] = {"reason": "judge not run"}; continue
        a, b = [((jd or {}).get(p) or {}).get(key) for p in (1, 2)]
        if not a or not b: v[ck] = "referred"; ev[ck] = {"reason": "model output invalid"}
        elif a["value"] != b["value"]: v[ck] = "referred"; ev[ck] = {"reason": f"model disagreement on {key}"}
        else: v[ck] = "fail" if a["value"] == bad else "pass"; ev[ck] = {"msg_id": a.get("message_id"), "reason": a.get("reason")}
    out["verdicts"] = v; out["evidence"] = ev
    out["needs"] = {"pass_1": n1, "pass_2": n2, "handoff_required": [r1, r2]}
    out["sensitive"] = {"pass_1": (ex.get(1) or {}).get("sensitive_requests", []), "pass_2": (ex.get(2) or {}).get("sensitive_requests", [])}
    fails = [c for c in CHECKS if v[c] == "fail"]; refs = [c for c in CHECKS if v[c] == "referred"]; kbc = [c for c in CHECKS if v[c] == "kb_conflict"]
    out["disposition"] = {"fails": fails, "referred": refs, "kb_conflict": kbc}  # a confirmed defect stays visible next to any referral
    out["referral"] = [{"check": c, "reason": ev[c].get("reason")} for c in refs]
    return out

def judge_extras(result, conv):
    """Text appended to each case in the judge request: verified claim verdicts and the redacted handoff record (event, queue, status, time, context)."""
    lines = ["CLAIM VERDICTS (checked by code):"]
    for c in result["claim_verdicts"]: lines.append(f"- {c['message_id']} \"{c['span']}\": {c['verdict']} ({c['reason']})")
    if len(lines) == 1: lines.append("- none")
    lines.append("HANDOFF RECORD (from the action log, masked):")
    ho = events(R.redact(conv), "handoff")
    for e in ho: lines.append(f"- {e['record_id']} at {e.get('at')} for reply {e.get('for_reply')}: queue {e.get('queue')}, status {e.get('status')}, context: \"{e.get('context') or ''}\"")
    if not ho: lines.append("- none")
    return "\n".join(lines)

def store_view(result):
    """The record the Phase 0 QA store ingests. The store keeps one disposition label per case, so a case with any referral or KB conflict is queued,
    while the result itself keeps every confirmed failure next to the referral."""
    d = result["disposition"]
    label = "kb_conflict" if d["kb_conflict"] else "referred" if d["referred"] else "full_verdict"
    return {**result, "disposition": label, "disposition_detail": d}
