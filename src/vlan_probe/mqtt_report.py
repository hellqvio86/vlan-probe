"""MQTT reporting for vlan_probe."""

import hashlib
import json
import re
import socket
from typing import Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

from .config import MQTTConfig

Message = Tuple[str, str]


class MQTTPublishError(Exception):
    """Raised when MQTT delivery fails (connect or publish)."""


def slugify(text: str) -> str:
    """Convert arbitrary text into an MQTT-safe topic segment."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug or "target"


def build_topic_prefix(topic_prefix: str, hostname: Optional[str] = None) -> str:
    """Build the topic prefix as ``<topic_prefix>/<hostname>``."""
    host = hostname or socket.gethostname()
    return f"{topic_prefix}/{slugify(host)}"


def _unique_target_slug(vlan: str, target: str, seen: Dict[Tuple[str, str], bool], raw_name: str) -> Tuple[str, str]:
    """Resolve slug collisions by appending a short hash of the raw name."""
    key = (vlan, target)
    if key not in seen:
        seen[key] = True
        return vlan, target
    suffix = hashlib.sha1(raw_name.encode()).hexdigest()[:8]
    return vlan, f"{target}-{suffix}"


def build_messages(
    results: List[Dict[str, object]],
    summary: Dict[str, object],
    mqtt_config: MQTTConfig,
    hostname: Optional[str] = None,
) -> List[Message]:
    """Build ``(topic, payload)`` pairs: one summary plus one per target."""
    prefix = build_topic_prefix(mqtt_config.topic_prefix, hostname)
    messages: List[Message] = [(f"{prefix}/summary", json.dumps(summary))]
    seen: Dict[Tuple[str, str], bool] = {}
    for res in results:
        vlan = slugify(str(res.get("target_vlan", "")))
        target = slugify(str(res.get("target_name", "")))
        vlan, target = _unique_target_slug(vlan, target, seen, str(res.get("target_name", "")))
        topic = f"{prefix}/targets/{vlan}/{target}"
        messages.append((topic, json.dumps(res)))
    return messages


def publish_to_mqtt(mqtt_config: MQTTConfig, messages: List[Message]) -> None:
    """
    Publish messages to the MQTT broker.

    Raises:
        MQTTPublishError: On connect or publish failure.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if mqtt_config.tls:
        client.tls_set(ca_certs=mqtt_config.ca_certs)
        if mqtt_config.insecure:
            client.tls_insecure_set(True)
    if mqtt_config.username:
        client.username_pw_set(mqtt_config.username, mqtt_config.password)
    socket.setdefaulttimeout(mqtt_config.connect_timeout)
    try:
        client.connect(mqtt_config.host, mqtt_config.port, keepalive=60)
    except Exception as e:
        raise MQTTPublishError(f"MQTT connect to {mqtt_config.host}:{mqtt_config.port} failed: {e}") from e
    finally:
        socket.setdefaulttimeout(None)

    client.loop_start()
    try:
        for topic, payload in messages:
            info = client.publish(topic, payload, qos=mqtt_config.qos, retain=mqtt_config.retain)
            try:
                info.wait_for_publish(mqtt_config.connect_timeout)
            except Exception as e:
                raise MQTTPublishError(f"MQTT publish to '{topic}' failed: {e}") from e
    finally:
        client.loop_stop()
        client.disconnect()
