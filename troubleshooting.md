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
