# Evidence and submission index

- Repository URL: https://github.com/omaraliii1/barq-academy
- Final commit: `__FILL__` (the last commit before submission, on the three-instance / port 8090 setup)
- Matching CI run: `__FILL__` (Actions run URL for the final commit)
- Continuous 12-18 minute video URL: `__FILL__`
- Challenge receipt ID: `__FILL__` (from `.assessment/challenge.json` after running `video_challenge.sh`)
- Starting video commit: `__FILL__` (commit `git status`/`git log` shows clean at the start of the recording)
- Later documentation-only commits, if any: `__FILL__` (list them and explain why they're doc-only)

Fill every `__FILL__` and every commit/timestamp cell below **after** the video is recorded and
the final commit is pushed - not before, since the values don't exist yet. Do not fabricate a
commit hash or timestamp; leave a cell as `__FILL__` rather than guess.

| Requirement | File / output | Commit | Video timestamp |
|---|---|---|---|
| Baseline kept, commit before technical changes | initial commit(s) | `__FILL__` | n/a |
| Progressive investigate -> fix -> verify commits | `git log --oneline` | `__FILL__` | n/a |
| Investigation journal, root causes, fixes, retests | `troubleshooting.md` | `__FILL__` | `__FILL__` |
| Log correlation, all template questions answered | `log_analysis.md` | `__FILL__` | `__FILL__` |
| Two Flask instances behind NGINX, working PG/Redis | `docker-compose.yml`, `nginx/nginx.conf` | `__FILL__` | `__FILL__` |
| Only NGINX published on host port | `docker-compose.yml` (`nginx.ports`) | `__FILL__` | `__FILL__` |
| frontend/backend network separation | `docker-compose.yml` (`networks:`) | `__FILL__` | `__FILL__` |
| NGINX blocked from PostgreSQL/Redis | `docker-compose.yml` (`nginx.networks: [frontend]`) | `__FILL__` | `__FILL__` |
| Container names app-01/app-02/nginx/postgres/redis | `docker-compose.yml` (`container_name:`) | `__FILL__` | `__FILL__` |
| Named PostgreSQL volume, Redis persistence | `docker-compose.yml` (`volumes:`, redis `command:`) | `__FILL__` | `__FILL__` |
| Health/readiness checks, env vars, secrets handling | `docker-compose.yml`, `Dockerfile`, `.env.example` | `__FILL__` | `__FILL__` |
| Non-root container user | `Dockerfile` (`USER app`) | `__FILL__` | `__FILL__` |
| Required endpoints (/, /health, /ready, /instance, /records, /counter) | `app/server.py` | `__FILL__` | `__FILL__` |
| validate.py: PASS/FAIL, bounded waits, non-zero exit | `validate.py` | `__FILL__` | `__FILL__` |
| failure_test.py: stop/verify/restore/recover | `failure_test.py` | `__FILL__` | `__FILL__` |
| backup.sh / restore.sh, proven PostgreSQL restore | `backup.sh`, `restore.sh` | `__FILL__` | `__FILL__` |
| Record survives app + PostgreSQL container recreation | `README.md` "Backup and restore" section, video | `__FILL__` | `__FILL__` |
| CI: build -> start -> readiness -> validate, fails on failure | `.github/workflows/ci.yml` | `__FILL__` | n/a |
| README: copyable setup/build/run/test/failure/backup/restore/cleanup | `README.md` | `__FILL__` | n/a |
| At least 5 decisions with trade-offs | `decisions.md` | `__FILL__` | n/a |
| At least 8 security/production findings | `security_review.md` | `__FILL__` | n/a |
| AI usage disclosure | `AI_USAGE.md` | `__FILL__` | n/a |
| Architecture diagram | `architecture.png` | `__FILL__` | n/a |
| Video: repo/commit/clean git status shown | video | n/a | `__FILL__` |
| Video: build/start, service health shown | video | n/a | `__FILL__` |
| Video: /, /health, /ready, /records, /counter tested | video | n/a | `__FILL__` |
| Video: /instance proves both backends serve via NGINX | video | n/a | `__FILL__` |
| Video: stop one backend, show traffic/errors, recover it | video | n/a | `__FILL__` |
| Video: record survives app+PostgreSQL recreation | video | n/a | `__FILL__` |
| Video: validate.py and failure_test.py run live | video | n/a | `__FILL__` |
| Video: one historical-log finding demonstrated | video | n/a | `__FILL__` |
| Video: video_challenge.sh run once, fault diagnosed/fixed | video | n/a | `__FILL__` |
| Video: port 8080 -> 8090 changed live, NGINX proven on 8090 | video | n/a | `__FILL__` |
| Video: third app instance added live, all three respond | video | n/a | `__FILL__` |
| Video: git status/diff shown, commits made and pushed on screen | video | n/a | `__FILL__` |

Match the final GitHub state, video, and every document above to the **three-instance setup on
port 8090** - not the two-instance/8080 state used for earlier development and testing.
