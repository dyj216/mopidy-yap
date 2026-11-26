import pathlib
from unittest import mock

from mopidy_yap import Extension, __version__, yap_factory
from mopidy_yap.frontend import YapFrontend
from mopidy_yap.websocket import WebSocketYapHandler


def test_version_comes_from_package_metadata():
    assert __version__
    assert Extension.version == __version__


def test_get_default_config():
    config = Extension().get_default_config()

    assert "[yap]" in config
    assert "enabled = true" in config
    for key in [
        "votes_to_skip",
        "votes_to_delete",
        "votes_to_top",
        "pause_button",
        "autoplay",
    ]:
        assert f"{key} =" in config


def test_get_config_schema():
    schema = Extension().get_config_schema()

    for key in [
        "enabled",
        "votes_to_skip",
        "votes_to_delete",
        "votes_to_top",
        "pause_button",
        "autoplay",
    ]:
        assert key in schema


def test_setup_registers_web_interface_websocket_and_frontend():
    registry = mock.Mock()

    Extension().setup(registry)

    registered = {c.args[0]: c.args[1] for c in registry.add.call_args_list}
    assert registered["frontend"] is YapFrontend

    static = registered["http:static"]
    assert static["name"] == "yap"
    assert (pathlib.Path(static["path"]) / "index.html").is_file()

    app = registered["http:app"]
    assert app["name"] == "yap"
    assert app["factory"] is yap_factory


def test_app_factory_serves_websocket_handler():
    core = mock.Mock()
    config = {"yap": {}}

    [(path, handler, kwargs)] = yap_factory(config, core)

    assert path == "/ws"
    assert handler is WebSocketYapHandler
    assert kwargs == {"core": core, "configuration": config}
