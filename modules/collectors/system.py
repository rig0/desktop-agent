"""System metrics collection for Desktop Agent.

This module provides collector classes for gathering system information
including CPU, memory, disk, network, and GPU metrics. Each collector
is independent and can be used separately or together via SystemInfoCollector.

All collectors are pure data collection classes - they don't handle
MQTT publishing, formatting, or any other concerns beyond gathering data.
"""

# Standard library imports
import logging
import math
import socket
import sys
import time
from typing import Any, Dict, Optional, Tuple

# Third-party imports
import psutil

# Local imports
from modules.utils.platform import PlatformUtils

logger = logging.getLogger(__name__)


class CPUCollector:
    """Collects CPU metrics.

    This collector gathers CPU-related information including usage percentage,
    model name, frequency, temperature, and core count.

    Attributes:
        platform: Platform utilities for platform-specific operations.

    Example:
        >>> cpu = CPUCollector()
        >>> usage = cpu.get_usage()
        >>> model = cpu.get_model()
        >>> print(f"CPU: {model}, Usage: {usage}%")
    """

    def __init__(self, platform_utils: Optional[PlatformUtils] = None):
        """Initialize CPU collector.

        Args:
            platform_utils: Platform-specific utilities (creates new instance if None).
        """
        self.platform = platform_utils or PlatformUtils()

    def get_usage(self, interval: float = 0.5) -> float:
        """Get current CPU usage percentage.

        Args:
            interval: Measurement interval in seconds (default: 0.5).

        Returns:
            CPU usage as percentage (0-100), rounded to nearest integer.

        Example:
            >>> cpu = CPUCollector()
            >>> cpu.get_usage()
            45.0
        """
        try:
            usage = psutil.cpu_percent(interval=interval)
            return round(usage)
        except Exception as e:
            logger.error(f"Error getting CPU usage: {e}")
            return 0.0

    def get_model(self) -> str:
        """Get CPU model name.

        Returns:
            CPU model string (e.g., "Intel Core i7-9700K").

        Example:
            >>> cpu = CPUCollector()
            >>> cpu.get_model()
            'Intel(R) Core(TM) i7-9700K CPU @ 3.60GHz'
        """
        return self.platform.get_cpu_model()

    def get_frequency(self) -> Optional[int]:
        """Get current CPU frequency in MHz.

        Returns:
            Current frequency in MHz (rounded), or None if unavailable.

        Example:
            >>> cpu = CPUCollector()
            >>> cpu.get_frequency()
            3600
        """
        try:
            freq = psutil.cpu_freq()
            if freq:
                return round(freq.current)
            return None
        except (AttributeError, OSError) as e:
            logger.debug(f"Could not get CPU frequency: {e}")
            return None

    def get_cores(self) -> int:
        """Get number of logical CPU cores.

        Returns:
            Number of logical CPU cores.

        Example:
            >>> cpu = CPUCollector()
            >>> cpu.get_cores()
            8
        """
        try:
            return psutil.cpu_count(logical=True)
        except Exception as e:
            logger.error(f"Error getting CPU cores: {e}")
            return 0

    def get_temperature(self) -> Optional[float]:
        """Get CPU temperature in Celsius (if available).

        Note:
            Temperature monitoring is platform-dependent and may not be
            available on all systems. This method attempts to read from
            sensors but returns None if unavailable.

        Returns:
            CPU temperature in Celsius, or None if unavailable.

        Example:
            >>> cpu = CPUCollector()
            >>> temp = cpu.get_temperature()
            >>> if temp:
            ...     print(f"CPU temp: {temp}°C")
        """
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                # Try common CPU temperature sensor names
                for sensor_name in ["coretemp", "k10temp", "zenpower", "cpu_thermal"]:
                    if sensor_name in temps:
                        for entry in temps[sensor_name]:
                            if entry.label and "Package" in entry.label:
                                return entry.current
                            if entry.label and "Tctl" in entry.label:
                                return entry.current
                        # If no specific label, return first entry
                        if temps[sensor_name]:
                            return temps[sensor_name][0].current
        except (AttributeError, OSError) as e:
            logger.debug(f"Could not get CPU temperature: {e}")
        return None


class MemoryCollector:
    """Collects memory metrics.

    This collector gathers system memory information including usage percentage,
    total memory, used memory, and available memory.

    Example:
        >>> mem = MemoryCollector()
        >>> usage = mem.get_usage()
        >>> total = mem.get_total()
        >>> print(f"Memory: {usage}% of {total} GB")
    """

    def __init__(self):
        """Initialize memory collector."""
        pass

    def get_usage(self) -> float:
        """Get current memory usage percentage.

        Returns:
            Memory usage as percentage (0-100), rounded to nearest integer.

        Example:
            >>> mem = MemoryCollector()
            >>> mem.get_usage()
            65.0
        """
        try:
            virtual_mem = psutil.virtual_memory()
            return round(virtual_mem.percent)
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 0.0

    def get_total(self) -> float:
        """Get total system memory in GB.

        Returns:
            Total memory in GB (rounded to 1 decimal place).

        Example:
            >>> mem = MemoryCollector()
            >>> mem.get_total()
            16.0
        """
        try:
            virtual_mem = psutil.virtual_memory()
            return round(virtual_mem.total / (1024**3), 1)
        except Exception as e:
            logger.error(f"Error getting total memory: {e}")
            return 0.0

    def get_used(self) -> float:
        """Get used memory in GB.

        Returns:
            Used memory in GB (rounded to 1 decimal place).

        Example:
            >>> mem = MemoryCollector()
            >>> mem.get_used()
            10.4
        """
        try:
            virtual_mem = psutil.virtual_memory()
            return round(virtual_mem.used / (1024**3), 1)
        except Exception as e:
            logger.error(f"Error getting used memory: {e}")
            return 0.0

    def get_available(self) -> float:
        """Get available memory in GB.

        Returns:
            Available memory in GB (rounded to 1 decimal place).

        Example:
            >>> mem = MemoryCollector()
            >>> mem.get_available()
            5.6
        """
        try:
            virtual_mem = psutil.virtual_memory()
            return round(virtual_mem.available / (1024**3), 1)
        except Exception as e:
            logger.error(f"Error getting available memory: {e}")
            return 0.0


class DiskCollector:
    """Collects disk usage metrics.

    This collector gathers disk usage information for the primary storage
    partition. On Windows, it monitors the C: drive. On Linux, it attempts
    to find the most relevant partition (prioritizing /var/home, /home, etc.).

    Example:
        >>> disk = DiskCollector()
        >>> usage = disk.get_usage()
        >>> total = disk.get_total()
        >>> print(f"Disk: {usage}% of {total} GB")
    """

    def __init__(self):
        """Initialize disk collector."""
        pass

    def get_smart_disk(self) -> Tuple[float, float, float, float]:
        """Get disk usage for the most relevant partition.

        On Windows, returns usage for C: drive.
        On Linux, prioritizes /var/home, /home, /run/host/var/home, then /.

        Returns:
            Tuple of (total, used, free, percent) all in bytes, except percent.

        Example:
            >>> disk = DiskCollector()
            >>> total, used, free, percent = disk.get_smart_disk()
            >>> print(f"Disk: {percent:.1f}% used")
        """
        if sys.platform.startswith("win"):
            # Windows: Monitor C: drive
            try:
                usage = psutil.disk_usage("C:\\")
                return usage.total, usage.used, usage.free, usage.percent
            except (PermissionError, OSError) as e:
                logger.error(f"Error accessing C: drive: {e}")
                return 0.0, 0.0, 0.0, 0.0
        else:
            # Linux: Find most relevant partition
            total = used = free = 0.0
            target_partitions = ["/var/home", "/home", "/run/host/var/home", "/"]

            for partition in psutil.disk_partitions(all=False):
                if partition.mountpoint in target_partitions:
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        total = usage.total
                        used = usage.used
                        free = usage.free
                        # Found a target partition, stop searching
                        break
                    except (PermissionError, OSError):
                        # Skip inaccessible partitions
                        continue

            # Calculate percentage
            percent = (used / total) * 100 if total > 0 else 0.0
            return total, used, free, percent

    def get_usage(self) -> float:
        """Get disk usage percentage.

        Returns:
            Disk usage as percentage (0-100), rounded to nearest integer.

        Example:
            >>> disk = DiskCollector()
            >>> disk.get_usage()
            75.0
        """
        try:
            _, _, _, percent = self.get_smart_disk()
            return round(percent)
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return 0.0

    def get_total(self) -> float:
        """Get total disk space in GB.

        Returns:
            Total disk space in GB (rounded to 1 decimal place).

        Example:
            >>> disk = DiskCollector()
            >>> disk.get_total()
            500.0
        """
        try:
            total, _, _, _ = self.get_smart_disk()
            return round(total / (1024**3), 1)
        except Exception as e:
            logger.error(f"Error getting total disk space: {e}")
            return 0.0

    def get_used(self) -> float:
        """Get used disk space in GB.

        Returns:
            Used disk space in GB (rounded to 1 decimal place).

        Example:
            >>> disk = DiskCollector()
            >>> disk.get_used()
            375.2
        """
        try:
            _, used, _, _ = self.get_smart_disk()
            return round(used / (1024**3), 1)
        except Exception as e:
            logger.error(f"Error getting used disk space: {e}")
            return 0.0


class NetworkCollector:
    """Collects network statistics.

    This collector gathers network I/O counters including bytes sent
    and bytes received since system boot.

    Example:
        >>> net = NetworkCollector()
        >>> sent = net.get_bytes_sent()
        >>> received = net.get_bytes_received()
        >>> print(f"Sent: {sent}, Received: {received}")
    """

    def __init__(self):
        """Initialize network collector."""
        pass

    def get_bytes_sent(self) -> int:
        """Get total bytes sent since boot.

        Returns:
            Total bytes sent.

        Example:
            >>> net = NetworkCollector()
            >>> net.get_bytes_sent()
            1536000000
        """
        try:
            net_io = psutil.net_io_counters()
            return net_io.bytes_sent
        except Exception as e:
            logger.error(f"Error getting bytes sent: {e}")
            return 0

    def get_bytes_received(self) -> int:
        """Get total bytes received since boot.

        Returns:
            Total bytes received.

        Example:
            >>> net = NetworkCollector()
            >>> net.get_bytes_received()
            3072000000
        """
        try:
            net_io = psutil.net_io_counters()
            return net_io.bytes_recv
        except Exception as e:
            logger.error(f"Error getting bytes received: {e}")
            return 0


class GPUCollector:
    """Collects GPU metrics.

    This collector gathers GPU information including usage, temperature,
    and memory usage. GPU monitoring requires the GPUtil library and
    compatible GPU drivers (primarily NVIDIA GPUs).

    Note:
        GPUtil support is optional. If GPUtil is not available or no
        compatible GPUs are detected, methods will return None or empty data.

    Example:
        >>> gpu = GPUCollector()
        >>> if gpu.is_available():
        ...     usage = gpu.get_usage()
        ...     temp = gpu.get_temperature()
    """

    def __init__(self):
        """Initialize GPU collector."""
        self._gputil_available = False
        self._gpus = []
        self._check_availability()

    def _check_availability(self) -> None:
        """Check if GPUtil is available and detect GPUs."""
        try:
            import GPUtil

            self._gputil_available = True
            self._gpus = GPUtil.getGPUs()
            if self._gpus:
                logger.info(f"Detected {len(self._gpus)} GPU(s)")
        except ImportError:
            logger.debug("GPUtil not available, GPU monitoring disabled")
        except Exception as e:
            logger.warning(f"Error detecting GPUs: {e}")

    def is_available(self) -> bool:
        """Check if GPU monitoring is available.

        Returns:
            True if GPUtil is available and GPUs are detected.

        Example:
            >>> gpu = GPUCollector()
            >>> if gpu.is_available():
            ...     print("GPU monitoring is available")
        """
        return self._gputil_available and len(self._gpus) > 0

    def _safe_number(self, val: Any, default: float = 0.0) -> float:
        """Safely convert value to float, handling None and invalid values.

        Args:
            val: Value to convert.
            default: Default value if conversion fails.

        Returns:
            Converted float value or default.
        """
        if val is None:
            return default
        if isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                return default
            return val
        return default

    def get_usage(self, gpu_index: int = 0) -> Optional[float]:
        """Get GPU usage percentage for specified GPU.

        Args:
            gpu_index: GPU index (default: 0 for first GPU).

        Returns:
            GPU usage as percentage (0-100), or None if unavailable.

        Example:
            >>> gpu = GPUCollector()
            >>> usage = gpu.get_usage(0)
            >>> if usage:
            ...     print(f"GPU 0 usage: {usage}%")
        """
        if not self.is_available() or gpu_index >= len(self._gpus):
            return None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpu_index < len(gpus):
                gpu = gpus[gpu_index]
                load = self._safe_number(
                    gpu.load * 100 if gpu.load is not None else None, 0
                )
                return round(load)
        except Exception as e:
            logger.debug(f"Error getting GPU usage: {e}")

        return None

    def get_temperature(self, gpu_index: int = 0) -> Optional[float]:
        """Get GPU temperature for specified GPU.

        Args:
            gpu_index: GPU index (default: 0 for first GPU).

        Returns:
            GPU temperature in Celsius, or None if unavailable.

        Example:
            >>> gpu = GPUCollector()
            >>> temp = gpu.get_temperature(0)
            >>> if temp:
            ...     print(f"GPU 0 temp: {temp}°C")
        """
        if not self.is_available() or gpu_index >= len(self._gpus):
            return None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpu_index < len(gpus):
                gpu = gpus[gpu_index]
                temp = self._safe_number(gpu.temperature, 0)
                return round(temp)
        except Exception as e:
            logger.debug(f"Error getting GPU temperature: {e}")

        return None

    def get_memory_used(self, gpu_index: int = 0) -> Optional[float]:
        """Get used GPU memory in GB for specified GPU.

        Args:
            gpu_index: GPU index (default: 0 for first GPU).

        Returns:
            Used GPU memory in GB (rounded), or None if unavailable.

        Example:
            >>> gpu = GPUCollector()
            >>> used = gpu.get_memory_used(0)
            >>> if used:
            ...     print(f"GPU 0 memory used: {used} GB")
        """
        if not self.is_available() or gpu_index >= len(self._gpus):
            return None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpu_index < len(gpus):
                gpu = gpus[gpu_index]
                used = self._safe_number(gpu.memoryUsed, 0)
                return round(used)
        except Exception as e:
            logger.debug(f"Error getting GPU memory used: {e}")

        return None

    def get_memory_total(self, gpu_index: int = 0) -> Optional[float]:
        """Get total GPU memory in GB for specified GPU.

        Args:
            gpu_index: GPU index (default: 0 for first GPU).

        Returns:
            Total GPU memory in GB (rounded), or None if unavailable.

        Example:
            >>> gpu = GPUCollector()
            >>> total = gpu.get_memory_total(0)
            >>> if total:
            ...     print(f"GPU 0 total memory: {total} GB")
        """
        if not self.is_available() or gpu_index >= len(self._gpus):
            return None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpu_index < len(gpus):
                gpu = gpus[gpu_index]
                total = self._safe_number(gpu.memoryTotal, 0)
                return round(total)
        except Exception as e:
            logger.debug(f"Error getting GPU memory total: {e}")

        return None

    def get_name(self, gpu_index: int = 0) -> Optional[str]:
        """Get GPU name for specified GPU.

        Args:
            gpu_index: GPU index (default: 0 for first GPU).

        Returns:
            GPU name string, or None if unavailable.

        Example:
            >>> gpu = GPUCollector()
            >>> name = gpu.get_name(0)
            >>> if name:
            ...     print(f"GPU 0: {name}")
        """
        if not self.is_available() or gpu_index >= len(self._gpus):
            return None

        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            if gpu_index < len(gpus):
                return gpus[gpu_index].name or "Unknown GPU"
        except Exception as e:
            logger.debug(f"Error getting GPU name: {e}")

        return None


class SystemInfoCollector:
    """Aggregates all system collectors.

    This class provides a unified interface for collecting all system
    information by coordinating the individual collector classes.

    Attributes:
        platform: Platform utilities instance.
        cpu: CPU collector instance.
        memory: Memory collector instance.
        disk: Disk collector instance.
        network: Network collector instance.
        gpu: GPU collector instance.

    Example:
        >>> collector = SystemInfoCollector()
        >>> data = collector.collect_all()
        >>> print(f"CPU: {data['cpu_usage']}%")
        >>> print(f"Memory: {data['memory_usage']}%")
    """

    def __init__(self):
        """Initialize all sub-collectors."""
        self.platform = PlatformUtils()
        self.cpu = CPUCollector(self.platform)
        self.memory = MemoryCollector()
        self.disk = DiskCollector()
        self.network = NetworkCollector()
        self.gpu = GPUCollector()

    def collect_all(self) -> Dict[str, Any]:
        """Collect all system metrics.

        Gathers data from all collectors and returns a comprehensive
        dictionary of system information. Values that cannot be collected
        are set to None or omitted.

        Returns:
            Dictionary containing all collected system metrics.

        Example:
            >>> collector = SystemInfoCollector()
            >>> data = collector.collect_all()
            >>> for key, value in data.items():
            ...     print(f"{key}: {value}")
        """
        data = {}

        # System info
        data["hostname"] = socket.gethostname()
        try:
            data["uptime_seconds"] = int(time.time() - psutil.boot_time())
        except Exception as e:
            logger.error(f"Error getting uptime: {e}")
            data["uptime_seconds"] = 0

        data["os"] = self.platform.get_platform().capitalize()
        data["os_version"] = self.platform.get_os_version()

        # CPU metrics
        data["cpu_model"] = self.cpu.get_model()
        data["cpu_usage"] = self.cpu.get_usage()
        data["cpu_cores"] = self.cpu.get_cores()
        data["cpu_frequency_mhz"] = self.cpu.get_frequency()

        cpu_temp = self.cpu.get_temperature()
        if cpu_temp is not None:
            data["cpu_temperature_c"] = cpu_temp

        # Memory metrics
        data["memory_usage"] = self.memory.get_usage()
        data["memory_total_gb"] = self.memory.get_total()
        data["memory_used_gb"] = self.memory.get_used()

        # Disk metrics
        data["disk_usage"] = self.disk.get_usage()
        data["disk_total_gb"] = self.disk.get_total()
        data["disk_used_gb"] = self.disk.get_used()

        # Network metrics
        from modules.utils.formatting import format_bytes

        data["network_sent_bytes"] = format_bytes(self.network.get_bytes_sent())
        data["network_recv_bytes"] = format_bytes(self.network.get_bytes_received())

        # GPU metrics (if available)
        if self.gpu.is_available():
            # Support multiple GPUs
            import GPUtil

            gpus = GPUtil.getGPUs()
            for i, gpu in enumerate(gpus):
                prefix = f"gpu{i}_"
                data[f"{prefix}name"] = self.gpu.get_name(i) or "Unknown"

                usage = self.gpu.get_usage(i)
                if usage is not None:
                    data[f"{prefix}load_percent"] = usage

                temp = self.gpu.get_temperature(i)
                if temp is not None:
                    data[f"{prefix}temperature_c"] = temp

                mem_used = self.gpu.get_memory_used(i)
                if mem_used is not None:
                    data[f"{prefix}memory_used_gb"] = mem_used

                mem_total = self.gpu.get_memory_total(i)
                if mem_total is not None:
                    data[f"{prefix}memory_total_gb"] = mem_total

        # Additional temperature sensors (if available)
        # These sensors are not very descriptive and produce a lot of empty sensors.
        # try:
        #     if hasattr(psutil, "sensors_temperatures"):
        #         temps = psutil.sensors_temperatures()
        #         for label, entries in temps.items():
        #             for entry in entries:
        #                 # Create sensor key
        #                 key = f"{label}_{entry.label}" if entry.label else label
        #                 # Clean the value (handle NaN/Inf)
        #                 if entry.current is not None:
        #                     if not (math.isnan(entry.current) or math.isinf(entry.current)):
        #                         data[key] = round(entry.current, 1)
        # except Exception as e:
        #     logger.debug(f"Error collecting temperature sensors: {e}")

        return data
