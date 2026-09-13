#!/usr/bin/env python3

"""Candidate deliverable: stop one backend, measure traffic, restore it and verify."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8080"
TARGET = "app-01"
REQUEST_COUNT = 20
TIMEOUT = 2
RECOVERY_TIMEOUT = 60


def run_compose(*args):
    command = ["docker", "compose", *args]
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result.stdout.strip()


def request_instance():
    try:
        with urllib.request.urlopen(
            f"{BASE_URL}/instance",
            timeout=TIMEOUT,
        ) as response:
            body = json.loads(response.read().decode())

            return {
                "success": True,
                "status": response.status,
                "instance": body.get("instance_id"),
            }

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": None,
            "instance": None,
            "error": str(exc),
        }


def measure_traffic(count):
    results = []

    for _ in range(count):
        results.append(request_instance())

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]

    instances = {}

    for result in successes:
        instance = result["instance"]
        instances[instance] = instances.get(instance, 0) + 1

    return {
        "total": len(results),
        "successful": len(successes),
        "failed": len(failures),
        "instances": instances,
        "results": results,
    }


def print_measurement(name, measurement):
    print(f"\n--- {name} ---")
    print(f"Requests:   {measurement['total']}")
    print(f"Successful: {measurement['successful']}")
    print(f"Failed:     {measurement['failed']}")
    print(f"Instances:  {measurement['instances']}")

    if measurement["failed"]:
        print("Failure examples:")

        for result in measurement["results"]:
            if not result["success"]:
                print(f"  {result['error']}")
                break


def wait_for_instance(instance, timeout=RECOVERY_TIMEOUT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        result = request_instance()

        if result["success"] and result["instance"] == instance:
            return True

        time.sleep(2)

    return False


def main():
    print("=== BARQ backend failure/recovery test ===")
    print(f"Target backend: {TARGET}")
    print(f"Public endpoint: {BASE_URL}")

    target_was_running = False

    try:
        # Make sure the target backend exists and is running.
        ps_output = run_compose("ps", "-q", TARGET)

        if not ps_output:
            raise RuntimeError(f"{TARGET} container was not found.")

        inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", TARGET],
            text=True,
            capture_output=True,
        )

        target_was_running = inspect.stdout.strip() == "true"

        if not target_was_running:
            raise RuntimeError(f"{TARGET} is not running.")

        # 1. Baseline traffic.
        baseline = measure_traffic(REQUEST_COUNT)
        print_measurement("Baseline traffic", baseline)

        if baseline["successful"] == 0:
            raise RuntimeError("Baseline traffic failed completely.")

        # 2. Stop one backend.
        print(f"\nStopping {TARGET}...")
        run_compose("stop", TARGET)

        # Give Docker/NGINX a moment to observe the failure.
        time.sleep(2)

        # 3. Measure traffic while backend is down.
        during_failure = measure_traffic(REQUEST_COUNT)
        print_measurement("Traffic while backend is stopped", during_failure)

        # The surviving backend must receive successful traffic.
        surviving_instances = {
            instance: count
            for instance, count in during_failure["instances"].items()
            if instance != TARGET
        }

        if not surviving_instances:
            raise RuntimeError(
                "No successful traffic reached a surviving backend."
            )

        if during_failure["successful"] == 0:
            raise RuntimeError(
                "All requests failed while one backend was stopped."
            )

        # 4. Restore backend.
        print(f"\nRestoring {TARGET}...")
        run_compose("start", TARGET)

        print(f"Waiting for {TARGET} to recover...")

        if not wait_for_instance(TARGET):
            raise RuntimeError(
                f"{TARGET} did not receive a successful request "
                f"within {RECOVERY_TIMEOUT} seconds."
            )

        # 5. Verify traffic after recovery.
        after_recovery = measure_traffic(REQUEST_COUNT)
        print_measurement("Traffic after backend recovery", after_recovery)

        if after_recovery["successful"] == 0:
            raise RuntimeError("Traffic did not recover.")

        if TARGET not in after_recovery["instances"]:
            raise RuntimeError(
                f"{TARGET} recovered but did not receive traffic."
            )

        print("\nPASS: backend failure and recovery test completed.")

        return 0

    except Exception as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        return 1

    finally:
        # Cleanup: make sure the target backend is running again.
        if target_was_running:
            print(f"\nCleanup: ensuring {TARGET} is running...")

            try:
                run_compose("start", TARGET)
            except Exception as exc:
                print(
                    f"WARNING: cleanup failed for {TARGET}: {exc}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    sys.exit(main())
