"""
Module Name: app.py
Author: TheDragonShaman
Created: July 15, 2025
Last Modified: December 23, 2025
Description:
    Application bootstrap for AuralArchive. Builds the Flask/SocketIO app,
    wires blueprints, and initializes core services and background tasks for
    the web UI and APIs.

Location:
    /app.py

"""

import logging
from flask import Flask, jsonify, request, redirect, url_for  # type: ignore
from flask_socketio import SocketIO  # type: ignore
from flask_login import LoginManager  # type: ignore

from config.config import Config
from utils.logger import get_module_logger, setup_logger

# Import blueprints
from routes.auth import auth_bp
from routes.main import main_bp
from routes.search import search_bp
from routes.library import library_bp
from routes.authors import authors_bp
from routes.series import series_bp
from routes.downloads import downloads_bp
from routes.settings import settings_bp
from routes.debug_tools import debug_bp
from api.settings_api import settings_api_bp
from routes.settings_tools.tabs import tabs_bp
from routes.settings_tools.indexers import indexers_bp
from api.manual_download_api import manual_search_api_bp
from routes.discover import discover_bp
from routes.imports import import_bp
from api.download_progress_api import download_progress_api
from api.streaming_download_api import streaming_download_api
from api.download_management_api import download_management_bp
from api.audible_auth_api import audible_auth_api
from api.audible_library_api import audible_library_api
from api.status_api import status_api_bp
from api.import_api import import_api_bp

LOGGER_NAME = "Core.App"
logger = get_module_logger(LOGGER_NAME)


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Setup logging with standardized module name
    global logger
    setup_logger(LOGGER_NAME, app.config.get('LOG_FILE', 'auralarchive_web.log'))
    logger = get_module_logger(LOGGER_NAME)
    logger.info(
        "Starting AuralArchive Flask application",
        extra={"socketio_async_mode": app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet')},
    )
    
    # Suppress duplicate werkzeug logs
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.handlers = []
    werkzeug_logger.setLevel(logging.WARNING)  # Only show warnings/errors from werkzeug
    
    # Initialize SocketIO with CORS support
    socketio = SocketIO(
        app,
        async_mode=app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet'),
        cors_allowed_origins=app.config.get('CORS_ALLOWED_ORIGINS'),
        logger=app.config.get('SOCKETIO_LOGGER', False),
        engineio_logger=app.config.get('ENGINEIO_LOGGER', False)
    )

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    @login_manager.user_loader
    def load_user(user_id):
        """Load user by ID for Flask-Login"""
        try:
            from auth.auth import get_user
            return get_user(user_id)
        except Exception as e:
            logger.error(f"Error loading user: {e}")
            return None
    
    @login_manager.unauthorized_handler
    def unauthorized():
        """Redirect to setup if no users, otherwise to login"""
        try:
            from auth.auth import has_users
            
            # For API requests, return JSON
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            
            # For regular requests, redirect to setup or login
            if not has_users():
                return redirect(url_for('auth.setup'))
            
            next_page = request.path if request.path != '/' else None
            return redirect(url_for('auth.login', next=next_page))
        except Exception as e:
            logger.error(f"Error in unauthorized handler: {e}")
            return redirect('/auth/login')

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp, url_prefix='/')
    app.register_blueprint(library_bp, url_prefix='/library')
    app.register_blueprint(search_bp, url_prefix='/search')  # Book search/discovery
    app.register_blueprint(series_bp, url_prefix='/series')
    app.register_blueprint(authors_bp, url_prefix='/authors')
    app.register_blueprint(downloads_bp, url_prefix='/downloads')
    app.register_blueprint(debug_bp, url_prefix='/')
    app.register_blueprint(discover_bp, url_prefix='/')
    app.register_blueprint(import_bp, url_prefix='/import')
    app.register_blueprint(settings_bp, url_prefix='/settings')
    app.register_blueprint(settings_api_bp)
    app.register_blueprint(tabs_bp, url_prefix='/settings')
    app.register_blueprint(indexers_bp, url_prefix='/settings')
    app.register_blueprint(manual_search_api_bp, url_prefix='/api/search')
    app.register_blueprint(download_progress_api, url_prefix='/')
    app.register_blueprint(download_management_bp, url_prefix='/api/downloads')
    app.register_blueprint(streaming_download_api, url_prefix='/')
    app.register_blueprint(audible_auth_api)
    app.register_blueprint(audible_library_api)
    app.register_blueprint(status_api_bp)
    app.register_blueprint(import_api_bp)
    
    # Initialize core services at startup to prevent lazy loading issues
    try:
        from services.service_manager import (
            get_database_service,
            get_config_service,
            get_audible_service_manager,
            get_download_management_service,
            get_automatic_download_service,
        )
        
        # Initialize services silently - ServiceManager will handle the logging
        database_service = get_database_service()
        get_config_service()
        get_download_management_service()
        automatic_download_service = get_automatic_download_service()
        logger.success(
            "Download management services started successfully",
            extra={"services": ["download_management", "automatic_download"]},
        )
        
        # Initialize Audible Service Manager (includes series service)
        get_audible_service_manager()
        logger.success(
            "Audible Service Manager started successfully",
            extra={"services": ["audible_catalog", "wishlist", "series"]},
        )

        logger.success(
            "Core services started successfully",
            extra={"services": ["database", "config", "audible"]},
        )
        
        # Initialize search services
        logger.debug("Initializing search services...")
        try:
            from services.service_manager import get_search_engine_service, get_indexer_manager_service
            from api.manual_download_api import init_search_services as init_manual_search_api

            # Initialize services
            search_engine_service = get_search_engine_service()
            get_indexer_manager_service()

            # Initialize manual search API (uses same search engine service)
            init_manual_search_api(
                auto_search_svc=automatic_download_service,
                manual_search_svc=search_engine_service,
                db_service=database_service,
            )

            logger.success(
                "Search services started successfully",
                extra={"indexers_initialized": True},
            )
        except Exception as exc:
            logger.error(
                "Error initializing search services",
                extra={"error": str(exc)},
            )
        
        # Initialize image cache service and preload images in background
        try:
            from services.image_cache import get_image_cache_service
            import threading
            
            def preload_images():
                """Background thread to preload images into cache."""
                try:
                    from services.image_cache import preload_images_from_database

                    preload_images_from_database()
                except Exception as exc:
                    logger.warning(
                        "Error preloading images",
                        extra={"error": str(exc)},
                    )
            
            # Initialize cache service
            get_image_cache_service()
            
            # Start image preloading in background thread
            preload_thread = threading.Thread(target=preload_images, daemon=True)
            preload_thread.start()
            
        except Exception as exc:
            logger.warning(
                "Error initializing image cache service",
                extra={"error": str(exc)},
            )

    except Exception as exc:
        logger.error(
            "Error initializing services at startup",
            extra={"error": str(exc)},
        )
    
    # API routes using service manager
    register_api_routes(app)
    
    # Error handlers
    register_error_handlers(app)
    
    logger.success("AuralArchive Flask application started successfully")
    return app, socketio

def register_api_routes(app):
    """Register API routes that use service manager"""
    from services.service_manager import get_database_service
    
    @app.route('/api/search/add-book', methods=['POST'])
    def api_add_book():
        """API endpoint to add book to library using service manager."""
        try:
            db_service = get_database_service()
            
            book_data = request.json
            asin = book_data.get('ASIN')
            
            if not asin:
                return jsonify({'error': 'ASIN is required'}), 400
            
            if db_service.check_book_exists(asin):
                return jsonify({'error': 'Book already exists in library'}), 409
            
            if db_service.add_book(book_data, status="Wanted"):
                logger.info(
                    "Added book to library",
                    extra={"title": book_data.get('Title', 'Unknown'), "asin": asin},
                )
                return jsonify({'success': True, 'message': 'Book added to library'})
            else:
                return jsonify({'error': 'Failed to add book'}), 500
        
        except Exception as exc:
            logger.error(
                "Error adding book",
                extra={"error": str(exc)},
            )
            return jsonify({'error': 'Failed to add book'}), 500
    
    @app.route('/api/books/<int:book_id>/status', methods=['PUT'])
    def api_update_book_status(book_id):
        """API endpoint to update book status using service manager."""
        try:
            db_service = get_database_service()
            new_status = request.json.get('status')
            if not new_status:
                return jsonify({'error': 'Status is required'}), 400

            if db_service.update_book_status(book_id, new_status):
                return jsonify({'success': True, 'message': 'Status updated'})
            else:
                return jsonify({'error': 'Failed to update status'}), 500

        except Exception as exc:
            logger.error(
                "Error updating book status",
                extra={"error": str(exc), "book_id": book_id, "status": request.json.get('status')},
            )
            return jsonify({'error': 'Failed to update status'}), 500
    
    @app.route('/api/books/<int:book_id>', methods=['DELETE'])
    def api_delete_book(book_id):
        """API endpoint to delete book using service manager."""
        try:
            db_service = get_database_service()
            logger.info("API delete request for book", extra={"book_id": book_id})
            if db_service.delete_book(book_id):
                logger.info("Book deleted via API", extra={"book_id": book_id})
                return jsonify({'success': True, 'message': 'Book deleted'})
            else:
                logger.warning("Book delete failed via API", extra={"book_id": book_id})
                return jsonify({'error': 'Failed to delete book'}), 500
        
        except Exception as exc:
            logger.error(
                "Error deleting book",
                extra={"error": str(exc), "book_id": book_id},
            )
            return jsonify({'error': 'Failed to delete book'}), 500
    
    @app.route('/api/stats')
    def api_stats():
        """API endpoint for library statistics."""
        try:
            db_service = get_database_service()
            stats = db_service.get_library_stats()
            return jsonify(stats)
        except Exception as exc:
            logger.error(
                "Error getting stats",
                extra={"error": str(exc)},
            )
            return jsonify({'error': 'Failed to get stats'}), 500
    
    @app.route('/health')
    def health_check():
        """Health check endpoint."""
        return jsonify({
            'status': 'healthy',
            'service': 'AuralArchive',
            'version': '1.0.0'
        })
    
    @app.route('/api/status')
    def api_status():
        """API status endpoint."""
        try:
            db_service = get_database_service()
            books_count = len(db_service.get_all_books())
            
            return jsonify({
                'success': True,
                'database': 'connected',
                'books_count': books_count,
                'status': 'operational'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e),
                'status': 'error'
            }), 500

def register_error_handlers(app):
    """Register error handlers"""
    
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({'error': 'Resource not found'}), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error("Internal server error", extra={"error": str(error)})
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        logger.error(
            "Unhandled exception",
            extra={"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}
        )
        return jsonify({'error': 'An unexpected error occurred'}), 500

# Create app instance
app, socketio = create_app()

# SocketIO Event Handlers
@socketio.on('connect')
def handle_connect():
    logger.info("SocketIO client connected", extra={"sid": request.sid})
    socketio.emit('connection_status', {'status': 'connected', 'message': 'Connected to AuralArchive'})

@socketio.on('disconnect') 
def handle_disconnect():
    logger.info("SocketIO client disconnected", extra={"sid": request.sid})

@socketio.on('ping')
def handle_ping():
    socketio.emit('pong', {'message': 'Server is alive'})

if __name__ == '__main__':
    import sys
    
    # CLI argument handling
    if len(sys.argv) > 1 and sys.argv[1] == '--show-paths':
        # Show detected paths for troubleshooting
        from utils.path_resolver import get_path_resolver
        pr = get_path_resolver()
        
        print("=" * 60)
        print("AuralArchive Path Configuration")
        print("=" * 60)
        print(f"Environment: {'Docker' if pr.is_docker() else 'Bare Metal'}")
        print("-" * 60)
        print(f"Config:      {pr.get_config_dir()}")
        print(f"Downloads:   {pr.get_downloads_dir()}")
        print(f"Import:      {pr.get_import_dir()}")
        print(f"Conversion:  {pr.get_conversion_dir()}")
        print(f"Cache:       {pr.get_cache_dir()}")
        print(f"Logs:        {pr.get_logs_dir()}")
        print(f"Auth:        {pr.get_auth_dir()}")
        print("=" * 60)
        sys.exit(0)
    
    logger.info("AuralArchive starting", extra={"mode": "development"})
    
    # Initialize wishlist service in background after startup
    def initialize_services():
        """Initialize background services after Flask app is fully loaded."""
        try:
            import time
            time.sleep(3)  # Wait for Flask to fully initialize
            
            from services.service_manager import get_audible_wishlist_service
            
            logger.debug("Initializing wishlist auto-sync service...")
            wishlist_service = get_audible_wishlist_service()
            
            # The service will auto-start if configured properly
            status = wishlist_service.get_status()
            if status.get('auto_sync_running', False):
                logger.info(
                    "Wishlist auto-sync already running",
                    extra={"interval_minutes": 15},
                )
            elif status.get('service_configured', False):
                # If service is configured but not auto-started, start it on startup
                success = wishlist_service.start_auto_sync("startup")
                if success:
                    logger.success("Wishlist auto-sync started successfully")
                else:
                    logger.warning("Failed to start wishlist auto-sync on startup")
            else:
                logger.warning("Audible not configured - wishlist auto-sync disabled")
            
            # Initialize download management service and start monitoring
            logger.debug("Initializing download management service...")
            try:
                from services.service_manager import get_download_management_service
                dm_service = get_download_management_service()
                
                # Start the monitoring thread
                dm_service.start_monitoring()
                logger.success(
                    "Download management service monitoring started successfully",
                    extra={"monitoring": True},
                )
                
            except Exception as exc:
                logger.error(
                    "Error starting download management service",
                    extra={"error": str(exc)},
                )
            
            
            # Start async audiobook management services
            logger.debug("Starting async audiobook management services...")
            try:
                import asyncio
                from services.service_manager import service_manager
                
                # Create event loop for background async services
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Start all async services
                loop.run_until_complete(service_manager.start_all_services())
                
                logger.success(
                    "All async audiobook management services started successfully",
                    extra={"services": "all_async"},
                )
                
            except Exception as exc:
                logger.error(
                    "Error starting async services",
                    extra={"error": str(exc)},
                )
                
        except Exception as exc:
            logger.error(
                "Error initializing background services",
                extra={"error": str(exc)},
            )
    
    # Start background services in separate thread
    import threading
    services_thread = threading.Thread(target=initialize_services, daemon=True)
    services_thread.start()
    
    # Run with SocketIO support
    socketio.run(app, debug=False, host='0.0.0.0', port=8765)
