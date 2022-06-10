import json
import time
import urllib.parse
import urllib.error

import pykka
import logging

from tornado.httpclient import HTTPClient, HTTPRequest
from mopidy.core import CoreListener, Core

logger = logging.getLogger(__name__)


class YapFrontend(pykka.ThreadingActor, CoreListener):
    def __init__(self, config, core: Core):
        super().__init__()

        self.config = config
        self.core = core
        self.spotify_token = None

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def track_playback_ended(self, tl_track, time_position):
        if self.config["spotify"] and self.config["spotify"]["enabled"] and self.config["yap"]["autoplay"]:
            tl_length = self.core.tracklist.get_length().get()
            if tl_length == 1:
                uris = self.load_more_tracks([tl_track.track.uri])
                if uris:
                    self.core.tracklist.add(uris=uris)

    def refresh_spotify_token(self):

        try:
            url = "https://auth.mopidy.com/spotify/token"
            data = {
                "client_id": self.config["spotify"]["client_id"],
                "client_secret": self.config["spotify"]["client_secret"],
                "grant_type": "client_credentials",
            }
        except Exception:
            error = {
                "message": "Could not refresh Spotify token: invalid configuration"
            }
            return error

        try:
            http_client = HTTPClient()
            request = HTTPRequest(
                url, method="POST", body=urllib.parse.urlencode(data)
            )
            response = http_client.fetch(request)

            token = json.loads(response.body)
            token["expires_at"] = time.time() + token["expires_in"]
            self.spotify_token = token

            response = {"spotify_token": token}
            return response

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            error = json.loads(e.read())
            error = {
                "message": "Could not refresh Spotify token: "
                           + error["error_description"]
            }
            return error

    def get_spotify_token(self):
        # Expired, so go get a new one
        if (
                not self.spotify_token
                or self.spotify_token["expires_at"] <= time.time()
        ):
            self.refresh_spotify_token()

        response = {"spotify_token": self.spotify_token}

        return response

    def load_more_tracks(self, seed_tracks: list):
        logger.debug("Loading a new track from Spotify")
        try:
            logger.debug("getting spotify token")
            self.get_spotify_token()
            spotify_token = self.spotify_token
            access_token = spotify_token["access_token"]
        except BaseException:
            error = "MopidyFrontend: access_token missing or invalid"
            logger.error(error)
            return False

        url = "https://api.spotify.com/v1/recommendations/"
        url = (
                url
                + "?seed_tracks="
                + (",".join(seed_tracks)).replace("spotify:track:", "")
        )
        url = url + "&limit=1"
        http_client = HTTPClient()

        try:
            http_response = http_client.fetch(
                url, headers={"Authorization": "Bearer " + access_token}
            )
            response_body = json.loads(http_response.body)

            uris = []
            for track in response_body["tracks"]:
                uris.append(track["uri"])

            return uris

        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            error = json.loads(e.read())
            error_response = {
                "message": "Could not fetch Spotify recommendations: "
                           + error["error_description"]
            }
            logger.error(
                "Could not fetch Spotify recommendations: "
                + error["error_description"]
            )
            logger.debug(error_response)
            return False
