import os, sys, subprocess, glob, re, json, copy, time, configparser, shutil
from pathlib import Path
from .config import COMMANDS_MOD

# ----------------------------
# System commands
# ----------------------------

def load_commands(filename="commands.ini"):
    BASE_DIR = Path(__file__).parent.parent
    commands_file = BASE_DIR / "data" / filename
    src = BASE_DIR / "resources" / "commands_example.ini"

    # Create data dir if needed
    commands_file.parent.mkdir(parents=True, exist_ok=True)

    # Create default if missing
    if not commands_file.exists():
        shutil.copy(src, commands_file)
        print(f"[Commands] Created default commands config at {commands_file}")

    # Parse file
    parser = configparser.ConfigParser()
    parser.optionxform = str  # preserve key case
    parser.read(commands_file, encoding="utf-8")

    commands = {}
    for section in parser.sections():
        cmd = parser.get(section, "cmd", fallback=None)
        wait = parser.getboolean(section, "wait", fallback=False)
        platforms = parser.get(section, "platforms", fallback=None)
        platforms = [p.strip() for p in platforms.split(",")] if platforms else None

        commands[section] = {
            "cmd": cmd,
            "wait": wait,
            "platforms": platforms,
        }

    return commands

ALLOWED_COMMANDS = load_commands() if COMMANDS_MOD else {}

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
    print(f"[Commands] Received command: {entry}")

    if isinstance(entry, dict):
        cmd = entry.get("cmd")
        wait = entry.get("wait", False)
        platforms = entry.get("platforms", None)
    else:
        cmd = entry
        wait = False
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

            if wait: # if you need result of command (ideal for scripts that return values)
                cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
                result = subprocess.run(cmd_str, env=env, shell=True, capture_output=True, text=True)
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout.strip() if result.stdout else result.stderr.strip()
                }

            else: # if you just need to launch and close (ideal for gui apps)
                cmd_arr = cmd if isinstance(cmd, list) else cmd.split()
                proc = subprocess.Popen(cmd_arr, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
                if proc.poll() is not None:
                    return {"success": False, "output": f"Command '{command_key}' failed to start."}
                return {"success": True, "output": f"Command '{command_key}' launched (Linux GUI)."}


        elif platform_name == "win":
            if wait: # if you need result of command (ideal for scripts that return values)
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout.strip() if result.stdout else result.stderr.strip()
                }

            else: # if you just need to launch and close (ideal for gui apps)
                subprocess.Popen(cmd, shell=True)
                return {"success": True, "output": f"Command '{command_key}' launched (Windows)."}

        else:
            return {"success": False, "output": f"Unsupported platform '{platform_name}'."}

    except Exception as e:
        return {"success": False, "output": str(e)}
