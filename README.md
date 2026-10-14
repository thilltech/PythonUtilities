# pythonutilities
Various Python scripts that I've written for my IT administration job. I'm sharing them here in case they make someone else's job a little easier too.

## Requirements

- Python 3.x
- Microsoft Windows
All scripts were written in and intended to run in Python 3.x and Windows 11 environments. They have not been tested in or developed for other environments.

## Current Scripts
### routereport.py

Analyzes output from the Windows `tracert` command and checks for user-defined IP addresses.

#### Features

- Runs a traceroute to a specified destination
- Searches for monitored IP addresses within the route
- Reports which monitored addresses were found
- Confirms whether the destination was reached
- Displays round-trip time (RTT) information when available

#### Used For

- Validating failover routing
- Verifying WAN or VPN path selection
- Confirming traffic is traversing expected network paths
- Troubleshooting network connectivity issues
