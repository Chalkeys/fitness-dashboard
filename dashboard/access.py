"""Who is looking: the owner, or a viewer.

The dashboard has one owner and, once it is reachable by other people, any
number of viewers. Viewers see everything and may pull every control — a
slider moved in a viewer's session changes that session's charts and nothing
else — but nothing they do reaches the files. Notes, settings and the reset
button are the owner's.

Identity arrives as a request header set by whatever sits in front of
Streamlit: Caddy's basic auth forwards the user it checked, Cloudflare Access
forwards the email it verified. Streamlit itself is bound to loopback so the
header cannot come from anywhere else. With no owner configured there is no
front, and everyone is the owner — which is how the LAN-only deployment ran.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

OWNER_ENV = "FITNESS_OWNER"

# In order of preference. Caddy's is set explicitly in the Caddyfile;
# Cloudflare Access sets its own on every request it lets through.
IDENTITY_HEADERS = ("X-Auth-User", "Cf-Access-Authenticated-User-Email")


def configured_owner() -> str:
    return os.environ.get(OWNER_ENV, "").strip()


def identity(headers: Mapping[str, str]) -> str:
    """The authenticated identity in the request, or an empty string."""
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    for name in IDENTITY_HEADERS:
        value = lowered.get(name.lower(), "").strip()
        if value:
            return value
    return ""


def is_owner(headers: Mapping[str, str], owner: str | None = None) -> bool:
    """True when the request is the owner's, or when no owner is configured.

    Comparison is case-insensitive: email addresses are, and a basic-auth
    username typed in a different case is still the same person.
    """
    owner = configured_owner() if owner is None else owner
    if not owner:
        return True
    return identity(headers).lower() == owner.lower()
