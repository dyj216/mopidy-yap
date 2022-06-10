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

You must install `mopidy <https://www.mopidy.com/>`_ (version 3) and some backends (soundcloud, spotify, youtube...).

**PROD:** you just have to install pip and then::

    sudo python3 -m pip install Mopidy-Yap

**DEV:** After cloning the repository, install by running::

    sudo python3 -m pip install -e .

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

Project resources
=================

- `Source code <https://github.com/dyj216/mopidy-yap>`_
- `Issue tracker <https://github.com/dyj216/mopidy-yap/issues>`_
