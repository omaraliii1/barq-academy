# Log analysis

All three supplied logs were analyzed with Python (`json`, stdlib only) and left unmodified in
`logs/`. Analysis scripts were run against the files as supplied; the commands below are exact
and reproducible from the repository root (stdlib only, no extra installs needed).

## 1. UTC interval, valid/malformed/duplicate lines per file

**Command:**
```bash
python3 - <<'PY'
import json
for name in ("access.log", "application.log", "error.log"):
    path = f"logs/{name}"
    with open(path) as f:
        lines = f.readlines()
    valid, malformed = [], 0
    for i, l in enumerate(lines):
        l = l.strip()
        if not l:
            continue
        try:
            valid.append(json.loads(l))
        except Exception:
            malformed += 1
            print(f"  malformed line #{i} in {name}: {l[:80]!r}")
    print(name, "total_lines=", len(lines), "malformed=", malformed)
PY
```

**Output / results:**

| File | Total lines | Valid | Malformed | Interval covered (UTC) |
|---|---|---|---|---|
| `access.log` | 726 | 725 | 1 (truncated JSON, line 311) | 2026-08-20T11:00:00.015Z -> 11:29:57.578Z |
| `application.log` | 730 | 729 | 1 (truncated JSON, line 401) | 2026-08-20T11:00:00.015Z -> 11:29:57.578Z |
| `error.log` | 68 | 68 (plain-text nginx format, not JSON) | 0 | 2026-08-20T11:05:02 -> 11:30:00 (rotation notice) |

Malformed lines (both are JSON cut off mid-object, consistent with a truncated write):
```
access.log:311:      {"timestamp":"2026-08-20T11:12:48Z","request_id":
application.log:401: {"timestamp":"2026-08-20T11:17:00Z","event":
```

**Duplicate lines** (exact, byte-for-byte repeats of an already-seen `request_id` + payload):
- `access.log`: 5 duplicate lines - `lab-000121`, `lab-000241`, `lab-000361`, `lab-000481`,
  `lab-000601`, each printed back-to-back, identical in every field.
- `application.log`: 2 duplicate `http_request` lines - `lab-000181`, `lab-000421`.
- `application.log` also has 47 *non-duplicate* extra lines: a `dependency_error` (ERROR) line
  followed by a `http_request` (WARN) line sharing the same `request_id`. These are two distinct
  events for one request (the app logs the failure, then logs the completed 503 response) and
  must not be treated as duplicates - see Q2.

## 2. Distinct client requests and de-duplication

**Command:**
```bash
python3 - <<'PY'
import json
seen = {}
dupes = 0
with open("logs/access.log") as f:
    for l in f:
        l = l.strip()
        if not l: continue
        try: d = json.loads(l)
        except Exception: continue
        if d["request_id"] in seen:
            dupes += 1
            continue
        seen[d["request_id"]] = d
print("distinct client requests:", len(seen), "duplicate lines skipped:", dupes)
PY
```

**Output:** `distinct client requests: 720   duplicate lines skipped: 5`

**Method:** `nginx.conf` assigns one `$request_id` per **client** request (`proxy_set_header
X-Request-ID $request_id`), and nginx writes exactly one `access.log` line per client request
even when it retries the request against a second upstream - the retry is recorded in the same
line via comma-separated `upstream` / `upstream_status` fields (see Q6), not as a second line. So:
- De-duplication key = `request_id`.
- The 5 exact duplicate lines were dropped (kept first occurrence) - these are not retries, just
  repeated log lines.
- `application.log` needed a second rule: only count `event == "http_request"` per `request_id`;
  the paired `dependency_error` lines are extra diagnostic detail for the *same* request, not a
  second request.
- Internal nginx-to-backend retries (visible as `"upstream": "IP1, IP2"`) are **one** client
  request, not two, and were counted once - counting `upstream_status` entries instead of
  `request_id` would have double-counted 19 requests.

Distinct requests: **720** (out of 725 valid access-log lines, 5 of which were duplicate prints of
requests already counted).

## 3. Final client status counts and error rate

**Command:**
```bash
python3 - <<'PY'
import json
from collections import Counter
seen = {}
with open("logs/access.log") as f:
    for l in f:
        try: d = json.loads(l.strip())
        except Exception: continue
        seen.setdefault(d["request_id"], d)
c = Counter(d["status"] for d in seen.values())
total = sum(c.values())
errors = sum(v for k, v in c.items() if k >= 500)
print(dict(sorted(c.items())), "total=", total, "5xx=", errors, f"rate={errors/total:.2%}")
PY
```

**Output:** `{200: 615, 404: 10, 502: 40, 503: 47, 504: 8}   total=720   5xx=95   rate=13.19%`

**Denominator:** the 720 distinct (de-duplicated) client requests from Q2. 404s (10, all
`/missing`) are excluded from the error rate - they are correct client-facing "not found"
responses, not server failures. Error rate = 95 5xx / 720 total = **13.19%**.

## 4. Which paths, time windows and backends account for the failures

**Command:**
```bash
python3 - <<'PY'
import json
from collections import Counter
seen = {}
with open("logs/access.log") as f:
    for l in f:
        try: d = json.loads(l.strip())
        except Exception: continue
        seen.setdefault(d["request_id"], d)
for status in (502, 503, 504):
    sub = [d for d in seen.values() if d["status"] == status]
    ts = sorted(d["timestamp"] for d in sub)
    print(status, len(sub), ts[0], "->", ts[-1], Counter(d["path"] for d in sub))
PY
```

**Output:**
```
502  40  2026-08-20T11:05:02.503Z -> 11:09:57.503Z  {'/health':10, '/records':10, '/counter':10, '/':10}
503  47  2026-08-20T11:12:09.525Z -> 11:21:45.041Z   {'/ready':23, '/counter':16, '/records':8}
504   8  2026-08-20T11:25:14.501Z -> 11:26:47.001Z   {'/records': 8}
```

Three distinct, non-overlapping failure windows, each with a different backend/path signature:

| Window (UTC) | Status | Paths hit | Backend(s) | Root cause (see troubleshooting.md) |
|---|---|---|---|---|
| 11:05:02-11:09:57 | 502 (40) + 19 silently-recovered via retry | `/`, `/health`, `/records`, `/counter` (40); `/ready`, `/instance` (19, recovered) | `172.23.0.12` only | app-02 unreachable (connection refused) |
| 11:12:09-11:15:52 | 503 (part of 47) | `/ready`, `/counter` | both app-01 and app-02 | Redis `TimeoutError` (31 dependency_error events) |
| 11:20:07-11:21:45 | 503 (part of 47) | `/ready`, `/records` | both app-01 and app-02 | Postgres `InvalidPassword` (16 dependency_error events) |
| 11:25:14-11:26:47 | 504 (8) | `/records` only | both app-01 and app-02 alternating | `proxy_read_timeout 2s` shorter than actual `/records` latency (2.7s) |

## 5. Median and p95 client latencies

**Command:**
```bash
python3 - <<'PY'
import json, math
seen = {}
with open("logs/access.log") as f:
    for l in f:
        try: d = json.loads(l.strip())
        except Exception: continue
        seen.setdefault(d["request_id"], d)
times = sorted(d["request_time"] for d in seen.values())
def pct(a, p):
    k = (len(a) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    return a[int(k)] if f == c else a[f] + (a[c] - a[f]) * (k - f)
print("median(s)=", pct(times, 0.50), "p95(s)=", pct(times, 0.95))
PY
```

**Output:** `median(s)= 0.054   p95(s)= 2.001`

**Method:** `request_time` from `access.log` (nginx's client-facing wall-clock time, in seconds,
including proxying overhead - the metric the client actually experiences). Percentile = linear
interpolation between order statistics on the full sorted array of all 720 de-duplicated requests
(the "nearest-rank with interpolation" method, not nearest-rank-only). **Units: seconds.** The p95
of ~2.0s is dominated by the 8 `/records` requests that hit the 2s `proxy_read_timeout` ceiling
exactly (504s) plus the successful-but-slow 2.7s `/records` responses that squeeze just under p95.

## 6. Which requests retried upstream, and how many succeeded

**Command:**
```bash
python3 - <<'PY'
import json
from collections import Counter
seen = {}
with open("logs/access.log") as f:
    for l in f:
        try: d = json.loads(l.strip())
        except Exception: continue
        seen.setdefault(d["request_id"], d)
retried = [d for d in seen.values() if "," in d["upstream"]]
print("retried:", len(retried), "succeeded(200):", sum(1 for d in retried if d["status"]==200))
print("paths:", Counter(d["path"] for d in retried))
print("first-attempt status on retried reqs:", Counter(d["upstream_status"].split(",")[0].strip() for d in retried))
PY
```

**Output:** `retried: 19   succeeded(200): 19` - `paths: {'/ready': 10, '/instance': 9}` - first
attempt was always `502` before falling through to the second backend.

**Evidence:** nginx logs both upstream attempts on one line when it retries, e.g.:
```json
{"request_id":"lab-000124","path":"/ready","status":200,
 "upstream":"172.23.0.12:8080, 172.23.0.11:8080","upstream_status":"502, 200","request_time":0.12}
```
19 of the 59 requests that hit the unreachable app-02 during the 11:05-11:09 window were
transparently retried against app-01 and returned `200` to the client (all 19 succeeded - 100%
retry success rate). The other 40 (on `/`, `/health`, `/records`, `/counter`) show only a single
upstream in the log and were returned to the client as `502` - the logs show *that* they weren't
retried, but not *why* only `/ready` and `/instance` were (see Q10).

## 7. Incident timeline (access + error + application logs correlated)

| Time (UTC) | Source | Event |
|---|---|---|
| 11:00:00 | access/application | Baseline traffic begins, all 200s |
| 11:05:02 | error.log | First `connect() failed (111: Connection refused)` to `172.23.0.12:8080` |
| 11:05:02-11:09:57 | access.log | 59 requests hit app-02; 19 (`/ready`,`/instance`) silently recovered via nginx retry to app-01, 40 (`/`,`/health`,`/records`,`/counter`) returned `502` to the client |
| 11:10:02 | access.log | First clean `200` direct to `172.23.0.12` - app-02 reachable again |
| 11:12:09 | application.log | First Redis `dependency_error` (`TimeoutError`) on app-02 |
| 11:12:09-11:15:52 | application.log | 31 Redis `TimeoutError` events across app-01 and app-02 -> 23x`/ready` + some `/counter` return `503` |
| 11:20:07 | application.log | First Postgres `dependency_error` (`InvalidPassword`) |
| 11:20:07-11:21:45 | application.log | 16 Postgres `InvalidPassword` events -> remaining `/ready` (503) and 8x`/records` (503) |
| 11:25:14 | error.log + access.log | First `upstream timed out (110)` on `/records`; client sees `504` after nginx's 2s `proxy_read_timeout` even though the app itself returns 200 at 2.7s |
| 11:25:14-11:26:47 | access.log | 8x`504` on `/records` only, alternating app-02/app-01 every ~3s in a ~30s-repeating pattern |
| 11:29:57 | access.log | Last recorded request |
| 11:30:00 | error.log | `[notice] log collector rotated stream` - logs end |

## 8. One correlated failed request and one correlated successful request

**Failed** - `request_id=lab-000606`, `/records`, 11:25:14-11:25:15 UTC:
- `error.log`: `upstream timed out (110: Operation timed out) ... request_id=lab-000606 ...
  upstream: "http://172.23.0.12:8080/records"`
- `access.log`: `{"request_id":"lab-000606","path":"/records","status":504,
  "upstream":"172.23.0.12:8080","upstream_status":"504","request_time":2.001}`
- `application.log`: `{"request_id":"lab-000606","instance_id":"app-02","path":"/records",
  "status":200,"duration_ms":2700}` - **the app itself completed the request successfully at
  2.7s, but the client had already been given a 504 at the 2s nginx timeout.** This is a
  timeout-tuning bug, not a backend failure.

**Successful (retried)** - `request_id=lab-000124`, `/ready`, 11:05:07 UTC:
- `access.log`: `{"request_id":"lab-000124","path":"/ready","status":200,
  "upstream":"172.23.0.12:8080, 172.23.0.11:8080","upstream_status":"502, 200",
  "request_time":0.12}`
- `application.log`: `{"request_id":"lab-000124","instance_id":"app-01","path":"/ready",
  "status":200,"duration_ms":120}` - app-02 refused the connection, nginx immediately retried
  app-01, which served it in 120ms. Client never saw an error.

## 9. Proxy/connectivity errors vs dependency/application errors - how to tell them apart

- **Proxy/connectivity** (nginx never reached a healthy app process, or gave up waiting on one):
  visible only in `error.log` with `connect() failed` or `upstream timed out`, and in
  `access.log` as a `50x` status where **no corresponding `application.log` entry exists for that
  `request_id` at all** (the app process never received or never finished the request from
  nginx's point of view) - e.g. all 40 unretried 502s in the 11:05 window have no matching
  `application.log` line.
- **Dependency/application** (the Flask process received the request and its own dependency check
  failed): visible in `application.log` as a `dependency_error` event (`ERROR` level, naming
  `redis` or `postgres` and an `error_type`) immediately followed by an `http_request` event with
  status `503` for the *same* `request_id` - the app is alive and responding, just reporting itself
  unhealthy. The 47 503s in the 11:12-11:21 window all have this exact pairing in
  `application.log`.
- The 8 `504`s are a **third, hybrid category**: nginx-level timeout, but the backend *did*
  finish the request (`application.log` shows `status: 200`) - a timeout-configuration mismatch
  rather than either the proxy or the app actually failing.

## 10. What the logs do not prove, and what to check next in a running environment

- The logs don't show *why* app-02 was unreachable for 11:05-11:09:57 (crash vs. slow start vs.
  network blip) - only that TCP connections were refused. In a running environment: `docker
  compose logs app-02` and `docker compose ps` around that window, or `docker inspect
  app-02 --format '{{.State}}'`, would show whether it was a container restart, an OOM-kill, or
  something else.
- The logs don't explain why only `/ready` and `/instance` were retried while `/`, `/health`,
  `/records`, `/counter` were not, during the same outage - the current `nginx.conf` in this repo
  enables `proxy_next_upstream` for all paths under `location /`, so this asymmetry reflects
  whatever config was live when these historical logs were generated, not necessarily the config
  now in the repo. This can only be confirmed by re-running the failure scenario against the
  current config (`failure_test.py`) and checking whether all six paths retry consistently.
- The Redis and Postgres `dependency_error` entries give an `error_type` (`TimeoutError`,
  `InvalidPassword`) but not the underlying cause (network partition vs. Redis restart vs. a
  rotated/wrong password) - that would need to be reproduced against the live containers to
  isolate.
- Logs prove client-observed outcomes, not root cause inside PostgreSQL/Redis themselves; nothing
  here reflects internal PostgreSQL/Redis logs, resource usage, or `docker stats` at the time.
