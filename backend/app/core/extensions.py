from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any, Protocol

from fastapi import APIRouter

logger = logging.getLogger("flowsentry.extensions")


class ConnectorAdapter(Protocol):
    """Service Provider Interface (SPI) for automation platform connectors."""

    provider_id: str
    display_name: str
    supports_polling: bool


class NotificationChannelHandler(Protocol):
    """SPI for outbound alert notification channels."""

    channel_id: str
    display_name: str


class AuthProviderHook(Protocol):
    """SPI for enterprise or custom authentication providers (e.g., SAML/OIDC)."""

    mode_id: str
    verify_token: Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class BuiltinConnectorSpec:
    provider_id: str
    display_name: str
    supports_polling: bool


@dataclass(frozen=True)
class BuiltinNotificationChannelSpec:
    channel_id: str
    display_name: str


@dataclass
class ExtensionRegistry:
    """Central registry for Community Core providers and optional external plugins."""

    connectors: dict[str, ConnectorAdapter] = field(default_factory=dict)
    notification_channels: dict[str, NotificationChannelHandler] = field(default_factory=dict)
    auth_providers: dict[str, AuthProviderHook] = field(default_factory=dict)
    extra_routers: list[APIRouter] = field(default_factory=list)
    _plugins_loaded: bool = False

    def register_connector(self, adapter: ConnectorAdapter) -> None:
        self.connectors[adapter.provider_id] = adapter

    def register_notification_channel(self, handler: NotificationChannelHandler) -> None:
        self.notification_channels[handler.channel_id] = handler

    def register_auth_provider(self, hook: AuthProviderHook) -> None:
        self.auth_providers[hook.mode_id] = hook

    def register_router(self, router: APIRouter) -> None:
        self.extra_routers.append(router)

    def load_entrypoint_extensions(self, group: str = "flowsentry.plugins") -> list[str]:
        """Discover optional external plugin distributions via Python entry points."""
        if self._plugins_loaded:
            return []
        self._plugins_loaded = True
        loaded: list[str] = []
        for ep in entry_points(group=group):
            try:
                registrar = ep.load()
                registrar(self)
                loaded.append(ep.name)
            except Exception as exc:
                logger.warning("Failed loading FlowSentry extension '%s': %s", ep.name, exc)
        return loaded


extension_registry = ExtensionRegistry()

# Built-in Community Core connectors & notification channels
extension_registry.register_connector(
    BuiltinConnectorSpec(provider_id="n8n", display_name="n8n (REST API + Webhooks)", supports_polling=True)
)
extension_registry.register_connector(
    BuiltinConnectorSpec(
        provider_id="custom_webhook",
        display_name="Custom Webhook / Direct API",
        supports_polling=False,
    )
)
extension_registry.register_notification_channel(
    BuiltinNotificationChannelSpec(channel_id="slack", display_name="Slack Incoming Webhook")
)
extension_registry.register_notification_channel(
    BuiltinNotificationChannelSpec(channel_id="email", display_name="Email (SMTP / SMTPS)")
)
