"""
pingreport.py
This script runs a continuous ping on a host until stopped, then generates a timestamped report of the ping results.

Tim Hill, 2026
License: GPLv3
Version: 1.0.0
Dependencies: Python 3.10+, Windows operating system
"""

import csv
import platform
import re
import subprocess
import threading
import time
from datetime import datetime

stop_requested = False


def listen_for_quit():
    global stop_requested

    while True:
        user_input = input()
        if user_input.strip().upper() == "Q":
            stop_requested = True
            break


def ping_host(host):
    param = "-n" if platform.system().lower() == "windows" else "-c"

    result = subprocess.run(["ping", param, "1", host], capture_output=True, text=True)

    output = result.stdout.strip()

    if result.returncode == 0:
        status = "UP"

        latency = ""

        if platform.system().lower() == "windows":
            match = re.search(r"time[=<]\s*(\d+)ms", output, re.IGNORECASE)
        else:
            match = re.search(r"time=(\d+\.?\d*)", output)

        if match:
            latency = match.group(1)

        # message = output.splitlines()[-1]
        # Leave message blank for successful pings
        message = ""

    else:
        status = "DOWN"
        latency = ""

        # Populate message only for failures
        if output:
            message = output.splitlines()[-1]
        elif result.stderr:
            message = result.stderr.strip()
        else:
            message = "No response"

    return status, latency, message


def main():

    host = input("Enter hostname or ip address to monitor: ").strip()

    while True:
        try:
            interval = float(input("Enter ping interval in seconds: "))
            if interval > 0:
                break
            print("Interval must be greater than 0.")
        except ValueError:
            print("Please enter a valid number.")

    print("\nMonitoring started.")
    print("Press Q then Enter at any time to stop.\n")

    threading.Thread(target=listen_for_quit, daemon=True).start()

    results = []
    csv_filename = None

    while not stop_requested:

        timestamp = datetime.now()

        if csv_filename is None:
            safe_host = re.sub(r"[^a-zA-Z0-9_-]", "_", host)
            csv_filename = (
                f"{safe_host}_ping_results_"
                f"{timestamp.strftime('%Y%m%d_%H%M%S')}.csv"
            )

        status, latency, message = ping_host(host)

        print(
            f"{timestamp.strftime('%Y-%m-%d %H:%M:%S')} | "
            f"{host} | "
            f"{status} | "
            f"{latency} ms | "
            f"{message}"
        )

        results.append(
            {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "latency": latency,
                "message": message,
            }
        )

        time.sleep(interval)

    with open(csv_filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile, fieldnames=["timestamp", "status", "latency", "message"]
        )

        writer.writeheader()
        writer.writerows(results)

    print(f"\nMonitoring stopped.")
    print(f"Results saved to: {csv_filename}")


if __name__ == "__main__":
    main()
