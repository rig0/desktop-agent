import os, sys, platform

def print_raw_os_info():
    print("sys.platform:", sys.platform)
    print("platform.system():", platform.system())
    print("platform.release():", platform.release())
    print("platform.version():", platform.version())
    print("platform.platform():", platform.platform())
    print("platform.uname():", platform.uname())

    # Linux-only raw check
    if sys.platform.startswith("linux") and os.path.exists("/etc/os-release"):
        print("\n--- /etc/os-release ---")
        with open("/etc/os-release") as f:
            for line in f:
                print(line.strip())

if __name__ == "__main__":
    print_raw_os_info()