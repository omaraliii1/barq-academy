# Troubleshooting journal

---

## Entry 1

- **Symptom:** `docker compose -p barq-assessment up --build -d` starts, but `postgres` and
  `redis` are reachable directly from the host on `15432`/`16379`, and NGINX's `backend` network
  membership means it can reach Postgres/Redis directly too - violating "block direct NGINX
  access to PostgreSQL/Redis" and "do not publish app/PostgreSQL/Redis ports".
- **Hypothesis:** baseline `docker-compose.yml` publishes `ports: ["127.0.0.1:15432:5432"]` on
  postgres and `["127.0.0.1:16379:6379"]` on redis, and lists `nginx` under `networks: [frontend,
backend]` instead of `[frontend]` only.
- **Actual output:** starter compose file has `ports: ["127.0.0.1:15432:5432"]` (postgres), `ports:
["127.0.0.1:16379:6379"]` (redis), and `nginx: networks: [frontend, backend]`.
- **Failed attempt:** none needed.
- **Root cause:** starter compose file intentionally exposes both dependency ports to the host
  and puts nginx on the backend network, defeating the network-isolation requirement.
- **Fix:** removed the `ports:` mappings from `postgres` and `redis`; changed nginx to `networks:
[frontend]` only.
- **Retest evidence:** `docker compose -p barq-assessment config` shows no `ports:` under
  `postgres`/`redis`; `docker compose -p barq-assessment ps` should show only `nginx` binding a
  host port.
- **Related commit:** a770d34, ae40fc2, bc48867.
- **Remaining uncertainty:** none - this is a static config comparison.
---

## Entry 2 
- **Symptom:** even after fixing ports/networks, a record created through `/records` does not
  survive `docker compose down && up` (recreating the postgres container loses data despite a
  named volume being declared).
- **Hypothesis:** the named volume is mounted at the wrong path, so PostgreSQL isn't actually
  writing its data directory to it.
- **Command or test:** inspect the `postgres` service block in the baseline compose file.
- **Actual output:** baseline has
  `volumes: ["postgres-data:/var/lib/postgresql/backup", "./database/init.sql:...:ro"]` **and**
  `tmpfs: [/var/lib/postgresql/data]` - the real data directory (`/var/lib/postgresql/data`) is
  overridden by an in-memory `tmpfs`, while the named volume is mounted to an unused `/backup`
  path that PostgreSQL never writes to.
- **Failed attempt:** initially assumed the volume declaration alone (`postgres-data:`) was
  sufficient and almost left the mount path unchanged - re-reading the official postgres image
  docs confirmed the data directory must be `/var/lib/postgresql/data` for `PGDATA` to persist.
- **Root cause:** `tmpfs` on the real data dir means every container recreation starts from an
  empty database; the named volume was a decoy mounted to a path Postgres doesn't use.
- **Fix:** changed the volume mount to `postgres-data:/var/lib/postgresql/data` and removed the
  `tmpfs:` entry entirely.
- **Retest evidence:** create a record via `POST /records`, run `docker
  compose -p barq-assessment up -d --force-recreate app-01 app-02 postgres`, then `GET /records`
  and confirm the record is still present.
- **Related commit:** d35ddcc, d3f7aa2.
- **Remaining uncertainty:** none once retested; this was a config-only bug.

---

## Entry 3
- **Symptom:** Redis-backed `/counter` resets to 0 after any redis container restart.
- **Hypothesis:** Redis has no persistence enabled.
- **Command or test:** compare the `redis` `command:` line in baseline vs. supplied requirement
  ("configure Redis persistence where appropriate").
- **Actual output:** baseline: `command: ["redis-server", "--save", "", "--appendonly", "no"]`.
- **Root cause:** AOF persistence explicitly disabled and RDB snapshotting also disabled (`--save
  ""`) - Redis was running fully in-memory with zero persistence.
- **Fix:** changed to `--appendonly yes` (kept `--save ""` since AOF alone is sufficient for this
  lab and avoids RDB's fork-based snapshot cost - see `decisions.md` #4).
- **Retest evidence:**  hit `/counter` a few times, `docker compose restart
  redis`, hit `/counter` again and confirm it continues from the prior value rather than resetting.
- **Related commit:** d6d07af.
- **Remaining uncertainty:** none.

---

## Entry 4
- **Symptom:** `curl http://127.0.0.1:8080/` returns connection refused even though `docker
  compose ps` shows `nginx` as `Up`.
- **Hypothesis:** the host port is mapped to the wrong container port, or nginx isn't actually
  listening where the mapping expects.
- **Command or test:** compare `nginx` service `ports:` and `nginx.conf`'s `listen` directive.
- **Actual output:** baseline compose maps `127.0.0.1:${PUBLIC_PORT:-8080}:81` (container port
  **81**), while `nginx.conf` has `listen 80;` - the container never listens on 81 at all.
- **Root cause:** host-to-container port mismatch (81 vs. 80) between compose and nginx.conf.
- **Fix:** changed the compose mapping to `127.0.0.1:${PUBLIC_PORT:-8080}:80` to match `listen
  80;` in `nginx.conf`.
- **Retest evidence:** `curl -i http://127.0.0.1:8080/` should return `200`.
- **Related commit:** ae40fc2.
- **Remaining uncertainty:** none.

---

## Entry 5 
- **Symptom:** even with the port fixed, only one Flask instance ever answers - the other never
  receives traffic and eventually nginx logs upstream errors for it.
- **Hypothesis:** the nginx `upstream` block has a typo in one of the two backend addresses.
- **Command or test:** read `nginx/nginx.conf`'s `upstream application_pool` block in baseline.
- **Actual output:** baseline: `server app-01:8081 max_fails=0;` (wrong port - the app listens on
  8080, not 8081) alongside `server app-02:8080 max_fails=0;`, plus `max_fails=0` (disables nginx's
  own failure tracking) and `proxy_next_upstream off;` (disables retry-on-failure entirely).
- **Root cause:** upstream port typo for app-01, and failover explicitly disabled.
- **Fix:** corrected `app-01:8081` to `app-01:8080`; set `max_fails=3 fail_timeout=5s` on both
  servers; enabled `proxy_next_upstream error timeout http_502 http_503 http_504;` so nginx can
  retry a failed backend without surfacing a client-facing error, consistent with the recovered
  requests seen in `log_analysis.md` Q6.
- **Retest evidence:**  repeated `curl http://127.0.0.1:8080/instance` should alternate `instance_id` between `app-01` and `app-02`.
- **Related commit:** 1df47e9, e12b24a.
- **Remaining uncertainty:** none.


---

## Entry 6 
- **Symptom:** `docker compose ps` shows the `app-01`/`app-02` healthcheck stuck `unhealthy`
  forever, even though the app itself responds fine to manual `curl`.
- **Hypothesis:** the healthcheck probes an endpoint the app doesn't implement.
- **Command or test:** compare the `x-app.healthcheck.test` command in baseline compose against
  `app/server.py`'s actual routes.
- **Actual output:** baseline healthcheck: `urllib.request.urlopen('http://127.0.0.1:8080/healthz'
  ...)`, but `app/server.py` only defines `/health` (no `z`) - every healthcheck probe returns
  `404`, which `urlopen` raises as an exception, so the check always fails.
- **Root cause:** healthcheck path/route mismatch.
- **Fix:** changed the healthcheck URL to `/health`.
- **Retest evidence:** `docker compose -p barq-assessment ps` should show
  `app-01`/`app-02` as `healthy` within the `start_period`.
- **Related commit:** f936568.
- **Remaining uncertainty:** none.

