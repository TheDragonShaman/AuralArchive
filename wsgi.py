"""
WSGI Entry Point - AuralArchive

Provides the application factory output (Flask app + SocketIO) for production
servers such as Gunicorn or uWSGI.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

from app import create_app


app, socketio = create_app()

# Example (Gunicorn + eventlet):
#   gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 wsgi:app
