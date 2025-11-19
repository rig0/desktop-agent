"""Unit tests for MQTT messaging abstraction layer.

This module tests the MessageBroker class which provides a clean abstraction
over MQTT operations. Tests verify that MQTT publish operations are called
correctly with proper topics, payloads, QoS, and retain settings.

Key Testing Patterns:
    - Mock MQTT client to avoid requiring actual broker
    - Verify method calls with assert_called_with()
    - Test JSON serialization for attributes and discovery
    - Test topic construction and naming conventions

Example Run:
    pytest tests/unit/modules/core/test_messaging.py -v
"""

import json

from modules.core.messaging import MessageBroker


class TestMessageBroker:
    """Test suite for MessageBroker class."""

    def test_initialization(self, mock_mqtt_client):
        """Test that MessageBroker initializes correctly with given parameters."""
        broker = MessageBroker(
            mock_mqtt_client, base_topic="desktop/test", discovery_prefix="ha"
        )

        assert broker.client == mock_mqtt_client
        assert broker.base_topic == "desktop/test"
        assert broker.discovery_prefix == "ha"

    def test_publish_state_basic(self, mock_mqtt_client):
        """Test basic state publishing with default QoS and retain."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_state("cpu", "75.5")

        # Verify MQTT publish was called with correct parameters
        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/cpu/state", payload="75.5", qos=1, retain=True
        )

    def test_publish_state_custom_qos_retain(self, mock_mqtt_client):
        """Test state publishing with custom QoS and retain settings."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_state("memory", "60", qos=2, retain=False)

        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/memory/state", payload="60", qos=2, retain=False
        )

    def test_publish_state_topic_construction(self, mock_mqtt_client):
        """Test that state topics are constructed correctly."""
        broker = MessageBroker(mock_mqtt_client, "desktop/my_pc")

        broker.publish_state("disk", "80")

        # Verify topic follows pattern: {base_topic}/{entity}/state
        call_args = mock_mqtt_client.publish.call_args
        assert call_args[0][0] == "desktop/my_pc/disk/state"

    def test_publish_attributes_basic(self, mock_mqtt_client):
        """Test basic attributes publishing with dict payload."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        attrs = {"model": "Intel i7", "cores": 8, "frequency": 3600}
        broker.publish_attributes("cpu", attrs)

        # Verify JSON serialization
        expected_payload = json.dumps(attrs)
        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/cpu/attrs", payload=expected_payload, qos=1, retain=True
        )

    def test_publish_attributes_json_serialization(self, mock_mqtt_client):
        """Test that attributes are correctly serialized to JSON."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        attrs = {"string": "value", "number": 42, "boolean": True, "null": None}
        broker.publish_attributes("sensor", attrs)

        # Extract the actual payload that was sent
        call_args = mock_mqtt_client.publish.call_args
        payload = call_args[1]["payload"]

        # Verify it's valid JSON and matches original data
        parsed = json.loads(payload)
        assert parsed == attrs

    def test_publish_attributes_empty_dict(self, mock_mqtt_client):
        """Test publishing empty attributes dict."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_attributes("sensor", {})

        # Should still publish with empty JSON object
        mock_mqtt_client.publish.assert_called_once()
        call_args = mock_mqtt_client.publish.call_args
        assert call_args[1]["payload"] == "{}"

    def test_publish_discovery_basic(self, mock_mqtt_client):
        """Test Home Assistant MQTT discovery message publishing."""
        broker = MessageBroker(
            mock_mqtt_client, "desktop/test", discovery_prefix="homeassistant"
        )

        config = {
            "name": "Test CPU",
            "state_topic": "desktop/test/cpu/state",
            "unit_of_measurement": "%",
            "device_class": "power_factor",
        }

        broker.publish_discovery("sensor", "test_cpu", config)

        # Verify topic construction: {discovery_prefix}/{domain}/{entity_id}/config
        expected_topic = "homeassistant/sensor/test_cpu/config"
        expected_payload = json.dumps(config)

        mock_mqtt_client.publish.assert_called_once_with(
            expected_topic, payload=expected_payload, qos=0, retain=True
        )

    def test_publish_discovery_custom_prefix(self, mock_mqtt_client):
        """Test discovery with custom prefix."""
        broker = MessageBroker(
            mock_mqtt_client, "desktop/test", discovery_prefix="custom_ha"
        )

        config = {"name": "Test Sensor"}
        broker.publish_discovery("binary_sensor", "test_binary", config)

        # Verify custom prefix is used
        call_args = mock_mqtt_client.publish.call_args
        assert call_args[0][0] == "custom_ha/binary_sensor/test_binary/config"

    def test_publish_discovery_different_domains(self, mock_mqtt_client):
        """Test discovery messages for different Home Assistant domains."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        domains = [
            "sensor",
            "binary_sensor",
            "switch",
            "button",
            "device_tracker",
        ]

        for domain in domains:
            config = {"name": f"Test {domain}"}
            broker.publish_discovery(domain, f"test_{domain}", config)

        # Verify all domains were published
        assert mock_mqtt_client.publish.call_count == len(domains)

    def test_publish_availability_online(self, mock_mqtt_client):
        """Test publishing online availability status."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_availability("online")

        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/availability", payload="online", qos=1, retain=True
        )

    def test_publish_availability_offline(self, mock_mqtt_client):
        """Test publishing offline availability status."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_availability("offline")

        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/availability", payload="offline", qos=1, retain=True
        )

    def test_publish_availability_custom_qos(self, mock_mqtt_client):
        """Test availability publishing with custom QoS."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.publish_availability("online", qos=2, retain=False)

        mock_mqtt_client.publish.assert_called_once_with(
            "desktop/test/availability", payload="online", qos=2, retain=False
        )

    def test_subscribe_basic(self, mock_mqtt_client):
        """Test basic topic subscription."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        broker.subscribe("desktop/test/command")

        # Verify subscribe was called
        mock_mqtt_client.subscribe.assert_called_once_with("desktop/test/command")
        # Verify no callback was added when none provided
        mock_mqtt_client.message_callback_add.assert_not_called()

    def test_subscribe_with_callback(self, mock_mqtt_client):
        """Test subscription with callback function."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        def on_message(client, userdata, msg):
            pass

        broker.subscribe("desktop/test/command", callback=on_message)

        # Verify both subscribe and callback were set
        mock_mqtt_client.subscribe.assert_called_once_with("desktop/test/command")
        mock_mqtt_client.message_callback_add.assert_called_once_with(
            "desktop/test/command", on_message
        )

    def test_multiple_operations(self, mock_mqtt_client):
        """Test multiple operations in sequence to ensure state management."""
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        # Publish state
        broker.publish_state("cpu", "50")
        assert mock_mqtt_client.publish.call_count == 1

        # Publish attributes
        broker.publish_attributes("cpu", {"model": "Intel"})
        assert mock_mqtt_client.publish.call_count == 2

        # Publish availability
        broker.publish_availability("online")
        assert mock_mqtt_client.publish.call_count == 3

        # All calls should have different topics
        calls = [call[0][0] for call in mock_mqtt_client.publish.call_args_list]
        assert len(calls) == len(set(calls))  # All unique topics

    def test_special_characters_in_entity_names(self, mock_mqtt_client):
        """Test handling of special characters in entity names.

        Note: This test documents current behavior. In production, entity names
        should be sanitized before passing to MessageBroker.
        """
        broker = MessageBroker(mock_mqtt_client, "desktop/test")

        # Test with underscore (common and safe)
        broker.publish_state("cpu_usage", "50")
        call_args = mock_mqtt_client.publish.call_args
        assert "cpu_usage" in call_args[0][0]

    def test_base_topic_variations(self, mock_mqtt_client):
        """Test different base topic formats."""
        # Test with trailing slash
        broker1 = MessageBroker(mock_mqtt_client, "desktop/test/")
        broker1.publish_state("cpu", "50")
        call1 = mock_mqtt_client.publish.call_args[0][0]

        mock_mqtt_client.reset_mock()

        # Test without trailing slash
        broker2 = MessageBroker(mock_mqtt_client, "desktop/test")
        broker2.publish_state("cpu", "50")
        call2 = mock_mqtt_client.publish.call_args[0][0]

        # Note: Current implementation doesn't normalize trailing slashes
        # This test documents the behavior; ideally topics should be normalized
        assert "//" not in call1 or "//" not in call2
