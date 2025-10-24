import os, sys, subprocess, glob, re, json, copy, time
from pathlib import Path
from .config import COMMANDS_MOD

# ----------------------------
# System commands
# ----------------------------

def load_commands(filename="commands.json"):
    BASE_DIR = Path(__file__).parent.parent
    config_file = BASE_DIR / "data" / filename
    if not config_file.exists():
        print(f"{config_file} not found. Creating now.")
        default_data = {
            "reboot": {
                "cmd": "reboot",
                "wait": False,
                "platforms": ["linux", "win"]
            },
            "shutdown": {
                "cmd": "shutdown",
                "wait": False,
                "platforms": ["linux", "win"]
            },
            "plexamp": {
                "cmd": "flatpak run com.plexamp.Plexamp",
                "wait": False,
                "platforms": ["linux"]
            },
            "plexamp_windows": {
                "cmd": "C:\\Users\\User\\AppData\\Local\\Programs\\Plexamp\\Plexamp.exe",
                "wait": False,
                "platforms": ["win"]
            }
        }
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=2)
        return default_data
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)

ALLOWED_COMMANDS = load_commands()

import os
import copy

def get_linux_gui_env() -> dict:
    # Return environment variables for launching GUI applications on Linux,
    env = copy.deepcopy(os.environ)

    # Detect Wayland
    wayland_display = env.get("WAYLAND_DISPLAY")
    use_wayland = bool(wayland_display)

    # Detect X11
    x11_display = env.get("DISPLAY")
    use_x11 = bool(x11_display)

    env["USE_WAYLAND"] = str(use_wayland)

    # If Wayland, ensure DISPLAY is also set for apps that require X11 fallback
    if use_wayland and not x11_display:
        env["DISPLAY"] = ":0"

    # DBUS_SESSION_BUS_ADDRESS
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        # Fallback to launching dbus-session if missing
        try:
            from subprocess import check_output
            dbus_address = check_output(["dbus-launch"], text=True).splitlines()
            for line in dbus_address:
                if line.startswith("DBUS_SESSION_BUS_ADDRESS="):
                    env["DBUS_SESSION_BUS_ADDRESS"] = line.split("=", 1)[1].strip()
                elif line.startswith("DBUS_SESSION_BUS_PID="):
                    env["DBUS_SESSION_BUS_PID"] = line.split("=", 1)[1].strip()
        except Exception:
            pass  # Ignore failures; some systems may not have dbus-launch

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
    if not COMMANDS_MOD:
        print(f"[Commands] Module not enabled.")
        return {"success": False, "output": f"[Commands] Module not enabled"}

    if command_key not in ALLOWED_COMMANDS:
        print(f"[Commands] Command '{command_key}' not allowed.")
        return {"success": False, "output": f"[Commands] Command '{command_key}' not allowed."}

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

            try:
                proc = subprocess.Popen(process_cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
                if proc.poll() is not None:
                    return {"success": False, "output": f"Command '{command_key}' failed to start."}
                return {"success": True, "output": f"Command '{command_key}' launched (Linux GUI)."}
            except Exception as e:
                return {"success": False, "output": str(e)}


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
