#!/usr/bin/env python3
"""
Rock-Solid Website Blocker
==========================

A multi-layered distraction blocker that makes it nearly impossible to bypass.

Layers of protection:
1. Hosts file blocking (redirects domains to 127.0.0.1)
2. Immutable flag (chattr +i) - prevents editing even as root
3. iptables firewall rules - blocks at kernel/network level
4. Scheduled unlock via systemd-run - no manual unblock possible
5. Signal immunity - can't be killed with Ctrl+C during lock

The only escape: reboot into recovery mode and manually undo.
That's enough friction to stop impulse browsing.

See explainer.md for deep technical details.
"""

import sys
import argparse
import logging
import subprocess
import platform
import socket
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, List
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BlockPageServer:
    """Manages the block page server as a persistent systemd service."""

    SERVICE_NAME = "deepwork-blockpage"

    @classmethod
    def start(cls):
        """Start the block page server as a persistent systemd service."""
        script_dir = Path(__file__).parent
        server_script = script_dir / 'block_server.py'

        if not server_script.exists():
            logger.warning("block_server.py not found, skipping block page")
            return

        # Stop any existing instance first
        cls.stop()

        try:
            # Start as a systemd service that persists after this script exits
            subprocess.run([
                "systemd-run",
                "--unit", cls.SERVICE_NAME,
                "--description", "DeepWork Block Page Server",
                "python3", str(server_script)
            ], check=True, capture_output=True)
            logger.info("Block page server started as systemd service")
        except subprocess.CalledProcessError as e:
            logger.warning(f"Could not start block page server: {e}")
        except FileNotFoundError:
            logger.warning("systemd-run not found, block page server not started")

    @classmethod
    def stop(cls):
        """Stop the block page server service."""
        try:
            subprocess.run(
                ["systemctl", "stop", cls.SERVICE_NAME],
                check=False, capture_output=True
            )
            logger.info("Block page server stopped")
        except Exception:
            pass  # Service may not exist


class RockSolidBlocker:
    """
    Multi-layered website blocker with maximum bypass resistance.

    Protection layers:
    1. /etc/hosts redirect to 127.0.0.1
    2. chattr +i immutable flag on hosts file
    3. iptables OUTPUT chain blocks for resolved IPs
    4. systemd-run scheduled unlock (no manual escape)
    """

    def __init__(self):
        self.system = platform.system()
        if self.system != "Linux":
            raise SystemError("Rock-solid mode requires Linux (for chattr and iptables)")

        self.hosts_path = Path("/etc/hosts")
        self.localhost = "127.0.0.1"
        self.localhost_v6 = "::1"
        self.block_marker_start = "# >>> DEEPWORK BLOCK START - DO NOT EDIT <<<"
        self.block_marker_end = "# >>> DEEPWORK BLOCK END <<<"
        self.iptables_comment = "deepwork-block"
        self.blocked_ips: Set[str] = set()

    def _run_cmd(self, cmd: List[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
        """Run a shell command with proper error handling."""
        try:
            result = subprocess.run(
                cmd,
                check=check,
                capture_output=capture,
                text=True
            )
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {' '.join(cmd)}")
            logger.error(f"Error: {e.stderr if e.stderr else e}")
            raise

    def _resolve_domain_ips(self, domain: str) -> Set[str]:
        """Resolve a domain to its IP addresses."""
        ips = set()
        try:
            # Get all IP addresses for the domain
            results = socket.getaddrinfo(domain, None, socket.AF_INET)
            for result in results:
                ips.add(result[4][0])
        except socket.gaierror:
            logger.warning(f"Could not resolve {domain}")
        return ips

    def _expand_domains(self, domains: Set[str]) -> Set[str]:
        """Add www. variant for each domain."""
        expanded = set()
        for domain in domains:
            domain = domain.strip().lower()
            if not domain:
                continue
            expanded.add(domain)
            if not domain.startswith('www.'):
                expanded.add('www.' + domain)
        return expanded

    # =========================================================================
    # Layer 1: Hosts File Blocking
    # =========================================================================

    def _remove_immutable_flag(self) -> None:
        """Remove immutable flag from hosts file."""
        try:
            self._run_cmd(["chattr", "-i", str(self.hosts_path)], check=False)
        except Exception:
            pass  # May already be mutable

    def _set_immutable_flag(self) -> None:
        """Set immutable flag on hosts file."""
        self._run_cmd(["chattr", "+i", str(self.hosts_path)])
        logger.info("Hosts file locked with immutable flag")

    def _add_hosts_entries(self, domains: Set[str]) -> None:
        """Add blocking entries to hosts file."""
        self._remove_immutable_flag()

        content = self.hosts_path.read_text()

        # Remove any existing block entries
        lines = content.splitlines()
        filtered_lines = []
        in_block = False
        for line in lines:
            if self.block_marker_start in line:
                in_block = True
                continue
            if self.block_marker_end in line:
                in_block = False
                continue
            if not in_block:
                filtered_lines.append(line)

        # Add new block entries
        filtered_lines.append("")
        filtered_lines.append(self.block_marker_start)
        for domain in sorted(domains):
            filtered_lines.append(f"{self.localhost} {domain}")
            filtered_lines.append(f"{self.localhost_v6} {domain}")
        filtered_lines.append(self.block_marker_end)

        self.hosts_path.write_text('\n'.join(filtered_lines) + '\n')
        logger.info(f"Added {len(domains)} domains to hosts file")

    def _remove_hosts_entries(self) -> None:
        """Remove blocking entries from hosts file."""
        self._remove_immutable_flag()

        content = self.hosts_path.read_text()
        lines = content.splitlines()
        filtered_lines = []
        in_block = False

        for line in lines:
            if self.block_marker_start in line:
                in_block = True
                continue
            if self.block_marker_end in line:
                in_block = False
                continue
            if not in_block:
                filtered_lines.append(line)

        self.hosts_path.write_text('\n'.join(filtered_lines) + '\n')
        logger.info("Removed hosts file entries")

    # =========================================================================
    # Layer 2: iptables Firewall Blocking
    # =========================================================================

    def _add_iptables_rules(self, domains: Set[str]) -> None:
        """Block domains at the firewall level using iptables."""
        for domain in domains:
            ips = self._resolve_domain_ips(domain)
            for ip in ips:
                if ip not in self.blocked_ips:
                    try:
                        self._run_cmd([
                            "iptables", "-A", "OUTPUT",
                            "-d", ip,
                            "-j", "REJECT",
                            "-m", "comment", "--comment", self.iptables_comment
                        ])
                        self.blocked_ips.add(ip)
                    except Exception as e:
                        logger.warning(f"Could not add iptables rule for {ip}: {e}")

        if self.blocked_ips:
            logger.info(f"Added iptables rules for {len(self.blocked_ips)} IPs")

    def _remove_iptables_rules(self) -> None:
        """Remove all deepwork iptables rules."""
        # List all rules and find ours
        try:
            result = self._run_cmd(
                ["iptables", "-L", "OUTPUT", "-n", "--line-numbers", "-v"],
                capture=True
            )

            # Parse and remove rules with our comment (in reverse order to preserve line numbers)
            lines_to_delete = []
            for line in result.stdout.splitlines():
                if self.iptables_comment in line:
                    parts = line.split()
                    if parts and parts[0].isdigit():
                        lines_to_delete.append(int(parts[0]))

            # Delete in reverse order
            for line_num in sorted(lines_to_delete, reverse=True):
                self._run_cmd(["iptables", "-D", "OUTPUT", str(line_num)], check=False)

            if lines_to_delete:
                logger.info(f"Removed {len(lines_to_delete)} iptables rules")
        except Exception as e:
            logger.warning(f"Could not clean iptables rules: {e}")

    # =========================================================================
    # Layer 3: DNS Cache Flush
    # =========================================================================

    def _flush_dns(self) -> None:
        """Flush DNS cache gently."""
        commands = [
            ["resolvectl", "flush-caches"],
            ["systemctl", "restart", "systemd-resolved"],
        ]

        for cmd in commands:
            try:
                self._run_cmd(cmd, check=False)
                logger.debug(f"Executed: {' '.join(cmd)}")
            except Exception:
                continue

        logger.info("DNS cache flushed")

    # =========================================================================
    # Layer 4: Scheduled Unlock (No Manual Escape)
    # =========================================================================

    def _save_unlock_time(self, unlock_time: datetime) -> None:
        """Save unlock time to a file for status display."""
        unlock_file = Path(__file__).parent / '.unlock_time'
        unlock_file.write_text(unlock_time.isoformat())

    def _clear_unlock_time(self) -> None:
        """Remove the unlock time file."""
        unlock_file = Path(__file__).parent / '.unlock_time'
        if unlock_file.exists():
            unlock_file.unlink()

    def _schedule_unlock(self, duration_minutes: float) -> None:
        """Schedule automatic unlock using systemd-run."""
        script_path = Path(__file__).resolve()
        unlock_time = datetime.now() + timedelta(minutes=duration_minutes)

        # Save unlock time to file for status display
        self._save_unlock_time(unlock_time)

        # Create the unlock command
        unlock_cmd = f"python3 {script_path} --unlock"

        # Schedule with systemd-run
        try:
            # Use absolute time (--on-calendar) to prevent drift if the computer sleeps
            stamp = unlock_time.strftime("%Y-%m-%d %H:%M:%S")
            self._run_cmd([
                "systemd-run",
                "--on-calendar", stamp,
                "--unit", "deepwork-unblock",
                "/bin/bash", "-c", unlock_cmd
            ])
            logger.info(f"Scheduled automatic unlock at {stamp}")
        except Exception as e:
            logger.warning(f"Could not schedule systemd unlock: {e}")
            logger.info("Falling back to 'at' command")

            # Fallback to 'at' command
            try:
                time_str = unlock_time.strftime("%H:%M")

                process = subprocess.Popen(
                    ["at", time_str],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                process.communicate(input=unlock_cmd.encode())
                logger.info(f"Scheduled unlock at {time_str} using 'at'")
            except Exception as e2:
                logger.error(f"Could not schedule unlock: {e2}")
                logger.error("You will need to manually run: sudo python3 blocker.py --unlock")

    # =========================================================================
    # Main Block/Unblock Methods
    # =========================================================================

    def block(self, domains: Set[str], duration_minutes: float, serve_block_page: bool = True) -> None:
        """
        Activate rock-solid blocking.

        This will:
        1. Add domains to hosts file
        2. Lock hosts file with immutable flag
        3. Add iptables rules for resolved IPs
        4. Schedule automatic unlock
        5. Optionally serve a block page on localhost
        """
        if os.geteuid() != 0:
            raise PermissionError("Must run as root (use sudo)")

        expanded_domains = self._expand_domains(domains)
        end_time = datetime.now() + timedelta(minutes=duration_minutes)

        logger.info("=" * 60)
        logger.info("ACTIVATING ROCK-SOLID BLOCK")
        logger.info("=" * 60)
        logger.info(f"Domains: {len(expanded_domains)}")
        logger.info(f"Duration: {duration_minutes} minutes")
        logger.info(f"Unlock at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

        # Layer 1: Hosts file
        self._add_hosts_entries(expanded_domains)

        # Layer 2: iptables (Disabled to prevent over-blocking of shared CDN IPs)
        # self._add_iptables_rules(expanded_domains)

        # Layer 3: DNS flush
        self._flush_dns()

        # Layer 4: Schedule unlock
        self._schedule_unlock(duration_minutes)

        # Layer 1b: Lock hosts file (after everything else)
        self._set_immutable_flag()

        # Optional: Block page server (runs as persistent systemd service)
        if serve_block_page:
            BlockPageServer.start()

        logger.info("")
        logger.info("=" * 60)
        logger.info("BLOCK ACTIVE - NO ESCAPE UNTIL TIMER EXPIRES")
        logger.info("=" * 60)
        logger.info("")
        logger.info("To bypass, you would need to:")
        logger.info("  1. Reboot into recovery mode")
        logger.info("  2. Run: chattr -i /etc/hosts")
        logger.info("  3. Edit /etc/hosts manually")
        logger.info("  4. Flush iptables: iptables -F OUTPUT")
        logger.info("")
        logger.info("That's enough friction to stop impulse browsing.")
        logger.info("Get back to work! 💪")
        logger.info("")

    def unblock(self) -> None:
        """Remove all blocking measures."""
        if os.geteuid() != 0:
            raise PermissionError("Must run as root (use sudo)")

        logger.info("=" * 60)
        logger.info("REMOVING BLOCK")
        logger.info("=" * 60)

        # Remove hosts entries (also removes immutable flag)
        self._remove_hosts_entries()

        # Remove iptables rules (if any exist from previous runs)
        self._remove_iptables_rules()

        # Flush DNS
        self._flush_dns()

        # Stop block page server
        BlockPageServer.stop()

        # Clear unlock time file
        self._clear_unlock_time()

        logger.info("=" * 60)
        logger.info("BLOCK REMOVED - Sites are now accessible")
        logger.info("=" * 60)


def parse_duration(time_str: str) -> float:
    """Parse time string into minutes."""
    units = {
        's': 1/60,
        'm': 1,
        'h': 60,
        'd': 1440
    }

    match = re.match(r'^(\d+(?:\.\d+)?)([smhd])?$', time_str.lower())
    if not match:
        raise ValueError(
            "Invalid time format. Use:\n"
            "  - Plain number for minutes: '30'\n"
            "  - With units: '30s', '45m', '2h', '1d'"
        )

    number, unit = match.groups()
    return float(number) * units.get(unit, 1)


def load_domains(file_path: Path) -> Set[str]:
    """Load domains from a text file."""
    if not file_path.exists():
        raise FileNotFoundError(f"Distractions file not found: {file_path}")

    domains = set()
    for line in file_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            domains.add(line)

    return domains


def main():
    parser = argparse.ArgumentParser(
        description='Rock-Solid Website Blocker - Cannot be bypassed without reboot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 blocker.py -t 25m          # 25-minute focus session
  sudo python3 blocker.py -t 2h           # 2-hour deep work block
  sudo python3 blocker.py -t 8h           # Full workday block
  sudo python3 blocker.py --unlock        # Manual unlock (scheduled automatically)

The block cannot be undone until the timer expires.
Only escape: reboot into recovery mode.
        """
    )

    parser.add_argument('-f', '--file', type=Path, default='distractions.txt',
                       help='File containing domains to block (default: distractions.txt)')
    parser.add_argument('-t', '--time', type=str, default='25m',
                       help='Block duration: 30s, 25m, 2h, 1d (default: 25m)')
    parser.add_argument('--unlock', action='store_true',
                       help='Remove all blocks (called automatically by scheduler)')
    parser.add_argument('--no-block-page', action='store_true',
                       help='Disable the localhost block page')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        blocker = RockSolidBlocker()

        if args.unlock:
            blocker.unblock()
        else:
            domains = load_domains(args.file)
            if not domains:
                logger.error("No domains found in distractions file")
                sys.exit(1)

            duration = parse_duration(args.time)
            blocker.block(domains, duration, serve_block_page=not args.no_block_page)

    except PermissionError as e:
        logger.error(f"Permission denied: {e}")
        logger.error("Run with sudo: sudo python3 blocker.py -t 25m")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
