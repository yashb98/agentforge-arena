#!/usr/bin/env python3
"""Start golden URL shortener (ephemeral port by default), run hidden pytest, stop server.

Sets AGENTFORGE_HIDDEN_TEST_BASE_URL for the pytest subprocess. Exits with pytest's code.
"""

from __future__ import annotations

import argparse
import http.client
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _wait_health(host: str, port: int, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            conn = http.client.HTTPConnection(host, port, timeout=2.0)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            if resp.status == 200:
                conn.close()
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise SystemExit(f"Server did not become healthy at http://{host}:{port}/health")


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="0 = ephemeral free port (default); avoids clashes with local :8000",
    )
    args = parser.parse_args()
    port = args.port if args.port > 0 else _free_port(args.host)
    root = _repo_root()
    golden = root / "challenges" / "fixtures" / "url-shortener-saas" / "golden"
    hidden = root / "challenges" / "library" / "url-shortener-saas" / "hidden_tests"
    if not golden.is_dir():
        print(f"Missing golden fixture: {golden}", file=sys.stderr)
        return 2
    if not hidden.is_dir():
        print(f"Missing hidden tests: {hidden}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(golden))

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            args.host,
            "--port",
            str(port),
        ],
        cwd=str(golden),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_health(args.host, port)
        base_url = f"http://{args.host}:{port}"
        pytest_env = os.environ.copy()
        pytest_env["AGENTFORGE_HIDDEN_TEST_BASE_URL"] = base_url
        pytest_cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(hidden),
            f"--rootdir={golden}",
            "-q",
            "--tb=short",
            "--override-ini=addopts=",
        ]
        result = subprocess.run(
            pytest_cmd,
            cwd=str(root),
            env=pytest_env,
            check=False,
        )
        return int(result.returncode)
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        if proc.returncode not in (0, -signal.SIGTERM, -15) and stderr:
            print(stderr[:2000], file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
