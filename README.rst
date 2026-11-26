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

You must install `mopidy <https://www.mopidy.com/>`_ (version 3 or 4) and some backends (soundcloud, spotify, youtube...).

**PROD:** you just have to install pip and then::

    sudo python3 -m pip install Mopidy-Yap

**DEV:** After cloning the repository, install by running::

    sudo python3 -m pip install -e .

The web interface is built with `Vite <https://vite.dev/>`_ from ``frontend/`` into ``src/mopidy_yap/static``::

    npm install
    npm run build

``npm start`` runs a dev server on http://localhost:3000/ that proxies to a
Mopidy instance on localhost:6680 (for example ``docker compose up``).

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

``autoplay`` only has an effect with Mopidy-Spotify enabled: when the queue is
about to run out, Yap adds a Spotify recommendation based on the last track.

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
