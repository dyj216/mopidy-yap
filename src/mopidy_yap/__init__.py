import logging
import pathlib
from importlib.metadata import version

from mopidy import config, ext

__version__ = version("Mopidy-Yap")

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = "Mopidy-Yap"
    ext_name = "yap"
    version = __version__

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()
        schema["votes_to_skip"] = config.Integer(minimum=1)
        schema["votes_to_delete"] = config.Integer(minimum=1)
        schema["votes_to_top"] = config.Integer(minimum=1)
        schema["pause_button"] = config.Boolean()
        schema["autoplay"] = config.Boolean()
        schema["lastfm_api_key"] = config.Secret(optional=True)
        return schema

    def setup(self, registry):
        from .frontend import YapFrontend

        registry.add(
            "http:static",
            {
                "name": self.ext_name,
                "path": str(pathlib.Path(__file__).parent / "static"),
            },
        )
        registry.add(
            "http:app",
            {
                "name": self.ext_name,
                "factory": yap_factory,
            },
        )
        registry.add("frontend", YapFrontend)


def yap_factory(configuration, core):
    from .websocket import WebSocketYapHandler

    return [
        (
            "/ws",
            WebSocketYapHandler,
            {"core": core, "configuration": configuration},
        ),
    ]
