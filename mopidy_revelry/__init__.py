import logging
import os

import tornado.web
import tornado.websocket
import tornado.escape
from mopidy import config, ext

__version__ = "0.1.0"

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = 'Mopidy-Revelry'
    ext_name = 'revelry'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        schema['votes_to_skip'] = config.Integer(minimum=1)
        schema['votes_to_delete'] = config.Integer(minimum=1)
        schema['votes_to_top'] = config.Integer(minimum=1)
        schema['pause_button'] = config.Boolean()
        return schema

    def validate_environment(self):
        pass

    def setup(self, registry):
        registry.add('http:static', {
            'name': self.ext_name,
            'path': os.path.join(os.path.dirname(__file__), 'static'),
        })
        registry.add('http:app', {
            'name': self.ext_name,
            'factory': revelry_factory,
        })


class WebSocketRevelryHandler(tornado.websocket.WebSocketHandler):
    users = set()
    current_track = ""
    votes_to_skip = set()
    votes_to_delete = {}
    votes_to_top = {}

    def initialize(self, core, configuration):
        self.core = core
        self.required_votes_to_skip = configuration["revelry"]["votes_to_skip"]
        self.required_votes_to_delete = configuration["revelry"]["votes_to_delete"]
        self.required_votes_to_top = configuration["revelry"]["votes_to_top"]
        self.pause_button = configuration["revelry"]["pause_button"]

    def get_compression_options(self):
        # Non-None enables compression with default options.
        return {}

    def check_origin(self, origin: str) -> bool:
        return True

    def open(self):
        WebSocketRevelryHandler.users.add(self)
        self.write_message({
            "action": "connect",
            "payload": {
                "message": "Connected!",
                "votes": len(WebSocketRevelryHandler.votes_to_skip),
                "tops": {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_top.items()},
                "deletes": {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_delete.items()},
                "pause_button": self.pause_button,
            },
        })
        logger.debug(f"New ws client. Current number of ws clients: {len(WebSocketRevelryHandler.users)}")

    def on_close(self):
        WebSocketRevelryHandler.users.remove(self)

    @classmethod
    def update_current_track(cls, track_name):
        logger.debug("updating current track name")
        cls.current_track = track_name

    @classmethod
    def send_updates(cls, ego, update):
        logger.debug("sending message to %d waiters", len(cls.users))
        for user in cls.users.difference({ego}):
            try:
                user.write_message(update)
            except:
                logger.error("Error sending message", exc_info=True)

    def on_message(self, message):
        logger.debug("got message %r", message)
        parsed = tornado.escape.json_decode(message)

        if parsed["action"] == "vote_to_skip":
            self._handle_skip(parsed)
        elif parsed["action"] == "vote_to_delete":
            self._handle_delete(parsed)
        elif parsed["action"] == "vote_to_top":
            self._handle_move_to_top(parsed)
        else:
            logger.warning("Unknown action %s", message)

    def _handle_skip(self, parsed):
        track = parsed["payload"]["track_name"]
        # If the current track is different to the one stored, clear votes
        if WebSocketRevelryHandler.current_track != track:
            WebSocketRevelryHandler.update_current_track(track)
            WebSocketRevelryHandler.votes_to_skip.clear()
        if self in WebSocketRevelryHandler.votes_to_skip:
            self.write_message({
                "action": "skip_update",
                "payload": {
                    "message": "You have already voted to skip this song.",
                    "votes": len(WebSocketRevelryHandler.votes_to_skip),
                },
            })
        else:
            WebSocketRevelryHandler.votes_to_skip.add(self)
            if len(WebSocketRevelryHandler.votes_to_skip) >= self.required_votes_to_skip:
                self.core.playback.next()
                WebSocketRevelryHandler.votes_to_skip.clear()
                WebSocketRevelryHandler.send_updates(
                    None,
                    {
                        "action": "skip_update",
                        "payload": {"message": "Skipping...", "votes": 0},
                    },
                )
            else:
                self.write_message({
                    "action": "skip_update",
                    "payload": {
                        "message": f"You have voted to skip this song. "
                                   f"({self.required_votes_to_skip - len(WebSocketRevelryHandler.votes_to_skip)}"
                                   f" more votes needed)",
                        "votes": len(WebSocketRevelryHandler.votes_to_skip),
                    },
                })
                WebSocketRevelryHandler.send_updates(
                    self,
                    {
                        "action": "skip_update",
                        "payload": {
                            "message": "Someone voted to skip",
                            "votes": len(WebSocketRevelryHandler.votes_to_skip),
                        },
                    }
                )

    def _handle_move_to_top(self, parsed):
        track_id = parsed["payload"]["track_id"]
        if track_id not in WebSocketRevelryHandler.votes_to_top:
            WebSocketRevelryHandler.votes_to_top[track_id] = set()
        if self in WebSocketRevelryHandler.votes_to_top[track_id]:
            self.write_message({
                "action": "top_update",
                "payload": {
                    "message": "You have already voted to top this song",
                    "tops": {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_top.items()}
                },
            })
        else:
            WebSocketRevelryHandler.votes_to_top[track_id].add(self)
            track = self.core.tracklist.filter({"tlid": [track_id]}).get()[0]
            if len(WebSocketRevelryHandler.votes_to_top[track_id]) >= self.required_votes_to_top:
                track_index = [tl_id for (tl_id, _) in self.core.tracklist.get_tl_tracks().get()].index(track_id)
                self.core.tracklist.move(start=track_index, end=track_index, to_position=1)
                self.remove_expired_ids(WebSocketRevelryHandler.votes_to_top)
                WebSocketRevelryHandler.votes_to_top.pop(track_id)
                tops = {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_top.items()}
                self.send_updates(None, {
                    "action": "top_update",
                    "payload": {
                        "message": f"{track.track.name} is moved to the top.",
                        "tops": tops
                    }
                })
            else:
                tops = {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_top.items()}
                self.write_message({
                    "action": "top_update",
                    "payload": {
                        "message":
                            f"You have voted to top {track.track.name}. "
                            f"({self.required_votes_to_top - len(WebSocketRevelryHandler.votes_to_top[track_id])}"
                            f" more votes needed)",
                        "tops": tops
                    },
                })
                WebSocketRevelryHandler.send_updates(
                    self,
                    {
                        "action": "top_update",
                        "payload": {
                            "message": f"Someone voted to top {track.track.name}",
                            "tops": tops,
                        },
                    }
                )

    def _handle_delete(self, parsed):
        track_id = parsed["payload"]["track_id"]
        if track_id not in WebSocketRevelryHandler.votes_to_delete:
            WebSocketRevelryHandler.votes_to_delete[track_id] = set()
        if self in WebSocketRevelryHandler.votes_to_delete[track_id]:
            self.write_message({
                "action": "delete_update",
                "payload": {
                    "message": "You have already voted to delete this song",
                    "deletes": {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_delete.items()}
                },
            })
        else:
            WebSocketRevelryHandler.votes_to_delete[track_id].add(self)
            if len(WebSocketRevelryHandler.votes_to_delete[track_id]) >= self.required_votes_to_delete:
                track = self.core.tracklist.remove({"tlid": [track_id]}).get()[0]
                self.remove_expired_ids(WebSocketRevelryHandler.votes_to_delete)
                deletes = {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_delete.items()}
                self.send_updates(None, {
                    "action": "delete_update",
                    "payload": {
                        "message": f"{track.track.name} is removed.",
                        "deletes": deletes
                    }
                })
            else:
                track = self.core.tracklist.filter({"tlid": [track_id]}).get()[0]
                deletes = {key: len(value) for (key, value) in WebSocketRevelryHandler.votes_to_delete.items()}
                self.write_message({
                    "action": "delete_update",
                    "payload": {
                        "message":
                            f"You have voted to delete {track.track.name}. "
                            f"({self.required_votes_to_delete - len(WebSocketRevelryHandler.votes_to_delete[track_id])}"
                            f" more votes needed)",
                        "deletes": deletes
                    },
                })
                WebSocketRevelryHandler.send_updates(
                    self,
                    {
                        "action": "delete_update",
                        "payload": {
                            "message": f"Someone voted to delete {track.track.name}",
                            "deletes": deletes,
                        },
                    }
                )

    def remove_expired_ids(self, id_collection: dict):
        tl_ids = (tl_id for (tl_id, _) in self.core.tracklist.get_tl_tracks().get())
        for voted_track_id in tuple(id_collection):
            if voted_track_id not in tl_ids:
                id_collection.pop(voted_track_id)


def revelry_factory(configuration, core):
    return [
        ('/ws', WebSocketRevelryHandler, {'core': core, 'configuration': configuration}),
    ]
