<img src="assets/barq-logo.svg" alt="BARQ Systems" width="180">

# BARQ DevOps Internship Assessment - Omar Ali Yassin

Fixed, tested and documented version of the BARQ Academy starter environment: two Flask
instances behind NGINX, PostgreSQL and Redis, with validation, failure-recovery and
backup/restore automation. See `assessment/TASK.md` for the original brief,
`troubleshooting.md` for the investigation journal, `log_analysis.md` for the log analysis,
`decisions.md` for design decisions, and `security_review.md` for the security review.

## Requirements

- Linux or WSL2, Python 3.12, Git, Docker with Compose (Linux containers).
- ~2 CPU cores, 4 GB free RAM, 3 GB free disk, plus Docker overhead.

## Setup

```bash
git clone <this-repo-url>
cd barq-academy
cp .env.example .env        # edit POSTGRES_PASSWORD / DATABASE_URL before first run
```

## Build and start

```bash
docker compose -p barq-assessment up --build -d
docker compose -p barq-assessment ps -a
```

Wait for `app-01`, `app-02`, `postgres`, `redis` and `nginx` to report `healthy`, then:

```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health
curl -i http://127.0.0.1:8080/ready
curl -i http://127.0.0.1:8080/instance
curl -s -X POST http://127.0.0.1:8080/records -H 'Content-Type: application/json' \
  -d '{"title":"example"}'
curl -i http://127.0.0.1:8080/records
curl -i http://127.0.0.1:8080/counter
```

## Stop / start without losing data

```bash
docker compose -p barq-assessment stop      # stop containers, keep volumes
docker compose -p barq-assessment start     # resume
docker compose -p barq-assessment down      # stop and remove containers, KEEP the named volume
```

Never pass `--volumes` / `-v` to `down` unless you intend to destroy the PostgreSQL data.

## App-only tests (fake dependencies, no Docker required)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

## Validate the running environment

```bash
docker compose -p barq-assessment up -d
./validate.py
```

Checks container health, all required endpoints, both backend identities, and PostgreSQL/Redis
readiness. Exits non-zero on any failure - see `validate.py` for the exact checks.

## Failure / recovery test

```bash
./failure_test.py
```

Stops one backend, sends traffic through NGINX to prove the environment keeps serving (via the
surviving backend or a controlled error), restarts the stopped backend, and verifies it resumes
serving requests. See `failure_test.py` output and `troubleshooting.md` for how this maps to the
supplied historical-log incident.

## Backup and restore (prove persistence)

```bash
# 1. create a record to track
curl -s -X POST http://127.0.0.1:8080/records -H 'Content-Type: application/json' \
  -d '{"title":"backup-proof"}'

# 2. back up
./backup.sh                       # writes backups/barq_tasks_<timestamp>.dump

# 3. destroy and recreate the app + postgres containers, keeping the named volume
docker compose -p barq-assessment up -d --force-recreate app-01 app-02 postgres

# 4. confirm the record is still there (volume persistence)
curl -s http://127.0.0.1:8080/records

# 5. restore from a specific backup (optional - proves the backup file itself is restorable,
#    e.g. onto a freshly-initialized database)
./restore.sh backups/barq_tasks_<timestamp>.dump
```

`restore.sh` with no argument restores the most recent file under `backups/`.

## CI

`.github/workflows/ci.yml` runs on every push and pull request: checkout -> Python syntax check
-> `docker compose config` -> build -> start -> wait for `/ready` -> `./validate.py`. The job
fails if validation fails. See the Actions tab for run history; the run for the final commit is
linked in `docs/EVIDENCE_INDEX.md`.

## Cleanup

```bash
docker compose -p barq-assessment down          # keep the postgres-data volume
docker compose -p barq-assessment down --volumes  # also delete it (irreversible - only for a
                                                    # full reset, never during a persistence test)
```

## Change the public port (8080 -> 8090)

```bash
PUBLIC_PORT=8090 docker compose -p barq-assessment up -d nginx
curl -i http://127.0.0.1:8090/
```

## Add a third app instance

```bash
docker compose -p barq-assessment up -d --scale app-01=1 --scale app-02=1 app-03
# or add an app-03 service block to docker-compose.yml matching app-01/app-02 and:
docker compose -p barq-assessment up -d app-03
./validate.py
```

## Video challenge

```bash
./video_challenge.sh
```

Run exactly once, unmodified, for the first time during the recorded video, after the
environment is healthy. See `assessment/TASK.md` "Recorded challenge" for the constraints.

## Documentation index

| File | Contents |
|---|---|
| `troubleshooting.md` | Investigation journal: symptoms, hypotheses, root causes, fixes, retests |
| `log_analysis.md` | Full analysis of the three supplied historical logs |
| `decisions.md` | Technical decisions, alternatives and trade-offs |
| `security_review.md` | Security/production-readiness findings |
| `AI_USAGE.md` | AI tool usage disclosure |
| `docs/EVIDENCE_INDEX.md` | Requirement -> file/output -> commit -> video-timestamp index |
| `architecture.png` | System diagram |
