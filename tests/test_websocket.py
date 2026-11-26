import json
import types

import pykka
import tornado.web
from tornado.httpclient import HTTPClientError, HTTPRequest
from tornado.testing import AsyncHTTPTestCase, gen_test
from tornado.websocket import websocket_connect

from mopidy_yap import yap_factory
from mopidy_yap.websocket import WebSocketYapHandler

from .conftest import add_tracks, make_config, play, start_core, track_names


class YapWebSocketTest(AsyncHTTPTestCase):
    def setUp(self):
        WebSocketYapHandler.users.clear()
        WebSocketYapHandler.current_track = ""
        WebSocketYapHandler.votes_to_skip.clear()
        WebSocketYapHandler.votes_to_delete.clear()
        WebSocketYapHandler.votes_to_top.clear()
        self.config = make_config(votes_to_skip=2, votes_to_delete=2, votes_to_top=1)
        self.config["http"]["allowed_origins"] = ["friend.example:3000"]
        self.core = start_core(self.config)
        super().setUp()

    def tearDown(self):
        super().tearDown()
        pykka.ActorRegistry.stop_all()

    def get_app(self):
        return tornado.web.Application(yap_factory(self.config, self.core))

    async def connect(self, origin=None):
        headers = {"Origin": origin} if origin else {}
        ws = await websocket_connect(
            HTTPRequest(self.get_url("/ws").replace("http", "ws"), headers=headers)
        )
        connected = json.loads(await ws.read_message())
        assert connected["action"] == "connect"
        return ws

    async def vote(self, ws, action, *, expect, **payload):
        """Send a vote and return the first message containing `expect`.

        Messages broadcast for other clients' votes may arrive first.
        """
        ws.write_message(json.dumps({"action": action, "payload": payload}))
        while True:
            message = json.loads(await ws.read_message())
            if expect in message["payload"]["message"]:
                return message

    def tlid(self, name):
        return next(
            t.tlid
            for t in self.core.tracklist.get_tl_tracks().get()
            if t.track.name == name
        )

    # Origin check

    @gen_test
    async def test_accepts_page_served_by_the_same_host(self):
        await self.connect(origin=f"http://127.0.0.1:{self.get_http_port()}")

    @gen_test
    async def test_accepts_origin_from_http_allowed_origins(self):
        await self.connect(origin="http://friend.example:3000")

    @gen_test
    async def test_rejects_other_origins(self):
        for origin in ["http://evil.example", "null"]:
            with self.assertRaises(HTTPClientError) as ctx:
                await self.connect(origin=origin)
            assert ctx.exception.code == 403

    @gen_test
    async def test_accepts_clients_without_origin_header(self):
        await self.connect()

    # Voting

    @gen_test
    async def test_skip_needs_the_configured_number_of_votes(self):
        tl_tracks = add_tracks(self.core, "a", "b")
        play(self.core, tl_tracks[0])
        alice, bob = await self.connect(), await self.connect()

        await self.vote(
            alice,
            "vote_to_skip",
            track_name="a",
            expect="You have voted to skip this song. (1 more votes needed)",
        )
        assert self.core.playback.get_current_tlid().get() == tl_tracks[0].tlid

        await self.vote(bob, "vote_to_skip", track_name="a", expect="Skipping...")
        self.core.stream_changed(uri=tl_tracks[1].track.uri).get()  # as audio would
        assert self.core.playback.get_current_tlid().get() == tl_tracks[1].tlid

    @gen_test
    async def test_voting_twice_does_not_count(self):
        add_tracks(self.core, "a", "b")
        alice = await self.connect()
        tlid = self.tlid("b")

        await self.vote(alice, "vote_to_delete", track_id=tlid, expect="voted")
        reply = await self.vote(
            alice, "vote_to_delete", track_id=tlid, expect="already voted"
        )

        assert reply["payload"]["deletes"] == {str(tlid): 1}
        assert track_names(self.core) == ["a", "b"]

    @gen_test
    async def test_delete_removes_track_after_enough_votes(self):
        add_tracks(self.core, "a", "b", "c")
        alice, bob = await self.connect(), await self.connect()
        tlid = self.tlid("b")

        await self.vote(alice, "vote_to_delete", track_id=tlid, expect="voted")
        await self.vote(bob, "vote_to_delete", track_id=tlid, expect="b is removed.")

        assert track_names(self.core) == ["a", "c"]

    # Move to top

    @gen_test
    async def test_move_to_top_when_nothing_is_playing_moves_track_first(self):
        add_tracks(self.core, "a", "b", "c")
        alice = await self.connect()

        await self.vote(alice, "vote_to_top", track_id=self.tlid("c"), expect="moved")

        assert track_names(self.core) == ["c", "a", "b"]

    @gen_test
    async def test_move_to_top_puts_later_track_after_current(self):
        tl_tracks = add_tracks(self.core, "a", "b", "c", "d", "e")
        play(self.core, tl_tracks[2])
        alice = await self.connect()

        await self.vote(alice, "vote_to_top", track_id=self.tlid("e"), expect="moved")

        assert track_names(self.core) == ["a", "b", "c", "e", "d"]
        assert self.core.tracklist.get_next_tlid().get() == self.tlid("e")

    @gen_test
    async def test_move_to_top_puts_earlier_track_after_current(self):
        tl_tracks = add_tracks(self.core, "a", "b", "c", "d", "e")
        play(self.core, tl_tracks[2])
        alice = await self.connect()

        await self.vote(alice, "vote_to_top", track_id=self.tlid("a"), expect="moved")

        assert track_names(self.core) == ["b", "c", "a", "d", "e"]
        assert self.core.tracklist.get_next_tlid().get() == self.tlid("a")


def test_remove_expired_ids_keeps_votes_for_tracks_still_queued():
    core = start_core(make_config())
    try:
        tl_tracks = add_tracks(core, "a", "b", "c")
        a, _, c = (t.tlid for t in tl_tracks)
        removed = 999
        votes = {c: {"alice"}, a: {"bob"}, removed: {"carol"}}
        handler = types.SimpleNamespace(core=core)

        WebSocketYapHandler.remove_expired_ids(handler, votes)

        assert votes == {c: {"alice"}, a: {"bob"}}
    finally:
        pykka.ActorRegistry.stop_all()
