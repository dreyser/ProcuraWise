from fastapi import Request

from procurawise.shared.config import Settings


def resolve_client_ip(request: Request, settings: Settings) -> str:
    """Fase 15 (Agreement.ip): never trusts `X-Forwarded-For` unless
    `Settings.trusted_proxy_hops` says a real reverse proxy sits in front of
    this process (Azure Container Apps, Fase 27 - see the field's docstring
    in shared/config.py). With hops=0 (every environment until then),
    always returns the direct connection's address, which cannot be spoofed
    by a client-supplied header."""
    if settings.trusted_proxy_hops > 0:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            hops = [hop.strip() for hop in forwarded_for.split(",") if hop.strip()]
            index = len(hops) - settings.trusted_proxy_hops
            if 0 <= index < len(hops):
                return hops[index]
    return request.client.host if request.client else "unknown"
