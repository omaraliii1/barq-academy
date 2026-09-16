#!/usr/bin/env python3

import json
import os
import subprocess
import sys
import time
import urllib.request

PUBLIC_PORT = int(os.getenv("PUBLIC_PORT", "8080"))
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"

REQUESTS = 30
REQUEST_TIMEOUT = 3


def request():
    try:
        request = urllib.request.Request(
            f"{BASE_URL}/instance",
            headers={"Connection": "close"},
        )

        start = time.perf_counter()

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            body = response.read().decode()

        duration = time.perf_counter() - start

        try:
            payload = json.loads(body)
            instance = payload.get("instance_id")
        except json.JSONDecodeError:
            instance = None

        return True, instance, duration

    except Exception:
        return False, None, None


def traffic_test(label, count=REQUESTS):
    print(f"\n--- {label} ---")

    successful = 0
    failed = 0
    instances = {}

    for _ in range(count):
        success, instance, duration = request()

        if success:
            successful += 1
            instances[instance] = instances.get(instance, 0) + 1
        else:
            failed += 1

    print(f"Requests:   {count}")
    print(f"Successful: {successful}")
    print(f"Failed:     {failed}")
    print(f"Instances:  {instances}")

    return successful, failed, instances


def compose(command):
    result = subprocess.run(
        ["docker", "compose"] + command,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    return result


def wait_for_instance(instance, timeout=30):
    print(f"\nWaiting up to {timeout}s for {instance} to recover...")

    deadline = time.time() + timeout

    while time.time() < deadline:
        success, current_instance, _ = request()

        if success and current_instance == instance:
            print(f"[PASS] {instance} is serving traffic again")
            return True

        time.sleep(1)

    print(f"[FAIL] {instance} did not recover within {timeout}s")
    return False


def main():
    print("=" * 60)
    print("BARQ backend failure/recovery test")
    print(f"Public endpoint: {BASE_URL}")
    print("=" * 60)

    # Establish baseline.
    baseline_success, baseline_failed, baseline_instances = traffic_test(
        "Baseline traffic"
    )

    if baseline_success == 0:
        print("[FAIL] No successful baseline traffic")
        sys.exit(1)

    # Stop one backend.
    print("\nStopping app-01...")
    compose(["stop", "app-01"])

    try:
        # Give NGINX a moment to detect the failed upstream.
        time.sleep(2)

        failed_success, failed_requests, failed_instances = traffic_test(
            "Traffic while app-01 is stopped"
        )

        # We expect traffic to continue through app-02.
        if failed_success == 0:
            print("[FAIL] No traffic survived backend failure")
            sys.exit(1)

        if "app-02" not in failed_instances:
            print(
                "[FAIL] app-02 did not serve traffic while app-01 was stopped"
            )
            sys.exit(1)

        print("[PASS] app-02 continued serving traffic")

        # Restore app-01.
        print("\nStarting app-01...")
        compose(["start", "app-01"])

        if not wait_for_instance("app-01"):
            sys.exit(1)

        # Prove recovered backend receives requests.
        recovery_success, recovery_failed, recovery_instances = traffic_test(
            "Traffic after app-01 recovery"
        )

        if "app-01" not in recovery_instances:
            print("[FAIL] Recovered app-01 did not serve traffic")
            sys.exit(1)

        print("[PASS] Recovered app-01 served traffic")

        print("\n" + "=" * 60)
        print("Failure/recovery test: PASS")
        print("=" * 60)

    finally:
        # Make a best effort to restore app-01 if the script exits unexpectedly.
        subprocess.run(
            ["docker", "compose", "start", "app-01"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
