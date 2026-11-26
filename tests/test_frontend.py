import logging
import urllib.parse
from unittest import mock

import httpx
import pytest

from mopidy_yap import frontend
from mopidy_yap.frontend import YapFrontend

from .conftest import add_tracks, make_config, play


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


@pytest.mark.parametrize(
    ("config", "expect_autoplay"),
    [
        (spotify_config(), True),
        (spotify_config(autoplay=False), False),
        (make_config(), False),  # no Mopidy-Spotify
    ],
)
def test_autoplay_adds_recommendation_when_queue_runs_out(
    core_proxy, config, expect_autoplay
):
    [tl_track] = add_tracks(core_proxy, "last")
    play(core_proxy, tl_track)
    yap = YapFrontend(config, core_proxy)

    with mock.patch.object(
        yap, "load_more_tracks", return_value=["dummy:recommended"]
    ) as load:
        yap.track_playback_ended(tl_track=tl_track, time_position=1000)

    uris = [t.track.uri for t in core_proxy.tracklist.get_tl_tracks().get()]
    if expect_autoplay:
        load.assert_called_once_with(["dummy:last"])
        assert uris == ["dummy:last", "dummy:recommended"]
    else:
        load.assert_not_called()
        assert uris == ["dummy:last"]
