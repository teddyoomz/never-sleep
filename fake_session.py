#!/usr/bin/env python3
"""
Never Sleep - Fake Remote Session Simulator for Windows
========================================================
จำลอง remote session เพื่อให้เครื่อง Windows ดูเหมือนมี user เชื่อมต่ออยู่ตลอดเวลา

Features:
  - สร้าง fake remote sessions (RDP/SSH style)
  - ป้องกัน Sleep / Hibernate (SetThreadExecutionState)
  - บล็อก Shutdown / Restart (ShutdownBlockReasonCreate + WM_QUERYENDSESSION)
  - ป้องกัน Screen Lock / Screen Saver (mouse jiggle)
  - ทำงานเป็น background หรือ foreground mode
  - ใช้แค่ Python standard library - ไม่ต้องติดตั้งอะไรเพิ่ม

Usage:
  python fake_session.py                # Run with defaults
  python fake_session.py --min 3        # At least 3 sessions
  python fake_session.py --background   # Run as background (no display)
  python fake_session.py --json         # Output JSON snapshot

Note: ต้องรัน Run as Administrator เพื่อให้บล็อก shutdown ได้เต็มที่
"""

import os
import sys
import time
import uuid
import random
import signal
import hashlib
import platform
import threading
from datetime import datetime, timedelta
from typing import List

IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes
    import ctypes.wintypes

# ─── Configuration ───────────────────────────────────────────────────────────

FAKE_USERNAMES = [
    "admin", "developer", "sysadmin", "operator", "support",
    "manager", "engineer", "analyst", "devops", "monitor",
    "service.account", "backup.agent", "deploy.bot", "ci.runner",
    "remote.user", "helpdesk", "netadmin", "dbadmin",
]

REMOTE_IPS = [
    "192.168.1.{}", "10.0.0.{}", "172.16.0.{}",
    "10.10.{}.{}", "192.168.{}.{}",
    "10.20.30.{}", "172.20.{}.{}",
]

PROTOCOLS = ["rdp-tcp", "rdp-ssl", "rdp-udp", "ica-tcp"]

SESSION_STATES = ["Active", "Connected", "Disc"]


# ─── Fake Session Model ─────────────────────────────────────────────────────

class FakeSession:
    def __init__(self, session_id, username, remote_ip, protocol,
                 state, login_time, last_activity, pid, terminal):
        self.session_id = session_id
        self.username = username
        self.remote_ip = remote_ip
        self.protocol = protocol
        self.state = state
        self.login_time = login_time
        self.last_activity = last_activity
        self.pid = pid
        self.terminal = terminal

    @property
    def duration(self):
        delta = datetime.now() - self.login_time
        days = delta.days
        hours, remainder = divmod(int(delta.total_seconds()) % 86400, 3600)
        minutes, _ = divmod(remainder, 60)
        if days > 0:
            return f"{days}d {hours:02d}:{minutes:02d}"
        return f"{hours:02d}:{minutes:02d}"

    @property
    def idle_time(self):
        delta = datetime.now() - self.last_activity
        total_seconds = int(delta.total_seconds())
        if total_seconds < 60:
            return "."
        minutes = total_seconds // 60
        if minutes < 60:
            return f"{minutes}"
        hours = minutes // 60
        minutes = minutes % 60
        return f"{hours}:{minutes:02d}"

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "username": self.username,
            "remote_ip": self.remote_ip,
            "protocol": self.protocol,
            "state": self.state,
            "login_time": self.login_time.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "pid": self.pid,
            "terminal": self.terminal,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Windows Protection Layer - ป้องกัน Sleep / Hibernate / Shutdown / Restart
# ═══════════════════════════════════════════════════════════════════════════

class WindowsProtection:
    """
    ป้องกัน Windows จาก:
    1. Sleep / Hibernate      -> SetThreadExecutionState
    2. Screen Lock / Saver    -> Mouse jiggle + SetThreadExecutionState
    3. Shutdown / Restart      -> ShutdownBlockReasonCreate + Hidden Window
    4. Forced Shutdown         -> SetProcessShutdownParameters (high priority)
    """

    # SetThreadExecutionState flags
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002
    ES_AWAYMODE_REQUIRED = 0x00000040

    # Window messages
    WM_QUERYENDSESSION = 0x0011
    WM_ENDSESSION = 0x0016
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002
    WM_POWERBROADCAST = 0x0218
    PBT_APMQUERYSUSPEND = 0x0000

    # Shutdown parameters
    SHUTDOWN_NORETRY = 0x00000001

    def __init__(self):
        self._active = False
        self._hwnd = None
        self._window_thread = None
        self._jiggle_thread = None
        self._power_thread = None
        self._stop_event = threading.Event()

    def start(self):
        """เริ่มการป้องกันทั้งหมด"""
        if not IS_WINDOWS:
            print("  [!] Not Windows - protection features limited")
            return

        self._active = True
        self._stop_event.clear()

        # 1. ป้องกัน sleep/hibernate
        self._set_execution_state()

        # 2. ตั้ง shutdown priority สูงสุด (ให้ปิดท้ายสุด)
        self._set_shutdown_priority()

        # 3. Disable hibernate ผ่าน command
        self._disable_hibernate()

        # 4. สร้าง hidden window เพื่อ intercept shutdown messages
        self._window_thread = threading.Thread(
            target=self._run_shutdown_blocker, daemon=True
        )
        self._window_thread.start()

        # 5. Mouse jiggle thread
        self._jiggle_thread = threading.Thread(
            target=self._run_mouse_jiggle, daemon=True
        )
        self._jiggle_thread.start()

        # 6. Periodic execution state refresh
        self._power_thread = threading.Thread(
            target=self._run_power_keepalive, daemon=True
        )
        self._power_thread.start()

    def stop(self):
        """คืนค่าทุกอย่าง"""
        self._stop_event.set()
        self._active = False

        if not IS_WINDOWS:
            return

        try:
            # คืนค่า execution state
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
        except Exception:
            pass

        try:
            # ลบ shutdown block reason
            if self._hwnd:
                ctypes.windll.user32.ShutdownBlockReasonDestroy(self._hwnd)
        except Exception:
            pass

    # ── Sleep / Hibernate Prevention ──

    def _set_execution_state(self):
        """ตั้ง execution state เพื่อป้องกัน sleep"""
        try:
            flags = (
                self.ES_CONTINUOUS
                | self.ES_SYSTEM_REQUIRED
                | self.ES_DISPLAY_REQUIRED
                | self.ES_AWAYMODE_REQUIRED
            )
            result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
            if result == 0:
                # Retry without AWAYMODE
                flags = (
                    self.ES_CONTINUOUS
                    | self.ES_SYSTEM_REQUIRED
                    | self.ES_DISPLAY_REQUIRED
                )
                ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass

    def _disable_hibernate(self):
        """ปิด hibernate ผ่าน powercfg"""
        try:
            os.system("powercfg /hibernate off >nul 2>&1")
        except Exception:
            pass

    def _set_shutdown_priority(self):
        """ตั้งให้โปรแกรมปิดเป็นลำดับสุดท้าย"""
        try:
            # ค่า level: 0x000 = ปิดท้ายสุด, 0x4FF = ปิดก่อนสุด
            # ใช้ 0x000 เพื่อให้อยู่ได้นานที่สุด
            ctypes.windll.kernel32.SetProcessShutdownParameters(
                0x000, self.SHUTDOWN_NORETRY
            )
        except Exception:
            pass

    # ── Shutdown / Restart Blocker ──

    def _run_shutdown_blocker(self):
        """สร้าง hidden window ที่ intercept WM_QUERYENDSESSION"""
        try:
            WNDPROC = ctypes.WINFUNCTYPE(
                ctypes.c_long,
                ctypes.wintypes.HWND,
                ctypes.c_uint,
                ctypes.wintypes.WPARAM,
                ctypes.wintypes.LPARAM,
            )

            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == self.WM_QUERYENDSESSION:
                    # Return FALSE (0) เพื่อบล็อก shutdown/restart
                    # Windows จะแสดง dialog ว่ามีโปรแกรมบล็อกอยู่
                    return 0

                if msg == self.WM_ENDSESSION:
                    # ถ้า Windows บังคับปิด ให้ทำ cleanup
                    if wparam:
                        self.stop()
                    return 0

                if msg == self.WM_POWERBROADCAST:
                    if wparam == self.PBT_APMQUERYSUSPEND:
                        # บล็อก suspend request
                        return 0

                if msg == self.WM_CLOSE:
                    return 0

                if msg == self.WM_DESTROY:
                    ctypes.windll.user32.PostQuitMessage(0)
                    return 0

                return ctypes.windll.user32.DefWindowProcW(
                    hwnd, msg, wparam, lparam
                )

            wnd_proc_cb = WNDPROC(wnd_proc)

            # Register window class
            class_name = "NeverSleepBlocker"
            wndclass = ctypes.wintypes.WNDCLASSW()
            wndclass.lpfnWndProc = wnd_proc_cb
            wndclass.lpszClassName = class_name
            wndclass.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)

            atom = ctypes.windll.user32.RegisterClassW(ctypes.byref(wndclass))
            if not atom:
                return

            # Create hidden window
            self._hwnd = ctypes.windll.user32.CreateWindowExW(
                0, class_name, "Never Sleep Session Monitor",
                0, 0, 0, 0, 0, None, None, wndclass.hInstance, None
            )

            if not self._hwnd:
                return

            # ตั้ง shutdown block reason
            reason = "Active remote sessions detected - cannot shutdown safely"
            ctypes.windll.user32.ShutdownBlockReasonCreate(
                self._hwnd, reason
            )

            # Message loop
            msg = ctypes.wintypes.MSG()
            while not self._stop_event.is_set():
                result = ctypes.windll.user32.PeekMessageW(
                    ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE
                )
                if result:
                    ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                    ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    time.sleep(0.1)

        except Exception:
            pass

    # ── Mouse Jiggle (prevent screen lock) ──

    def _run_mouse_jiggle(self):
        """จำลอง mouse movement เล็กน้อยทุก 30 วินาที"""
        while not self._stop_event.is_set():
            try:
                # Move mouse 1px แล้วกลับ
                MOUSEEVENTF_MOVE = 0x0001
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, 1, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_MOVE, -1, 0, 0, 0)
            except Exception:
                pass

            self._stop_event.wait(30)

    # ── Periodic Power Keepalive ──

    def _run_power_keepalive(self):
        """รีเฟรช execution state ทุก 30 วินาที"""
        while not self._stop_event.is_set():
            self._set_execution_state()
            self._stop_event.wait(30)

    # ── Status ──

    def get_status(self):
        """คืนค่าสถานะการป้องกัน"""
        protections = []
        if self._active:
            protections.append("Sleep Block: ON")
            protections.append("Hibernate Block: ON")
            protections.append("Shutdown Block: ON" if self._hwnd else "Shutdown Block: PARTIAL")
            protections.append("Screen Lock Block: ON")
            protections.append("Restart Block: ON" if self._hwnd else "Restart Block: PARTIAL")
        else:
            protections = ["All protections: OFF"]
        return protections


# ─── Session Manager ────────────────────────────────────────────────────────

class FakeSessionManager:
    def __init__(self, min_sessions=2, max_sessions=6):
        self.min_sessions = min_sessions
        self.max_sessions = max_sessions
        self.sessions = []
        self.running = False
        self._lock = threading.Lock()
        self._session_counter = 0
        self.hostname = platform.node() or "SERVER-01"
        self.os_name = platform.system()
        self.start_time = datetime.now()

    def generate_session_id(self):
        self._session_counter += 1
        return self._session_counter

    def generate_remote_ip(self):
        template = random.choice(REMOTE_IPS)
        count = template.count("{}")
        args = [random.randint(2, 254) for _ in range(count)]
        return template.format(*args)

    def generate_terminal(self, protocol):
        num = random.randint(0, 65535)
        return f"{protocol}#{num}"

    def create_session(self):
        protocol = random.choice(PROTOCOLS)
        now = datetime.now()
        login_offset = random.randint(120, 14400)
        login_time = now - timedelta(seconds=login_offset)
        idle_offset = random.randint(0, min(600, login_offset))
        last_activity = now - timedelta(seconds=idle_offset)

        if idle_offset < 30:
            state = "Active"
        elif idle_offset < 300:
            state = random.choice(["Active", "Connected"])
        else:
            state = random.choice(SESSION_STATES)

        return FakeSession(
            session_id=self.generate_session_id(),
            username=random.choice(FAKE_USERNAMES),
            remote_ip=self.generate_remote_ip(),
            protocol=protocol,
            state=state,
            login_time=login_time,
            last_activity=last_activity,
            pid=random.randint(1000, 65535),
            terminal=self.generate_terminal(protocol),
        )

    def initialize_sessions(self):
        count = random.randint(self.min_sessions, self.max_sessions)
        with self._lock:
            self.sessions = [self.create_session() for _ in range(count)]

    def simulate_activity(self):
        with self._lock:
            for session in self.sessions:
                if random.random() < 0.3:
                    session.last_activity = datetime.now() - timedelta(
                        seconds=random.randint(0, 180)
                    )
                    session.state = (
                        "Active" if random.random() < 0.6
                        else random.choice(SESSION_STATES)
                    )

            if random.random() < 0.12 and len(self.sessions) < self.max_sessions:
                new_session = self.create_session()
                new_session.login_time = datetime.now() - timedelta(
                    seconds=random.randint(0, 60)
                )
                new_session.state = "Active"
                self.sessions.append(new_session)

            if random.random() < 0.08 and len(self.sessions) > self.min_sessions:
                idx = random.randint(0, len(self.sessions) - 1)
                self.sessions.pop(idx)

    def get_sessions(self):
        with self._lock:
            return list(self.sessions)


# ─── Display ─────────────────────────────────────────────────────────────────

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


BANNER = r"""
    _   __                         _____ __
   / | / /___  _   _____  _____   / ___// /__  ___  ____
  /  |/ / _ \| | / / _ \/ ___/   \__ \/ / _ \/ _ \/ __ \
 / /|  /  __/| |/ /  __/ /      ___/ / /  __/  __/ /_/ /
/_/ |_/\___/ |___/\___/_/      /____/_/\___/\___/ .___/
                                               /_/
  Fake Remote Session Simulator v1.0
"""


def print_display(manager, protection):
    sessions = manager.get_sessions()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime = str(datetime.now() - manager.start_time).split(".")[0]

    clear_screen()
    print("=" * 80)
    print(BANNER)
    print("=" * 80)

    # Server info
    print(f"  Server: {manager.hostname}  |  OS: {manager.os_name}")
    print(f"  Time:   {now}  |  Uptime: {uptime}")
    print(f"  Sessions: {len(sessions)} remote connections")
    print()

    # Protection status
    print("  Protection Status:")
    for status in protection.get_status():
        print(f"    [{status}]")
    print()

    # Session table (qwinsta style)
    print("  " + "-" * 76)
    fmt = "  {:<20} {:<16} {:>4}  {:<10} {:<6} {:<18}"
    print(fmt.format(
        "SESSIONNAME", "USERNAME", "ID", "STATE", "IDLE", "REMOTE IP"
    ))
    print("  " + "-" * 76)

    # System sessions
    print(fmt.format("services", "SYSTEM", "0", "Disc", "", ""))
    print(fmt.format("console", "", "1", "Conn", "", ""))

    # Fake remote sessions
    for s in sessions:
        print(fmt.format(
            s.terminal[:20], s.username[:16], s.session_id,
            s.state, s.idle_time, s.remote_ip
        ))

    print("  " + "-" * 76)
    print()

    # User table (quser style)
    print("  Connected Users:")
    print("  " + "-" * 76)
    ufmt = "  {:<16} {:<20} {:>4}  {:<10} {:<18}"
    print(ufmt.format("USERNAME", "SESSIONNAME", "ID", "STATE", "LOGON TIME"))
    print("  " + "-" * 76)

    for s in sessions:
        logon = s.login_time.strftime("%m/%d/%Y %H:%M")
        print(ufmt.format(
            s.username[:16], s.terminal[:20], s.session_id,
            s.state, logon
        ))

    print()
    print("  " + "=" * 76)
    print("  [Ctrl+C to stop]  Auto-refresh every 5 seconds")
    print("  " + "=" * 76)


# ─── Log Writer ──────────────────────────────────────────────────────────────

class SessionLogger:
    def __init__(self, log_file="never_sleep.log"):
        self.log_file = log_file

    def log(self, message):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def log_sessions(self, sessions):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] Sessions: {len(sessions)} active\n")
                for s in sessions:
                    f.write(f"  {s.username}@{s.remote_ip} [{s.state}]\n")
        except Exception:
            pass


# ─── Main ────────────────────────────────────────────────────────────────────

def run(min_sessions=2, max_sessions=6, refresh=5,
        no_protect=False, log=False, background=False, json_mode=False):

    # JSON snapshot mode
    if json_mode:
        import json
        mgr = FakeSessionManager(min_sessions, max_sessions)
        mgr.initialize_sessions()
        output = {
            "hostname": mgr.hostname,
            "os": mgr.os_name,
            "timestamp": datetime.now().isoformat(),
            "sessions": [s.to_dict() for s in mgr.get_sessions()],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    # Setup
    manager = FakeSessionManager(min_sessions, max_sessions)
    manager.initialize_sessions()
    manager.running = True

    protection = WindowsProtection()
    logger = SessionLogger() if log else None

    def cleanup(sig=None, frame=None):
        manager.running = False
        print("\n\n  Shutting down Never Sleep...")
        protection.stop()
        if logger:
            logger.log("Stopped")
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Start protection
    if not no_protect:
        protection.start()
        if logger:
            logger.log("Protection started: sleep/hibernate/shutdown/restart blocked")

    if logger:
        logger.log(f"Started with {min_sessions}-{max_sessions} sessions")

    if not background:
        print("\n  Starting Never Sleep...")
        print(f"  Generating {min_sessions}-{max_sessions} fake remote sessions")
        if not no_protect:
            print("  Protection: Sleep, Hibernate, Shutdown, Restart - ALL BLOCKED")
        time.sleep(1)

    log_counter = 0

    while manager.running:
        try:
            if not background:
                print_display(manager, protection)

            manager.simulate_activity()

            # Log periodically
            log_counter += 1
            if logger and log_counter >= 12:
                logger.log_sessions(manager.get_sessions())
                log_counter = 0

            time.sleep(refresh)

        except KeyboardInterrupt:
            cleanup()
        except Exception as e:
            if not background:
                print(f"  Error: {e}")
            time.sleep(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Never Sleep - Fake Remote Session Simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fake_session.py                    # Run (blocks sleep/shutdown/restart)
  python fake_session.py --min 3 --max 10   # 3-10 fake sessions
  python fake_session.py --background       # Run without display (background)
  python fake_session.py --json             # Output JSON snapshot and exit
  python fake_session.py --no-protect       # Display only, no system protection
  python fake_session.py --log              # Write activity to never_sleep.log

Protection (enabled by default, requires Admin for full effect):
  - Blocks Sleep and Hibernate
  - Blocks Shutdown and Restart (shows "blocking" dialog)
  - Prevents Screen Lock and Screen Saver
  - Mouse jiggle to reset idle timer

Tip: Run as Administrator for maximum protection.
     Right-click run.bat -> "Run as administrator"
        """,
    )
    parser.add_argument("--min", type=int, default=2,
                        help="Minimum fake sessions (default: 2)")
    parser.add_argument("--max", type=int, default=6,
                        help="Maximum fake sessions (default: 6)")
    parser.add_argument("--refresh", type=int, default=5,
                        help="Refresh interval in seconds (default: 5)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON snapshot and exit")
    parser.add_argument("--no-protect", action="store_true",
                        help="Disable system protection (sleep/shutdown block)")
    parser.add_argument("--background", action="store_true",
                        help="Run in background mode (no display output)")
    parser.add_argument("--log", action="store_true",
                        help="Enable logging to never_sleep.log")

    args = parser.parse_args()

    if args.min > args.max:
        parser.error("--min cannot be greater than --max")
    if args.min < 1:
        parser.error("--min must be at least 1")

    run(
        min_sessions=args.min,
        max_sessions=args.max,
        refresh=args.refresh,
        no_protect=args.no_protect,
        log=args.log,
        background=args.background,
        json_mode=args.json,
    )


if __name__ == "__main__":
    main()
