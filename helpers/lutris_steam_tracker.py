#!/usr/bin/env python3
import os
import time
import psutil
import signal
import sys
from datetime import datetime
from .config import GAME_FILE

# CONFIG
POLL_INTERVAL = 5
STARTUP_DELAY = 30

# Use SCRIPT_DIR as base for data files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(SCRIPT_DIR, "../data/game_agent/lutris_steam_tracker.log")

# Normalize paths (resolve ../)
TRACK_FILE = os.path.abspath(GAME_FILE)
LOG_FILE = os.path.abspath(LOG_FILE)

# Processes to monitor
TARGET_PROCESSES = ["reaper", "pressure-vessel-wrap", "steam.exe"]


def log(msg):
    # Write a timestamped message to the log file.
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} {msg}\n")
    # Also print to stdout if we're in foreground mode
    print(f"{ts} {msg}", flush=True)

def write_game_name(name):
    with open(TRACK_FILE, "w") as f:
        f.write(name + "\n")
    log(f"[tracker] Tracking game: {name}")

def clear_game_name():
    open(TRACK_FILE, "w").close()
    log("[tracker] Cleared game tracking file.")

def find_target_pids():
    # Return a set of PIDs for all matching target processes.
    matches = set()
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in [t.lower() for t in TARGET_PROCESSES]:
                matches.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def monitor_loop(game_name):
    write_game_name(game_name)
    log(f"[tracker] Waiting {STARTUP_DELAY}s before checking for processes...")
    time.sleep(STARTUP_DELAY)

    log("[tracker] Scanning for target processes...")
    target_pids = set()

    # Wait for target processes to appear
    TIMEOUT = 300  # 5 minutes in seconds
    start_time = time.time()
    while not target_pids:
        target_pids = find_target_pids()
        if target_pids:
            break

        if time.time() - start_time > TIMEOUT:
            log("[tracker] Timeout reached while waiting for target processes.")
            raise TimeoutError("No target processes appeared within timeout")

        time.sleep(POLL_INTERVAL)

    # After we find the first target_pids
    log(f"[tracker] Target detected: {target_pids}. Monitoring until all exit...")

    for pid in target_pids:
        try:
            p = psutil.Process(pid)
            log(f"[tracker] PID {pid} -> name={p.name()} cmdline={p.cmdline()}")
        except Exception as e:
            log(f"[tracker] Could not inspect PID {pid}: {e}")

    # Wait until *all* target PIDs are gone
    while True:
        active_pids = find_target_pids()
        still_alive = target_pids.intersection(active_pids)
        if not still_alive:
            break
        time.sleep(POLL_INTERVAL)

    clear_game_name()
    log("[tracker] All target processes exited, cleared file.")


def daemonize():
    # Double-fork to fully detach from parent process (Lutris).
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        log(f"[tracker] Fork #1 failed: {e}")
        sys.exit(1)

    os.setsid()  # New session and process group

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        log(f"[tracker] Fork #2 failed: {e}")
        sys.exit(1)

    # Redirect stdio to /dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    with open("/dev/null", "r") as devnull_r, open("/dev/null", "a+") as devnull_w:
        os.dup2(devnull_r.fileno(), sys.stdin.fileno())
        os.dup2(devnull_w.fileno(), sys.stdout.fileno())
        os.dup2(devnull_w.fileno(), sys.stderr.fileno())

    # Ignore signals sent by Lutris
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

def main():
    game_name = os.getenv("GAME_NAME", "Unknown")
    log(f"[tracker] Starting tracker for '{game_name}' (pid={os.getpid()})")

    # Detach so Lutris doesn’t kill us
    log("[tracker] Daemonizing...")
    daemonize()

    log(f"[tracker] Daemonized successfully (pid={os.getpid()})")
    try:
        monitor_loop(game_name)
    except Exception as e:
        log(f"[tracker] Exception: {e}")
        clear_game_name()

if __name__ == "__main__":
    main()
