# Deep Dive: How the DeepWork Blocker Works

This project uses a layered defense strategy to create behavioral friction. Unlike browser extensions that are easy to disable, this tool targets the system level to ensure that by the time you've bypassed it, your distraction urge has likely passed.

---

## The Philosophy: Friction > Impulse
Most distraction urges fade within 5-10 minutes. By making the bypass process take longer than that (or require a reboot), the path of least resistance becomes getting back to work.

---

## Layer 1: DNS Redirection (Dual-Stack)
The blocker modifies `/etc/hosts` to redirect distracting domains to `localhost`. 

### Why IPv6 matters
Modern sites often resolve to IPv6 addresses. If you only block `127.0.0.1` (IPv4), your browser may bypass the block via `::1` (IPv6). We block both:

```text
127.0.0.1 reddit.com
::1       reddit.com
```

---

## Layer 2: The Immutable Flag (`chattr`)
Even if you have `sudo` access, the blocker prevents you from reversing the changes immediately using the Linux **immutable flag**.

```bash
sudo chattr +i /etc/hosts
```

Once this flag is set:
- No user (not even `root`) can modify or delete the file.
- The only way to edit it is to run `chattr -i`, which is a command most users don't remember during a distraction impulse.

---

## Layer 3: Scheduled Unlock (`systemd-run`)
There is no "Stop" button. When you start a session, the script uses `systemd-run` to schedule a one-shot task in the future.

```python
subprocess.run([
    "systemd-run",
    "--on-active", f"{duration}m",
    "--unit", "deepwork-unblock",
    "python3 blocker.py --unlock"
])
```

The system itself holds the key. You have to wait for the timer to fire, or perform a disruptive system recovery to get around it.

---

## Layer 4: Block Page Server
Instead of a "Connection Refused" error, we serve a custom HTML page on ports 80 (HTTP) and 443 (HTTPS).

- **Port 80**: Shows the block page instantly.
- **Port 443**: Shows a certificate warning (because we can't spoof a real site's SSL). This warning acts as an additional layer of friction.

---

## Why we don't use `iptables` (Firewall)
Earlier versions used `iptables` to block the IP addresses of sites. We removed this because:
1. **Shared IPs**: Large sites (Reddit, Substack) share IP addresses with "good" sites (Gmail, Fast.com) via CDNs like Cloudflare. Blocking the IP would break half the internet.
2. **Complexity**: Firewall rules are more likely to cause system-wide instability.

By sticking to **Domain-level blocking** via the hosts file, we ensure that only the distractions are blocked, while your work tools remain fast and functional.

---

## Summary of Defense
| Layer | Mechanism | Bypass Difficulty |
|-------|-----------|-------------------|
| **Hosts File** | DNS Redirect | Easy (if mutable) |
| **chattr** | Filesystem Lock | Medium (requires knowledge) |
| **systemd** | Managed Timer | Medium (requires systemctl) |
| **Recovery** | Reboot to Recovery | High (breaks workflow) |
