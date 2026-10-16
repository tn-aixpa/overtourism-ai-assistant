#!/usr/bin/env python3
"""
Black-box probe for the /agent -> /agent/stream -> /agent/result flow.

Run it against a REAL deployment (staging, or localhost) to find out where time
goes and whether `done` ever goes missing. Unlike the pytest suite, it sees the
real LLM, the real backend, your reverse proxy / ingress and your network.

    python scripts/sse_probe.py --base http://localhost:8000 --token $TOKEN \
        --sessions 5 --turns 3 --message "list the scenarios" \
        --territory-header ... (see --help)

Typical diagnosis runs
----------------------
1. Direct to uvicorn   (--base http://localhost:8000)
2. Through the proxy   (--base https://your.public.host)
   If (1) is fast and (2) is slow/lumpy  -> proxy buffering / idle timeout
   (compare `last_status->done`: buffered proxies deliver events in bursts).
3. --sessions 1 vs --sessions 20  -> thread-pool / event-loop contention.
4. --token-in-query                -> exercise the EventSource auth path.

What it measures per turn (all client-side, monotonic clock)
------------------------------------------------------------
post          POST /agent round trip (also runs auth/me + get_allowed_territories
              + save_state on the event loop on the server)
first_event   POST returned -> first status event   (queueing + router + 1st LLM call)
last->done    last status event -> `done`            (final answer generation +
              state persistence + SSE polling; this is where "answer ready but
              not delivered" shows up)
done->result  `done` -> GET /agent/result answered   (auth/me round trip + JSON)
total         POST sent -> answer in hand

When a stream ends/stalls WITHOUT `done` the probe immediately calls
GET /agent/result: 200 means "the turn had finished, the `done` was lost / the
stream was cut" (stream or proxy problem); 404 means "the turn is genuinely
still running" (slow LLM/backend or a hung turn).

Correlating with the server log (optional: --server-log app.log)
----------------------------------------------------------------
Your log format already carries ms timestamps. For each session the probe
prints the wall-clock time at which the client saw `done`, and - if you pass the
log - the server-side hops:

  "Output message: ..."                       answer generated
  "Agent completed session <sid>"             publish_done() (after save_state)
  "Sending SSE event for session <sid>: __done__"   generator yields `done`

  answer->completed : state rebuild + save_state/dump_to_file     (cause A)
  completed->sent   : SSE polling + event-loop availability       (cause C)
  sent->client      : network / proxy buffering
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

_EOL = re.compile(r"\r\n|\n|\r")


def sse_lines(response):
    buf = ""
    for chunk in response.iter_text():
        buf += chunk
        parts = _EOL.split(buf)
        buf = parts.pop()
        yield from parts
    if buf:
        yield buf


def parse_sse(lines):
    name, data = "message", []
    for line in lines:
        if line == "":
            if data or name != "message":
                yield name, "\n".join(data)
            name, data = "message", []
        elif line.startswith(":"):
            yield "comment", line[1:].strip()
        elif line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))


@dataclass
class Turn:
    session: str
    index: int
    outcome: str = "?"  # ok | no-done(result-ready) | no-done(still-running) | error
    detail: str = ""
    t_post_sent: float = 0
    t_post_back: float = 0
    t_first: float | None = None
    t_last_status: float | None = None
    t_done: float | None = None
    wall_done: dt.datetime | None = None
    t_result: float | None = None
    n_status: int = 0
    n_keepalive: int = 0
    arrivals: list[float] = field(default_factory=list)

    def hops(self):
        d = {}
        d["post"] = self.t_post_back - self.t_post_sent
        if self.t_first:
            d["first_event"] = self.t_first - self.t_post_back
        if self.t_done and self.t_last_status:
            d["last->done"] = self.t_done - self.t_last_status
        elif self.t_done:
            d["post->done"] = self.t_done - self.t_post_back
        if self.t_result and self.t_done:
            d["done->result"] = self.t_result - self.t_done
        if self.t_result:
            d["total"] = self.t_result - self.t_post_sent
        return d


def run_turn(args, session: str, index: int) -> Turn:
    tr = Turn(session, index)
    headers = {} if args.token_in_query else {"Authorization": f"Bearer {args.token}"}
    rheaders = {"Authorization": f"Bearer {args.token}"}
    form = {"message": args.message, "session_id": session}
    if args.integrated:
        form["integrated_mode"] = "true"
    try:
        with httpx.Client(base_url=args.base, timeout=httpx.Timeout(args.timeout), verify=not args.insecure) as c:
            tr.t_post_sent = time.monotonic()
            r = c.post("/agent", data=form, headers=rheaders)
            tr.t_post_back = time.monotonic()
            if r.status_code != 202:
                tr.outcome, tr.detail = "error", f"POST /agent -> {r.status_code} {r.text[:200]}"
                return tr
            params = {"token": args.token} if args.token_in_query else None
            try:
                with c.stream("GET", f"/agent/stream/{session}", headers=headers, params=params) as s:
                    if s.status_code != 200:
                        tr.outcome, tr.detail = "error", f"stream -> {s.status_code}"
                        return tr
                    for name, _data in parse_sse(sse_lines(s)):
                        now = time.monotonic()
                        if name == "status":
                            tr.n_status += 1
                            tr.t_first = tr.t_first or now
                            tr.t_last_status = now
                            tr.arrivals.append(now)
                        elif name == "comment":
                            tr.n_keepalive += 1
                        elif name == "done":
                            tr.t_done, tr.wall_done = now, dt.datetime.now()
                            break
            except (httpx.TransportError, httpx.StreamError) as e:
                tr.detail = f"stream broke: {type(e).__name__}"
            if tr.t_done is None:
                rr = c.get(f"/agent/result/{session}", headers=rheaders)
                tr.t_result = time.monotonic()
                tr.outcome = "no-done(result-ready)" if rr.status_code == 200 else "no-done(still-running)"
                tr.detail += f" result->{rr.status_code}"
                return tr
            rr = c.get(f"/agent/result/{session}", headers=rheaders)
            tr.t_result = time.monotonic()
            tr.outcome = "ok" if rr.status_code == 200 else "error"
            if rr.status_code != 200:
                tr.detail = f"/agent/result -> {rr.status_code} {rr.text[:200]}"
    except httpx.TimeoutException as e:
        tr.outcome, tr.detail = "no-done(timeout)", f"{type(e).__name__} after {args.timeout}s"
    except Exception as e:  # noqa: BLE001
        tr.outcome, tr.detail = "error", f"{type(e).__name__}: {e}"
    return tr


def run_session(args, i: int) -> list[Turn]:
    session = f"probe-{uuid.uuid4().hex[:8]}"
    out = []
    for k in range(args.turns):
        if args.stagger:
            time.sleep(args.stagger * i / max(1, args.sessions))
        t = run_turn(args, session, k)
        out.append(t)
        if t.outcome.startswith("error") and "409" in t.detail:
            time.sleep(1)
    return out


# --------------------------------------------------------------------------- #
# optional server-log correlation
# --------------------------------------------------------------------------- #
_LOG_RE = re.compile(
    r"^(?P<ts>\d\d-\d\d-\d{4} \d\d:\d\d:\d\d\.\d{3}) \[(?P<thread>[^\]]*)\] \S+\s+(?P<rest>.*)$"
)


def _ts(s):
    return dt.datetime.strptime(s, "%d-%m-%Y %H:%M:%S.%f")


def server_hops(path, session):
    answer = completed = sent = None
    last_out = {}
    try:
        for line in open(path, encoding="utf-8", errors="replace"):
            m = _LOG_RE.match(line)
            if not m:
                continue
            rest, th = m["rest"], m["thread"]
            if "Output message:" in rest:
                last_out[th] = _ts(m["ts"])
            elif f"Agent completed session {session}" in rest:
                completed = _ts(m["ts"])
                answer = last_out.get(th)
            elif f"Sending SSE event for session {session}: __done__" in rest:
                sent = _ts(m["ts"])
    except OSError:
        return None
    return answer, completed, sent


def fmt(sec):
    return "   -  " if sec is None else f"{sec:6.2f}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--token", default="", help="bearer token (not needed if AUTH_ENABLED=false)")
    ap.add_argument("--message", default="Hello, what can you do?")
    ap.add_argument("--sessions", type=int, default=3, help="concurrent sessions")
    ap.add_argument("--turns", type=int, default=2, help="sequential turns per session")
    ap.add_argument("--stagger", type=float, default=0.0, help="spread session start over N seconds")
    ap.add_argument("--timeout", type=float, default=180, help="max seconds to wait for `done`")
    ap.add_argument("--token-in-query", action="store_true", help="auth the stream via ?token= like EventSource")
    ap.add_argument("--integrated", action="store_true")
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--server-log", help="server log file, to print per-hop server-side timings")
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    with ThreadPoolExecutor(args.sessions) as ex:
        turns = [t for chunk in ex.map(lambda i: run_session(args, i), range(args.sessions)) for t in chunk]
    wall = time.monotonic() - t0

    print(f"\n{len(turns)} turns, {args.sessions} concurrent sessions, {wall:.1f}s wall\n")
    print(f"{'session':<15}{'#':>2} {'outcome':<24}{'post':>7}{'1st evt':>8}{'last->done':>11}{'done->res':>10}{'total':>7}  ev  ka  done@")
    for t in turns:
        h = t.hops()
        print(
            f"{t.session:<15}{t.index:>2} {t.outcome:<24}{fmt(h.get('post'))}{fmt(h.get('first_event')):>8}"
            f"{fmt(h.get('last->done', h.get('post->done'))):>11}{fmt(h.get('done->result')):>10}{fmt(h.get('total')):>7}"
            f"  {t.n_status:>2}  {t.n_keepalive:>2}  {t.wall_done:%H:%M:%S.%f}"[:-3]
            if t.wall_done
            else f"{t.session:<15}{t.index:>2} {t.outcome:<24}  {t.detail}"
        )
        if t.outcome != "ok" and t.detail and t.wall_done:
            print(f"{'':<18}{t.detail}")

    def stat(name):
        v = [t.hops()[name] for t in turns if name in t.hops()]
        if v:
            q = statistics.quantiles(v, n=20, method="inclusive")[18] if len(v) >= 3 else max(v)
            print(f"  {name:<13} median {statistics.median(v):6.2f}s   p95 {q:6.2f}s   max {max(v):6.2f}s")

    print("\nSummary")
    for k in ("post", "first_event", "last->done", "done->result", "total"):
        stat(k)
    bad = [t for t in turns if t.outcome != "ok"]
    print(f"  outcomes: {len(turns)-len(bad)} ok, {len(bad)} not ok")
    for kind in sorted({t.outcome for t in bad}):
        print(f"    {kind}: {sum(1 for t in bad if t.outcome == kind)}")

    if args.server_log:
        print("\nServer-side hops (from --server-log)")
        print(f"  {'session':<15}{'answer->completed':>19}{'completed->sent':>17}{'sent->client':>14}")
        for t in turns:
            sh = server_hops(args.server_log, t.session)
            if not sh or not (sh[1] and sh[2]):
                continue
            answer, completed, sent = sh
            a = (completed - answer).total_seconds() if answer else None
            b = (sent - completed).total_seconds()
            c = (t.wall_done - sent).total_seconds() if t.wall_done else None
            print(f"  {t.session:<15}{fmt(a):>19}{fmt(b):>17}{fmt(c):>14}")
        print("  (sent->client assumes client and server clocks agree)")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
