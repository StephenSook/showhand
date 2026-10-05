#!/usr/bin/env python3
"""Own a terminal for GEAR-SONIC and arm stock ZMQ control.

The deploy binary sets the terminal to non-canonical mode and reads one key at a
time. ``]`` requests control. One newline toggles ZMQ streaming. A second newline
would toggle it back off. This process keeps the pty master open until SONIC
exits; closing it early delivers SIGHUP.
"""

from __future__ import annotations

import argparse
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path


class PtyDriver:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.status_dir = Path(args.status_dir)
        self.status_dir.mkdir(parents=True, exist_ok=True)
        self.proc: subprocess.Popen[bytes] | None = None
        self.master: int | None = None
        self.pending = ""
        self.state = "init"
        self.init_deadline = time.monotonic() + args.init_timeout_s
        self.port_deadline = 0.0
        self.key_deadline = 0.0
        self.failed = False

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self._on_stop)
        signal.signal(signal.SIGINT, self._on_stop)
        master, slave = os.openpty()
        self.master = master
        self.proc = subprocess.Popen(
            [self.args.wrapper, self.args.log_dir, self.args.run_id],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave)
        (self.status_dir / "sonic_pid").write_text(f"{self.proc.pid}\n", encoding="utf-8")
        self._note(f"spawned sonic_pid={self.proc.pid}")
        try:
            self._loop()
        finally:
            if self.master is not None:
                os.close(self.master)
                self.master = None
        assert self.proc is not None
        return self.proc.wait()

    def _loop(self) -> None:
        assert self.proc is not None
        assert self.master is not None
        while self.proc.poll() is None:
            now = time.monotonic()
            self._advance(now)
            if self.failed and self.state == "failed":
                self._drain_once()
                continue
            timeout = 0.02
            try:
                readable, _, _ = select.select([self.master], [], [], timeout)
            except InterruptedError:
                continue
            if readable:
                self._read_master()
        self._read_master()

    def _advance(self, now: float) -> None:
        if self.state == "init" and now > self.init_deadline:
            self._fail(f"Init Done was not seen within {self.args.init_timeout_s:.0f}s")
        elif self.state == "wait_port" and now > self.port_deadline:
            self._fail(f"ZMQ publisher port {self.args.port} did not open")
        elif self.state == "wait_port" and self._port_open():
            self._note("publisher_port_open")
            (self.status_dir / "port_open").write_text(f"{time.time_ns()}\n", encoding="utf-8")
            self._write_key(b"]")
            self.state = "wait_control"
            self.key_deadline = now + self.args.key_timeout_s
        elif self.state in {"wait_control", "wait_zmq"} and now > self.key_deadline:
            self._fail(f"key sequence timed out in state {self.state}")

    def _read_master(self) -> None:
        assert self.master is not None
        try:
            chunk = os.read(self.master, 65536)
        except OSError:
            return
        if not chunk:
            return
        self.pending += chunk.decode("utf-8", errors="replace")
        while "\n" in self.pending:
            line, self.pending = self.pending.split("\n", 1)
            self._handle_line(line.rstrip("\r"))

    def _drain_once(self) -> None:
        assert self.master is not None
        try:
            readable, _, _ = select.select([self.master], [], [], 0.2)
        except InterruptedError:
            return
        if readable:
            self._read_master()

    def _handle_line(self, line: str) -> None:
        if self.state == "init" and line == "Init Done":
            (self.status_dir / "init_done").write_text(f"{time.time_ns()}\n", encoding="utf-8")
            self._note("init_done")
            self.state = "wait_port"
            self.port_deadline = time.monotonic() + self.args.arm_timeout_s
            return
        if self.state == "wait_control" and "transitioning to CONTROL state" in line:
            (self.status_dir / "control").write_text(f"{time.time_ns()}\n", encoding="utf-8")
            self._note("control")
            self._write_key(b"\n")
            self.state = "wait_zmq"
            self.key_deadline = time.monotonic() + self.args.key_timeout_s
            return
        if self.state == "wait_zmq" and "ZMQ STREAMING MODE: ENABLED" in line:
            (self.status_dir / "ready").write_text(f"{time.time_ns()}\n", encoding="utf-8")
            self._note("zmq_enabled")
            self.state = "drain"
            return
        if "ZMQ STREAMING MODE: DISABLED" in line or "ZMQ STREAMING MODE: FORCE DISABLED" in line:
            self._fail(f"ZMQ streaming left the enabled state: {line}")

    def _write_key(self, payload: bytes) -> None:
        assert self.master is not None
        os.write(self.master, payload)

    def _port_open(self) -> bool:
        # A TCP connect would attach a non-ZMQ client to the publisher. `ss` only looks.
        result = subprocess.run(
            ["ss", "-ltn", f"sport = :{self.args.port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        needle = f":{self.args.port}"
        return any(needle in line and "LISTEN" in line for line in result.stdout.splitlines())

    def _fail(self, reason: str) -> None:
        if self.failed:
            return
        self.failed = True
        self.state = "failed"
        (self.status_dir / "failed").write_text(reason + "\n", encoding="utf-8")
        self._note(f"failed {reason}")
        self._kill_replay()

    def _kill_replay(self) -> None:
        pid_path = Path(self.args.replay_pid_file)
        if not pid_path.is_file():
            return
        text = pid_path.read_text(encoding="utf-8").strip()
        if not text:
            return
        try:
            os.killpg(int(text), signal.SIGTERM)
        except (OSError, ValueError) as error:
            self._note(f"replay_kill_failed {error}")

    def _on_stop(self, _signum: int, _frame: object) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except OSError as error:
                self._note(f"sonic_kill_failed {error}")

    def _note(self, text: str) -> None:
        print(f"SHOWHAND_PTY {text}", file=sys.stderr, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status-dir", required=True)
    parser.add_argument("--replay-pid-file", required=True)
    parser.add_argument("--port", type=int, default=5556)
    parser.add_argument("--init-timeout-s", type=float, default=240.0)
    parser.add_argument("--arm-timeout-s", type=float, default=180.0)
    parser.add_argument("--key-timeout-s", type=float, default=0.35)
    args = parser.parse_args()
    return PtyDriver(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
