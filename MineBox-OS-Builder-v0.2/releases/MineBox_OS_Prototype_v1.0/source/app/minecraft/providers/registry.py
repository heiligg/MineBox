from __future__ import annotations

from typing import Any

from minecraft.providers.base import BaseProvider, SupportLevel
from minecraft.providers.fabric import FabricProvider
from minecraft.providers.forge import ForgeProvider
from minecraft.providers.paper import PaperProvider
from minecraft.providers.vanilla import VanillaProvider

# NeoForge remains available via existing downloads/launcher paths; map to Forge-like experimental.
_PROVIDERS: dict[str, BaseProvider] = {
    "vanilla": VanillaProvider(),
    "paper": PaperProvider(),
    "fabric": FabricProvider(),
    "forge": ForgeProvider(),
}


def get_provider(name: str) -> BaseProvider:
    key = (name or "vanilla").strip().lower()
    if key == "neoforge":
        # Preserve NeoForge installs; treat as experimental like Forge.
        provider = ForgeProvider()
        provider.name = "neoforge"
        return provider
    if key not in _PROVIDERS:
        raise KeyError(f"Unknown Minecraft provider: {name}")
    return _PROVIDERS[key]


def list_providers() -> list[BaseProvider]:
    providers = list(_PROVIDERS.values())
    # Surface neoforge as experimental sibling without deleting launcher support.
    neo = ForgeProvider()
    neo.name = "neoforge"
    providers.append(neo)
    return providers


def provider_capabilities() -> list[dict[str, Any]]:
    return [provider.to_public_dict() for provider in list_providers()]


__all__ = [
    "SupportLevel",
    "get_provider",
    "list_providers",
    "provider_capabilities",
]
