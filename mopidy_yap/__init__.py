import logging
import os

from mopidy import config, ext

__version__ = "0.1.3"

from mopidy_yap.frontend import YapFrontend
from mopidy_yap.websocket import WebSocketYapHandler

logger = logging.getLogger(__name__)


class Extension(ext.Extension):
    dist_name = 'Mopidy-Yap'
    ext_name = 'yap'
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
        schema['autoplay'] = config.Boolean()
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
            'factory': yap_factory,
        })
        registry.add("frontend", YapFrontend)


def yap_factory(configuration, core):
    return [
        ('/ws', WebSocketYapHandler, {'core': core, 'configuration': configuration}),
    ]
