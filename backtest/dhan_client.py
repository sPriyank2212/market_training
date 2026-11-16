"""Thin, READ-ONLY Dhan Data API wrapper.

Security properties (enforced in code, not by convention):
  * Credentials only from env vars (loaded from .env via python-dotenv); never hardcoded.
  * The token is masked in anything printed/logged.
  * Any URL containing "/orders" raises BEFORE a network call.
  * Only POSTs to allow-listed path prefixes (config: dhan.allowed_path_prefixes).
  * 401/403 prints the exact expiry message.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml
from dotenv import load_dotenv

TOKEN_EXPIRED_MSG = "Token expired — generate a new one at web.dhan.co → DhanHQ Trading APIs."
ROOT = Path(__file__).parent


class ForbiddenEndpointError(RuntimeError):
    """Raised before any network call if a URL is not a permitted read-only data endpoint."""


class TokenExpiredError(RuntimeError):
    """Raised on HTTP 401/403 from Dhan."""


def mask_token(token: str | None) -> str:
    if not token:
        return "<unset>"
    return f"{token[:4]}...{token[-4:]}" if len(token) > 12 else "****"


DEFAULT_VERSION = "v1"


def active_version() -> str:
    """Strategy version under test. Select with env BACKTEST_VERSION (default v1)."""
    return os.environ.get("BACKTEST_VERSION", DEFAULT_VERSION)


def version_dir(version: str | None = None) -> Path:
    return ROOT / "versions" / (version or active_version())


def results_dir(cfg: dict) -> Path:
    d = version_dir(cfg["version"]) / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_config(version: str | None = None) -> dict:
    """Load versions/<version>/config.yaml. Each strategy version is a frozen, self-contained config;
    candles/cache are shared across versions."""
    v = version or active_version()
    path = version_dir(v) / "config.yaml"
    if not path.exists():
        raise FileNotFoundError(f"No config for strategy version {v!r}: {path}")
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("version") != v:
        raise ValueError(f"{path} declares version {cfg.get('version')!r}, expected {v!r}")
    return cfg


def assert_url_allowed(url: str, allowed_prefixes: list[str]) -> None:
    """Hard guard. Runs before every request."""
    if "/orders" in url.lower():
        raise ForbiddenEndpointError(f"Refusing URL containing /orders: {url}")
    path = urlparse(url).path
    # strip the version segment (/v2) so prefixes are written as "/charts/"
    rel = path[3:] if path.startswith("/v2") else path
    if not any(rel.startswith(p) for p in allowed_prefixes):
        raise ForbiddenEndpointError(f"Path not on read-only allow-list: {path}")


class DhanClient:
    def __init__(self, config: dict | None = None):
        load_dotenv(ROOT / ".env")
        self.cfg = (config or load_config())["dhan"]
        self.client_id = os.environ.get("DHAN_CLIENT_ID", "")
        self._token = os.environ.get("DHAN_ACCESS_TOKEN", "")

    def __repr__(self) -> str:
        return f"DhanClient(client_id={self.client_id!r}, token={mask_token(self._token)})"

    def _headers(self) -> dict:
        if not self.client_id or not self._token:
            raise RuntimeError("DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set — fill backtest/.env")
        return {
            "access-token": self._token,
            "client-id": self.client_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def post(self, path: str, body: dict) -> dict:
        """POST to a read-only data endpoint, e.g. post('/charts/intraday', {...})."""
        url = self.cfg["base_url"].rstrip("/") + path
        assert_url_allowed(url, self.cfg["allowed_path_prefixes"])  # before any network I/O
        last_exc: Exception | None = None
        for attempt in range(1, self.cfg["max_retries"] + 1):
            try:
                r = requests.post(url, json=body, headers=self._headers(),
                                  timeout=self.cfg["timeout_seconds"])
            except requests.RequestException as e:
                last_exc = e
            else:
                if r.status_code in (401, 403):
                    print(TOKEN_EXPIRED_MSG)
                    raise TokenExpiredError(TOKEN_EXPIRED_MSG)
                if r.status_code == 429 or r.status_code >= 500:
                    last_exc = RuntimeError(f"HTTP {r.status_code}")
                elif r.status_code >= 400:
                    # Surface Dhan's own error message (response bodies never contain the token).
                    raise RuntimeError(f"HTTP {r.status_code} from {path}: {r.text[:300]}")
                else:
                    return r.json()
            time.sleep(self.cfg["backoff_seconds"] * attempt)
        raise RuntimeError(f"Dhan request failed after retries: {last_exc}")
