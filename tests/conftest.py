import pykka
import pytest
from mopidy import backend, core, models

try:
    from mopidy.types import PlaybackState  # Mopidy 4
except ImportError:
    from mopidy.core import PlaybackState  # Mopidy 3


# Tracks with artist and title, findable through library search.
CATALOG: dict[str, models.Track] = {}


def catalog_track(artist, title, scheme="dummy"):
    """Add a tagged track to the dummy library and return its URI."""
    uri = f"{scheme}:{artist}/{title}".replace(" ", "_")
    CATALOG[uri] = models.Track(
        uri=uri, name=title, artists=[models.Artist(name=artist)], length=1000
    )
    return uri


class DummyLibrary(backend.LibraryProvider):
    def lookup(self, uri):
        if uri in CATALOG:
            return [CATALOG[uri]]
        return [models.Track(uri=uri, name=uri.removeprefix("dummy:"), length=1000)]

    def search(self, query=None, uris=None, exact=False):
        artists = [a.casefold() for a in query.get("artist", [])]
        titles = [t.casefold() for t in query.get("track_name", [])]
        return models.SearchResult(
            uri="dummy:search",
            tracks=[
                t
                for t in CATALOG.values()
                if any(a.name.casefold() in artists for a in t.artists)
                and t.name.casefold() in titles
            ],
        )


class DummyPlayback(backend.PlaybackProvider):
    """Playback that always succeeds, without GStreamer."""

    def prepare_change(self):
        pass

    def change_track(self, track):
        return True

    def play(self):
        return True

    def pause(self):
        return True

    def resume(self):
        return True

    def seek(self, time_position):
        return True

    def stop(self):
        return True

    def get_time_position(self):
        return 0


class DummyBackend(pykka.ThreadingActor, backend.Backend):
    uri_schemes = ("dummy", "spotify")

    def __init__(self, config, audio):
        super().__init__()
        self.library = DummyLibrary(backend=self)
        self.playback = DummyPlayback(audio=audio, backend=self)


def make_config(**yap):
    return {
        "core": {"max_tracklist_length": 10000},
        "http": {"allowed_origins": []},
        "proxy": {
            "scheme": None,
            "hostname": None,
            "port": None,
            "username": None,
            "password": None,
        },
        "yap": {
            "enabled": True,
            "votes_to_skip": 3,
            "votes_to_delete": 3,
            "votes_to_top": 3,
            "pause_button": False,
            "autoplay": True,
            "lastfm_api_key": None,
            **yap,
        },
    }


@pytest.fixture(autouse=True)
def reset_shared_state():
    from mopidy_yap.websocket import WebSocketYapHandler

    CATALOG.clear()
    WebSocketYapHandler.lastfm_tracks.clear()
    WebSocketYapHandler.io_loop = None
    yield


@pytest.fixture
def config():
    return make_config()


def start_core(config):
    """A real Mopidy core with a dummy backend, as the extension guide suggests.

    Stop it with pykka.ActorRegistry.stop_all().
    """
    dummy = DummyBackend.start(config=config, audio=None).proxy()
    return core.Core.start(config=config, backends=[dummy], audio=None).proxy()


@pytest.fixture
def core_proxy(config):
    yield start_core(config)
    pykka.ActorRegistry.stop_all()


def add_tracks(core_proxy, *names):
    return core_proxy.tracklist.add(uris=[f"dummy:{n}" for n in names]).get()


def play(core_proxy, tl_track):
    """Start playing a track. Without audio, core waits for the stream to
    change before the track becomes current, so send that event like audio
    would."""
    core_proxy.playback.play(tlid=tl_track.tlid).get()
    core_proxy.stream_changed(uri=tl_track.track.uri).get()
    core_proxy.state_changed(
        old_state=PlaybackState.STOPPED,
        new_state=PlaybackState.PLAYING,
        target_state=None,
    ).get()


def track_names(core_proxy):
    return [t.track.name for t in core_proxy.tracklist.get_tl_tracks().get()]
