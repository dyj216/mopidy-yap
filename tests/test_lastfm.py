import logging
from unittest import mock

import httpx
import pytest
from mopidy import models

from mopidy_yap import frontend
from mopidy_yap.frontend import YapFrontend
from mopidy_yap.websocket import WebSocketYapHandler

from .conftest import catalog_track, make_config, play

API_KEY = "test-lastfm-key"


class FakeLastfm:
    """Serves track.getSimilar and artist.getSimilar with fixed answers."""

    def __init__(self, similar=(), similar_artists=(), error=None, status=200):
        self.similar = similar
        self.similar_artists = similar_artists
        self.error = error
        self.status = status
        self.requests = []

    def methods(self):
        return [r.url.params["method"] for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, text="oops")
        if self.error:
            return httpx.Response(200, json={"error": self.error, "message": "Nope"})
        if request.url.params["method"] == "artist.getsimilar":
            return httpx.Response(
                200,
                json={
                    "similarartists": {
                        "artist": [
                            {"name": a, "url": f"https://www.last.fm/music/{a}"}
                            for a in self.similar_artists
                        ]
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "similartracks": {
                    "track": [
                        {
                            "name": title,
                            "artist": {"name": artist},
                            "url": f"https://www.last.fm/music/{artist}/_/{title}",
                        }
                        for artist, title in self.similar
                    ]
                }
            },
        )


def make_yap(core_proxy, fake, **yap_config):
    config = make_config(lastfm_api_key=API_KEY, **yap_config)
    yap = YapFrontend(config, core_proxy)
    yap.http_client = httpx.Client(transport=httpx.MockTransport(fake))
    return yap


def queued(core_proxy):
    return [t.uri for t in core_proxy.tracklist.get_tracks().get()]


def start_last_track(core_proxy, yap, uri):
    [tl_track] = core_proxy.tracklist.add(uris=[uri]).get()
    play(core_proxy, tl_track)
    yap.track_playback_started(tl_track=tl_track)


def test_queues_the_first_similar_track_found_in_the_library(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    take_on_me = catalog_track("a-ha", "Take on Me")
    fake = FakeLastfm(similar=[("Not In", "The Library"), ("a-ha", "Take on Me")])
    yap = make_yap(core_proxy, fake)

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [seed, take_on_me]
    [request] = fake.requests
    assert str(request.url).startswith(frontend.LASTFM_API_URL)
    assert dict(request.url.params) == {
        "method": "track.getsimilar",
        "artist": "Rick Astley",
        "track": "Never Gonna Give You Up",
        "autocorrect": "1",
        "limit": str(frontend.LASTFM_SIMILAR_TRACKS),
        "api_key": API_KEY,
        "format": "json",
    }


def test_records_last_fm_page_of_recommended_track(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    take_on_me = catalog_track("a-ha", "Take on Me")
    yap = make_yap(core_proxy, FakeLastfm(similar=[("a-ha", "Take on Me")]))

    start_last_track(core_proxy, yap, seed)

    assert WebSocketYapHandler.lastfm_tracks == {
        take_on_me: "https://www.last.fm/music/a-ha/_/Take on Me"
    }


def test_library_match_ignores_case_and_allows_title_suffixes():
    def track(artist, title, uri):
        return models.Track(uri=uri, name=title, artists=[models.Artist(name=artist)])

    core = mock.Mock()
    core.library.search.return_value.get.return_value = [
        models.SearchResult(
            uri="x:search",
            tracks=[
                track("Someone Else", "Take on Me", "x:cover"),
                track("A-HA", "take on me - 2015 Remaster", "x:remaster"),
            ],
        )
    ]
    yap = YapFrontend(make_config(lastfm_api_key=API_KEY), core)

    assert yap._find_in_library("a-ha", "Take on Me") == "x:remaster"
    core.library.search.assert_called_once_with(
        query={"artist": ["a-ha"], "track_name": ["Take on Me"]}
    )


def test_skips_tracks_already_queued(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    take_on_me = catalog_track("a-ha", "Take on Me")
    wham = catalog_track("Wham!", "Last Christmas")
    core_proxy.tracklist.add(uris=[take_on_me]).get()
    yap = make_yap(
        core_proxy,
        FakeLastfm(similar=[("a-ha", "Take on Me"), ("Wham!", "Last Christmas")]),
    )

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [take_on_me, seed, wham]


def test_adds_nothing_when_no_similar_track_is_in_the_library(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    yap = make_yap(core_proxy, FakeLastfm(similar=[("Not In", "The Library")]))

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [seed]


def test_needs_artist_and_title_to_ask_last_fm(core_proxy):
    fake = FakeLastfm(similar=[("a-ha", "Take on Me")])
    yap = make_yap(core_proxy, fake)

    start_last_track(core_proxy, yap, "dummy:untagged")  # no artist

    assert fake.requests == []
    assert queued(core_proxy) == ["dummy:untagged"]


def test_caches_last_fm_answers(core_proxy):
    fake = FakeLastfm(similar=[("a-ha", "Take on Me")])
    yap = make_yap(core_proxy, fake)

    yap.lastfm_similar("Rick Astley", "Never Gonna Give You Up")
    yap.lastfm_similar("rick astley", "never gonna give you up")

    assert len(fake.requests) == 1


def test_unknown_track_is_cached_and_not_logged_as_error(core_proxy, caplog):
    fake = FakeLastfm(error=6)
    yap = make_yap(core_proxy, fake)

    with caplog.at_level(logging.ERROR):
        assert yap.lastfm_similar("Nobody", "Nothing") == []
        assert yap.lastfm_similar("Nobody", "Nothing") == []

    assert len(fake.requests) == 1
    assert caplog.text == ""


def test_http_errors_are_logged_without_the_api_key(core_proxy, caplog):
    fake = FakeLastfm(status=500)
    yap = make_yap(core_proxy, fake)

    with caplog.at_level(logging.DEBUG):
        assert yap.lastfm_similar("Rick Astley", "Never Gonna Give You Up") == []
        yap.lastfm_similar("Rick Astley", "Never Gonna Give You Up")

    assert "Yap: could not fetch Last.fm recommendations: HTTP 500" in caplog.text
    assert API_KEY not in caplog.text
    assert len(fake.requests) == 2  # failures are not cached


def test_httpx_request_logs_hide_the_api_key(caplog):
    url = httpx.URL(frontend.LASTFM_API_URL, params={"api_key": API_KEY, "a": "b"})

    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info("HTTP Request: %s %s", "GET", url)

    assert API_KEY not in caplog.text
    assert "api_key=***" in caplog.text


def test_falls_back_to_last_fm_when_spotify_has_nothing(core_proxy):
    seed = catalog_track(
        "Rick Astley", "Never Gonna Give You Up", scheme="spotify:track"
    )
    take_on_me = catalog_track("a-ha", "Take on Me")
    config = make_config(lastfm_api_key=API_KEY)
    config["spotify"] = {"enabled": True, "client_id": "x", "client_secret": "y"}
    yap = YapFrontend(config, core_proxy)
    yap.http_client = httpx.Client(
        transport=httpx.MockTransport(FakeLastfm(similar=[("a-ha", "Take on Me")]))
    )

    with mock.patch.object(yap, "load_more_tracks", return_value=[]) as spotify:
        start_last_track(core_proxy, yap, seed)

    spotify.assert_called_once_with([seed])
    assert queued(core_proxy) == [seed, take_on_me]


def test_autoplay_off_disables_last_fm_too(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    catalog_track("a-ha", "Take on Me")
    fake = FakeLastfm(similar=[("a-ha", "Take on Me")])
    yap = make_yap(core_proxy, fake, autoplay=False)

    start_last_track(core_proxy, yap, seed)

    assert fake.requests == []
    assert queued(core_proxy) == [seed]


@pytest.mark.parametrize("key", [None, ""])
def test_without_spotify_or_last_fm_autoplay_does_nothing(core_proxy, key):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    yap = YapFrontend(make_config(lastfm_api_key=key), core_proxy)

    with mock.patch.object(yap, "recommend") as recommend:
        start_last_track(core_proxy, yap, seed)

    recommend.assert_not_called()
    assert queued(core_proxy) == [seed]


# Fallback to similar artists


def test_prefers_similar_tracks_over_similar_artists(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    take_on_me = catalog_track("a-ha", "Take on Me")
    catalog_track("Wham!", "Last Christmas")
    fake = FakeLastfm(similar=[("a-ha", "Take on Me")], similar_artists=["Wham!"])
    yap = make_yap(core_proxy, fake)

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [seed, take_on_me]
    assert fake.methods() == ["track.getsimilar"]


def test_falls_back_to_a_track_by_a_similar_artist(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    wham = catalog_track("Wham!", "Last Christmas")
    fake = FakeLastfm(
        similar=[("Not In", "The Library")],
        similar_artists=["Also Not In Library", "Wham!"],
    )
    yap = make_yap(core_proxy, fake)

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [seed, wham]
    assert fake.methods() == ["track.getsimilar", "artist.getsimilar"]
    assert dict(fake.requests[1].url.params) == {
        "method": "artist.getsimilar",
        "artist": "Rick Astley",
        "autocorrect": "1",
        "limit": str(frontend.LASTFM_SIMILAR_ARTISTS),
        "api_key": API_KEY,
        "format": "json",
    }
    # Linked to the artist's Last.fm page, as the terms require.
    assert WebSocketYapHandler.lastfm_tracks == {
        wham: "https://www.last.fm/music/Wham!"
    }


def test_similar_artist_fallback_skips_queued_tracks(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    wham = catalog_track("Wham!", "Last Christmas")
    toto = catalog_track("Toto", "Africa")
    core_proxy.tracklist.add(uris=[wham]).get()
    yap = make_yap(core_proxy, FakeLastfm(similar_artists=["Wham!", "Toto"]))

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy) == [wham, seed, toto]


def test_similar_artist_fallback_picks_any_of_their_tracks(core_proxy):
    seed = catalog_track("Rick Astley", "Never Gonna Give You Up")
    wham = {
        catalog_track("Wham!", "Last Christmas"),
        catalog_track("Wham!", "Freedom"),
    }
    yap = make_yap(core_proxy, FakeLastfm(similar_artists=["Wham!"]))

    start_last_track(core_proxy, yap, seed)

    assert queued(core_proxy)[1] in wham


def test_similar_artists_are_cached(core_proxy):
    fake = FakeLastfm(similar_artists=["Wham!"])
    yap = make_yap(core_proxy, fake)

    yap.lastfm_similar_artists("Rick Astley")
    yap.lastfm_similar_artists("RICK ASTLEY")

    assert len(fake.requests) == 1


def test_library_match_skips_excluded_versions():
    def track(title, uri):
        return models.Track(uri=uri, name=title, artists=[models.Artist(name="a-ha")])

    core = mock.Mock()
    core.library.search.return_value.get.return_value = [
        models.SearchResult(
            uri="x:search",
            tracks=[
                track("Take on Me", "x:original"),
                track("Take on Me - Remaster", "x:remaster"),
            ],
        )
    ]
    yap = YapFrontend(make_config(lastfm_api_key=API_KEY), core)

    assert yap._find_in_library("a-ha", "Take on Me", {"x:original"}) == "x:remaster"
