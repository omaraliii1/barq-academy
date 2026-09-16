#!/usr/bin/env python3
import time
import subprocess
import sys
import json


"""Validate that the required BARQ services are running."""

REQUIRED_SERVICES = [
    "nginx",
    "app-01",
    "app-02",
    "postgres",
    "redis",
]



def wait_for_http(url, timeout=30):
    start = time.time()

    while time.time() - start < timeout:
        result = subprocess.run(
            ["curl", "-sf", "--max-time", "2", url],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return True

        time.sleep(1)

    return False


def check_endpoint(path, expected_status=200):
    url = f"http://127.0.0.1:8080{path}"

    result = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
         "--max-time", "2", url],
        capture_output=True,
        text=True,
    )

    status = result.stdout.strip()

    if status == str(expected_status):
        print(f"[PASS] GET {path} returns {status}")
        return 0

    print(f"[FAIL] GET {path} returned {status}, expected {expected_status}")
    return 1



def check_instance():
    url = "http://127.0.0.1:8080/instance"

    result = subprocess.run(
        ["curl", "-s", "--max-time", "2", url],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("[FAIL] GET /instance request failed")
        return 1

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print("[FAIL] GET /instance returned invalid JSON")
        return 1

    instance_id = data.get("instance_id")

    if instance_id in {"app-01", "app-02"}:
        print(f"[PASS] GET /instance identifies {instance_id}")
        return 0

    print(f"[FAIL] GET /instance returned invalid instance_id: {instance_id}")
    return 1



def check_records():
    url = "http://127.0.0.1:8080/records"
    title = f"validation-{time.time_ns()}"

    create_result = subprocess.run(
        [
            "curl", "-sS", "--max-time", "2",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"title": title}),
            "-w", "\n%{http_code}",
            url,
        ],
        capture_output=True,
        text=True,
    )

    if create_result.returncode != 0:
        print("[FAIL] POST /records request failed")
        return 1

    lines = create_result.stdout.strip().splitlines()
    status = lines[-1] if lines else ""

    if status != "201":
        print(f"[FAIL] POST /records returned {status}, expected 201")
        return 1

    try:
        data = json.loads("\n".join(lines[:-1]))
    except json.JSONDecodeError:
        print("[FAIL] POST /records returned invalid JSON")
        return 1

    if data.get("record", {}).get("title") != title:
        print("[FAIL] POST /records did not return the created record")
        return 1

    get_result = subprocess.run(
        ["curl", "-sS", "--max-time", "2", url],
        capture_output=True,
        text=True,
    )

    if get_result.returncode != 0:
        print("[FAIL] GET /records request failed")
        return 1

    try:
        data = json.loads(get_result.stdout)
    except json.JSONDecodeError:
        print("[FAIL] GET /records returned invalid JSON")
        return 1

    records = data.get("records", [])

    if any(record.get("title") == title for record in records):
        print("[PASS] /records can create and read PostgreSQL records")
        return 0

    print("[FAIL] Created record was not found by GET /records")
    return 1



def check_counter():
    url = "http://127.0.0.1:8080/counter"

    first_result = subprocess.run(
        ["curl", "-sS", "--max-time", "2", url],
        capture_output=True,
        text=True,
    )

    if first_result.returncode != 0:
        print("[FAIL] First GET /counter request failed")
        return 1

    try:
        first_data = json.loads(first_result.stdout)
        first_value = first_data["counter"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("[FAIL] First /counter response is invalid")
        return 1

    second_result = subprocess.run(
        ["curl", "-sS", "--max-time", "2", url],
        capture_output=True,
        text=True,
    )

    if second_result.returncode != 0:
        print("[FAIL] Second GET /counter request failed")
        return 1

    try:
        second_data = json.loads(second_result.stdout)
        second_value = second_data["counter"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print("[FAIL] Second /counter response is invalid")
        return 1

    if second_value == first_value + 1:
        print("[PASS] /counter increments correctly using Redis")
        return 0

    print(
        f"[FAIL] /counter did not increment correctly: "
        f"{first_value} -> {second_value}"
    )
    return 1




def check_services():
    failed = 0

    for service in REQUIRED_SERVICES:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", service],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0 and result.stdout.strip() == "true":
            print(f"[PASS] {service} is running")
        else:
            print(f"[FAIL] {service} is not running")
            failed += 1

    return failed


def main():
    failed = check_services()

    if wait_for_http("http://127.0.0.1:8080/health"):
        print("[PASS] NGINX /health is reachable")
    else:
        print("[FAIL] NGINX /health did not become ready within 30 seconds")
        failed += 1
    
    
    failed += check_endpoint("/")
    failed += check_endpoint("/health")
    failed += check_endpoint("/ready")
    failed += check_instance()
    failed += check_records()
    failed += check_counter()
    
    
    print()
    if failed == 0:
        print("Validation passed.")
        return 0

    print(f"Validation failed: {failed} check(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
