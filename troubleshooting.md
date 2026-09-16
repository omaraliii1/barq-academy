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


