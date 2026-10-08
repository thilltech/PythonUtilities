# ---------------------------------------------------------------------
# Traceroute Analyzer
#
# This script parses traceroute information and checks for specific IPs
# in the route. This can be used to confirm the status of failover 
#routing as well as verifying specific IP routes.
#
# Tim Hill, 2026
# ---------------------------------------------------------------------

import ipaddress
import re
import subprocess
import sys
from datetime import datetime

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

DESTINATION = "8.8.8.8"

# Replace these example IP addresses with the addresses and description
# you want to watch for in the traceroute.
MONITORED_IPS = {
    "Primary route": "192.0.2.0",
    "Internet VPN": "198.51.100.10",
    "LTE Backup": "203.0.113.10",
}

# Maximum time tracert waits for each reply, in milliseconds.
TIMEOUT_MS = 2000

# Maximum number of hops.
MAX_HOPS = 30


def validate_configuration():
    """Validate the destination and monitored IP addresses."""
    addresses = {"Destination": DESTINATION}
    addresses.update(MONITORED_IPS)

    for name, address in addresses.items():
        try:
            ipaddress.ip_address(address)
        except ValueError:
            print(f"Configuration error: {name} has an invalid IP address: {address}")
            sys.exit(1)


def run_tracert():
    """Run Windows tracert and return its output."""
    command = [
        "tracert",
        "-d",                   # Do not perform DNS resolution
        "-h", str(MAX_HOPS),    # Maximum number of hops
        "-w", str(TIMEOUT_MS),  # Timeout per probe in milliseconds
        DESTINATION,
    ]

    print(f"Running traceroute to {DESTINATION}...")
    print(f"Command: {' '.join(command)}")
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
    """Parse tracert output into structured hop information."""
    hops = []

    for line in output.splitlines():
        # A tracert hop line begins with a hop number.
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
        destination_rtt = sum(destination_hop["rtts"]) / len(
            destination_hop["rtts"]
        )

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
    print("HOP SUMMARY")
    print("=" * 70)

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
                f"{rtt:g} ms" if rtt >= 1 else "<1 ms"
                for rtt in hop["rtts"]
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
    """Print the final failover analysis."""
    print()
    print("=" * 70)
    print("TRACEROUTE ANALYSIS")
    print("=" * 70)

    print(f"Destination:          {DESTINATION}")
    print(f"Destination reached:  {'YES' if reached_destination else 'NO'}")

    if reached_destination:
        print(f"Destination hop:      {destination_hop['hop']}")

        if destination_rtt is not None:
            print(f"Approximate RTT:      {destination_rtt:.1f} ms")
        else:
            print("Approximate RTT:      Destination reached, but no RTT was parsed")
    else:
        print("Destination hop:      Not reached")
        print("Approximate RTT:      Not available")

    print()
    print("Monitored route addresses:")

    detected_paths = []

    for label, result in monitored_results.items():
        if result["seen"]:
            hop_list = ", ".join(str(hop) for hop in result["hops"])
            print(
                f"  [SEEN]     {label}: {result['ip']} "
                f"at hop(s) {hop_list}"
            )
            detected_paths.append(label)
        else:
            print(f"  [NOT SEEN] {label}: {result['ip']}")

    print()
    print("Failover path assessment:")

    if len(detected_paths) == 1:
        print(f"  The route appears to be using: {detected_paths[0]}")
    elif len(detected_paths) > 1:
        print(
            "  Multiple monitored addresses appeared in the route: "
            + ", ".join(detected_paths)
        )
        print(
            "  This can be normal if the listed addresses represent "
            "different devices along the same path."
        )
    else:
        print("  None of the monitored IP addresses appeared in the route.")
        print(
            "  The ISP may not expose the expected address in traceroute, "
            "or an intermediate device may be filtering ICMP responses."
        )


def main():
    validate_configuration()

    print("=" * 70)
    print("NETWORK FAILOVER TRACEROUTE TEST")
    print("=" * 70)
    print(f"Test started: {datetime.now():%Y-%m-%d %H:%M:%S}")
    print()

    output = run_tracert()
# Uncomment these lines if you want the raw output from the traceroute.
    #print("Raw tracert output:")
    #print("-" * 70)
    #print(output.strip())
    #print("-" * 70)
    #print()

    hops = parse_tracert_output(output)

    print_hop_summary(hops)

    results = analyze_results(hops)
    print_analysis(*results)

    print()
    print(f"Test completed: {datetime.now():%Y-%m-%d %H:%M:%S}")

    # Exit code can be used by monitoring or automation software.
    if results[0]:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()