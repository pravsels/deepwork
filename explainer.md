# Deep Dive: How the Rock-Solid Website Blocker Works

This document explains the technical mechanisms behind each layer of protection in the blocker. Understanding these concepts is valuable for anyone interested in Linux system administration, networking, and security.

---

## Table of Contents

1. [The Problem: Why Simple Blockers Fail](#the-problem-why-simple-blockers-fail)
2. [Layer 1: Hosts File Blocking](#layer-1-hosts-file-blocking)
3. [Layer 2: The Immutable Flag (chattr)](#layer-2-the-immutable-flag-chattr)
4. [Layer 3: iptables Firewall Rules](#layer-3-iptables-firewall-rules)
5. [Layer 4: Scheduled Unlock (systemd-run)](#layer-4-scheduled-unlock-systemd-run)
6. [Layer 5: Block Page Server](#layer-5-block-page-server)
7. [The Combined Effect](#the-combined-effect)
8. [Known Bypass Methods](#known-bypass-methods)
9. [Further Hardening Ideas](#further-hardening-ideas)

---

## The Problem: Why Simple Blockers Fail

Most website blockers fail because they're too easy to bypass. When you're in the grip of a distraction urge, your brain becomes remarkably creative at finding workarounds:

| Blocker Type | Bypass Method | Time to Bypass |
|--------------|---------------|----------------|
| Browser extension | Disable extension, use incognito, use another browser | 5 seconds |
| Simple hosts file edit | Edit /etc/hosts back | 30 seconds |
| App-based blocker | Kill the app, uninstall it | 10 seconds |

The key insight: **the bypass friction must exceed the impulse duration**. Most distraction urges fade within 5-10 minutes. If bypassing takes longer than that (or requires a reboot), you'll likely give up and get back to work.

---

## Layer 1: Hosts File Blocking

### What is the hosts file?

The hosts file is your computer's first DNS lookup. Before your system queries a DNS server to resolve a domain name to an IP address, it checks the local hosts file.

**Location:**
- Linux/macOS: `/etc/hosts`
- Windows: `C:\Windows\System32\drivers\etc\hosts`

### How it works

```
# Normal DNS resolution flow:
Browser → "reddit.com" → DNS Server → "151.101.1.140" → Connection

# With hosts file blocking:
Browser → "reddit.com" → Hosts file says "127.0.0.1" → Connection to localhost → Fails
```

When we add this line to `/etc/hosts`:
```
127.0.0.1 reddit.com
```

The system resolves `reddit.com` to `127.0.0.1` (localhost) instead of Reddit's actual IP. Since there's no web server on localhost port 80/443, the connection fails.

### The code

```python
def _add_hosts_entries(self, domains: Set[str]) -> None:
    # Read current hosts file
    content = self.hosts_path.read_text()

    # Add our blocking entries
    for domain in domains:
        content += f"127.0.0.1 {domain}\n"

    # Write back
    self.hosts_path.write_text(content)
```

### Why we expand domains

We add both `reddit.com` and `www.reddit.com` because they're technically different hostnames:

```python
def _expand_domains(self, domains: Set[str]) -> Set[str]:
    expanded = set()
    for domain in domains:
        expanded.add(domain)
        if not domain.startswith('www.'):
            expanded.add('www.' + domain)
    return expanded
```

### Limitations

- Only blocks exact domain matches (subdomains like `old.reddit.com` need separate entries)
- Can be bypassed by editing the hosts file back
- Can be bypassed by using the IP address directly (if you know it)

**Bypass difficulty: Easy** - Just edit the file back.

---

## Layer 2: The Immutable Flag (chattr)

### What is chattr?

`chattr` (change attribute) is a Linux command that sets special file attributes. The most powerful is the **immutable flag** (`+i`), which prevents ANY modification to the file - even by root.

### How it works

```bash
# Set immutable flag
sudo chattr +i /etc/hosts

# Now even root cannot modify:
sudo echo "test" >> /etc/hosts
# bash: /etc/hosts: Operation not permitted

sudo rm /etc/hosts
# rm: cannot remove '/etc/hosts': Operation not permitted

# To modify, you must first remove the flag:
sudo chattr -i /etc/hosts
```

### The magic: Self-protection

The key insight is **we can set the immutable flag and then delete our ability to remove it**:

```python
def _set_immutable_flag(self) -> None:
    subprocess.run(["chattr", "+i", str(self.hosts_path)])
```

Once set, the only ways to remove it are:
1. Run `chattr -i /etc/hosts` (requires knowing about chattr)
2. Boot into recovery mode and remove it
3. Boot from a live USB

### Under the hood: Extended attributes

The immutable flag is stored in the file's extended attributes (xattr) in the filesystem. You can view it with:

```bash
lsattr /etc/hosts
# ----i------------ /etc/hosts
#     ^ immutable flag
```

The `i` flag is enforced by the kernel itself, at the VFS (Virtual File System) layer. This means:
- No userspace program can bypass it
- Even root is bound by it
- Only `chattr -i` or a kernel bypass can remove it

### Technical deep dive: How chattr works

```
┌─────────────────────────────────────────────────────────────┐
│                        User Space                            │
├─────────────────────────────────────────────────────────────┤
│  chattr +i /etc/hosts                                       │
│       │                                                      │
│       ▼                                                      │
│  ioctl(fd, FS_IOC_SETFLAGS, &flags)                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       Kernel Space                           │
├─────────────────────────────────────────────────────────────┤
│  VFS Layer                                                   │
│       │                                                      │
│       ▼                                                      │
│  ext4_ioctl() → sets EXT4_IMMUTABLE_FL in inode             │
│                                                              │
│  On any write attempt:                                       │
│  ext4_file_write_iter() checks flags → EPERM if immutable   │
└─────────────────────────────────────────────────────────────┘
```

The flag is stored in the inode's `i_flags` field in the ext4 filesystem.

**Bypass difficulty: Medium** - Requires knowing about chattr, or rebooting.

---

## Layer 3: iptables Firewall Rules

### What is iptables?

`iptables` is the Linux kernel's built-in firewall. It operates at the network layer, filtering packets based on rules you define. It's incredibly powerful and operates at a level below any application.

### Why we need it

The hosts file only blocks DNS resolution. But what if someone:
- Knows Reddit's IP address and connects directly?
- Uses a different DNS server?
- Has the IP cached?

iptables blocks the actual network packets, regardless of how the destination was determined.

### How it works

```bash
# Block all outgoing traffic to a specific IP
sudo iptables -A OUTPUT -d 151.101.1.140 -j REJECT

# Now ANY connection attempt to that IP fails:
curl 151.101.1.140
# curl: (7) Failed to connect: Connection refused
```

### The code

```python
def _add_iptables_rules(self, domains: Set[str]) -> None:
    for domain in domains:
        # First, resolve domain to IPs
        ips = self._resolve_domain_ips(domain)

        for ip in ips:
            subprocess.run([
                "iptables", "-A", "OUTPUT",  # Append to OUTPUT chain
                "-d", ip,                     # Destination IP
                "-j", "REJECT",               # Action: reject connection
                "-m", "comment",              # Add a comment for identification
                "--comment", "deepwork-block"
            ])
```

### iptables chains explained

```
                    ┌─────────────┐
                    │   Network   │
                    └──────┬──────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                      PREROUTING                               │
│            (before routing decision)                          │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
┌─────────────────────┐    ┌─────────────────────┐
│       INPUT         │    │      FORWARD        │
│  (to this machine)  │    │  (through machine)  │
└─────────────────────┘    └─────────────────────┘
              │
              ▼
┌─────────────────────┐
│   Local Processes   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      OUTPUT         │  ◄── We block here!
│ (from this machine) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    POSTROUTING      │
└──────────┬──────────┘
           │
           ▼
    ┌─────────────┐
    │   Network   │
    └─────────────┘
```

We use the **OUTPUT** chain because we want to block connections **originating from this machine**.

### REJECT vs DROP

- `REJECT`: Sends back an error packet (connection refused). Fast failure.
- `DROP`: Silently discards packets. Connection hangs until timeout.

We use `REJECT` for faster feedback (the browser shows an error immediately instead of hanging).

### Viewing current rules

```bash
# List all OUTPUT rules with line numbers
sudo iptables -L OUTPUT -n --line-numbers -v

# Example output:
Chain OUTPUT (policy ACCEPT 0 packets, 0 bytes)
num   pkts bytes target  prot opt in  out  source     destination
1        0     0 REJECT  all  --  *   *    0.0.0.0/0  151.101.1.140  /* deepwork-block */
2        0     0 REJECT  all  --  *   *    0.0.0.0/0  151.101.65.140 /* deepwork-block */
```

### Limitations

- IPs can change (especially for large sites with CDNs)
- Sites with many IPs might not all be blocked
- Rules are lost on reboot (need iptables-persistent to save)

**Bypass difficulty: Medium** - Need to know iptables to remove rules, or reboot.

---

## Layer 4: Scheduled Unlock (systemd-run)

### The problem with manual unlock

If there's an `--unlock` flag, what stops you from just running it when you're tempted?

```bash
# Too easy!
sudo python3 blocker.py --unlock
```

### The solution: Remove the escape hatch

We use `systemd-run` to schedule the unlock command to run **in the future**, as a one-shot systemd timer:

```python
def _schedule_unlock(self, duration_minutes: float) -> None:
    script_path = Path(__file__).resolve()
    unlock_cmd = f"python3 {script_path} --unlock"

    subprocess.run([
        "systemd-run",
        "--on-active", f"{int(duration_minutes)}m",  # Run after X minutes
        "--unit", "deepwork-unblock",                 # Name the unit
        "/bin/bash", "-c", unlock_cmd
    ])
```

### How systemd-run works

```bash
# Schedule a command to run in 25 minutes
systemd-run --on-active=25m /bin/echo "Time's up!"

# This creates a transient timer unit:
# - deepwork-unblock.timer (triggers after 25m)
# - deepwork-unblock.service (runs the command)
```

### Can you cancel it?

Yes, technically:
```bash
sudo systemctl stop deepwork-unblock.timer
```

But you'd need to:
1. Know the unit name
2. Know how to use systemctl
3. Remember to also undo chattr and iptables

**The friction compounds.**

### Fallback: The 'at' command

If systemd-run isn't available, we fall back to the classic `at` scheduler:

```python
# Schedule command at specific time
process = subprocess.Popen(
    ["at", "14:30"],
    stdin=subprocess.PIPE
)
process.communicate(input=b"python3 /path/to/blocker.py --unlock")
```

**Bypass difficulty: Medium** - Requires knowing about systemd timers or at jobs.

---

## Layer 5: Block Page Server

### Why show a block page?

Without it, blocked sites just show a connection error:
```
This site can't be reached
127.0.0.1 refused to connect.
```

That's functional but ugly. A nice block page:
1. Confirms the block is intentional (not a network issue)
2. Provides motivation to stay focused
3. Feels more "professional" like Cold Turkey

### How it works

We run a tiny HTTP server on localhost port 80:

```python
class BlockPageServer:
    def __init__(self, port: int = 80):
        self.server = socketserver.TCPServer(
            ("127.0.0.1", self.port),
            self._create_handler()
        )

    def start(self):
        # Run in background thread
        thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True
        )
        thread.start()
```

### The request flow

```
┌────────────┐     ┌───────────────┐     ┌─────────────────┐
│   Browser  │ ──► │  /etc/hosts   │ ──► │ 127.0.0.1:80    │
│ reddit.com │     │ reddit.com →  │     │ Block Page      │
│            │     │ 127.0.0.1     │     │ Server          │
└────────────┘     └───────────────┘     └─────────────────┘
                                                  │
                                                  ▼
                                         ┌─────────────────┐
                                         │  "Focus Mode    │
                                         │   Active" page  │
                                         └─────────────────┘
```

### HTTPS caveat

This only works for HTTP (port 80). HTTPS sites will show a certificate error because:
1. Browser connects to `127.0.0.1` thinking it's `reddit.com`
2. Our server doesn't have a valid SSL cert for `reddit.com`
3. Browser shows security warning

This is actually fine - the site is still blocked, just with a certificate error instead of a pretty page.

---

## The Combined Effect

Here's what happens when all layers are active:

```
User tries to visit reddit.com
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Hosts File                                          │
│ reddit.com → 127.0.0.1                                       │
│ Status: BLOCKED (redirected to localhost)                    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Block Page Server                                   │
│ Shows "Focus Mode Active" page                               │
│ Status: User sees block message                              │
└─────────────────────────────────────────────────────────────┘

User tries to bypass by using IP directly (151.101.1.140)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: iptables                                            │
│ OUTPUT chain rejects packets to 151.101.1.140                │
│ Status: BLOCKED (connection refused)                         │
└─────────────────────────────────────────────────────────────┘

User tries to edit /etc/hosts
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Immutable Flag                                      │
│ chattr +i prevents any modification                          │
│ Status: BLOCKED (operation not permitted)                    │
└─────────────────────────────────────────────────────────────┘

User tries to run --unlock
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Scheduled Unlock                                    │
│ Unlock only runs when timer fires                            │
│ Status: Must wait or know systemctl to cancel                │
└─────────────────────────────────────────────────────────────┘
```

---

## Known Bypass Methods

Being honest about limitations helps you understand the security model:

### Easy bypasses (that we accept)

| Method | Difficulty | Notes |
|--------|------------|-------|
| Use phone | Trivial | Out of scope - block on phone too |
| Use different computer | Trivial | Out of scope |
| Reboot to recovery mode | Medium | Takes 5+ minutes, breaks flow |
| Boot from live USB | Hard | Takes 10+ minutes |

### Technical bypasses (require knowledge)

| Method | Commands Needed | Likelihood |
|--------|-----------------|------------|
| Remove immutable + edit hosts | `chattr -i`, edit file, `chattr +i` | Low if you don't know chattr |
| Flush iptables | `iptables -F OUTPUT` | Low if you don't know iptables |
| Cancel systemd timer | `systemctl stop deepwork-unblock.timer` | Low |
| Use VPN/proxy | Start VPN | Medium - but most VPNs are blocked too |
| Use Tor | Start Tor browser | Medium |

### The philosophy

We're not trying to be unbreakable. We're trying to add enough friction that:

```
Friction to bypass > Duration of impulse
```

Most distraction urges fade in 5-10 minutes. If bypassing takes:
- 30 seconds: You'll bypass
- 5 minutes: Maybe you'll bypass
- 10+ minutes (reboot): Probably not worth it

---

## Further Hardening Ideas

Want to go even further? Here are advanced options:

### 1. Block chattr itself

```bash
# Rename chattr so you can't easily use it
sudo mv /usr/bin/chattr /usr/bin/.chattr-hidden-$(date +%s)
```

### 2. DNS-level blocking

Edit `/etc/resolv.conf` to use a filtered DNS that blocks distractions:
```
nameserver 1.1.1.3  # Cloudflare family-friendly DNS
```

Then make that immutable too:
```bash
sudo chattr +i /etc/resolv.conf
```

### 3. Block at router level

If you control your router, add firewall rules there. This blocks all devices.

### 4. Nuclear option: Block ALL non-essential traffic

```bash
# Default deny, allow only specific IPs
iptables -P OUTPUT DROP
iptables -A OUTPUT -d YOUR_WORK_SERVER -j ACCEPT
iptables -A OUTPUT -d 8.8.8.8 -j ACCEPT  # DNS
# ... etc
```

### 5. Use a separate user account

Create a "focus" user with no sudo access. Switch to it during work.

---

## Conclusion

This blocker works by **layering defenses**:

1. **Hosts file** - Redirects domains to localhost
2. **Immutable flag** - Prevents editing the hosts file
3. **iptables** - Blocks at the network level
4. **Scheduled unlock** - Removes the manual escape hatch
5. **Block page** - Provides visual feedback

Each layer can be bypassed individually, but together they create enough friction to defeat casual impulse browsing.

The goal isn't perfect security - it's **behavioral change through friction**. When the path of least resistance is getting back to work, that's what you'll do.

---

## References

- [Linux man page: chattr](https://man7.org/linux/man-pages/man1/chattr.1.html)
- [iptables tutorial](https://www.netfilter.org/documentation/HOWTO/packet-filtering-HOWTO.html)
- [systemd.timer documentation](https://www.freedesktop.org/software/systemd/man/systemd.timer.html)
- [Cal Newport: Deep Work](https://www.calnewport.com/books/deep-work/)
- [Cold Turkey Blocker](https://getcoldturkey.com/) - The inspiration for this project

---

*"The ability to perform deep work is becoming increasingly rare at exactly the same time it is becoming increasingly valuable in our economy."* — Cal Newport
