import os, sys, subprocess, glob, re, json
from pathlib import Path

# ----------------------------
# System commands
# ----------------------------

def load_commands(filename="commands.json"):
    BASE_DIR = Path(__file__).parent.parent
    config_file = BASE_DIR / "config" / filename
    if not config_file.exists():
        raise FileNotFoundError(f"{config_file} not found at {config_file}")
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)

ALLOWED_COMMANDS = load_commands()

def get_linux_gui_env():
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")

    # Ensure our wrapper is found first (move to config,make dynamic and conditional(in container?))
    env["PATH"] = "/var/home/rambo/Apps/Agent/helpers:" + env.get("PATH", "")

    # Detect display server
    if "WAYLAND_DISPLAY" in env:
        env["DISPLAY"] = ":0"  # Still needed for some apps via XWayland
        env["USE_WAYLAND"] = "1"
    else:
        env.setdefault("DISPLAY", ":0")
        env.pop("USE_WAYLAND", None)

    # Detect DBUS session
    for pid_path in glob.glob("/proc/*/environ"):
        try:
            with open(pid_path, "rb") as f:
                data = f.read().decode(errors="ignore")
                m = re.search(r"DBUS_SESSION_BUS_ADDRESS=([^\x00]+)", data)
                if m:
                    env["DBUS_SESSION_BUS_ADDRESS"] = m.group(1)
                    break
        except Exception:
            continue

    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        # Fallback: only use dbus-launch if no session bus found
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={env['XDG_RUNTIME_DIR']}/bus"

    return env

# Reboot / Shutdown handler
def run_system_power_command(action: str) -> dict:
    try:
        if sys.platform.startswith("linux"):
            cmd = "systemctl reboot" if action == "reboot" else "systemctl poweroff"
        elif sys.platform.startswith("win"):
            cmd = "shutdown /r /t 0" if action == "reboot" else "shutdown /s /t 0"
        else:
            return {"success": False, "output": f"Unsupported platform: {sys.platform}"}

        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "output": f"{action.capitalize()} command executed."}
    except Exception as e:
        return {"success": False, "output": str(e)}

# Reboot / Shutdown handler
def run_system_power_command(action: str) -> dict:
    try:
        platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None
        if not platform_name:
            return {"success": False, "output": f"Unsupported platform: {sys.platform}"}

        if platform_name == "linux":
            if action == "reboot":
                cmd = "reboot"
                # cmd = "sudo systemctl reboot"
            elif action == "shutdown":
                cmd = "poweroff"
                # cmd = "sudo systemctl poweroff"
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        elif platform_name == "win":
            if action == "reboot":
                cmd = "shutdown /r /t 0"
            elif action == "shutdown":
                cmd = "shutdown /s /t 0"
            else:
                return {"success": False, "output": f"Unknown action '{action}'"}

        subprocess.Popen(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"success": True, "output": f"{action.capitalize()} command executed."}

    except Exception as e:
        return {"success": False, "output": str(e)}

# Run predefined commands
def run_predefined_command(command_key: str) -> dict:
    if command_key not in ALLOWED_COMMANDS:
        return {"success": False, "output": f"Command '{command_key}' not allowed."}

    entry = ALLOWED_COMMANDS[command_key]
    if isinstance(entry, dict):
        cmd = entry.get("cmd")
        wait = entry.get("wait", True)
        platforms = entry.get("platforms", None)
    else:
        cmd = entry
        wait = True
        platforms = None

    platform_name = "linux" if sys.platform.startswith("linux") else "win" if sys.platform.startswith("win") else None

    if platforms and platform_name not in platforms:
        return {"success": False, "output": f"Command '{command_key}' not available on {platform_name}."}

    # Special commands
    if cmd in ["reboot", "shutdown"]:
        return run_system_power_command(cmd)

    try:
        if platform_name == "linux":
            env = get_linux_gui_env()
            process_cmd = cmd if isinstance(cmd, list) else cmd.split()

            # Prepend dbus-launch if no running DBUS session detected
            if not env.get("USE_WAYLAND") and "unix:path=" in env.get("DBUS_SESSION_BUS_ADDRESS", ""):
                process_cmd = ["dbus-launch"] + process_cmd

            subprocess.Popen(process_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "output": f"Command '{command_key}' launched (Linux GUI)."}

        elif platform_name == "win":
            if wait:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout.strip() if result.stdout else result.stderr.strip()
                }
            else:
                subprocess.Popen(cmd, shell=True)
                return {"success": True, "output": f"Command '{command_key}' launched (Windows)."}

        else:
            return {"success": False, "output": f"Unsupported platform '{platform_name}'."}

    except Exception as e:
        return {"success": False, "output": str(e)}
