"""TraceLock messaging gateway for OSINT operators.

Platforms (v1): Telegram long-poll, HTTP webhook, email file queue.
WhatsApp: webhook / Cloud API hook points (credentials not baked in).
"""

from tracelock.gateway.runner import GatewayConfig, run_gateway

__all__ = ["GatewayConfig", "run_gateway"]
