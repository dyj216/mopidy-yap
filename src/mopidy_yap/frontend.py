import logging
import time

import httpx
import pykka
from mopidy import httpclient
from mopidy.core import Core, CoreListener

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://auth.mopidy.com/spotify/token"
SPOTIFY_RECOMMENDATIONS_URL = "https://api.spotify.com/v1/recommendations"


def get_http_client(config) -> httpx.Client:
    """HTTP client that respects Mopidy's proxy config and identifies Yap."""
    from . import Extension, __version__

    return httpx.Client(
        proxy=httpclient.format_proxy(config["proxy"]),
        headers={
            "User-Agent": httpclient.format_user_agent(
                f"{Extension.dist_name}/{__version__}"
            )
        },
        timeout=10,
    )


class YapFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core: Core):
        super().__init__()

        self.config = config
        self.core = core
        self.spotify_token = None
        self.http_client = None

    def on_stop(self):
        if self.http_client is not None:
            self.http_client.close()

    def _autoplay_enabled(self) -> bool:
        return (
            "spotify" in self.config
            and self.config["spotify"].get("enabled", False)
            and self.config["yap"]["autoplay"]
        )

    def track_playback_started(self, tl_track):
        # Queue a recommendation as soon as the last track starts, so playback
        # continues into it. get_next_tlid() honours consume, repeat, random
        # and single, so with repeat on nothing is ever added.
        if not self._autoplay_enabled():
            return
        if not tl_track.track.uri.startswith("spotify:track:"):
            return  # Spotify can only recommend based on Spotify tracks
        if self.core.tracklist.get_next_tlid().get() is not None:
            return
        uris = self.load_more_tracks([tl_track.track.uri])
        if uris:
            self.core.tracklist.add(uris=uris)

    def _http(self) -> httpx.Client:
        if self.http_client is None:
            self.http_client = get_http_client(self.config)
        return self.http_client

    def _spotify_access_token(self) -> str:
        """Return a valid Spotify access token, fetching a new one if needed."""
        if self.spotify_token and self.spotify_token["expires_at"] > time.time():
            return self.spotify_token["access_token"]

        response = self._http().post(
            SPOTIFY_TOKEN_URL,
            data={
                "client_id": self.config["spotify"]["client_id"],
                "client_secret": self.config["spotify"]["client_secret"],
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        token = response.json()
        token["expires_at"] = time.time() + token["expires_in"]
        self.spotify_token = token
        return token["access_token"]

    def load_more_tracks(self, seed_tracks: list[str]) -> list[str]:
        """Return URIs of Spotify tracks recommended for the seed tracks."""
        logger.debug("Yap: loading a recommended track from Spotify")
        try:
            access_token = self._spotify_access_token()
            response = self._http().get(
                SPOTIFY_RECOMMENDATIONS_URL,
                params={
                    "seed_tracks": ",".join(
                        uri.removeprefix("spotify:track:") for uri in seed_tracks
                    ),
                    "limit": 1,
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return [track["uri"] for track in response.json()["tracks"]]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            logger.error("Yap: could not fetch Spotify recommendations: %s", e)
            return []
