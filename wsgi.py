"""
Module Name: wsgi.py
Author: TheDragonShaman
Created: Apr 15 2026
Last Modified: Apr 15 2026
Description:
    WSGI entry point for running AuralArchive with Gunicorn and gevent.
    Applies gevent monkey patching, sets SocketIO async mode, and starts
    background services during process bootstrap.

Location:
    /wsgi.py

"""

from gevent import monkey
monkey.patch_all()

import os

os.environ.setdefault('SOCKETIO_ASYNC_MODE', 'gevent')

from app import app, start_background_services  # noqa: E402

from gevent import spawn as gevent_spawn
gevent_spawn(start_background_services)

application = app
