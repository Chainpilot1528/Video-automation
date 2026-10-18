"""HTTPS helpers: always verify certificates, using certifi's CA bundle.

python.org builds of Python on macOS have no trusted root store until the user
runs "Install Certificates.command"; bundling certifi avoids that step without
ever disabling verification.
"""

from __future__ import annotations

import ssl
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_context() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # fall back to the platform store
        return ssl.create_default_context()


def urlopen(req, timeout: float | None = None):
    """urllib.request.urlopen with verified TLS."""
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
