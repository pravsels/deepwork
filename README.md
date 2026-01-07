# Deep Work Blocker

Distraction blocker with 4-layer protection: `/etc/hosts` + `chattr +i` + `iptables` + `systemd-run`. 

Cannot be bypassed without rebooting into recovery mode.

## Usage

```bash
./focus
```

Pick a duration (25m to 8h) and get to work. Edit `distractions.txt` to customize blocked sites.

## Installation

```bash
chmod +x focus focus.py
./focus
```

Requires: Linux, Python 3.6+, sudo

## Technical Details

See [explainer.md](explainer.md) for internals and hardening options.

## License

MIT
