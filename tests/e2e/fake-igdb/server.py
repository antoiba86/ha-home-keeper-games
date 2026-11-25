"""A fake Twitch token endpoint and a fake IGDB for the e2e stack.

Home Assistant reaches it at ``http://igdb:8080`` through the
``HOME_KEEPER_GAMES_IGDB_*_URL`` variables of ``compose.yml``. It knows only the
few games below, so the tests and the screenshots get the same results each run.

- ``POST /oauth2/token``: a token for any keys.
- ``POST /v4/games``: an Apicalypse body. ``search "<text>"`` gives the games with
  the text in the name. ``where id = <n>`` gives that game.
- ``GET /images/t_cover_big/<image_id>.jpg``: 1 cover image for every id.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

COVER = Path(__file__).with_name("cover.jpg")
GAMES = [
    {
        "id": 1001,
        "name": "Hades",
        "summary": "Battle out of the Underworld in this rogue-like dungeon crawler.",
        "first_release_date": 1600387200,
        "genres": [{"name": "Role-playing (RPG)"}, {"name": "Indie"}],
        "franchises": [{"name": "Hades"}],
        "cover": {"image_id": "e2ehades"},
        "platforms": [167, 48, 130, 169, 49, 6],
    },
    {
        "id": 1002,
        "name": "Hades II",
        "summary": "Battle beyond the Underworld.",
        "first_release_date": 1758758400,
        "genres": [{"name": "Role-playing (RPG)"}],
        "franchises": [{"name": "Hades"}],
        "cover": {"image_id": "e2ehades2"},
        "platforms": [508, 130, 6],
    },
    {
        "id": 1003,
        "name": "Hades' Star",
        "first_release_date": 1493856000,
        "platforms": [6],
    },
]


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value: object) -> None:
        self._send(200, json.dumps(value).encode())

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", "replace")
        if self.path == "/oauth2/token":
            token = {"access_token": "e2e", "expires_in": 5000000}
            self._json({**token, "token_type": "bearer"})
        elif self.path == "/v4/games":
            self._json(_games(body))
        else:
            self._send(404, b"[]")

    def do_GET(self) -> None:
        cover = re.fullmatch(r"/images/t_cover_big/[a-z0-9]+\.jpg", self.path)
        if cover and COVER.is_file():
            self._send(200, COVER.read_bytes(), "image/jpeg")
        else:
            self._send(404, b"")

    def log_message(self, format: str, *args: object) -> None:
        return


def _games(body: str) -> list[dict]:
    if found := re.match(r'search "([^"]*)";', body):
        text = found.group(1).casefold()
        return [g for g in GAMES if text in g["name"].casefold()]
    if found := re.search(r"where id = (\d+);", body):
        return [g for g in GAMES if g["id"] == int(found.group(1))]
    return []


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
