#!/usr/bin/env python3
"""
Focus Mode - Simple Interactive Interface
==========================================

Just run: sudo ./focus.py

No flags, no commands - just pick an option.
"""

import os
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header():
    print(f"""
{Colors.CYAN}{Colors.BOLD}
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║                    {Colors.RED}█▀▀ █▀█ █▀▀ █ █ █▀▀{Colors.CYAN}                    ║
    ║                    {Colors.RED}█▀  █ █ █   █ █ ▀▀█{Colors.CYAN}                    ║
    ║                    {Colors.RED}▀   ▀▀▀ ▀▀▀ ▀▀▀ ▀▀▀{Colors.CYAN}                    ║
    ║                                                           ║
    ║              Deep Work Distraction Blocker                ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
{Colors.RESET}""")


def get_block_status():
    """Check if block is active and return status info."""
    status = {
        'is_active': False,
        'unlock_time': None
    }

    hosts_path = Path('/etc/hosts')
    script_dir = Path(__file__).parent
    unlock_file = script_dir / '.unlock_time'

    # Check for block markers in hosts file
    try:
        content = hosts_path.read_text()
        status['is_active'] = 'DEEPWORK BLOCK START' in content
    except:
        pass

    # Read unlock time from file
    if unlock_file.exists():
        try:
            unlock_str = unlock_file.read_text().strip()
            status['unlock_time'] = datetime.fromisoformat(unlock_str)
        except:
            pass

    return status


def print_status_banner(status: dict):
    """Print the current block status on main page."""
    if status['is_active']:
        print(f"    ┌─────────────────────────────────────────────────────┐")
        print(f"    │  {Colors.GREEN}{Colors.BOLD}FOCUS MODE ACTIVE{Colors.RESET}                                  │")

        if status['unlock_time']:
            unlock_str = status['unlock_time'].strftime('%H:%M')
            print(f"    │  Blocking until {Colors.CYAN}{unlock_str}{Colors.RESET}                               │")
        else:
            print(f"    │  {Colors.DIM}Unlock time unknown{Colors.RESET}                                │")

        print(f"    └─────────────────────────────────────────────────────┘")
    else:
        print(f"    {Colors.DIM}No active block. Enter a duration to start focusing.{Colors.RESET}")
    print()


def print_menu(block_active: bool):
    """Print menu options based on whether block is active."""
    if block_active:
        print(f"""    {Colors.DIM}Block is locked. Wait for timer or reboot to recovery mode.{Colors.RESET}

    {Colors.DIM}[q]{Colors.RESET}  Quit
""")
    else:
        print(f"""
    {Colors.DIM}Examples: 25m, 1h30m, 90m, 1d{Colors.RESET}

    {Colors.CYAN}[e]{Colors.RESET}  Edit sites     {Colors.DIM}modify blocked sites list{Colors.RESET}
    {Colors.DIM}[q]{Colors.RESET}  Quit
""")


def get_duration_minutes(duration_str: str) -> float:
    """Parse time string into minutes. Supports combined formats."""
    units = {
        's': 1/60,
        'm': 1,
        'h': 60,
        'd': 1440
    }
    components = re.findall(r'(\d+(?:\.\d+)?)\s*([smhd])?', duration_str.lower())
    if not components:
        return 0.0

    total_minutes = 0.0
    for number, unit in components:
        total_minutes += float(number) * units.get(unit, 1)
    return total_minutes


def confirm_block(duration_str: str) -> bool:
    """Show confirmation before blocking."""
    clear_screen()
    print_header()

    minutes = get_duration_minutes(duration_str)
    if minutes <= 0:
        print(f"\n    {Colors.RED}Invalid duration format.{Colors.RESET}")
        input(f"\n    {Colors.DIM}Press Enter to continue...{Colors.RESET}")
        return False

    end_time = datetime.now() + timedelta(minutes=minutes)
    end_str = end_time.strftime('%H:%M')

    # Format display string for the duration
    display = duration_str
    if minutes >= 60:
        h = int(minutes // 60)
        m = int(minutes % 60)
        display = f"{h}h {m}m" if m else f"{h}h"
    elif minutes >= 1:
        display = f"{int(minutes)}m"
    else:
        display = f"{int(minutes*60)}s"

    print(f"""
    {Colors.BOLD}Ready to block distractions{Colors.RESET}

    {Colors.CYAN}Duration:{Colors.RESET}  {display} ({duration_str})
    {Colors.CYAN}Until:{Colors.RESET}     {end_str}

    {Colors.RED}{Colors.BOLD}WARNING:{Colors.RESET} Once started, you {Colors.RED}CANNOT{Colors.RESET} undo this
    until the timer expires. The only escape is
    rebooting into recovery mode.

""")

    try:
        confirm = input(f"    {Colors.BOLD}Start focus session? [y/N]: {Colors.RESET}").strip().lower()
        return confirm == 'y'
    except KeyboardInterrupt:
        return False


def start_block(duration: str) -> bool:
    """Start the blocker. Returns True on success."""
    script_dir = Path(__file__).parent
    blocker_path = script_dir / 'blocker.py'

    print(f"\n    {Colors.GREEN}Starting focus mode...{Colors.RESET}\n")

    result = subprocess.run(
        ['python3', str(blocker_path), '-t', duration],
        cwd=script_dir
    )

    return result.returncode == 0


def edit_sites():
    """Open distractions.txt in editor."""
    script_dir = Path(__file__).parent
    distractions_path = script_dir / 'distractions.txt'

    editor = os.environ.get('EDITOR', 'nano')
    subprocess.run([editor, str(distractions_path)])


def main():
    # Check for root
    if os.geteuid() != 0:
        print(f"\n{Colors.RED}Please run with sudo:{Colors.RESET}")
        print(f"  sudo python3 {sys.argv[0]}\n")
        sys.exit(1)

    while True:
        clear_screen()
        print_header()

        # Get current status and show it
        status = get_block_status()
        print_status_banner(status)

        # Show appropriate menu
        print_menu(block_active=status['is_active'])

        try:
            choice = input(f"    {Colors.BOLD}> {Colors.RESET}").strip().lower()
        except KeyboardInterrupt:
            print("\n")
            break
        except EOFError:
            break

        if choice == 'q' or choice == '':
            break

        if status['is_active']:
            # Block is active - only quit is valid
            print(f"\n    {Colors.DIM}Block is active. Only [q] to quit.{Colors.RESET}")
            input(f"\n    {Colors.DIM}Press Enter to continue...{Colors.RESET}")
            continue

        if choice == 'e':
            edit_sites()
            continue

        # Treat everything else as a duration
        if confirm_block(choice):
            start_block(choice)

    clear_screen()
    print(f"\n    {Colors.CYAN}Stay focused!{Colors.RESET}\n")


if __name__ == "__main__":
    main()
