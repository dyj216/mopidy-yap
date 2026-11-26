import logging
import urllib.parse
from unittest import mock

import httpx
import pytest

from mopidy_yap import frontend
from mopidy_yap.frontend import YapFrontend

from .conftest import make_config, play


def spotify_config(**yap):
    config = make_config(**yap)
    config["spotify"] = {
        "enabled": True,
        "client_id": "the-id",
        "client_secret": "the-secret",
    }
    return config


class FakeSpotify:
    """Serves the Spotify token and recommendations endpoints."""

    def __init__(self, recommendations_status=200):
        self.requests = []
        self.recommendations_status = recommendations_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == frontend.SPOTIFY_TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "the-token", "expires_in": 3600}
            )
        if request.url.path == "/v1/recommendations":
            if self.recommendations_status != 200:
                return httpx.Response(self.recommendations_status, json={})
            return httpx.Response(
                200, json={"tracks": [{"uri": "spotify:track:recommended"}]}
            )
        return httpx.Response(404)


@pytest.fixture
def fake_spotify():
    return FakeSpotify()


@pytest.fixture
def yap(fake_spotify):
    yap = YapFrontend(spotify_config(), core=None)
    yap.http_client = httpx.Client(transport=httpx.MockTransport(fake_spotify))
    return yap


def test_http_client_identifies_yap_and_uses_mopidy_proxy_config():
    config = make_config()
    config["proxy"] = {
        "scheme": "http",
        "hostname": "proxy.example",
        "port": 3128,
        "username": None,
        "password": None,
    }

    with mock.patch.object(frontend.httpx, "Client") as client:
        frontend.get_http_client(config)

    kwargs = client.call_args.kwargs
    assert kwargs["proxy"] == "http://proxy.example:3128"
    assert kwargs["headers"]["User-Agent"].startswith("Mopidy-Yap/")
    assert " Mopidy/" in kwargs["headers"]["User-Agent"]


def test_http_client_without_proxy_config_connects_directly():
    with mock.patch.object(frontend.httpx, "Client") as client:
        frontend.get_http_client(make_config())

    assert client.call_args.kwargs["proxy"] is None


def test_load_more_tracks_returns_recommended_uris(yap, fake_spotify):
    uris = yap.load_more_tracks(["spotify:track:seed1", "spotify:track:seed2"])

    assert uris == ["spotify:track:recommended"]
    token_request, recommendations_request = fake_spotify.requests
    assert urllib.parse.parse_qs(token_request.content.decode()) == {
        "client_id": ["the-id"],
        "client_secret": ["the-secret"],
        "grant_type": ["client_credentials"],
    }
    assert recommendations_request.url.params["seed_tracks"] == "seed1,seed2"
    assert recommendations_request.url.params["limit"] == "1"
    assert recommendations_request.headers["Authorization"] == "Bearer the-token"


def test_load_more_tracks_reuses_token_until_it_expires(yap, fake_spotify):
    yap.load_more_tracks(["spotify:track:a"])
    yap.load_more_tracks(["spotify:track:b"])

    token_requests = [
        r for r in fake_spotify.requests if str(r.url) == frontend.SPOTIFY_TOKEN_URL
    ]
    assert len(token_requests) == 1


def test_load_more_tracks_logs_and_returns_nothing_on_http_error(yap, caplog):
    yap.http_client = httpx.Client(
        transport=httpx.MockTransport(FakeSpotify(recommendations_status=404))
    )

    with caplog.at_level(logging.ERROR):
        uris = yap.load_more_tracks(["spotify:track:a"])

    assert uris == []
    assert "Yap: could not fetch Spotify recommendations" in caplog.text


def start_autoplay_scenario(core_proxy, config, uris, play_index, **options):
    """Queue `uris`, set tracklist options, start the track at `play_index` and
    deliver track_playback_started to Yap. Returns the queued URIs afterwards
    and the mocked load_more_tracks."""
    for option, value in options.items():
        getattr(core_proxy.tracklist, f"set_{option}")(value).get()
    tl_tracks = core_proxy.tracklist.add(uris=uris).get()
    play(core_proxy, tl_tracks[play_index])
    yap = YapFrontend(config, core_proxy)

    with mock.patch.object(
        yap, "load_more_tracks", return_value=["spotify:track:recommended"]
    ) as load:
        yap.track_playback_started(tl_track=tl_tracks[play_index])

    queued = [t.track.uri for t in core_proxy.tracklist.get_tl_tracks().get()]
    return queued, load


A, B, REC = "spotify:track:a", "spotify:track:b", "spotify:track:recommended"


@pytest.mark.parametrize("consume", [False, True])
def test_autoplay_queues_recommendation_when_last_track_starts(core_proxy, consume):
    queued, load = start_autoplay_scenario(
        core_proxy, spotify_config(), [A, B], play_index=1, consume=consume
    )

    load.assert_called_once_with([B])
    assert queued == [A, B, REC]


def test_autoplay_waits_while_more_tracks_are_queued(core_proxy):
    queued, load = start_autoplay_scenario(
        core_proxy, spotify_config(), [A, B], play_index=0
    )

    load.assert_not_called()
    assert queued == [A, B]


def test_autoplay_adds_nothing_with_repeat_on(core_proxy):
    queued, load = start_autoplay_scenario(
        core_proxy, spotify_config(), [A, B], play_index=1, repeat=True
    )

    load.assert_not_called()
    assert queued == [A, B]


def test_autoplay_needs_a_spotify_track_to_seed_from(core_proxy):
    queued, load = start_autoplay_scenario(
        core_proxy, spotify_config(), ["dummy:local"], play_index=0
    )

    load.assert_not_called()
    assert queued == ["dummy:local"]


@pytest.mark.parametrize(
    "config",
    [spotify_config(autoplay=False), make_config()],  # make_config: no Spotify
    ids=["autoplay off", "no Mopidy-Spotify"],
)
def test_autoplay_disabled(core_proxy, config):
    queued, load = start_autoplay_scenario(core_proxy, config, [A], play_index=0)

    load.assert_not_called()
    assert queued == [A]
