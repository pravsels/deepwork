#!/usr/bin/env python3
"""
Standalone Block Page Server
============================

Runs as a persistent service to show the block page.
Started/stopped by blocker.py via systemd.

Serves on both:
- Port 80 (HTTP) - block page shows directly
- Port 443 (HTTPS) - browser shows cert warning, then block page

For HTTPS, we generate a self-signed certificate. Browsers will warn
about the invalid cert, but users can click through to see the block page.
This is actually useful - it's another layer of friction!
"""

import http.server
import socketserver
import ssl
import socket
import signal
import sys
import os
import threading
import subprocess
from pathlib import Path

HTTP_PORT = 80
HTTPS_PORT = 443

SCRIPT_DIR = Path(__file__).parent
CERT_DIR = SCRIPT_DIR / '.certs'
CERT_FILE = CERT_DIR / 'block.crt'
KEY_FILE = CERT_DIR / 'block.key'


def load_html():
    """Load block page HTML."""
    html_path = SCRIPT_DIR / 'block_page.html'

    if html_path.exists():
        return html_path.read_text()

    return """<!DOCTYPE html>
<html>
<head><title>Blocked</title>
<style>body{background:#1a1a2e;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.c{text-align:center}h1{color:#e53e3e;font-size:3rem}</style>
</head>
<body><div class="c"><h1>Focus Mode Active</h1><p>Get back to work.</p></div></body>
</html>"""


def generate_self_signed_cert():
    """Generate a self-signed SSL certificate for HTTPS blocking."""
    if CERT_FILE.exists() and KEY_FILE.exists():
        return True

    CERT_DIR.mkdir(exist_ok=True)

    print("Generating self-signed SSL certificate...")

    # Generate using openssl
    try:
        # Generate private key and certificate in one command
        subprocess.run([
            'openssl', 'req', '-x509',
            '-newkey', 'rsa:2048',
            '-keyout', str(KEY_FILE),
            '-out', str(CERT_FILE),
            '-days', '3650',  # 10 years
            '-nodes',  # No passphrase
            '-subj', '/CN=DeepWork Block/O=Focus Mode/C=US',
            '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost'
        ], check=True, capture_output=True)

        # Secure the key file
        os.chmod(KEY_FILE, 0o600)
        print(f"Certificate generated: {CERT_FILE}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"Failed to generate certificate: {e}")
        return False
    except FileNotFoundError:
        print("openssl not found. HTTPS blocking will be unavailable.")
        return False


HTML_CONTENT = load_html()


class BlockHandler(http.server.BaseHTTPRequestHandler):
    """Handler that serves the block page for all requests."""

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode())

    def do_POST(self):
        self.do_GET()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Silent


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class ThreadedTCPServer(socketserver.ThreadingMixIn, ReusableTCPServer):
    """Handle each request in a separate thread."""
    daemon_threads = True


def run_http_server():
    """Run HTTP server on port 80."""
    try:
        server = ThreadedTCPServer(("127.0.0.1", HTTP_PORT), BlockHandler)
        print(f"HTTP server running on http://127.0.0.1:{HTTP_PORT}")
        server.serve_forever()
    except PermissionError:
        print(f"Cannot bind to port {HTTP_PORT} (permission denied)")
    except OSError as e:
        print(f"HTTP server error: {e}")


def run_https_server():
    """Run HTTPS server on port 443."""
    if not CERT_FILE.exists() or not KEY_FILE.exists():
        if not generate_self_signed_cert():
            print("Skipping HTTPS server (no certificate)")
            return

    try:
        server = ThreadedTCPServer(("127.0.0.1", HTTPS_PORT), BlockHandler)

        # Wrap socket with SSL
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(CERT_FILE), str(KEY_FILE))

        server.socket = context.wrap_socket(
            server.socket,
            server_side=True
        )

        print(f"HTTPS server running on https://127.0.0.1:{HTTPS_PORT}")
        server.serve_forever()

    except PermissionError:
        print(f"Cannot bind to port {HTTPS_PORT} (permission denied)")
    except ssl.SSLError as e:
        print(f"SSL error: {e}")
    except OSError as e:
        print(f"HTTPS server error: {e}")


def signal_handler(sig, frame):
    print("\nShutting down block servers...")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("Starting DeepWork block page servers...")

    # Generate cert if needed
    generate_self_signed_cert()

    # Start HTTP server in a thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Start HTTPS server in a thread
    https_thread = threading.Thread(target=run_https_server, daemon=True)
    https_thread.start()

    # Keep main thread alive
    try:
        while True:
            http_thread.join(timeout=1)
            https_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
