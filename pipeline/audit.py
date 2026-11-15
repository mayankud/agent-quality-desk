"""File-access audit for agent runs, using Linux inotify through ctypes (no installs).
Watches every directory under the given roots and logs open and read events with UTC timestamps.
  python3 audit.py start LOGFILE ROOT [ROOT ...]   (runs until killed)
  python3 audit.py report LOGFILE START_UTC END_UTC ALLOWED_PREFIX [ALLOWED_PREFIX ...]"""
import ctypes, ctypes.util, os, struct, sys, json, datetime as dt, select

IN_ACCESS, IN_OPEN, IN_CREATE, IN_ISDIR = 0x1, 0x20, 0x100, 0x40000000
MASK = IN_ACCESS | IN_OPEN | IN_CREATE

HEARTBEAT_S = 5
MAX_SILENCE_S = 12  # the report fails if the watcher log has a longer silence anywhere in the window

def now(): return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def start(log, roots):
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    fd = libc.inotify_init1(0)
    if fd < 0: sys.exit("inotify_init1 failed")
    wd = {}
    def add(path):
        w = libc.inotify_add_watch(fd, path.encode(), MASK)
        if w >= 0: wd[w] = path
    for r in roots:
        for dp, dns, _ in os.walk(r):
            dns[:] = [d for d in dns if d != "__pycache__"]
            add(dp)
    out = open(log, "a", buffering=1); out.write(json.dumps({"t": now(), "event": "audit_started", "dirs": len(wd), "roots": roots}) + "\n")
    while True:
        r, _, _ = select.select([fd], [], [], HEARTBEAT_S)
        if not r: out.write(json.dumps({"t": now(), "event": "heartbeat"}) + "\n"); continue
        buf = os.read(fd, 65536); i = 0
        while i < len(buf):
            w, mask, cookie, ln = struct.unpack_from("iIII", buf, i); name = buf[i + 16:i + 16 + ln].rstrip(b"\0").decode(errors="replace"); i += 16 + ln
            path = os.path.join(wd.get(w, "?"), name) if name else wd.get(w, "?")
            if mask & IN_CREATE and mask & IN_ISDIR: add(path)
            kind = "open" if mask & IN_OPEN else "read" if mask & IN_ACCESS else "create"
            out.write(json.dumps({"t": now(), "event": kind, "path": path, "dir": bool(mask & IN_ISDIR)}) + "\n")

def report(log, t0, t1, allowed):
    ev = [json.loads(l) for l in open(log) if l.strip()]
    win = [e for e in ev if e.get("path") and t0 <= e["t"] <= t1]
    bad = [e for e in win if not any(e["path"].startswith(a) for a in allowed)]
    ts = lambda t: dt.datetime.strptime(t, "%Y-%m-%dT%H:%M:%S.%fZ").timestamp()
    alive = sorted([ts(e["t"]) for e in ev if t0 <= e["t"] <= t1] + [ts(e["t"]) for e in ev if e["event"] == "heartbeat" and e["t"] > t1][:1])
    pts = [ts(t0)] + alive + [ts(t1)] if alive else []
    gap = max((b - a for a, b in zip(pts, pts[1:])), default=None) if pts else None
    covered = gap is not None and gap <= MAX_SILENCE_S and any(e["event"] == "heartbeat" and e["t"] >= t1 for e in ev)
    res = {"window": [t0, t1], "events_in_window": len(win), "outside_allowed": len(bad), "examples": bad[:10],
           "watcher_max_silence_s": round(gap, 1) if gap is not None else None, "watcher_covered_window": covered,
           "allowed_prefixes": allowed, "verdict": "AUDIT NOT RUNNING FOR THE WHOLE WINDOW" if not covered else ("clean" if not bad else "ACCESS OUTSIDE ALLOWED PATHS")}
    print(json.dumps(res, indent=1)); return res

if __name__ == "__main__":
    if sys.argv[1] == "start": start(sys.argv[2], sys.argv[3:])
    else: report(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:])
