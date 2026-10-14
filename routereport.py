"""
routereport.py
This script parses output from the Windows tracert command and checks for specific IPs. This can be used to confirm the status of failover routing or for verifying specific IP routes. 

Tim Hill, 2026
License: GPLv3
Version: 1.0.1
Dependencies: Python 3.10+, Windows operating system
"""

import ipaddress
import re
import subprocess
import sys
from datetime import datetime

DESTINATION = input("Enter the destination IP address: ")

MONITORED_IPS = {}
while True:
    name = input(
        "Enter a name for the next address you want to monitor (or 'done' to finish): "
    )

    if name.lower() == "done":
        break

    ip = input(f"Enter the IP address for {name}: ")

    MONITORED_IPS[name] = ip

print("\nMonitoring for the following addresses:")
for name, ip in MONITORED_IPS.items():
    print(f"{name}: {ip}")

# Maximum time tracert waits for each reply, in milliseconds. Update with your preferred value.
TIMEOUT_MS = 2000

# Maximum number of hops. Update with your preferred value.
MAX_HOPS = 30


def validate_configuration():
    """Make sure addresses in the configuration section are valid."""
    addresses = {"Destination": DESTINATION}
    addresses.update(MONITORED_IPS)

    for name, address in addresses.items():
        try:
            ipaddress.ip_address(address)
        except ValueError:
            print(f"Configuration error: Invalid {name} address {address}")
            sys.exit(1)


def run_tracert():
    """Run tracert command and return its output."""
    command = [
        "tracert",
        "-d",  # No DNS resolution
        "-h",
        str(MAX_HOPS),
        "-w",
        str(TIMEOUT_MS),
        DESTINATION,
    ]

    print(f"Running traceroute to {DESTINATION} using command: {' '.join(command)}")
    print()

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=((MAX_HOPS * TIMEOUT_MS * 3) / 1000) + 30,
        )
    except FileNotFoundError:
        print("Error: The Windows tracert command was not found.")
        print("This script is intended to run on Windows.")
        sys.exit(1)
    except subprocess.TimeoutExpired as error:
        print("Error: tracert exceeded the script's overall timeout.")

        partial_output = error.stdout or ""
        if isinstance(partial_output, bytes):
            partial_output = partial_output.decode(errors="replace")

        return partial_output

    return result.stdout


def extract_ip_addresses(line):
    """Extract valid IPv4 addresses from a line of tracert output."""
    candidates = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", line)
    valid_addresses = []
    for candidate in candidates:
        try:
            parsed = ipaddress.ip_address(candidate)
            if parsed.version == 4:
                valid_addresses.append(candidate)
        except ValueError:
            continue

    return valid_addresses


def extract_round_trip_times(line):
    """
    Extract RTT measurements from one tracert hop.

    Handles values such as:
      14 ms
      <1 ms
      Request timed out.
    """
    round_trip_times = []

    for value in re.findall(r"(<\s*1|\d+)\s*ms", line, flags=re.IGNORECASE):
        normalized = value.replace(" ", "")

        if normalized.startswith("<"):
            round_trip_times.append(0.5)
        else:
            round_trip_times.append(float(normalized))

    return round_trip_times


def parse_tracert_output(output):
    """Parse tracert output."""
    hops = []
    for line in output.splitlines():
        # Each line begins with the hop number.
        hop_match = re.match(r"^\s*(\d+)\s+", line)

        if not hop_match:
            continue

        hop_number = int(hop_match.group(1))
        ip_addresses = extract_ip_addresses(line)
        round_trip_times = extract_round_trip_times(line)

        hops.append(
            {
                "hop": hop_number,
                "ips": ip_addresses,
                "rtts": round_trip_times,
                "timed_out": "*" in line and not ip_addresses,
                "raw": line.rstrip(),
            }
        )

    return hops


def analyze_results(hops):
    """Analyze destination reachability, RTT, and monitored IP matches."""
    destination_hop = None

    for hop in hops:
        if DESTINATION in hop["ips"]:
            destination_hop = hop
            break

    reached_destination = destination_hop is not None

    destination_rtt = None
    if destination_hop and destination_hop["rtts"]:
        destination_rtt = sum(destination_hop["rtts"]) / len(destination_hop["rtts"])

    monitored_results = {}

    for label, monitored_ip in MONITORED_IPS.items():
        matching_hops = []

        for hop in hops:
            if monitored_ip in hop["ips"]:
                matching_hops.append(hop["hop"])

        monitored_results[label] = {
            "ip": monitored_ip,
            "seen": len(matching_hops) > 0,
            "hops": matching_hops,
        }

    return reached_destination, destination_rtt, destination_hop, monitored_results


def print_hop_summary(hops):
    """Print a simplified summary of all parsed hops."""
    print("=" * 70)
    print("HOP SUMMARY\n")

    if not hops:
        print("No traceroute hops were parsed.")
        return

    for hop in hops:
        if hop["timed_out"]:
            print(f"Hop {hop['hop']:>2}: Timed out")
            continue

        addresses = ", ".join(hop["ips"]) if hop["ips"] else "No IP returned"

        if hop["rtts"]:
            rtt_text = ", ".join(
                f"{rtt:g} ms" if rtt >= 1 else "<1 ms" for rtt in hop["rtts"]
            )
        else:
            rtt_text = "No RTT measurements"

        print(f"Hop {hop['hop']:>2}: {addresses} | {rtt_text}")


def print_analysis(
    reached_destination,
    destination_rtt,
    destination_hop,
    monitored_results,
):
    """Print the route analysis."""
    print()
    print("=" * 70)
    print("ROUTE ANALYSIS\n")
    print(f"Destination:          {DESTINATION}")
    print(f"Destination reached:  {'YES' if reached_destination else 'NO'}")

    if reached_destination:
        print(f"Number of hops:       {destination_hop['hop']}")

        if destination_rtt is not None:
            print(f"Approximate RTT:      {destination_rtt:.1f} ms")
        else:
            print(
                "Approximate RTT:      Destination reached, but Round-Trip Time could not be measured."
            )
    else:
        print("Destination hop:      Not reached")
        print("Approximate RTT:      Not available")

    print()
    print("Monitored addresses:")

    detected_paths = []

    for label, result in monitored_results.items():
        if result["seen"]:
            hop_list = ", ".join(str(hop) for hop in result["hops"])
            print(f"  [SEEN]     {label}: {result['ip']} " f"at hop(s) {hop_list}")
            detected_paths.append(label)
        else:
            print(f"  [NOT SEEN] {label}: {result['ip']}")

    print()
    print("Routing assessment:")

    if len(detected_paths) == 1:
        print(f"  The route is using {detected_paths[0]}.")
    elif len(detected_paths) > 1:
        print(
            "  Multiple monitored addresses appeared in the route: "
            + ", ".join(detected_paths)
        )
    else:
        print("  None of the monitored IP addresses appeared in the route.")
        print(
            "  This may be due to router configuration or filtered network responses."
        )


def main():
    validate_configuration()
    print(f"Network traceroute test started: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print()
    output = run_tracert()

    hops = parse_tracert_output(output)

    print_hop_summary(hops)

    results = analyze_results(hops)
    print_analysis(*results)

    print()
    print(f"Test completed: {datetime.now():%Y-%m-%d %H:%M:%S}")

# Exit code for future automation
    if results[0]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
