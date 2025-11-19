"""Pytest configuration and global fixtures.

This module provides fixtures and configuration that are available to all tests.
Fixtures defined here are automatically discovered by pytest and can be used
by any test function by including them as parameters.

Common Fixtures:
    - mock_mqtt_client: Mocked MQTT client for testing without broker
    - mock_config: Mocked configuration values
    - temp_config_file: Temporary config file for testing
    - sample_system_data: Sample system metrics data

Example:
    def test_something(mock_mqtt_client):
        # mock_mqtt_client is automatically injected
        result = some_function(mock_mqtt_client)
        assert result is not None
"""

import configparser
from unittest.mock import MagicMock, Mock

import pytest


@pytest.fixture
def mock_mqtt_client():
    """Provide a mocked MQTT client for testing.

    This fixture creates a fully mocked paho-mqtt client that can be used
    in tests without requiring an actual MQTT broker connection.

    Returns:
        MagicMock: Mocked MQTT client with common methods stubbed

    Example:
        def test_publish(mock_mqtt_client):
            broker = MessageBroker(mock_mqtt_client, "test/topic")
            broker.publish_state("sensor", "value")
            mock_mqtt_client.publish.assert_called_once()
    """
    client = MagicMock()
    # Configure return values for common methods
    client.connect.return_value = 0
    client.publish.return_value = MagicMock(rc=0)
    client.subscribe.return_value = (0, 1)
    client.loop_start.return_value = None
    client.loop_stop.return_value = None
    client.disconnect.return_value = None
    return client


@pytest.fixture
def mock_config_values():
    """Provide mock configuration values for testing.

    Returns:
        dict: Dictionary of configuration values

    Example:
        def test_with_config(mock_config_values):
            assert mock_config_values['MQTT_BROKER'] == 'test.mqtt.broker'
    """
    return {
        "device_id": "test_device",
        "device_name": "Test Device",
        "base_topic": "desktop/test_device",
        "discovery_prefix": "homeassistant",
        "MQTT_BROKER": "test.mqtt.broker",
        "MQTT_PORT": 1883,
        "MQTT_USER": "test_user",
        "MQTT_PASS": "test_pass",
        "PUBLISH_INT": 5,
        "API_MOD": True,
        "API_PORT": 5555,
        "API_AUTH_TOKEN": "test_token_12345",
        "COMMANDS_MOD": True,
        "GAME_MONITOR": False,
        "MEDIA_MONITOR": False,
        "UPDATES_MOD": False,
    }


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config.ini file for testing.

    Args:
        tmp_path: pytest fixture providing temporary directory

    Returns:
        Path: Path to temporary config file

    Example:
        def test_load_config(temp_config_file):
            config = load_config(temp_config_file)
            assert config is not None
    """
    config = configparser.ConfigParser()

    config["device"] = {"name": "Test Device", "interval": "5"}

    config["mqtt"] = {
        "broker": "test.broker.local",
        "port": "1883",
        "username": "testuser",
        "password": "testpass",
        "max_connection_retries": "5",
        "min_reconnect_delay": "1",
        "max_reconnect_delay": "30",
        "connection_timeout": "10",
    }

    config["modules"] = {
        "api": "true",
        "commands": "true",
        "media_monitor": "false",
        "game_monitor": "false",
        "updates": "false",
    }

    config["api"] = {"port": "5555", "auth_token": "test_api_token_123"}

    config_file = tmp_path / "config.ini"
    with open(config_file, "w") as f:
        config.write(f)

    return config_file


@pytest.fixture
def sample_system_data():
    """Provide sample system metrics data for testing.

    Returns:
        dict: Sample system information dictionary

    Example:
        def test_format_system_data(sample_system_data):
            formatted = format_data(sample_system_data)
            assert formatted['cpu_usage'] == 45.0
    """
    return {
        "hostname": "test-hostname",
        "uptime_seconds": 86400,
        "os": "Linux",
        "os_version": "Ubuntu 22.04",
        "cpu_model": "Intel Core i7-9700K",
        "cpu_usage": 45.0,
        "cpu_cores": 8,
        "cpu_frequency_mhz": 3600,
        "cpu_temperature_c": 55.0,
        "memory_usage": 60.0,
        "memory_total_gb": 16.0,
        "memory_used_gb": 9.6,
        "disk_usage": 75.0,
        "disk_total_gb": 500.0,
        "disk_used_gb": 375.0,
        "network_sent_bytes": "1.5 GB",
        "network_recv_bytes": "3.2 GB",
    }


@pytest.fixture
def mock_psutil(monkeypatch):
    """Mock psutil functions for testing without real system access.

    This fixture patches psutil functions to return predictable values,
    allowing tests to run consistently across different systems.

    Args:
        monkeypatch: pytest fixture for patching

    Example:
        def test_cpu_usage(mock_psutil):
            collector = CPUCollector()
            usage = collector.get_usage()
            assert usage == 50.0  # From mock
    """
    # Mock CPU metrics
    monkeypatch.setattr("psutil.cpu_percent", lambda interval: 50.0)
    monkeypatch.setattr("psutil.cpu_count", lambda logical: 8)

    # Mock memory metrics
    class MockVirtualMemory:
        percent = 60.0
        total = 16 * 1024**3  # 16 GB
        used = 9.6 * 1024**3  # 9.6 GB
        available = 6.4 * 1024**3  # 6.4 GB

    monkeypatch.setattr("psutil.virtual_memory", lambda: MockVirtualMemory())

    # Mock network metrics
    class MockNetIO:
        bytes_sent = 1500000000  # 1.5 GB
        bytes_recv = 3200000000  # 3.2 GB

    monkeypatch.setattr("psutil.net_io_counters", lambda: MockNetIO())

    return Mock()


@pytest.fixture
def mock_subprocess_run(monkeypatch):
    """Mock subprocess.run for testing command execution.

    Returns:
        Mock: Mock object that can be configured per test

    Example:
        def test_command_success(mock_subprocess_run):
            mock_subprocess_run.return_value.returncode = 0
            mock_subprocess_run.return_value.stdout = "Success"
            result = run_command("echo test")
            assert result['success'] is True
    """
    mock = Mock()
    mock.return_value.returncode = 0
    mock.return_value.stdout = ""
    mock.return_value.stderr = ""
    monkeypatch.setattr("subprocess.run", mock)
    return mock


# Pytest hooks for custom behavior


def pytest_configure(config):
    """Configure pytest with custom settings.

    This hook runs before test collection begins and can be used to
    register custom markers, configure plugins, etc.
    """
    # Set environment variables for config that gets loaded at module import time
    import os

    os.environ["DA_NON_INTERACTIVE"] = "1"
    os.environ["DA_MQTT_BROKER"] = "localhost"
    os.environ["DA_MQTT_PORT"] = "1883"
    os.environ["DA_MQTT_USER"] = "test_user"
    os.environ["DA_MQTT_PASS"] = "test_pass"
    os.environ["DA_DEVICE_NAME"] = "test_device"
    os.environ["DA_API_AUTH_TOKEN"] = "test_token_12345"  # For API module validation

    # Add custom markers (already defined in pytest.ini, but can add more here)
    pass


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add automatic markers.

    This hook runs after test collection and can be used to automatically
    add markers to tests based on their location or name.

    Args:
        config: pytest config object
        items: list of collected test items
    """
    for item in items:
        # Auto-mark all tests in tests/unit as unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Auto-mark integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
