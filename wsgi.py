"""
Module Name: wsgi.py
Author: TheDragonShaman
Created: August 2, 2025
Last Modified: December 23, 2025
Description:
	WSGI entry point for AuralArchive. Exposes the Flask and SocketIO
	application factory outputs for production servers (e.g., Gunicorn,
	uWSGI) to import and run.

Location:
	/wsgi.py

"""

from utils.logger import get_module_logger
from app import create_app


LOGGER = get_module_logger("Core.Wsgi")

app, socketio = create_app()
LOGGER.success(
	"WSGI application loaded successfully",
	extra={"socketio_async_mode": app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet')},
)

# Example (Gunicorn + eventlet):
#   gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 wsgi:app
