# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision
- Choice:
- Why:
- Alternative:
- Trade-off:
- Evidence / commit:
- Production improvement:

Cover your base image, health checks, networks, timeouts/retries, restart/resource settings,
storage and any other meaningful choices.


# Technical Decisions

## 1. Running the Application as a Non-Root User

### Decision

The Flask application runs inside the container as a dedicated non-root user (`app`, UID 10001) instead of running as `root`.

### Why

Running the application as a non-root user reduces the impact of a potential application or dependency compromise. The application only needs access to its own files and network connections, so root privileges are unnecessary.

### Alternative Considered

Run the application as the default `root` user inside the Python image.

### Trade-off

A non-root configuration can require additional file ownership and permission management during image construction. The Dockerfile therefore creates the application user and copies application files with the correct ownership.

### Evidence

The Dockerfile creates the `app` user and switches to it using:

```dockerfile
USER app
```

### Production Consideration

The production deployment should continue enforcing non-root execution and should additionally use filesystem permissions and container security controls that prevent unnecessary privilege escalation.

---

## 2. Frontend and Backend Network Separation

### Decision

The Compose environment is divided into two Docker networks:

* `frontend` — NGINX and application containers
* `backend` — application containers, PostgreSQL, and Redis

The backend network is configured as an internal network.

### Why

The application needs to receive requests from NGINX and communicate with PostgreSQL and Redis. PostgreSQL and Redis do not need to be directly reachable from NGINX or from the host.

Separating the networks limits unnecessary connectivity and reduces the attack surface.

### Alternative Considered

Place every container on a single Docker network.

### Trade-off

Network separation adds configuration complexity because services must explicitly join the networks they require. However, it provides clearer communication boundaries and better reflects how service tiers are normally separated.

### Evidence

The Compose configuration places:

```text
NGINX      -> frontend
app-01     -> frontend + backend
app-02     -> frontend + backend
PostgreSQL -> backend
Redis      -> backend
```

The backend network is configured with:

```yaml
backend:
  internal: true
```

### Production Consideration

Production environments should apply the same least-connectivity principle while potentially introducing additional network policies, firewall controls, or service-mesh policies depending on the platform.

---

## 3. Only NGINX Exposes a Host Port

### Decision

NGINX is the only service that publishes a port to the host. The Flask application, PostgreSQL, and Redis containers communicate internally through Docker networks.

### Why

NGINX acts as the single public entry point to the application. Exposing the application or database services directly would bypass the reverse proxy and unnecessarily increase the attack surface.

The intended request flow is:

```text
Client
  |
  v
NGINX :8080
  |
  +----> app-01:8080
  |
  +----> app-02:8080
```

PostgreSQL and Redis remain accessible only through the backend network.

### Alternative Considered

Publish ports for the Flask instances, PostgreSQL, and Redis so they can be accessed directly from the host.

### Trade-off

Direct host access to individual services is convenient for debugging, but it weakens the network boundary and does not represent the intended application architecture.

### Evidence

The Compose configuration publishes only the NGINX port:

```yaml
ports:
  - "127.0.0.1:${PUBLIC_PORT:-8080}:80"
```

The application, PostgreSQL, and Redis services have no host `ports` configuration.

### Production Consideration

In production, NGINX or an external load balancer would remain the controlled entry point, with backend services kept on private networks or subnets.

---

## 4. Redis AOF Persistence

### Decision

Redis is configured with Append Only File (AOF) persistence:

```text
appendonly yes
```

while snapshot saving is disabled.

### Why

AOF records Redis write operations so Redis data can be reconstructed after a container restart. This provides persistence beyond the lifetime of the Redis container.

### Alternative Considered

Use Redis without persistence or rely only on periodic RDB snapshots.

### Trade-off

AOF provides stronger write durability but introduces additional disk I/O and storage requirements. Disabling RDB snapshots also means there is no independent snapshot-based recovery mechanism in this configuration.

### Evidence

Redis is started with:

```yaml
command:
  - redis-server
  - --save
  - ""
  - --appendonly
  - "yes"
```

### Production Consideration

Production Redis should use an explicit persistence and recovery strategy appropriate to the data's importance. This could include persistent volumes, controlled AOF/RDB settings, replication, backups, and monitoring of disk usage.

The current configuration should not be treated as a complete production disaster-recovery solution.

---

## 5. Secrets Management

### Decision

Application configuration and credentials should be supplied at runtime rather than embedded in the application source code or container image.

### Why

Credentials embedded in source code or container images can be exposed through Git history, image layers, registry access, or developer tooling. Keeping secrets outside the image reduces unnecessary exposure.

### Alternative Considered

Store database credentials directly in application source code or copy the environment file into the Docker image during the build.

### Trade-off

Runtime secret injection requires additional configuration and makes local setup slightly less convenient. However, it provides a much safer separation between application code and environment-specific credentials.

### Evidence

The application reads configuration through environment variables, and Docker Compose provides environment configuration at runtime.

The Docker image should not contain the local secret-bearing environment file.

### Production Consideration

For production, credentials should be stored in a dedicated secret-management system such as a cloud secret manager, Vault, or the secret-management mechanism provided by the deployment platform.

Any credentials previously committed to Git history should be considered exposed and rotated rather than relying only on `.gitignore`.

---

## 6. Docker Compose Dependency Ordering

### Decision

Application containers explicitly depend on PostgreSQL and Redis becoming healthy before the application is started.

### Why

Starting containers in the correct order reduces startup failures caused by the application attempting to connect to dependencies that are still initializing.

Container creation order alone is not sufficient because a running container does not necessarily mean the service inside it is ready to accept connections.

### Alternative Considered

Use simple `depends_on` relationships without health conditions, or allow the application to start immediately and rely entirely on retry logic.

### Trade-off

Health-based dependency ordering makes the Compose configuration more explicit, but it increases startup configuration complexity. Application-level readiness checks and timeouts are still necessary because dependency availability can change after startup.

### Evidence

The application services use health-based dependencies:

```yaml
depends_on:
  postgres:
    condition: service_healthy
  redis:
    condition: service_healthy
```

PostgreSQL and Redis each provide their own health checks.

### Production Consideration

Dependency ordering should not be treated as a complete availability mechanism. Production services should remain resilient to dependencies becoming temporarily unavailable after startup through bounded timeouts, retries, readiness checks, monitoring, and appropriate recovery mechanisms.

---

## Summary

These decisions establish the main security, networking, persistence, and startup behavior of the Compose environment:

| Decision                    | Main Objective                                         |
| --------------------------- | ------------------------------------------------------ |
| Non-root application user   | Reduce container privilege                             |
| Frontend/backend separation | Limit unnecessary network access                       |
| NGINX-only host port        | Provide a controlled public entry point                |
| Redis AOF                   | Preserve Redis state across restarts                   |
| Secrets management          | Prevent credentials from being embedded in images/code |
| Dependency ordering         | Start applications only after dependencies are healthy |

These decisions describe the current architecture and its intended direction. Production-specific improvements are explicitly identified rather than being presented as already implemented.
