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
        print(f"    {Colors.DIM}No active block. Select a duration to start focusing.{Colors.RESET}")
    print()


def print_menu(block_active: bool):
    """Print menu options based on whether block is active."""
    if block_active:
        print(f"""    {Colors.DIM}Block is locked. Wait for timer or reboot to recovery mode.{Colors.RESET}

    {Colors.DIM}[q]{Colors.RESET}  Quit
""")
    else:
        print(f"""
    {Colors.BOLD}Select a focus session:{Colors.RESET}

    {Colors.GREEN}[1]{Colors.RESET}  Pomodoro       {Colors.DIM}25 minutes{Colors.RESET}
    {Colors.GREEN}[2]{Colors.RESET}  Short focus    {Colors.DIM}45 minutes{Colors.RESET}
    {Colors.GREEN}[3]{Colors.RESET}  Deep work      {Colors.DIM}90 minutes{Colors.RESET}
    {Colors.GREEN}[4]{Colors.RESET}  Long session   {Colors.DIM}2 hours{Colors.RESET}
    {Colors.GREEN}[5]{Colors.RESET}  Extended       {Colors.DIM}3 hours{Colors.RESET}
    {Colors.GREEN}[6]{Colors.RESET}  Half day       {Colors.DIM}4 hours{Colors.RESET}
    {Colors.GREEN}[7]{Colors.RESET}  Full day       {Colors.DIM}8 hours{Colors.RESET}
    {Colors.YELLOW}[8]{Colors.RESET}  Custom         {Colors.DIM}enter your own duration{Colors.RESET}

    {Colors.CYAN}[e]{Colors.RESET}  Edit sites     {Colors.DIM}modify blocked sites list{Colors.RESET}

    {Colors.DIM}[q]{Colors.RESET}  Quit
""")


def get_duration_choices():
    return {
        '1': ('25m', '25 minutes'),
        '2': ('45m', '45 minutes'),
        '3': ('90m', '90 minutes'),
        '4': ('2h', '2 hours'),
        '5': ('3h', '3 hours'),
        '6': ('4h', '4 hours'),
        '7': ('8h', '8 hours'),
    }


def get_custom_duration():
    print(f"\n    {Colors.YELLOW}Enter duration:{Colors.RESET}")
    print(f"    {Colors.DIM}Examples: 30m, 2h, 1d{Colors.RESET}")
    print()

    try:
        duration = input(f"    {Colors.BOLD}Duration: {Colors.RESET}").strip()
        if not duration:
            return None

        if not re.match(r'^\d+[smhd]?$', duration.lower()):
            print(f"\n    {Colors.RED}Invalid format. Use: 30m, 2h, 1d, etc.{Colors.RESET}")
            input(f"\n    {Colors.DIM}Press Enter to continue...{Colors.RESET}")
            return None

        return duration
    except KeyboardInterrupt:
        return None


def confirm_block(duration_str: str, duration_display: str) -> bool:
    """Show confirmation before blocking."""
    clear_screen()
    print_header()

    match = re.match(r'^(\d+)([smhd])?$', duration_str.lower())
    if match:
        num, unit = match.groups()
        num = int(num)
        unit = unit or 'm'

        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        seconds = num * multipliers[unit]
        end_time = datetime.now() + timedelta(seconds=seconds)
        end_str = end_time.strftime('%H:%M')
    else:
        end_str = "unknown"

    print(f"""
    {Colors.BOLD}Ready to block distractions{Colors.RESET}

    {Colors.CYAN}Duration:{Colors.RESET}  {duration_display}
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

    durations = get_duration_choices()

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

        elif status['is_active']:
            # Block is active - only quit is valid
            print(f"\n    {Colors.DIM}Block is active. Only [q] to quit.{Colors.RESET}")
            input(f"\n    {Colors.DIM}Press Enter to continue...{Colors.RESET}")

        elif choice in durations:
            duration, display = durations[choice]
            if confirm_block(duration, display):
                start_block(duration)

        elif choice == '8':
            custom = get_custom_duration()
            if custom:
                if confirm_block(custom, custom):
                    start_block(custom)

        elif choice == 'e':
            edit_sites()

        else:
            print(f"\n    {Colors.RED}Invalid option{Colors.RESET}")
            input(f"\n    {Colors.DIM}Press Enter to continue...{Colors.RESET}")

    clear_screen()
    print(f"\n    {Colors.CYAN}Stay focused!{Colors.RESET}\n")


if __name__ == "__main__":
    main()
