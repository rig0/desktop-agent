"""Data formatting and transformation utilities.

This module provides reusable formatting functions for converting
raw system data into human-readable strings suitable for display
in Home Assistant or API responses.
"""

from typing import Optional


def format_bytes(bytes_value: float, decimal_places: int = 1) -> str:
    """Format bytes into human-readable size.

    Converts a byte value into a human-readable string with appropriate
    units (B, KB, MB, GB, TB, PB).

    Args:
        bytes_value: Size in bytes to format.
        decimal_places: Number of decimal places to display (default: 1).

    Returns:
        Formatted string (e.g., "1.5 GB", "512.0 MB").

    Example:
        >>> format_bytes(1536000000)
        '1.5 GB'
        >>> format_bytes(524288000)
        '524.3 MB'
        >>> format_bytes(1024)
        '1.0 KB'
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.{decimal_places}f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.{decimal_places}f} PB"


def format_percentage(value: float, decimal_places: int = 1) -> str:
    """Format a value as a percentage string.

    Args:
        value: Percentage value (0-100).
        decimal_places: Number of decimal places to display (default: 1).

    Returns:
        Formatted percentage string (e.g., "75.5%").

    Example:
        >>> format_percentage(75.543)
        '75.5%'
        >>> format_percentage(100.0, decimal_places=0)
        '100%'
    """
    return f"{value:.{decimal_places}f}%"


def format_temperature(celsius: float, unit: str = "C") -> str:
    """Format temperature with unit.

    Converts and formats temperature value with the specified unit.
    Supports Celsius (C) and Fahrenheit (F).

    Args:
        celsius: Temperature in Celsius.
        unit: Temperature unit ("C" or "F", default: "C").

    Returns:
        Formatted temperature string (e.g., "45.2°C", "113.4°F").

    Example:
        >>> format_temperature(45.2)
        '45.2°C'
        >>> format_temperature(0, unit="F")
        '32.0°F'
        >>> format_temperature(100, unit="F")
        '212.0°F'
    """
    if unit.upper() == "F":
        fahrenheit = (celsius * 9/5) + 32
        return f"{fahrenheit:.1f}°F"
    return f"{celsius:.1f}°C"


def format_frequency(hz: float) -> str:
    """Format frequency in GHz.

    Converts a frequency from Hz to GHz and formats it.

    Args:
        hz: Frequency in Hz.

    Returns:
        Formatted frequency string (e.g., "3.60 GHz").

    Example:
        >>> format_frequency(3600000000)
        '3.60 GHz'
        >>> format_frequency(2400000000)
        '2.40 GHz'
    """
    ghz = hz / 1_000_000_000
    return f"{ghz:.2f} GHz"


def sanitize_topic(name: str) -> str:
    """Sanitize a string for use in MQTT topics.

    Replaces spaces and special characters with underscores, converts
    to lowercase, and removes problematic characters for MQTT topics.

    Args:
        name: String to sanitize.

    Returns:
        Sanitized string safe for MQTT topics.

    Example:
        >>> sanitize_topic("My PC Name")
        'my_pc_name'
        >>> sanitize_topic("Test/Device")
        'test_device'
        >>> sanitize_topic("CPU #1 Temp")
        'cpu_1_temp'
    """
    # Convert to lowercase
    name = name.lower()

    # Replace spaces with underscores
    name = name.replace(" ", "_")

    # Remove or replace problematic characters for MQTT topics
    # MQTT wildcards and special characters: +, #, /, $, \, ?
    for char in ["/", "+", "#", "$", "\\", "?"]:
        name = name.replace(char, "_")

    # Remove multiple consecutive underscores
    while "__" in name:
        name = name.replace("__", "_")

    # Remove leading and trailing underscores
    return name.strip("_")
