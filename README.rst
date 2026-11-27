******************************
Mopidy-Yap (yet another party)
******************************

Mopidy web extension inspired by the `Mopidy-Party <https://github.com/Lesterpig/mopidy-party>`_ extension.
It allows guests to manage the sound.

- React and MUI based web interface
- Search soundtracks and add it to the queue
- Skip current track after a configurable number of votes (defaults to 3)
- Upvote any element in the playlist to play next with votes

Installation
============

You need `Mopidy <https://mopidy.com/>`_ (version 3 or 4) with some backends
(local files, Spotify, YouTube...), and Python 3.11 or newer.

Install Yap into the same Python environment as Mopidy, then restart Mopidy.
If Mopidy came from your distribution's packages (apt, pacman, ...)::

    sudo python3 -m pip install --break-system-packages Mopidy-Yap

Recent distributions (Debian 12, Ubuntu 23.04, Raspberry Pi OS Bookworm, Arch
and others) protect the system Python from pip, so ``--break-system-packages``
is needed; on older systems you can leave it out. If you installed Mopidy in a
virtual environment, use that environment's pip instead, without the flag or
``sudo``::

    /path/to/venv/bin/pip install Mopidy-Yap

**Development:** after cloning the repository, install it in editable mode into
the environment Mopidy runs in, with the same flags as above::

    sudo python3 -m pip install --break-system-packages -e .

The web interface is built with `Vite <https://vite.dev/>`_ from ``frontend/`` into ``src/mopidy_yap/static``::

    npm install
    npm run build

``npm start`` runs a dev server on http://localhost:3000/ that proxies to a
Mopidy instance on localhost:6680 (for example ``docker compose up``).

``docker compose up`` runs Mopidy with Yap on http://localhost:6680/ and plays
the music in ``~/Music`` (mounted read-only). Create that folder first:
otherwise Docker creates an empty one owned by root.

Tests need Mopidy and its GStreamer bindings. With those installed::

    python3 -m pip install -e ".[test]"
    python3 -m pytest

Or run them in the Docker image::

    docker build -t mopidy-yap .
    docker run --rm --user root -v "$PWD:/repo:ro" -w /repo \
        -e PYTHONDONTWRITEBYTECODE=1 --entrypoint sh mopidy-yap \
        -c "pip install -q --break-system-packages pytest && python3 -m pytest -p no:cacheprovider"

Releases are published to PyPI by GitHub Actions (``.github/workflows/release.yml``)
when a version tag is pushed: set the new version in ``pyproject.toml`` and
``package.json``, commit, then ``git tag -a vX.Y.Z -m "Version X.Y.Z"`` and
``git push origin vX.Y.Z``. The workflow runs the tests, checks the tag
against the version and that the built web interface is committed, and
publishes with PyPI Trusted Publishing (no API token needed). It then creates
the GitHub release, listing the commits since the previous tag and attaching
the built files, unless a release for the tag was already created by hand.

Usage
=====

To use the interface, simply use your browser to visit your Mopidy instance's IP at port 6680 to see all available web interfaces.
For example, http://localhost:6680/

Direct access to Mopidy Yap should then be: http://localhost:6680/yap/

Configuration
=============

::

    [yap]
    enabled = true
    votes_to_skip = 3
    votes_to_delete = 3
    votes_to_top = 3
    pause_button = false
    autoplay = true
    lastfm_api_key =

Autoplay
--------

When the last track in the queue starts playing, ``autoplay`` adds a
recommended track so the music keeps going. Nothing is added while repeat is
on. Recommendations come from:

- **Spotify**, for Spotify tracks, when Mopidy-Spotify is enabled.
- **Last.fm**, for any track with an artist and title: Yap asks Last.fm for
  similar tracks and queues the first one it finds in your music sources
  (local files or any other backend's search). If none of them is there, it
  falls back to a random track by one of Last.fm's similar artists. Recently
  played tracks are skipped. This needs your own free Last.fm API key in
  ``lastfm_api_key``.

With neither set up, autoplay does nothing.

To get a Last.fm API key, log in to Last.fm, fill in the form at
https://www.last.fm/api/account/create (only the application name and
description are needed) and copy the "API key" into ``lastfm_api_key``. Using
the key means accepting the `Last.fm API terms
<https://www.last.fm/api/tos>`_, which allow non-commercial use only.

Recommendations powered by `AudioScrobbler <https://www.last.fm>`_: when
Last.fm is used, the web interface credits it and links each recommended
track to its Last.fm page (or the artist's page, for the fallback).

Yap's websocket only accepts connections from pages served by the same Mopidy
instance. To use the interface from another origin, add it to Mopidy's
``http/allowed_origins`` setting, like for Mopidy's own websocket.

Limitations
===========

- This frontend can display a stream, but you can not add a stream to the queue with this backend.
- This frontend can only display the upcoming tracks. If you want to handle the tracklist, you should use a
  different frontend for that.

Project resources
=================

- `Source code <https://github.com/dyj216/mopidy-yap>`_
- `Issue tracker <https://github.com/dyj216/mopidy-yap/issues>`_
