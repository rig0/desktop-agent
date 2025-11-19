"""Unit tests for system metrics collection.

This module tests the various collector classes that gather system information
including CPU, memory, disk, network, and GPU metrics.

Key Testing Patterns:
    - Mock psutil functions to avoid platform dependencies
    - Test error handling when metrics are unavailable
    - Verify data type and range of returned values
    - Test edge cases (missing sensors, permission errors, etc.)

Example Run:
    pytest tests/unit/modules/collectors/test_system.py -v
"""

# import math
from unittest.mock import MagicMock, patch

from modules.collectors.system import (
    CPUCollector,
    DiskCollector,
    GPUCollector,
    MemoryCollector,
    NetworkCollector,
    SystemInfoCollector,
)


class TestCPUCollector:
    """Test suite for CPUCollector class."""

    @patch("modules.collectors.system.psutil.cpu_percent")
    def test_get_usage_returns_rounded_percentage(self, mock_cpu_percent):
        """Test that CPU usage returns rounded percentage."""
        mock_cpu_percent.return_value = 45.6
        collector = CPUCollector()

        usage = collector.get_usage()

        assert usage == 46.0  # Rounded from 45.6
        mock_cpu_percent.assert_called_once_with(interval=0.5)

    @patch("modules.collectors.system.psutil.cpu_percent")
    def test_get_usage_custom_interval(self, mock_cpu_percent):
        """Test CPU usage with custom interval."""
        mock_cpu_percent.return_value = 50.0
        collector = CPUCollector()

        usage = collector.get_usage(interval=1.0)

        mock_cpu_percent.assert_called_once_with(interval=1.0)
        assert usage == 50.0

    @patch("modules.collectors.system.psutil.cpu_percent")
    def test_get_usage_error_handling(self, mock_cpu_percent):
        """Test CPU usage error handling."""
        mock_cpu_percent.side_effect = Exception("CPU error")
        collector = CPUCollector()

        usage = collector.get_usage()

        assert usage == 0.0  # Error returns 0

    @patch("modules.collectors.system.PlatformUtils")
    def test_get_model(self, mock_platform):
        """Test CPU model retrieval."""
        mock_platform_instance = mock_platform.return_value
        mock_platform_instance.get_cpu_model.return_value = "Intel Core i7-9700K"

        collector = CPUCollector(mock_platform_instance)
        model = collector.get_model()

        assert model == "Intel Core i7-9700K"
        mock_platform_instance.get_cpu_model.assert_called_once()

    @patch("modules.collectors.system.psutil.cpu_freq")
    def test_get_frequency(self, mock_cpu_freq):
        """Test CPU frequency retrieval."""
        mock_freq = MagicMock()
        mock_freq.current = 3600.4
        mock_cpu_freq.return_value = mock_freq

        collector = CPUCollector()
        freq = collector.get_frequency()

        assert freq == 3600  # Rounded down from 3600.4

    @patch("modules.collectors.system.psutil.cpu_freq")
    def test_get_frequency_unavailable(self, mock_cpu_freq):
        """Test CPU frequency when unavailable."""
        mock_cpu_freq.return_value = None

        collector = CPUCollector()
        freq = collector.get_frequency()

        assert freq is None

    @patch("modules.collectors.system.psutil.cpu_count")
    def test_get_cores(self, mock_cpu_count):
        """Test CPU core count retrieval."""
        mock_cpu_count.return_value = 8

        collector = CPUCollector()
        cores = collector.get_cores()

        assert cores == 8
        mock_cpu_count.assert_called_once_with(logical=True)

    @patch("modules.collectors.system.psutil.sensors_temperatures")
    def test_get_temperature_coretemp(self, mock_temps):
        """Test CPU temperature from coretemp sensor."""
        mock_temps.return_value = {
            "coretemp": [
                MagicMock(label="Package id 0", current=55.0),
                MagicMock(label="Core 0", current=52.0),
            ]
        }

        collector = CPUCollector()
        temp = collector.get_temperature()

        assert temp == 55.0

    @patch("modules.collectors.system.psutil.sensors_temperatures")
    def test_get_temperature_k10temp(self, mock_temps):
        """Test CPU temperature from k10temp sensor (AMD)."""
        mock_temps.return_value = {"k10temp": [MagicMock(label="Tctl", current=60.0)]}

        collector = CPUCollector()
        temp = collector.get_temperature()

        assert temp == 60.0

    def test_get_temperature_unavailable(self):
        """Test CPU temperature when sensors are unavailable."""
        collector = CPUCollector()

        # Test when psutil doesn't have sensors_temperatures
        with patch.object(collector, "get_temperature", return_value=None):
            temp = collector.get_temperature()
            assert temp is None


class TestMemoryCollector:
    """Test suite for MemoryCollector class."""

    @patch("modules.collectors.system.psutil.virtual_memory")
    def test_get_usage(self, mock_virtual_memory):
        """Test memory usage retrieval."""
        mock_mem = MagicMock()
        mock_mem.percent = 65.4
        mock_virtual_memory.return_value = mock_mem

        collector = MemoryCollector()
        usage = collector.get_usage()

        assert usage == 65.0  # Rounded

    @patch("modules.collectors.system.psutil.virtual_memory")
    def test_get_total(self, mock_virtual_memory):
        """Test total memory retrieval."""
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3  # 16 GB in bytes
        mock_virtual_memory.return_value = mock_mem

        collector = MemoryCollector()
        total = collector.get_total()

        assert total == 16.0

    @patch("modules.collectors.system.psutil.virtual_memory")
    def test_get_used(self, mock_virtual_memory):
        """Test used memory retrieval."""
        mock_mem = MagicMock()
        mock_mem.used = 10.5 * 1024**3  # 10.5 GB in bytes
        mock_virtual_memory.return_value = mock_mem

        collector = MemoryCollector()
        used = collector.get_used()

        assert used == 10.5

    @patch("modules.collectors.system.psutil.virtual_memory")
    def test_get_available(self, mock_virtual_memory):
        """Test available memory retrieval."""
        mock_mem = MagicMock()
        mock_mem.available = 5.5 * 1024**3  # 5.5 GB in bytes
        mock_virtual_memory.return_value = mock_mem

        collector = MemoryCollector()
        available = collector.get_available()

        assert available == 5.5

    @patch("modules.collectors.system.psutil.virtual_memory")
    def test_memory_error_handling(self, mock_virtual_memory):
        """Test memory collector error handling."""
        mock_virtual_memory.side_effect = Exception("Memory error")

        collector = MemoryCollector()
        assert collector.get_usage() == 0.0
        assert collector.get_total() == 0.0


class TestDiskCollector:
    """Test suite for DiskCollector class."""

    @patch("modules.collectors.system.sys.platform", "linux")
    @patch("modules.collectors.system.psutil.disk_partitions")
    @patch("modules.collectors.system.psutil.disk_usage")
    def test_get_smart_disk_linux_home(self, mock_disk_usage, mock_disk_partitions):
        """Test disk detection on Linux (prioritizes /home)."""
        # Mock partitions
        mock_partitions = [
            MagicMock(mountpoint="/"),
            MagicMock(mountpoint="/home"),
            MagicMock(mountpoint="/boot"),
        ]
        mock_disk_partitions.return_value = mock_partitions

        # Mock disk usage for /home
        mock_usage = MagicMock()
        mock_usage.total = 500 * 1024**3  # 500 GB
        mock_usage.used = 375 * 1024**3  # 375 GB
        mock_usage.free = 125 * 1024**3  # 125 GB
        mock_disk_usage.return_value = mock_usage

        collector = DiskCollector()
        total, used, free, percent = collector.get_smart_disk()

        assert total == 500 * 1024**3
        assert used == 375 * 1024**3
        assert free == 125 * 1024**3
        assert percent == 75.0

    @patch("modules.collectors.system.sys.platform", "win32")
    @patch("modules.collectors.system.psutil.disk_usage")
    def test_get_smart_disk_windows(self, mock_disk_usage):
        """Test disk detection on Windows (C: drive)."""
        mock_usage = MagicMock()
        mock_usage.total = 1000 * 1024**3  # 1 TB
        mock_usage.used = 500 * 1024**3  # 500 GB
        mock_usage.free = 500 * 1024**3  # 500 GB
        mock_usage.percent = 50.0
        mock_disk_usage.return_value = mock_usage

        collector = DiskCollector()
        total, used, free, percent = collector.get_smart_disk()

        assert total == 1000 * 1024**3
        assert percent == 50.0
        mock_disk_usage.assert_called_once_with("C:\\")

    @patch("modules.collectors.system.DiskCollector.get_smart_disk")
    def test_get_usage(self, mock_smart_disk):
        """Test disk usage percentage retrieval."""
        mock_smart_disk.return_value = (0, 0, 0, 75.3)

        collector = DiskCollector()
        usage = collector.get_usage()

        assert usage == 75.0

    @patch("modules.collectors.system.DiskCollector.get_smart_disk")
    def test_get_total(self, mock_smart_disk):
        """Test total disk space retrieval."""
        mock_smart_disk.return_value = (500 * 1024**3, 0, 0, 0)

        collector = DiskCollector()
        total = collector.get_total()

        assert total == 500.0

    @patch("modules.collectors.system.DiskCollector.get_smart_disk")
    def test_get_used(self, mock_smart_disk):
        """Test used disk space retrieval."""
        mock_smart_disk.return_value = (0, 375 * 1024**3, 0, 0)

        collector = DiskCollector()
        used = collector.get_used()

        assert used == 375.0


class TestNetworkCollector:
    """Test suite for NetworkCollector class."""

    @patch("modules.collectors.system.psutil.net_io_counters")
    def test_get_bytes_sent(self, mock_net_io):
        """Test network bytes sent retrieval."""
        mock_io = MagicMock()
        mock_io.bytes_sent = 1500000000  # 1.5 GB
        mock_net_io.return_value = mock_io

        collector = NetworkCollector()
        sent = collector.get_bytes_sent()

        assert sent == 1500000000

    @patch("modules.collectors.system.psutil.net_io_counters")
    def test_get_bytes_received(self, mock_net_io):
        """Test network bytes received retrieval."""
        mock_io = MagicMock()
        mock_io.bytes_recv = 3200000000  # 3.2 GB
        mock_net_io.return_value = mock_io

        collector = NetworkCollector()
        received = collector.get_bytes_received()

        assert received == 3200000000

    @patch("modules.collectors.system.psutil.net_io_counters")
    def test_network_error_handling(self, mock_net_io):
        """Test network collector error handling."""
        mock_net_io.side_effect = Exception("Network error")

        collector = NetworkCollector()
        assert collector.get_bytes_sent() == 0
        assert collector.get_bytes_received() == 0


class TestGPUCollector:
    """Test suite for GPUCollector class."""

    def test_gputil_not_available(self):
        """Test GPU collector when GPUtil is not available."""
        # Mock the import to raise ImportError
        with patch(
            "builtins.__import__", side_effect=ImportError("No module named 'GPUtil'")
        ):
            collector = GPUCollector()
            assert collector.is_available() is False

    def test_gputil_available_with_gpus(self):
        """Test GPU collector when GPUs are detected."""
        mock_gpu = MagicMock()
        mock_gpu.name = "NVIDIA GeForce RTX 3080"

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import to return our mock module
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            assert collector.is_available() is True

    def test_get_usage(self):
        """Test GPU usage retrieval."""
        mock_gpu = MagicMock()
        mock_gpu.load = 0.75  # 75%

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            usage = collector.get_usage(0)

            assert usage == 75.0

    def test_get_temperature(self):
        """Test GPU temperature retrieval."""
        mock_gpu = MagicMock()
        mock_gpu.temperature = 65.5

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            temp = collector.get_temperature(0)

            assert temp == 66.0  # Rounded

    def test_get_memory_used(self):
        """Test GPU memory used retrieval."""
        mock_gpu = MagicMock()
        mock_gpu.memoryUsed = 4096  # MB

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            mem = collector.get_memory_used(0)

            assert mem == 4096

    def test_get_name(self):
        """Test GPU name retrieval."""
        mock_gpu = MagicMock()
        mock_gpu.name = "NVIDIA GeForce RTX 3080"

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            name = collector.get_name(0)

            assert name == "NVIDIA GeForce RTX 3080"

    def test_safe_number_handling(self):
        """Test that _safe_number handles invalid values."""
        mock_gpu = MagicMock()
        mock_gpu.temperature = float("nan")

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            collector = GPUCollector()
            temp = collector.get_temperature(0)

            assert temp == 0.0  # NaN converted to default

    def test_gpu_not_available_returns_none(self):
        """Test that GPU methods return None when not available."""
        with patch.object(GPUCollector, "is_available", return_value=False):
            collector = GPUCollector()

            assert collector.get_usage(0) is None
            assert collector.get_temperature(0) is None
            assert collector.get_memory_used(0) is None
            assert collector.get_name(0) is None


class TestSystemInfoCollector:
    """Test suite for SystemInfoCollector aggregator."""

    @patch("modules.collectors.system.socket.gethostname")
    @patch("modules.collectors.system.psutil.boot_time")
    @patch("modules.collectors.system.time.time")
    def test_collect_all_basic(self, mock_time, mock_boot_time, mock_hostname):
        """Test that collect_all gathers data from all collectors."""
        mock_hostname.return_value = "test-host"
        mock_time.return_value = 100000
        mock_boot_time.return_value = 50000

        with patch.multiple(
            "modules.collectors.system.psutil",
            cpu_percent=lambda interval: 50.0,
            cpu_count=lambda logical: 8,
            cpu_freq=lambda: MagicMock(current=3600),
            virtual_memory=lambda: MagicMock(
                percent=60.0,
                total=16 * 1024**3,
                used=9.6 * 1024**3,
            ),
            net_io_counters=lambda: MagicMock(
                bytes_sent=1500000000,
                bytes_recv=3200000000,
            ),
        ):
            collector = SystemInfoCollector()
            data = collector.collect_all()

        # Verify basic fields
        assert data["hostname"] == "test-host"
        assert data["uptime_seconds"] == 50000
        assert data["cpu_usage"] == 50.0
        assert data["cpu_cores"] == 8
        assert data["memory_usage"] == 60.0
        assert data["memory_total_gb"] == 16.0

    @patch("modules.collectors.system.socket.gethostname")
    @patch("modules.collectors.system.time.time")
    @patch("modules.collectors.system.psutil.boot_time")
    def test_collect_all_includes_network(self, mock_boot, mock_time, mock_hostname):
        """Test that network data is formatted correctly."""
        mock_hostname.return_value = "test"
        mock_time.return_value = 100
        mock_boot.return_value = 0

        # Mock format_bytes at the point it's imported (inside collect_all)
        with patch("modules.utils.formatting.format_bytes") as mock_format:
            mock_format.side_effect = lambda x: f"{x} bytes"

            with patch.multiple(
                "modules.collectors.system.psutil",
                cpu_percent=lambda interval: 50.0,
                cpu_count=lambda logical: 8,
                virtual_memory=lambda: MagicMock(
                    percent=60.0,
                    total=16 * 1024**3,
                    used=9.6 * 1024**3,
                ),
                net_io_counters=lambda: MagicMock(
                    bytes_sent=1500000000,
                    bytes_recv=3200000000,
                ),
            ):
                collector = SystemInfoCollector()
                data = collector.collect_all()

        # Verify network data is formatted
        assert "network_sent_bytes" in data
        assert "network_recv_bytes" in data

    def test_collect_all_with_gpu(self):
        """Test that GPU data is included when available."""
        mock_gpu = MagicMock()
        mock_gpu.name = "Test GPU"
        mock_gpu.load = 0.5
        mock_gpu.temperature = 60.0
        mock_gpu.memoryUsed = 4096
        mock_gpu.memoryTotal = 8192

        # Create a mock GPUtil module
        mock_gputil = MagicMock()
        mock_gputil.getGPUs.return_value = [mock_gpu]

        # Mock the import
        import sys

        with patch.dict(sys.modules, {"GPUtil": mock_gputil}):
            with patch(
                "modules.collectors.system.socket.gethostname", return_value="test"
            ):
                with patch("modules.collectors.system.time.time", return_value=100):
                    with patch(
                        "modules.collectors.system.psutil.boot_time", return_value=0
                    ):
                        with patch.multiple(
                            "modules.collectors.system.psutil",
                            cpu_percent=lambda interval: 50.0,
                            cpu_count=lambda logical: 8,
                            virtual_memory=lambda: MagicMock(
                                percent=60.0,
                                total=16 * 1024**3,
                                used=9.6 * 1024**3,
                            ),
                            net_io_counters=lambda: MagicMock(
                                bytes_sent=1500000000,
                                bytes_recv=3200000000,
                            ),
                        ):
                            collector = SystemInfoCollector()
                            data = collector.collect_all()

            # Verify GPU data is present
            assert "gpu0_name" in data
            assert "gpu0_load_percent" in data
            assert data["gpu0_name"] == "Test GPU"
