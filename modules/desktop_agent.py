import os, sys, time, socket, math, platform, subprocess, psutil, GPUtil, re, glob

# ----------------------------
# System Info Helpers
# ----------------------------

def get_system_info():
    cpu_freq = psutil.cpu_freq()
    virtual_mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()

    gpu_flat = get_gpu_info_flat()
    temps_flat = get_temperatures_flat()

    total, used, free, percent = get_disk_info()

    return {
        "hostname": socket.gethostname(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "os": platform.system(),
        "os_release": platform.release(),
        "os_version": get_os_version(),
        "cpu_model": get_cpu_model(),
        "cpu_usage": round(psutil.cpu_percent(interval=0.5)),
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_frequency_mhz": round(cpu_freq.current) if cpu_freq else None,
        "memory_usage": round(virtual_mem.percent),
        "memory_total_gb": round(virtual_mem.total / (1024 ** 3), 1),
        "memory_used_gb": round(virtual_mem.used / (1024 ** 3), 1),
        "disk_usage": round(percent),
        "disk_total_gb": round(total / (1024 ** 3), 1),
        "disk_used_gb": round(used / (1024 ** 3), 1),
        "network_sent_bytes": bytes_to_human(net_io.bytes_sent),
        "network_recv_bytes": bytes_to_human(net_io.bytes_recv),
        **gpu_flat,
        **temps_flat
    }

def get_os_version():
    if sys.platform.startswith("linux"):
        try:
            # Try standard library first
            distro_name = ""
            distro_version = ""
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release") as f:
                    data = {}
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            data[k] = v.strip('"')
                    distro_name = data.get("NAME", "Linux")
                    distro_version = data.get("VERSION_ID", "")
            return f"{distro_name} {distro_version}".strip()
        except:
            return platform.version()
    elif sys.platform.startswith("win"):
        return platform.version()
    else:
        return platform.version()

def get_cpu_model():
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if "model name" in line:
                        return line.strip().split(":")[1].strip()
        except:
            return "Unknown CPU"
    elif sys.platform.startswith("win"):
        try:
            output = subprocess.check_output("wmic cpu get Name", shell=True).decode()
            lines = [line.strip() for line in output.splitlines() if line.strip()]
            if len(lines) >= 2:
                return lines[1]
        except:
            return "Unknown CPU"
    else:
        return platform.processor() or "Unknown CPU"

def get_disk_info():
    # For Windows systems, get the disk info of the root directory
    if sys.platform.startswith("win"):
        usage = psutil.disk_usage('C:\\')
        return usage.total, usage.used, usage.free, usage.percent

    # For Linux systems, focus on /var/home partition
    else:
        total = used = free = 0
        target_partitions = ['/var/home', '/home']
        for partition in psutil.disk_partitions(all=False):
            if partition.mountpoint in target_partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    total = usage.total
                    used = usage.used
                    free = usage.free
                    # Once we find a match, we don't need to check other partitions
                    break
                except PermissionError:
                    # Skip partitions that cannot be accessed
                    continue
                except OSError:
                    # Skip invalid mount points
                    continue
                
        # Calculate the percentage of disk used
        percent = (used / total) * 100 if total > 0 else 0
        return total, used, free, percent

def safe_number(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return default
        return val
    return default

def clean_value(val):
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val

def get_gpu_info_flat():
    gpus = GPUtil.getGPUs()
    gpu_info = {}
    for i, gpu in enumerate(gpus):
        prefix = f"gpu{i}_"
        gpu_info[prefix + "name"] = gpu.name or "Unknown"
        gpu_info[prefix + "load_percent"] = round(safe_number(gpu.load * 100 if gpu.load is not None else None, 0))
        gpu_info[prefix + "memory_total_gb"] = round(safe_number(gpu.memoryTotal, 0))
        gpu_info[prefix + "memory_used_gb"] = round(safe_number(gpu.memoryUsed, 0))
        gpu_info[prefix + "temperature_c"] = round(safe_number(gpu.temperature, 0))
    return gpu_info

def get_temperatures_flat():
    temps = {}
    if hasattr(psutil, "sensors_temperatures"):
        raw_temps = psutil.sensors_temperatures()
        for label, entries in raw_temps.items():
            for entry in entries:
                key = f"{label}_{entry.label}" if entry.label else f"{label}"
                temps[key] = clean_value(entry.current)
    return temps

def bytes_to_human(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    step = 1024.0
    i = 0
    while n >= step and i < len(units) - 1:
        n /= step
        i += 1
    return f"{n:.2f} {units[i]}"
