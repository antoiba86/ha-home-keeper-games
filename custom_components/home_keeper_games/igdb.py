"""The IGDB client: the Twitch token and the HTTP reads for ``catalog.py``.

* The keys are a Twitch client ID and client secret in the config entry data.
  The client reads them at each call, so a change in the options flow needs no
  reload. The secret goes only in the body of the token request, never in a URL,
  so no error text or log line has it.
* The app token stays in memory. The client gets a new one before it expires,
  when the keys change, and once after a 401 from IGDB.
* At most 4 requests each second: an async lock makes the next request wait.
* Each request has a timeout of 10 seconds.
* 3 environment variables can replace the URLs (``igdb_urls``). Only the test
  setups set them, to point at a fake server.

Each failure is a :class:`LibraryError` with a translation key:
``igdb_not_configured``, ``invalid_igdb_auth`` or ``igdb_unavailable``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, TypedDict

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import catalog
from .const import (
    COVER_MAX_BYTES,
    IGDB_API_URL,
    IGDB_API_URL_ENV,
    IGDB_IMAGES_URL,
    IGDB_IMAGES_URL_ENV,
    IGDB_MIN_INTERVAL_S,
    IGDB_TIMEOUT_S,
    IGDB_TOKEN_MARGIN_S,
    IGDB_TOKEN_URL,
    IGDB_TOKEN_URL_ENV,
    PANEL_VERSION,
    USER_AGENT,
)
from .models import LibraryError

_LOGGER = logging.getLogger(__name__)

#: ``(client_id, client_secret)``, or None when the keys are not set.
Keys = tuple[str, str] | None


class IgdbUrls(TypedDict, total=False):
    """The URL overrides of the client."""

    api_url: str
    token_url: str
    images_url: str


def igdb_urls(env: Mapping[str, str]) -> IgdbUrls:
    """The URL overrides that *env* sets. An empty variable keeps the default."""
    out: IgdbUrls = {}
    if url := env.get(IGDB_API_URL_ENV, "").strip().rstrip("/"):
        out["api_url"] = url
    if url := env.get(IGDB_TOKEN_URL_ENV, "").strip():
        out["token_url"] = url
    if url := env.get(IGDB_IMAGES_URL_ENV, "").strip().rstrip("/"):
        out["images_url"] = url
    return out


class IgdbClient:
    """Reads games and covers from IGDB with the keys of the config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        keys: Callable[[], Keys],
        *,
        api_url: str = IGDB_API_URL,
        token_url: str = IGDB_TOKEN_URL,
        images_url: str = IGDB_IMAGES_URL,
        min_interval: float = IGDB_MIN_INTERVAL_S,
    ) -> None:
        self._hass = hass
        self._keys = keys
        self._api = api_url
        self._token_url = token_url
        self.images_url = images_url
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last = 0.0
        # (keys, token, monotonic expiry)
        self._token: tuple[tuple[str, str], str, float] | None = None

    @property
    def configured(self) -> bool:
        """Whether the config entry has the keys."""
        return self._keys() is not None

    def _keys_or_error(self) -> tuple[str, str]:
        keys = self._keys()
        if keys is None:
            raise LibraryError("igdb_not_configured")
        return keys

    async def _wait_turn(self) -> None:
        delay = self._last + self._min_interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.monotonic()

    def _timeout(self) -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=IGDB_TIMEOUT_S)

    async def async_check_keys(self, client_id: str, client_secret: str) -> None:
        """Get a token for the keys.

        Raise ``invalid_igdb_auth`` or ``igdb_unavailable``.
        """
        await self._new_token((client_id, client_secret))

    async def _new_token(self, keys: tuple[str, str]) -> str:
        session = async_get_clientsession(self._hass)
        form = {
            "client_id": keys[0],
            "client_secret": keys[1],
            "grant_type": "client_credentials",
        }
        try:
            async with session.post(
                self._token_url, data=form, timeout=self._timeout()
            ) as response:
                if response.status in (400, 401, 403):
                    raise LibraryError("invalid_igdb_auth")
                if response.status >= 300:
                    raise LibraryError("igdb_unavailable")
                body = await response.json(content_type=None)
        except LibraryError:
            raise
        except (TimeoutError, aiohttp.ClientError, ValueError) as err:
            _LOGGER.debug("The Twitch token request failed: %s", type(err).__name__)
            raise LibraryError("igdb_unavailable") from err
        token = body.get("access_token") if isinstance(body, dict) else None
        expires = body.get("expires_in") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise LibraryError("igdb_unavailable")
        life = expires if isinstance(expires, int) and expires > 0 else 3600
        self._token = (keys, token, time.monotonic() + life)
        return token

    async def _token_for(self, keys: tuple[str, str]) -> str:
        if self._token is not None:
            held, token, expiry = self._token
            if held == keys and expiry - time.monotonic() > IGDB_TOKEN_MARGIN_S:
                return token
        return await self._new_token(keys)

    async def _query(self, endpoint: str, body: str) -> Any:
        """POST an Apicalypse *body* to *endpoint*. Return the JSON reply."""
        keys = self._keys_or_error()
        session = async_get_clientsession(self._hass)
        async with self._lock:
            for attempt in (1, 2):
                token = await self._token_for(keys)
                await self._wait_turn()
                headers = {
                    "Client-ID": keys[0],
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT.format(version=PANEL_VERSION),
                }
                try:
                    async with session.post(
                        f"{self._api}/{endpoint}",
                        data=body.encode(),
                        headers=headers,
                        timeout=self._timeout(),
                    ) as response:
                        if response.status == 401 and attempt == 1:
                            self._token = None
                            continue
                        if response.status in (401, 403):
                            raise LibraryError("invalid_igdb_auth")
                        if response.status >= 300:
                            raise LibraryError("igdb_unavailable")
                        return await response.json(content_type=None)
                except LibraryError:
                    raise
                except (TimeoutError, aiohttp.ClientError, ValueError) as err:
                    _LOGGER.debug("The IGDB request failed: %s", type(err).__name__)
                    raise LibraryError("igdb_unavailable") from err
        raise LibraryError("igdb_unavailable")  # pragma: no cover

    async def async_search(
        self, text: str, platform: str | None, limit: int
    ) -> list[dict[str, Any]]:
        """The game records whose title matches *text*, best first."""
        self._keys_or_error()
        if not catalog.clean_query(text):
            return []
        found = await self._query("games", catalog.search_body(text, platform, limit))
        return catalog.records(found)

    async def async_game(self, igdb_id: int) -> dict[str, Any] | None:
        """The game record with the id *igdb_id*, or None."""
        found = catalog.records(await self._query("games", catalog.game_body(igdb_id)))
        return found[0] if found else None

    async def async_cover(self, image: str) -> bytes | None:
        """The bytes of a cover image, or None on any failure.

        A cover is extra: a failure never stops the add of the game.
        """
        session = async_get_clientsession(self._hass)
        url = catalog.cover_url(self.images_url, image)
        try:
            async with session.get(url, timeout=self._timeout()) as response:
                if response.status != 200:
                    return None
                data = await response.content.read(COVER_MAX_BYTES + 1)
        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.debug("The IGDB cover download failed: %s", type(err).__name__)
            return None
        return data if 0 < len(data) <= COVER_MAX_BYTES else None
