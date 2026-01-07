# Deep Work Blocker

A rock-solid distraction blocker that **cannot be bypassed** without rebooting into recovery mode.

## Quick Start

```bash
./focus
```

That's it. Pick a duration from the menu and get to work.

## How It Works

Four layers of protection make this nearly impossible to bypass:

| Layer | Mechanism | What it blocks |
|-------|-----------|----------------|
| 1 | `/etc/hosts` | DNS resolution (redirects to localhost) |
| 2 | `chattr +i` | Editing hosts file (even as root) |
| 3 | `iptables` | Direct IP connections at kernel level |
| 4 | `systemd-run` | Schedules unlock - no manual escape |

Plus a **block page** that shows when you try to visit blocked sites.

The only escape is rebooting into recovery mode - enough friction to stop impulse browsing.

## Installation

```bash
# Clone the repo
git clone <repo-url>
cd deepwork

# Make executable
chmod +x focus focus.py

# Run it
./focus
```

No dependencies required beyond Python 3.

## Usage

### Interactive Mode (Recommended)

```bash
./focus
```

Shows a menu:
```
[1]  Pomodoro       25 minutes
[2]  Short focus    45 minutes
[3]  Deep work      90 minutes
[4]  Long session   2 hours
[5]  Half day       4 hours
[6]  Full day       8 hours
[7]  Custom         enter your own duration

[s]  Status         check if block is active
[e]  Edit sites     modify blocked sites list
[u]  Unlock         remove block (if stuck)
```

### Command Line Mode

```bash
sudo python3 blocker.py -t 25m    # 25-minute Pomodoro
sudo python3 blocker.py -t 2h     # 2-hour deep work
sudo python3 blocker.py -t 8h     # Full workday
sudo python3 blocker.py --unlock  # Remove block (scheduled automatically)
```

## Files

| File | Description |
|------|-------------|
| `focus` | Simple launcher script |
| `focus.py` | Interactive menu interface |
| `blocker.py` | Core blocking logic |
| `distractions.txt` | List of sites to block |
| `block_page.html` | Custom block page (shown when visiting blocked sites) |
| `explainer.md` | Deep technical documentation |

## Customization

### Edit Blocked Sites

```bash
nano distractions.txt
```

One domain per line. Comments start with `#`.

### Customize Block Page

Edit `block_page.html` to change what you see when visiting blocked sites.

## Technical Details

See [explainer.md](explainer.md) for a deep dive into:
- How each blocking layer works
- Linux internals (chattr, iptables, systemd)
- Known bypass methods
- Further hardening options

## Requirements

- Linux (uses `chattr` and `iptables`)
- Python 3.6+
- Root access (sudo)

## Philosophy

> "The ability to perform deep work is becoming increasingly rare at exactly the same time it is becoming increasingly valuable in our economy."
> — Cal Newport

Most blockers fail because they're too easy to bypass. This one is designed so that **bypassing takes longer than the distraction urge lasts**. By the time you could reboot into recovery mode, you've already moved on.

## License

MIT
