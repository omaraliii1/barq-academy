#!/usr/bin/env python3

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

PUBLIC_PORT = int(os.getenv("PUBLIC_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"

TIMEOUT = 30
INTERVAL = 2

failures = 0


def log_pass(message):
    print(f"[PASS] {message}")


def log_fail(message):
    global failures
    failures += 1
    print(f"[FAIL] {message}")


def request(path, method="GET", body=None, timeout=5):
    url = BASE_URL + path

    data = None
    headers = {}

    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw

            return response.status, payload

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw

        return exc.code, payload

    except Exception as exc:
        return None, str(exc)


def wait_for_ready():
    print(f"Waiting up to {TIMEOUT}s for application readiness...")

    deadline = time.time() + TIMEOUT

    while time.time() < deadline:
        status, payload = request("/ready", timeout=3)

        if status == 200:
            log_pass("/ready reports PostgreSQL and Redis ready")
            return True

        time.sleep(INTERVAL)

    log_fail(f"/ready did not become healthy within {TIMEOUT}s")
    return False


def check_endpoint(path, expected_status=200):
    status, payload = request(path)

    if status == expected_status:
        log_pass(f"{path} returns HTTP {expected_status}")
        return payload

    log_fail(f"{path} expected HTTP {expected_status}, got {status}: {payload}")
    return None


def check_instances():
    instances = set()

    for _ in range(20):
        status, payload = request("/instance")

        if status != 200:
            log_fail(f"/instance returned HTTP {status}")
            return

        if isinstance(payload, dict):
            instance = payload.get("instance_id")
            if instance:
                instances.add(instance)

    expected = {"app-01", "app-02"}

    if expected.issubset(instances):
        log_pass(f"Both backend instances observed: {sorted(instances)}")
    else:
        log_fail(
            f"Expected both app-01 and app-02, observed: {sorted(instances)}"
        )


def check_records():
    title = f"validation-{int(time.time())}"

    status, payload = request(
        "/records",
        method="POST",
        body={"title": title},
    )

    if status != 201:
        log_fail(f"POST /records expected 201, got {status}: {payload}")
        return

    log_pass("POST /records creates a PostgreSQL record")

    status, payload = request("/records")

    if status != 200:
        log_fail(f"GET /records expected 200, got {status}")
        return

    records = payload.get("records", []) if isinstance(payload, dict) else []

    if any(record.get("title") == title for record in records):
        log_pass("GET /records returns the created PostgreSQL record")
    else:
        log_fail("Created PostgreSQL record was not found")


def check_counter():
    status1, payload1 = request("/counter")
    status2, payload2 = request("/counter")

    if status1 != 200 or status2 != 200:
        log_fail(
            f"/counter failed: first={status1}, second={status2}"
        )
        return

    try:
        first = int(payload1["counter"])
        second = int(payload2["counter"])
    except (KeyError, TypeError, ValueError):
        log_fail(f"/counter returned unexpected data: {payload1}, {payload2}")
        return

    if second > first:
        log_pass(f"Redis counter increments: {first} -> {second}")
    else:
        log_fail(f"Redis counter did not increment: {first} -> {second}")


def check_network_isolation():
    try:
        result = subprocess.run(
            ["docker", "inspect", "nginx", "app-01", "app-02", "postgres", "redis"],
            capture_output=True,
            text=True,
            check=True,
        )

        containers = json.loads(result.stdout)

        published = []

        for container in containers:
            name = container["Name"].lstrip("/")

            ports = container["NetworkSettings"]["Ports"] or {}

            for container_port, bindings in ports.items():
                if bindings:
                    for binding in bindings:
                        published.append(
                            (
                                name,
                                container_port,
                                binding.get("HostIp"),
                                binding.get("HostPort"),
                            )
                        )

        non_nginx = [item for item in published if item[0] != "nginx"]

        if non_nginx:
            log_fail(
                f"Non-NGINX containers expose host ports: {non_nginx}"
            )
        else:
            log_pass("Only NGINX publishes a host port")

        nginx_ports = [item for item in published if item[0] == "nginx"]

        expected_port = str(PUBLIC_PORT)

        if any(item[3] == expected_port for item in nginx_ports):
            log_pass(f"NGINX publishes host port {PUBLIC_PORT}")
        else:
            log_fail(
                f"NGINX does not publish expected host port {PUBLIC_PORT}: "
                f"{nginx_ports}"
            )

    except subprocess.CalledProcessError as exc:
        log_fail(f"Could not inspect Docker containers: {exc}")
    except Exception as exc:
        log_fail(f"Network isolation check failed: {exc}")


def check_container_health():
    containers = ["nginx", "app-01", "app-02", "postgres", "redis"]

    for container in containers:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Health.Status}}",
                    container,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            health = result.stdout.strip()

            if health == "healthy":
                log_pass(f"{container} is healthy")
            else:
                log_fail(f"{container} health status: {health}")

        except subprocess.CalledProcessError:
            log_fail(f"Could not inspect health of {container}")


def main():
    print("=" * 60)
    print("BARQ Academy environment validation")
    print(f"Public endpoint: {BASE_URL}")
    print("=" * 60)

    # First establish bounded readiness.
    wait_for_ready()

    # Required endpoints.
    check_endpoint("/")
    check_endpoint("/health")
    check_endpoint("/ready")
    check_endpoint("/instance")

    # Real PostgreSQL operation.
    check_records()

    # Real Redis operation.
    check_counter()

    # Prove both application instances are behind NGINX.
    check_instances()

    # Docker-level checks.
    check_container_health()
    check_network_isolation()

    print("=" * 60)

    if failures:
        print(f"Validation: FAIL ({failures} failed checks)")
        sys.exit(1)

    print("Validation: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
