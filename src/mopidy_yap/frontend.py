import logging
import random
import re
import time

import httpx
import pykka
from mopidy import httpclient
from mopidy.core import Core, CoreListener

logger = logging.getLogger(__name__)

SPOTIFY_TOKEN_URL = "https://auth.mopidy.com/spotify/token"
SPOTIFY_RECOMMENDATIONS_URL = "https://api.spotify.com/v1/recommendations"

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
# Last.fm sends no caching headers, so keep answers for a day.
LASTFM_CACHE_SECONDS = 24 * 60 * 60
LASTFM_CACHE_SIZE = 500
# Similar tracks, then similar artists, to look up in the library before
# giving up. Artists get a longer list: a small library is more likely to have
# something by a similar artist than one of a few exact tracks.
LASTFM_SIMILAR_TRACKS = 20
LASTFM_SIMILAR_ARTISTS = 50
# Recently played tracks are not recommended again.
RECENT_HISTORY = 50


class _RedactApiKey(logging.Filter):
    """httpx logs request URLs, and Last.fm takes the API key in the URL."""

    _pattern = re.compile(r"(api_key=)[^&\s'\"]+")

    def filter(self, record):
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._pattern.sub(r"\1***", str(a))
                if isinstance(a, str | httpx.URL)
                else a
                for a in record.args
            )
        record.msg = self._pattern.sub(r"\1***", str(record.msg))
        return True


logging.getLogger("httpx").addFilter(_RedactApiKey())


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


def _describe_http_error(error: Exception) -> str:
    """Describe an httpx error without its URL, which may hold an API key."""
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    return type(error).__name__


def _same(a: str, b: str) -> bool:
    return a.casefold().strip() == b.casefold().strip()


class YapFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core: Core):
        super().__init__()

        self.config = config
        self.core = core
        self.spotify_token = None
        self.http_client = None
        self.lastfm_cache = {}

    def on_stop(self):
        if self.http_client is not None:
            self.http_client.close()

    def _spotify_enabled(self) -> bool:
        return "spotify" in self.config and self.config["spotify"].get("enabled", False)

    def _lastfm_api_key(self) -> str | None:
        return self.config["yap"].get("lastfm_api_key") or None

    def track_playback_started(self, tl_track):
        # Queue a recommendation as soon as the last track starts, so playback
        # continues into it. get_next_tlid() honours consume, repeat, random
        # and single, so with repeat on nothing is ever added.
        if not self.config["yap"]["autoplay"]:
            return
        if not (self._spotify_enabled() or self._lastfm_api_key()):
            return
        if self.core.tracklist.get_next_tlid().get() is not None:
            return
        uris = self.recommend(tl_track.track)
        if uris:
            self.core.tracklist.add(uris=uris)

    def recommend(self, track) -> list[str]:
        """URIs to queue after `track`: from Spotify for Spotify tracks, else
        (or if Spotify has nothing) from Last.fm, searched in the library."""
        if self._spotify_enabled() and track.uri.startswith("spotify:track:"):
            uris = self.load_more_tracks([track.uri])
            if uris:
                return uris
        if self._lastfm_api_key():
            uri = self.lastfm_recommendation(track)
            if uri:
                return [uri]
        return []

    def _http(self) -> httpx.Client:
        if self.http_client is None:
            self.http_client = get_http_client(self.config)
        return self.http_client

    # Spotify

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

    # Last.fm

    def _lastfm_get(self, method: str, limit: int, **params) -> dict | None:
        """Call a Last.fm API method, cached as its terms require.

        Returns the response data, or None if Last.fm had no answer.
        """
        key = (method, *(str(v).casefold() for v in params.values()))
        cached = self.lastfm_cache.get(key)
        if cached and cached[0] > time.time():
            return cached[1]

        logger.debug("Yap: calling Last.fm %s", method)
        try:
            response = self._http().get(
                LASTFM_API_URL,
                params={
                    "method": method,
                    **params,
                    "autocorrect": 1,
                    "limit": limit,
                    "api_key": self._lastfm_api_key(),
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            logger.error(
                "Yap: could not fetch Last.fm recommendations: %s",
                _describe_http_error(e),
            )
            return None  # not cached, so the next track tries again

        if "error" in data:
            # Error 6 means Last.fm doesn't know the track or artist.
            log = logger.debug if data["error"] == 6 else logger.error
            log("Yap: Last.fm error %s: %s", data["error"], data.get("message"))
            data = None

        if len(self.lastfm_cache) >= LASTFM_CACHE_SIZE:
            self.lastfm_cache.pop(next(iter(self.lastfm_cache)))
        self.lastfm_cache[key] = (time.time() + LASTFM_CACHE_SECONDS, data)
        return data

    def lastfm_similar(self, artist: str, title: str) -> list[dict]:
        """Last.fm's similar tracks: dicts with "artist", "title" and "url"
        (the Last.fm track page)."""
        data = self._lastfm_get(
            "track.getsimilar", LASTFM_SIMILAR_TRACKS, artist=artist, track=title
        )
        return [
            {"artist": t["artist"]["name"], "title": t["name"], "url": t["url"]}
            for t in (data or {}).get("similartracks", {}).get("track", [])
        ]

    def lastfm_similar_artists(self, artist: str) -> list[dict]:
        """Last.fm's similar artists: dicts with "artist" and "url" (the
        Last.fm artist page)."""
        data = self._lastfm_get(
            "artist.getsimilar", LASTFM_SIMILAR_ARTISTS, artist=artist
        )
        return [
            {"artist": a["name"], "url": a["url"]}
            for a in (data or {}).get("similarartists", {}).get("artist", [])
        ]

    def lastfm_recommendation(self, track) -> str | None:
        """Find something Last.fm considers similar in the user's library.

        Tries Last.fm's similar tracks first. If none of them is in the
        library, falls back to any track by one of the similar artists.
        """
        if not track.name or not track.artists:
            return None  # Last.fm needs an artist and a title
        artist = sorted(a.name for a in track.artists if a.name)[0]

        excluded = {t.uri for t in self.core.tracklist.get_tracks().get()}
        excluded |= {
            ref.uri for _, ref in self.core.history.get_history().get()[:RECENT_HISTORY]
        }

        for candidate in self.lastfm_similar(artist, track.name):
            uri = self._find_in_library(
                candidate["artist"], candidate["title"], excluded
            )
            if uri:
                return self._recommended(uri, candidate["url"])

        logger.debug("Yap: no similar track in the library, trying similar artists")
        for candidate in self.lastfm_similar_artists(artist):
            uri = self._find_artist_in_library(candidate["artist"], excluded)
            if uri:
                return self._recommended(uri, candidate["url"])

        logger.debug("Yap: nothing Last.fm recommends is in the library")
        return None

    def _recommended(self, uri: str, lastfm_url: str) -> str:
        from .websocket import WebSocketYapHandler

        WebSocketYapHandler.mark_lastfm_recommendation(uri, lastfm_url)
        return uri

    def _library_tracks(self, query: dict, artist: str):
        """Tracks found by a library search whose artist matches `artist`."""
        results = self.core.library.search(query=query).get()
        for result in results or []:
            for found in result.tracks or ():
                if found.name and any(
                    _same(a.name or "", artist) for a in found.artists
                ):
                    yield found

    def _find_in_library(
        self, artist: str, title: str, excluded: set = frozenset()
    ) -> str | None:
        query = {"artist": [artist], "track_name": [title]}
        for found in self._library_tracks(query, artist):
            if (
                found.name.casefold().startswith(title.casefold())
                and found.uri not in excluded
            ):
                return found.uri
        return None

    def _find_artist_in_library(self, artist: str, excluded: set) -> str | None:
        """A random track by `artist` from the library that isn't excluded."""
        uris = {
            found.uri
            for found in self._library_tracks({"artist": [artist]}, artist)
            if found.uri not in excluded
        }
        return random.choice(sorted(uris)) if uris else None
