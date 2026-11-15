"""Agent Quality Desk - Run 4 engine, lock 3 (PRD v7, feedback on reports v3 to v5 applied).

Deterministic stand-ins for tier 1 and tier 2, not model calls.
New in Run 3: holdout v2 schema, KB compiled from the v2 policies, two independent claim
extractors with a disagreement record, empty-claim-list referral on money or policy
conversations, routing-v6 plus R-money, multi-defect scoring.
The QA store, timing and referral-delivery layer is imported unchanged from Phase 0 desk.py.
"""
import re, json, hashlib, datetime as dt, sys, pathlib

from qa_store import Desk, timely_relevant_referral, audit_selected, next_batch  # Phase 0 QA store and timing layer, unchanged

PIPELINE_VERSION = "desk-0.6.3"
TIER1_VERSION = "t1-rules-0.6"
TIER2_VERSION = "t2-parse-0.6"
ROUTING_VERSION = "routing-v7-statement"
MODEL_VERSION = "none (deterministic stand-ins)"
PROMPT_VERSION = "none"
RUBRIC_VERSION = "PRD v7 + holdout v2 label conventions"
CHECKS = ["c1", "c2", "c3", "c4", "c5", "c6"]
CRITICAL = ["c1", "c2", "c3"]

def ts(s): return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
def low(s): return s.lower().replace("’", "'")

class KB2:
    def __init__(self, kb): self.kb = kb
    def refund_policy(self, at):
        live = [v for v in self.kb["refund_policy"] if ts(v["effective"]) <= at]
        return sorted(live, key=lambda v: v["effective"])[-1]
    def refund_help(self, at):
        live = [v for v in self.kb["refund_help"] if ts(v["effective"]) <= at]
        return sorted(live, key=lambda v: v["effective"])[-1] if live else None

# ------------------------------------------------------------------ text helpers
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
       "twelve": 12, "fourteen": 14, "fifteen": 15, "twenty": 20, "thirty": 30, "forty-five": 45, "sixty": 60, "ninety": 90, "a": 1, "an": 1}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
STOP = set("a an the i you we our your my me it is are be to of for on in and or can do does how what where why when "
           "please thanks thank there this that with about get got have has just so any all now again was from use try".split())

def sentences(text): return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
def cwords(text): return {w for w in re.findall(r"[a-z]+", low(text)) if w not in STOP and len(w) > 2}

def durations(t):
    out = []
    for n, u in re.findall(r"\b(\d+|[a-z\-]+)[\s-]+(calendar day|business day|day|minute|hour|week)s?\b", t):
        v = int(n) if n.isdigit() else NUM.get(n)
        if v is None: continue
        out.append((v, u))
    return out

def to_minutes(v, u): return v * {"minute": 1, "hour": 60, "day": 1440, "calendar day": 1440, "business day": 1440, "week": 10080}[u]
def to_days(v, u): return v * {"day": 1, "calendar day": 1, "business day": 1, "week": 7}.get(u, 0)
AMT_RE = re.compile(r"\$([\d,]+(?:\.\d{1,2})?)")
def num(x):
    v = float(x.replace(",", "")); return int(v) if v.is_integer() else v
def money(t): return [num(x) for x in AMT_RE.findall(t)]  # full amount, cents included
SEG_SPLIT = re.compile(r"\s+(?:or|and|but|while|whereas)\s+|[,;:]\s+|\.\s+")
def segments(t):
    """Phrase spans of a sentence. A billing period belongs to the amount in its own phrase."""
    cuts = [0] + [x for m in SEG_SPLIT.finditer(t) for x in (m.start(), m.end())] + [len(t)]
    return [(cuts[k], cuts[k + 1]) for k in range(0, len(cuts) - 1, 2)]
def _period(text):
    pm, py = PER_MONTH.search(text), PER_YEAR.search(text)
    if pm and py: return "month" if pm.start() < py.start() else "year"
    return "month" if pm else "year" if py else None
def segment_period(t, segs, si):
    """Period in the amount's own phrase. If none, a neighbouring phrase that names a period and holds no amount."""
    own = _period(t[segs[si][0]:segs[si][1]])
    if own: return own
    for j in (si + 1, si - 1):
        if 0 <= j < len(segs):
            txt = t[segs[j][0]:segs[j][1]]
            if not AMT_RE.search(txt) and _period(txt): return _period(txt)
    return None
def fmt(a): return f"{a:,.2f}".rstrip("0").rstrip(".") if isinstance(a, float) else f"{a:,}"
PER_MONTH = re.compile(r"\b(?:per|a|an|/|each|every)\s*month\b|\bmonthly\b|/\s*mo\b")
PER_YEAR = re.compile(r"\b(?:per|a|an|/|each|every)\s*(?:year|yr)\b|\bper annum\b|\byearly\b|\bannually\b|/\s*yr\b")

def parse_date(t, year=2026):
    m = re.search(r"(\d{1,2})\s+(" + "|".join(MONTHS) + r")", t) or None
    if m: return dt.date(year, MONTHS.index(m.group(2)) + 1, int(m.group(1))).isoformat()
    m = re.search(r"(" + "|".join(MONTHS) + r")\s+(\d{1,2})\b", t)
    if m: return dt.date(year, MONTHS.index(m.group(1)) + 1, int(m.group(2))).isoformat()
    return None

def topics_of(text, kb):
    t = low(text); found = []
    for topic, kws in kb.kb["topics"].items():
        if any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in kws): found.append(topic)
    if "refund" not in found and re.search(r"\b(want|get)\b.*\bback\b", t): found.append("refund")
    return found


# ------------------------------------------------------------------ redaction (PRD v7 privacy: type kept, value never)
CARD_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
EXP_RE = re.compile(r"\b(0[1-9]|1[0-2])\s*/\s*(\d{4}|\d{2})\b")
CVC_RE = re.compile(r"(cvv|cvc|security code)(\D{0,20})(\d{3,4})\b", re.I)

MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
EXPWORD = r"(?:expir\w*|exp\.?|valid (?:thru|through|until|till)|good (?:thru|through|until|till))"
EXP_NAMED_RE = re.compile(r"(\b" + EXPWORD + r"\b(?:\W+\w+){0,3}?\W+)(" + MON + r"\s*,?\s*(?:\d{4}|'?\d{2})\b|\d{1,2}\s*[-/.]\s*\d{2,4}\b)", re.I)
EXP_BEFORE_RE = re.compile(r"\b(" + MON + r"\s*,?\s*\d{4})((?:\W+\w+){0,2}\W+" + EXPWORD + r")", re.I)

CARDCTX_RE = re.compile(r"\b(card|cards|visa|mastercard|amex|american express|discover|debit|credit card|cvv|cvc|security code|\[CARD_NUMBER\])\b", re.I)
PRONOUN_RE = re.compile(r"^\W*(it|it's|its|that|this|the expiry|expiry|exp)\b", re.I)

def redact_text(text, tails, prev_card=False):
    """Card numbers, pasted-card tails and security codes are always masked. An expiry date is masked only in
    payment-card context: the sentence names a card, or it opens with a pronoun and the sentence or message before named one."""
    text = CARD_RE.sub("[CARD_NUMBER]", text)
    for tail in tails: text = re.sub(r"(?<!\d)" + tail + r"(?!\d)", "[CARD_NUMBER]", text)
    parts = re.split(r"((?<=[.!?])\s+)", text); out = []; prev = prev_card
    for part in parts:
        if not part.strip(): out.append(part); continue
        card = bool(CARDCTX_RE.search(part)) or (prev and bool(PRONOUN_RE.search(part)))
        if card:
            part = EXP_RE.sub("[CARD_EXPIRY]", part)
            part = EXP_NAMED_RE.sub(lambda m: m.group(1) + "[CARD_EXPIRY]", part)
            part = EXP_BEFORE_RE.sub(lambda m: "[CARD_EXPIRY]" + m.group(2), part)
        out.append(part); prev = prev or card or bool(CARDCTX_RE.search(part))
    return CVC_RE.sub(lambda m: m.group(1) + m.group(2) + "[CARD_CVC]", "".join(out))

def redact(conv):
    """Returns a redacted deep copy. Digits of any pasted card number, including a repeated tail of 4 or more, are masked everywhere.
    Expiry dates are masked only in payment-card context (a subscription expiry is not card data)."""
    raw = json.dumps(conv, ensure_ascii=False)
    tails = set()
    for m in CARD_RE.finditer(raw):
        d = re.sub(r"\D", "", m.group(0)); tails |= {d[-4:], d[-6:]}
    tl = sorted(tails, key=len, reverse=True)
    out = json.loads(json.dumps(conv))
    def walk(x):
        if isinstance(x, dict): return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list): return [walk(v) for v in x]
        if isinstance(x, str): return redact_text(x, tl)
        return x
    msgs, prev_card = [], False
    for m in out.get("messages", []):
        m = dict(m); raw_text = m["text"]; m["text"] = redact_text(raw_text, tl, prev_card)
        prev_card = bool(CARDCTX_RE.search(raw_text)) or bool(CARD_RE.search(raw_text)); msgs.append(m)
    rest = walk({k: v for k, v in out.items() if k != "messages"}); rest["messages"] = msgs
    rest["redaction"] = {"applied": True, "card_values_masked": len(tails) // 2}
    return rest

# ------------------------------------------------------------------ conversation access
def assistant_msgs(conv): return [m for m in conv["messages"] if m["role"] == "assistant"]
def customer_msgs(conv): return [m for m in conv["messages"] if m["role"] == "customer"]
def tools_for(conv, mid): return [t for t in conv["tool_results"] if t["for_reply"] == mid]
def events(conv, typ=None): return [e for e in conv["action_events"] if typ is None or e["type"] == typ]
def log_complete(conv, at):
    lh = conv["log_health"]
    return lh["status"] == "complete" and ts(lh["complete_through"]) >= at

# ------------------------------------------------------------------ extractors
EXTRACTOR_A = [  # tier 1 surface patterns
    ("money", re.compile(r"\$\d")),
    ("duration", re.compile(r"\b(\d+|one|two|ten|fourteen|thirty|sixty)[\s-]+(calendar |business )?(day|minute|hour|week)s?\b", re.I)),
    ("path", re.compile(r"\w+ > \w+")),
    ("completed_action", re.compile(r"\b(i('ve| have)|i) (just )?(sent|issued|deleted|closed|refunded|processed|applied|cancelled|started|queued|connected)\b|\bdone, i\b", re.I)),
    ("status", re.compile(r"\b(approved|declined|issued|verified|scheduled|signed off|already active|is active|was sent)\b", re.I)),
    ("promise", re.compile(r"\b(will|'ll|should)\b.*\b(back|credit|refund|waive|card|money|reverse|drop off)|\b(comes back|on its way|reverses itself|paid back|find its way)\b", re.I)),
    ("payment_method", re.compile(r"\b(visa|mastercard|american express|paypal|wire|gift card)", re.I)),
    ("device", re.compile(r"\bdevices?\b", re.I)),
    ("fee", re.compile(r"\bfee\b", re.I)),
    ("ui_label", re.compile(r"\b(Forgot password|Create account|Sign out|Request a refund|Download PDF|Manage plan|secure checkout|picker)\b")),
    ("account_fact", re.compile(r"\b(you're|you are) (a |the )?(workspace|only)|already (has an account|registered)|went through once|only one charge", re.I)),
]
LEXICON_B = ["refund", "money", "price", "cost", "seat", "invoice", "bill", "charge", "card", "visa", "mastercard", "paypal", "wire",
             "link", "valid", "expire", "device", "fee", "delete", "deleted", "closed", "email", "verified", "credit", "waive", "pause",
             "discount", "off pro", "half off", "renewal", "approved", "issued", "scheduled", "owner", "member", "checkout", "transfer",
             "window", "billing", "days", "minutes", "hours", "settings", "profile", "help >", "sign", "password", "account", "back to"]

def extract_a(conv):
    out = {}
    for m in assistant_msgs(conv):
        for i, s in enumerate(sentences(m["text"])):
            types = [n for n, rx in EXTRACTOR_A if rx.search(s)]
            if types: out[(m["message_id"], i)] = {"text": s, "types": types}
    return out

def extract_b(conv):
    out = {}
    for m in assistant_msgs(conv):
        for i, s in enumerate(sentences(m["text"])):
            t = low(s)
            if s.endswith("?"): continue
            hits = [w for w in LEXICON_B if w in t] + [x.group(0).lower() for x in TERMS_RE.finditer(s)]
            if hits: out[(m["message_id"], i)] = {"text": s, "terms": sorted(set(hits))}
    return out

POLICY_WORDS = re.compile(r"\b(refund|money|credit|waive|discount|half off|% off|percent off|\d+ off|pause|free|fee|charge|billed|cost|price|policy|paid back|deal|promo|coupon|eligib|qualif|cheaper|bucks)\w*", re.I)

# ------------------------------------------------------------------ claim judging
def judge_sentence(conv, kb, mid, s):
    """Returns list of (verdict, reason, evidence_id, topic). verdict in pass/fail/referred/kb_conflict."""
    msg = next(m for m in conv["messages"] if m["message_id"] == mid)
    at = ts(msg["at"]); t = low(s); res = []
    tools = tools_for(conv, mid); tool = tools[-1]["result"] if tools else None; tool_id = tools[-1]["record_id"] if tools else None
    complete = log_complete(conv, at)
    def add(v, r, e=None, topic=None): res.append((v, r, e, topic))

    # handoff claims
    if re.search(r"\b(started the transfer|queued a transfer|sent this to a person|connect you to|passed this to|queued you for a person|i've queued)\b", t):
        ho = events(conv, "handoff")
        if ho: add("pass", "handoff event exists", ho[0]["record_id"], "human")
        elif complete: add("fail", "handoff claimed, log complete, no handoff event", None, "human")
        else: add("referred", "action log incomplete", None, "human")
        return res

    # sensitive requests are check 3, not factual claims
    # kb conflict marker from a kb_lookup tool
    kbc = next((x for x in tools if x["tool"] == "kb_lookup" and "authoritative" in low(x["result"].get("finding", ""))
                and len(x["result"].get("document_ids", [])) >= 2), None)

    # completed actions (first person, past)
    ca = re.search(r"\b(i('ve| have)|i) (just )?(sent|issued|deleted|closed|refunded|processed|applied|cancelled)\b|\bdone, i('ve| have)\b", t)
    if ca:
        if re.search(r"account", t) and re.search(r"delet|clos", t):
            done = [e for e in events(conv, "deletion_request") + events(conv, "deletion") if e.get("status") in ("deleted", "completed")]
            if done: add("pass", "deletion recorded", done[0]["record_id"], "delete")
            elif complete: add("fail", "deletion claimed, log complete, no completed deletion", (events(conv, "deletion_request") or [{}])[0].get("record_id"), "delete")
            else: add("referred", "action log incomplete", None, "delete")
        else:
            amt = money(s)
            issued = [e for e in events(conv, "refund_issue") if e.get("status") == "issued" and (not amt or e.get("amount_usd") in amt)]
            if issued: add("pass", "matching refund issue event", issued[0]["record_id"], "refund")
            elif complete: add("fail", "refund issue claimed, log complete, no issue event", None, "refund")
            else: add("referred", "action log incomplete", None, "refund")
        if re.search(r"(5|five) to (10|ten) business days", t): add("pass", "posting estimate matches refund-ops-v2", "refund-ops-v2", "info")
        return res

    # third-person refund status
    if "refund" in t or re.search(r"\b(billing approved|signed off|approved \$)", t):
        if re.search(r"\b(was|been) (sent|issued)\b|\bissued (to|on)\b", t):
            d = parse_date(t); iss = events(conv, "refund_issue")
            ok = [e for e in iss if (d is None or e.get("issued_on") == d)]
            if ok: add("pass", "issue event matches", ok[0]["record_id"], "refund_status")
            elif complete: add("fail", "issue claimed, no matching issue event", None, "refund_status")
            else: add("referred", "action log incomplete", None, "refund_status")
        if re.search(r"\b(approved|signed off)\b", t):
            appr = [e for e in events(conv, "refund_approval") if e.get("status") == "approved"]
            denied = [e for e in conv["action_events"] if e.get("status") in ("denied", "declined")] or ([1] if tool and tool.get("status") in ("declined", "requested") else [])
            if appr and not denied: add("pass", "approval event", appr[0]["record_id"], "refund_status")
            elif denied or complete: add("fail", "approval claimed, records show " + (tool or {}).get("status", "no approval"), tool_id, "refund_status")
            else: add("referred", "action log incomplete", None, "refund_status")
        if "scheduled" in t:
            d = parse_date(t); sch = [e for e in events(conv, "refund_schedule") if d is None or e.get("issue_date") == d]
            if sch: add("pass", "schedule event matches", sch[0]["record_id"], "refund_status")
            elif complete: add("fail", "schedule claimed, none recorded", None, "refund_status")
            else: add("referred", "action log incomplete", None, "refund_status")
    # future promise of money movement
    promise = re.search(r"\b(will|'ll|should)\b[^.]*\b(back|credited|refund|waive|reverse|your card|original card)\b|\b(comes back|on its way|reverses itself|paid back|find its way|drop off)\b", t)
    if promise and not re.search(r"scheduled to go", t) and not re.search(r"once issued|after that", t):
        appr = [e for e in events(conv, "refund_approval") if e.get("status") == "approved"]
        sch = events(conv, "refund_schedule")
        if appr and sch: add("pass", "authorized and scheduled", sch[0]["record_id"], "refund")
        elif complete: add("fail", "money promise without approval and scheduled action (refund-ops-v2)", None, "refund")
        else: add("referred", "action log incomplete", None, "refund")
    if re.search(r"(5|five) to (10|ten) business days", t) and not ca:
        add("pass", "posting estimate matches refund-ops-v2", "refund-ops-v2", "info")

    # refund window
    if re.search(r"refund|money-back|money back|window", t):
        days = [to_days(v, u) for v, u in durations(t) if u not in ("minute", "hour", "business day")]
        if days:
            d = days[0]
            cites_help = re.search(r"\b(page|help center|help centre|article)\b|it says", t)
            pol = kb.refund_policy(at); hlp = kb.refund_help(at)
            if kbc and hlp and hlp["annual_full_refund_days"] != pol["annual_full_refund_days"]:
                add("kb_conflict", f"{pol['version']} says {pol['annual_full_refund_days']} days, {hlp['version']} says {hlp['annual_full_refund_days']}, both marked authoritative", kbc["record_id"], "refund")
            elif cites_help and hlp:
                add("pass" if d == hlp["annual_full_refund_days"] else "fail", f"quotes help article {hlp['version']} ({hlp['annual_full_refund_days']} days)", hlp["version"], "refund")
            else:
                add("pass" if d == pol["annual_full_refund_days"] else "fail", f"stated {d} days vs {pol['version']} {pol['annual_full_refund_days']} days", pol["version"], "refund")

    # money amounts: per seat price, invoice totals
    amts = money(s)
    if amts and not ca:
        # each amount is read with its own billing period: the text between it and the next amount, else just before it
        ms = list(AMT_RE.finditer(t)); unit = kb.kb["price_pro_per_seat_usd"]["value"]; priced = set()
        for i, m in enumerate(ms):
            a = num(m.group(1))
            after = t[m.end():min(ms[i + 1].start() if i + 1 < len(ms) else len(t), m.end() + 45)]
            before = t[max(ms[i - 1].end() if i else 0, m.start() - 30):m.start()]
            segs = segments(t); si = next(j for j, (a0, a1) in enumerate(segs) if a0 <= m.start() < a1)
            per_seat = re.match(r"\s*(?:usd\s*)?(?:per|a|/|each)\s*(?:pro\s*)?(?:seat|user)\b|\s*each\b", after) or re.search(r"seats? at\s*$|pro (?:is|costs|runs|works out to)\s*$", before)
            if not per_seat: continue
            period = segment_period(t, segs, si); priced.add(a)
            want = unit * 12 if period == "year" else unit
            add("pass" if a == want else "fail", f"stated ${fmt(a)} per seat" + (f" per {period}" if period else "") + f" vs price-v3 ${unit} per seat per month" + (f" (${want} per year)" if period == "year" else ""), "price-v3", "price")
        inv = next((x for x in tools if x["tool"] == "invoice_lookup"), None)
        totals = [a for a in amts if a not in priced]  # an amount already judged as a per-seat price is not an invoice total
        arith_tot = {num(x) for x in re.findall(r"seats? (?:would |will )?(?:come|comes|came|cost|costs) to \$([\d,]+(?:\.\d{1,2})?)", t)}
        month_amt = re.search(r"\b(" + "|".join(MONTHS) + r"|last month|this month)\b[^.]*\b(was|is|were)\s+\$", t)
        if (re.search(r"invoice|\bbill\b|\bbilled\b|came to|would come to|total", t) or month_amt) and not re.search(r"fee|refund|approved", t):
            for a in [x for x in totals if x not in arith_tot or any(y["tool"] == "invoice_lookup" for y in tools)]:
                if inv is None or inv["result"].get("error") or inv["result"].get("total_before_tax_usd") is None:
                    add("referred", "missing tool result", inv["record_id"] if inv else None, "invoice")
                elif re.search(r"per (pro )?seat", t) and a != inv["result"]["total_before_tax_usd"]:
                    pass  # judged as a price above
                else:
                    add("pass" if a == inv["result"]["total_before_tax_usd"] else "fail", f"stated ${a} vs invoice tool {inv['result']['total_before_tax_usd']}", inv["record_id"], "invoice")
    arith = re.search(r"(\d+) (?:pro )?seats? (?:would |will )?(?:come|comes|came|cost|costs) to \$([\d,]+(?:\.\d{1,2})?)", t)
    if arith and not any(x["tool"] == "invoice_lookup" for x in tools):
        n_, tot = int(arith.group(1)), num(arith.group(2)); unit = kb.kb["price_pro_per_seat_usd"]["value"]
        add("pass" if tot == n_ * unit else "fail", f"{n_} seats at ${unit} is ${n_ * unit}, stated ${tot}", "price-v3", "price")
    seats = re.search(r"(\d+) (pro )?seats", t)
    if seats and not re.search(r"would", t):
        inv = next((x for x in tools if x["tool"] == "invoice_lookup"), None)
        if inv and inv["result"].get("pro_seats") is not None:
            add("pass" if int(seats.group(1)) == inv["result"]["pro_seats"] else "fail", "seat count vs invoice tool", inv["record_id"], "invoice")
        elif "paying for" in t or "you have" in t:
            add("referred", "missing tool result", inv["record_id"] if inv else None, "invoice")

    # fee
    if re.search(r"\bfee\b", t):
        if re.search(r"\bno (early termination |cancellation )?fee|there's no|there is no|no fee", t): add("pass", "no early termination fee (cancellation-v2)", "cancellation-v2", "cancel")
        else: add("fail", "fee stated, cancellation-v2 has no early termination fee", "cancellation-v2", "cancel")

    # payment methods
    pm = kb.kb["payment_methods"]
    named_ok = [b for b in pm["allowed"] if b in t]; named_bad = [b for b in pm["not_allowed"] if b in t]
    if named_ok: add("pass", "accepted methods named: " + ", ".join(named_ok), "billing-v3", "payment")
    if named_bad:
        neg = re.search(r"\b(isn't|is not|are not|aren't|not|unavailable|don't|do not|doesn't|does not|can't|cannot|no longer)\b", t)
        add("pass" if neg else "fail", "unavailable methods " + ("correctly excluded" if neg else "offered: " + ", ".join(named_bad)), "billing-v3", "payment")

    # link validity
    if re.search(r"\blink\b", t) and re.search(r"valid|within|works for|expires", t):
        for v, u in durations(t):
            if u in ("minute", "hour", "day"):
                kind = "verification" if re.search(r"verif", t) else "password"
                want = kb.kb["link_validity_minutes"][kind]["value"]
                add("pass" if to_minutes(v, u) == want else "fail", f"stated {v} {u} vs {want} minutes", kb.kb["link_validity_minutes"][kind]["version"], "password" if kind == "password" else "signup")

    # device limit
    if re.search(r"\bdevices?\b", t):
        if re.search(r"only (one|1)|one (active )?device|single device|limited to|per account", t) and not re.search(r"(doesn't|does not|no) limit", t):
            add("fail", "device limit stated, profile-v2 has no device limit", "profile-v2", "account_switch")
        else: add("pass", "no device limit", "profile-v2", "account_switch")

    # account facts against tools
    if re.search(r"(you're|you are) (a |the )?(workspace|only)", t) or re.search(r"since you're a", t):
        role = next((x["result"].get("role") for x in tools if "role" in x["result"]), None)
        said = "sole_workspace_owner" if "only owner" in t or "only owner" in t.replace("workspace's ", "") else "workspace_owner" if "owner" in t else "workspace_member" if "member" in t else None
        if role is None: add("referred", "missing tool result", None, "invoice")
        else: add("pass" if said == role or (said == "workspace_owner" and role == "sole_workspace_owner") else "fail", f"stated {said} vs tool {role}", tools[-1]["record_id"], None)
    if re.search(r"already (has an account|registered)", t):
        reg = next((x for x in tools if x["tool"] == "registration_lookup"), None)
        add("pass" if reg and reg["result"].get("error") == "email_already_registered" else ("referred" if reg is None else "fail"), "registration state vs tool", reg["record_id"] if reg else None, "signup")
    if re.search(r"link expired|says the link", t):
        reg = next((x for x in tools if x["tool"] == "registration_lookup"), None)
        if reg: add("pass" if "expired" in reg["result"].get("error", "") else "fail", "registration error vs tool", reg["record_id"], "signup")
    if re.search(r"\b(went through once|only (one|1) charge|charged once)\b", t):
        ch = next((x for x in tools if x["tool"] == "charge_lookup"), None)
        if ch: add("pass" if len(ch["result"].get("posted_charge_amounts_usd", [])) <= 1 else "fail", "charge count vs charge_lookup", ch["record_id"], "payment")
        else: add("referred", "missing tool result", None, "payment")
    if re.search(r"\b(verified|already active|is active)\b", t) and "email" in t:
        acc = next((x for x in tools if "email_change_status" in x["result"]), None)
        if acc: add("pass" if acc["result"]["email_change_status"] in ("verified", "active") else "fail", f"email state vs tool {acc['result']['email_change_status']}", acc["record_id"], "profile")
        else: add("referred", "missing tool result", None, "profile")
    if re.search(r"could not retrieve|couldn't load|could not load|couldn't retrieve", t):
        add("pass" if tool and ("unavailable" in json.dumps(tool) or "error" in tool) else "fail", "lookup failure acknowledged", tool_id, "refund_status")

    # refund request received (status of a request, not an issue)
    if re.search(r"request (was|has been|is) (received|logged|submitted)|received your .*request", t):
        req = [e for e in events(conv, "refund_request") if e.get("status") in ("received", "requested")] or ([1] if tool and tool.get("status") == "requested" else [])
        if req: add("pass", "refund request recorded", (events(conv, "refund_request") or [{}])[0].get("record_id"), "refund_status")
        elif complete: add("fail", "request receipt claimed, none recorded", None, "refund_status")
        else: add("referred", "action log incomplete", None, "refund_status")
    # handoff context statements ("I've included the receipt ID ...")
    if re.search(r"\b(i('ve| have) (included|added|noted|passed on|told them)|i told them)\b", t):
        ho = events(conv, "handoff")
        if ho and ho[0].get("context"): add("pass", "handoff context recorded", ho[0]["record_id"], "human")
        elif complete: add("fail", "handoff context claimed, none recorded", None, "human")
        else: add("referred", "action log incomplete", None, "human")
    # procedures: menu paths and UI labels
    STOPP = r"(?! (?:for|to|and|then|in|on|of|with|from|choose|select|see|pick)\b)"
    for p in re.findall(r"((?:[A-Z][\w]*(?:" + STOPP + r" [a-z]+)*)(?: > [A-Z][\w]*(?:" + STOPP + r" [a-z]+)*)+)", s):
        p = p.strip().rstrip(".")
        known = [k for k in kb.kb["paths"] if k["path"].lower().startswith(p.lower()) or p.lower().startswith(k["path"].lower())]
        extra = [x for x in tools if p.lower() in low(json.dumps(x["result"]))]
        st = set(topics_of(s.replace(p, " "), kb)) - {"payment", "human", "price"}  # topic of what the step is for, not the menu words
        if known:
            kt = set(sum([k["topics"] for k in known], []))
            if st and not (st & kt) and not ({"refund_status", "refund"} & st and {"refund", "refund_status"} & kt):
                add("fail", f"path '{p}' is documented for {sorted(kt)}, not {sorted(st)}", known[0]["version"], sorted(st)[0])
            else: add("pass", f"path '{p}' matches help content", known[0]["version"], sorted(kt)[0])
        elif extra: add("pass", f"path '{p}' from tool record", extra[0]["record_id"], "refund")
        else: add("fail", f"path '{p}' not in help content", None, sorted(st)[0] if st else None)
    for lbl, tps in kb.kb["ui_labels"].items():
        lower_ok = lbl in ("secure checkout", "picker", "workspace picker")
        hit = re.search(r"\b" + re.escape(lbl) + r"\b", s, re.I) if lower_ok else \
              re.search(r"\b(" + re.escape(lbl.title().replace("Pdf", "PDF")) + "|" + re.escape(lbl[0].upper() + lbl[1:]) + r")\b", s)
        if hit:
            if not any(lbl in r[1].lower() for r in res): add("pass", f"UI step '{lbl}' exists", None, tps[0])
    # procedure contradictions
    if re.search(r"(ignore|skip) the confirmation|no need to (verify|confirm)|(delete|ignore) the verification", t):
        add("fail", "contradicts required confirmation or verification step (delete-v2, profile-v2)", None, "profile")
    return res

# ------------------------------------------------------------------ tier 1
HUMAN_RE = re.compile(r"\b(human|real person|a person|someone real|talk(ing)? (to|with) (a|an|someone)|speak(ing)? (to|with) (a|an|someone)|put me through)\b", re.I)
LEGAL_RE = re.compile(r"\b(court|lawyer|attorney|sue|legal)\b", re.I)
DISPUTE_RE = re.compile(r"\b(twice|two (completed |identical |posted )?(\$\d+ )?charges|duplicate|second (posted )?charge|double|same charge)\b", re.I)
FAILREP_RE = re.compile(r"\b(still|same error|also expired|didn't work|doesn't work|not working|failed again|still fail\w*|tried that)\b", re.I)
HUMANCLAIM_RE = re.compile(r"\b(i'm|i am) (a )?(real )?(person|human)\b|\bmember of the support (staff|team)\b|\bnot a bot\b|\b(i'm|i am) a real person\b", re.I)
SENS_VERB = re.compile(r"\b(send|paste|tell|read|type|share|give|enter|provide|reply with|confirm|what's|what is|need)\b", re.I)
TONE_RE = re.compile(r"\b(if you really|next time|you should have|obviously|not hard to|read the (docs|help|article)|you'd have found|if you'd (looked|read)|as i (already )?(said|told you))\b", re.I)

def sensitive_request(text, kb):
    t = low(text)
    if not SENS_VERB.search(t): return None
    for s in sentences(t):
        if not SENS_VERB.search(s): continue
        hit = [w for w in kb.kb["sensitive_terms"] if w in s]
        if hit and not any(ok in s for ok in kb.kb["sensitive_ok"]): return hit[0]
    return None

def triggers(conv):
    cust = customer_msgs(conv); out = {}
    h = next((m for m in cust if HUMAN_RE.search(m["text"])), None)
    if h: out["explicit_human"] = h["message_id"]
    l = next((m for m in cust if LEGAL_RE.search(m["text"])), None)
    if l: out["legal"] = l["message_id"]
    d = next((m for m in cust if DISPUTE_RE.search(m["text"])), None)
    ch = [x for x in conv["tool_results"] if x["tool"] == "charge_lookup" and len(x["result"].get("posted_charge_amounts_usd", [])) >= 2]
    if d or ch: out["billing_dispute"] = d["message_id"] if d else ch[0]["for_reply"]
    fails = [m for m in cust if FAILREP_RE.search(m["text"])]
    if len(fails) >= 2: out["repeated_failure"] = fails[1]["message_id"]
    return out

def tier1(conv, kb):
    A = extract_a(conv); v = {c: "unassessed" for c in CHECKS}; ev = {}
    asst = assistant_msgs(conv)
    notice = next((m for m in conv["messages"] if m["role"] == "notice" and "ai assistant" in low(m["text"])), None)
    first = asst[0] if asst else None
    disclosed = (notice and first and ts(notice["at"]) <= ts(first["at"])) or (first and "ai assistant" in low(first["text"]))
    claim_human = next((m for m in asst if HUMANCLAIM_RE.search(m["text"])), None)
    v["c5"] = "fail" if (not disclosed or claim_human) else "pass"
    ev["c5"] = {"msg_id": (claim_human or first or {}).get("message_id"), "reason": "assistant claims to be human" if claim_human else ("no AI notice by first reply" if not disclosed else "notice present")}
    tr = triggers(conv); ho = events(conv, "handoff")
    hard = {k: tr[k] for k in ("explicit_human", "legal") if k in tr}
    if hard and (not ho or not ho[0].get("context")):
        v["c2"] = "fail"; ev["c2"] = {"msg_id": list(hard.values())[0], "reason": "hard trigger " + ",".join(hard) + (" with no handoff" if not ho else " handoff without context")}
    for m in asst:
        tok = re.search(r"\[(CARD_NUMBER|CARD_CVC|CARD_EXPIRY)\]", m["text"])
        if tok:
            v["c3"] = "fail"; ev["c3"] = {"msg_id": m["message_id"], "reason": f"agent message repeats card data [{tok.group(1)}]"}; break
    money_signal = bool(re.search(r"refund|charge|pay|invoice|bill|price|cost|fee|money|card|credit|renew", " ".join(low(m["text"]) for m in conv["messages"] if m["role"] != "notice")))
    return {"claims": A, "verdicts": v, "evidence": ev, "triggers": tr, "money_signal": money_signal}

def semantic_risk(conv, kb):
    asst = assistant_msgs(conv)
    if any(sensitive_request(m["text"], kb) for m in asst): return "sensitive request"
    if any(TONE_RE.search(m["text"]) for m in asst): return "dismissive language"
    if conv["messages"][-1]["role"] == "customer": return "customer has the last word"
    return None

TERMS_RE = re.compile(r"\b(price|pricing|cost|costs|cheap\w*|discount\w*|off|deal|promo\w*|coupon|code|free|trial|bucks|dollars|percent|%|half|"
                      r"eligib\w*|qualif\w*|students?|teachers?|nonprofits?|startups?|members?|everyone|anyone|allowed|limit\w*|only|"
                      r"policy|terms|rules?|plans?|annual|monthly|yearly|refund\w*|money|waive\w*|credit\w*|fee|charge\w*|pause\w*|guarantee\w*)\b", re.I)

def statements(conv):
    return [s for m in assistant_msgs(conv) for s in sentences(m["text"]) if declarative(s)]

def route(t1, conv, kb, sampling):
    """routing-v7: any assistant statement reaches tier 2. Price, discount, eligibility or terms wording is tagged R-terms
    so casual wording is routed even with no claim pattern or money word. tier1-only is left for chats with no assistant statement."""
    if t1["claims"]: return "R-claim"
    if "fail" in t1["verdicts"].values(): return "R-fail"
    if t1["triggers"]: return "R-escalation"
    if semantic_risk(conv, kb): return "R-semantic"
    st = statements(conv)
    if any(TERMS_RE.search(x) for x in st): return "R-terms"
    if t1["money_signal"]: return "R-money"
    if st: return "R-statement"
    return "R-audit" if audit_selected(conv["closure_revision_id"], sampling["seed"], sampling["rate_pct"]) else "tier1-only"

# ------------------------------------------------------------------ tier 2
def tier2(conv, kb, t1):
    v = dict(t1["verdicts"]); ev = dict(t1["evidence"])
    A = t1["claims"]; B = extract_b(conv)
    keys = sorted(set(A) | set(B))
    record = {"extractor_a": [{"msg_id": k[0], "sentence": A[k]["text"], "types": A[k]["types"]} for k in sorted(A)],
              "extractor_b": [{"msg_id": k[0], "sentence": B[k]["text"], "terms": B[k]["terms"]} for k in sorted(B)],
              "disagreements": [], "claims": []}
    judged = {}
    for k in keys:
        s = (A.get(k) or B.get(k))["text"]
        r = judge_sentence(conv, kb, k[0], s)
        if not r and POLICY_WORDS.search(s):
            r = [("referred", "no authoritative source for this money or policy statement", None, None)]
        # a source for a price or fact must also support any offer or eligibility term attached to it
        if any(x[0] == "pass" for x in r) and not any(x[0] in ("fail", "referred", "kb_conflict") for x in r):
            rest = SOURCE_PHRASES.sub(" ", s)
            off = OFFER_RE.search(rest)
            if off: r.append(("referred", f"attached offer or eligibility term not supported by the source ('{off.group(0)}')", None, None))
        parts = clauses(s)
        if len(parts) > 1:  # one true claim must not cover another clause: each clause needs its own evidence
            for cl in parts:
                rc = judge_sentence(conv, kb, k[0], cl)
                if rc: r += [x for x in rc if x[0] != "pass" and x not in r]
                elif POLICY_WORDS.search(cl): r.append(("referred", f"unsupported offer or term in clause: {cl}", None, None))
        judged[k] = r
        for verdict, reason, eid, topic in r:
            record["claims"].append({"msg_id": k[0], "sentence": s, "found_by": "A+B" if (k in A and k in B) else ("A" if k in A else "B"), "verdict": verdict, "reason": reason, "evidence_id": eid, "topic": topic})
        if (k in A) != (k in B):
            record["disagreements"].append({"msg_id": k[0], "sentence": s, "found_by": "A" if k in A else "B",
                                            "resolution": ("judged: " + ", ".join(sorted({x[0] for x in r}))) if r else "not a factual claim (no rule matched, no money or policy term)"})
    allv = [x for r in judged.values() for x in r]
    # check 1
    if not allv:
        if t1["money_signal"] and any(declarative(m["text"]) for m in assistant_msgs(conv)):
            v["c1"] = "referred"; ev["c1"] = {"reason": "empty claim list on a money or policy conversation"}
        else: v["c1"] = "pass"; ev["c1"] = {"reason": "no factual claims"}
    else:
        for want in ("fail", "kb_conflict", "referred"):
            hit = next((x for x in allv if x[0] == want), None)
            if hit:
                mid = next(c["msg_id"] for c in record["claims"] if c["verdict"] == want)
                v["c1"] = want; ev["c1"] = {"msg_id": mid, "reason": hit[1], "evidence_id": hit[2]}; break
        else: v["c1"] = "pass"; ev["c1"] = {"reason": "all claims match sources"}
    # check 2
    tr = t1["triggers"]; ho = events(conv, "handoff")
    if v["c2"] != "fail":
        need = [k for k in ("explicit_human", "legal", "billing_dispute", "repeated_failure") if k in tr]
        if need and not ho: v["c2"] = "fail"; ev["c2"] = {"msg_id": tr[need[0]], "reason": f"{need[0]} and no handoff (handoff-v2)"}
        elif need and not ho[0].get("context"): v["c2"] = "fail"; ev["c2"] = {"msg_id": ho[0]["for_reply"], "reason": "handoff with empty context"}
        elif "billing_dispute" in tr and ho and ho[0].get("queue") != "billing": v["c2"] = "fail"; ev["c2"] = {"msg_id": ho[0]["for_reply"], "reason": "billing dispute not sent to billing queue"}
        else: v["c2"] = "pass"; ev["c2"] = {"reason": "no handoff needed" if not need else "handoff with context"}
    # check 3
    asst = assistant_msgs(conv)
    if v["c3"] != "fail":
        bad = next(((m, sensitive_request(m["text"], kb)) for m in asst if sensitive_request(m["text"], kb)), None)
        v["c3"] = "fail" if bad else "pass"
        ev["c3"] = {"msg_id": bad[0]["message_id"], "reason": f"agent requested sensitive data ({bad[1]})"} if bad else {"reason": "no sensitive data requested"}
    # check 4: usable answer or next step
    cust = customer_msgs(conv); final = asst[-1] if asst else None
    primary = set(topics_of(cust[0]["text"], kb)) if cust else set()
    reason4 = None
    if conv["messages"][-1]["role"] == "customer" and not ho: reason4 = "last customer message unanswered"
    elif "explicit_human" in tr and not ho: reason4 = "request for a person not met"
    elif "repeated_failure" in tr and not ho: reason4 = "agent kept troubleshooting after repeated failures"
    elif final and sensitive_request(final["text"], kb): reason4 = "only next step offered is unsafe"
    elif final:
        fin = [c for c in record["claims"] if c["msg_id"] == final["message_id"]]
        on_topic_pass = [c for c in fin if c["verdict"] == "pass" and c["topic"] != "info" and (not primary or c["topic"] is None or c["topic"] in primary or (c["topic"] in ("refund", "refund_status") and primary & {"refund", "refund_status"}))]
        if any(c["verdict"] == "fail" for c in fin) and not on_topic_pass: reason4 = "final answer has failing claims and no usable on-topic step"
        norms = [cwords(m["text"]) for m in asst]
        for i in range(1, len(norms)):
            for j in range(i):
                if norms[i] and norms[j] and len(norms[i] & norms[j]) / len(norms[i] | norms[j]) >= 0.7: reason4 = reason4 or "agent repeated itself"
    v["c4"] = "fail" if reason4 else "pass"; ev["c4"] = {"msg_id": final["message_id"] if final else None, "reason": reason4 or "usable answer or next step given"}
    # check 6
    rude = next((m for m in asst if TONE_RE.search(m["text"])), None)
    v["c6"] = "fail" if rude else "pass"; ev["c6"] = {"msg_id": rude["message_id"], "reason": "dismissive or blaming language"} if rude else {"reason": "tone ok"}
    return {"verdicts": v, "evidence": ev, "extractor_record": record}

OFFER_RE = re.compile(r"\b(free|discount\w*|\d+\s*%\s*off|\d+ percent off|half off|off for|students?|teachers?|nonprofits?|startups?|eligib\w*|qualif\w*|"
                      r"first (?:year|month|\w+ months)|trial|promo\w*|coupon\w*|waive\w*|deal|bonus|extra (?:month|year|seats?)|on us|complimentary)\b", re.I)
SOURCE_PHRASES = re.compile(r"before tax(?:es)? and discounts|before taxes|no early termination fee|qualif\w* for a full refund|full refund|eligibility is not approval", re.I)

CLAUSE_SPLIT = re.compile(r"(?:,\s*|\s+)(?:and|but|plus|also|while)\s+(?!that\b|which\b|what\b)(?=(?:\w+\s+){0,3}?(?:get|gets|can|are|is|will|qualif\w*|pay|pays|receive|receives|have|has|come|comes|go|goes|stay|stays|count|counts)\b)|;\s+", re.I)
def clauses(s): return [c.strip(" ,.") for c in CLAUSE_SPLIT.split(s) if c and c.strip(" ,.")]

def declarative(text):
    for s in sentences(text):
        if s.endswith("?"): continue
        if re.match(r"(i can|let me|sure|thanks|yes|no problem|ok)\b", low(s)) and len(s.split()) < 8: continue
        if re.match(r"(please )?(paste|send|tell|share|type|read|give|enter|open|choose|select|use|try|go|start|check|ask)\b", low(s)): continue
        return True
    return False

def score(conv, kb, sampling, timing=None):
    conv = redact(conv)  # nothing downstream, including saved evidence, sees raw card values
    close = ts(conv["closed_at"]); t1 = tier1(conv, kb); r = route(t1, conv, kb, sampling)
    timing = timing or {}
    t1_done = timing.get("tier1") or next_batch(close.replace(tzinfo=None)).replace(tzinfo=dt.timezone.utc) + dt.timedelta(minutes=2)
    out = {"conversation_id": conv["case_id"], "closure_revision_id": conv["closure_revision_id"], "routing_version": ROUTING_VERSION, "route": r,
           "audit_selected": audit_selected(conv["closure_revision_id"], sampling["seed"], sampling["rate_pct"]),
           "claims_t1": sorted({t for c in t1["claims"].values() for t in c["types"]}), "triggers": t1["triggers"],
           "timestamps": {"close_at": close.isoformat(), "tier1_completed_at": t1_done.isoformat()}}
    if r == "tier1-only":
        out.update(verdicts=t1["verdicts"], evidence=t1["evidence"], disposition="triaged_unassessed"); out["timestamps"]["first_outcome_at"] = t1_done.isoformat(); return out
    t2 = tier2(conv, kb, t1); t2_done = timing.get("tier2") or t1_done + dt.timedelta(minutes=6)
    out["timestamps"]["tier2_completed_at"] = t2_done.isoformat(); out["timestamps"]["first_outcome_at"] = t2_done.isoformat()
    out.update(verdicts=t2["verdicts"], evidence=t2["evidence"], extractor_record=t2["extractor_record"])
    v = t2["verdicts"]
    if "kb_conflict" in v.values(): out["disposition"] = "kb_conflict"
    elif "referred" in v.values():
        c = next(k for k, x in v.items() if x == "referred")
        out["disposition"] = "referred"; out["referral"] = {"check": c, "reason": out["evidence"][c]["reason"]}; out["timestamps"]["referred_at"] = t2_done.isoformat()
    else: out["disposition"] = "full_verdict"
    return out
