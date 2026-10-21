from .base import MediaKind, StockError, StockFile, StockItem, StockLicense, StockProvider
from .museums import AICProvider, MetProvider
from .pexels import PexelsProvider

PROVIDERS = {"pexels": PexelsProvider, "met": MetProvider, "aic": AICProvider}
MUSEUMS = ("met", "aic")  # public-domain still images only


def get_stock_provider(name: str) -> StockProvider:
    if name not in PROVIDERS:
        raise StockError(f"unknown stock provider {name!r}; available: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]()


def parse_ref(ref: str, default_kind: MediaKind = "video") -> tuple[str, MediaKind, str]:
    """``pexels:video:123``, ``pexels:photo:123`` or ``pexels:123`` -> (provider, kind, id)."""
    parts = ref.split(":")
    if len(parts) == 2:
        return parts[0], default_kind, parts[1]
    if len(parts) == 3 and parts[1] in ("video", "photo"):
        return parts[0], parts[1], parts[2]  # type: ignore[return-value]
    raise StockError(f"bad stock reference {ref!r}; use provider:video:ID or provider:photo:ID")


__all__ = ["AICProvider", "MUSEUMS", "MediaKind", "MetProvider", "PROVIDERS", "PexelsProvider", "StockError", "StockFile", "StockItem", "StockLicense",
           "StockProvider", "get_stock_provider", "parse_ref"]
