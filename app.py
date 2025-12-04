"""
Application Bootstrap - AuralArchive

Creates the Flask/SocketIO application, registers blueprints, and initializes
the core services needed for the web UI and APIs.

Author: AuralArchive Development Team
Updated: December 2, 2025
"""

import logging
from flask import Flask, jsonify, request  # type: ignore
from flask_socketio import SocketIO  # type: ignore

from config.config import Config
from utils.logger import setup_logger

# Import blueprints
from routes.main import main_bp
from routes.search import search_bp
from routes.library import library_bp
from routes.authors import authors_bp
from routes.series import series_bp
from routes.downloads import downloads_bp
from routes.settings import settings_bp
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

logger = logging.getLogger("AuralArchiveLogger")


def create_app(config_class=Config):
    """Application factory pattern"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Setup logging
    global logger
    logger = setup_logger("AuralArchiveLogger", app.config.get('LOG_FILE', 'auralarchive_web.log'))
    logger.info("Starting AuralArchive Flask application")
    
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

    # Register blueprints
    app.register_blueprint(main_bp, url_prefix='/')
    app.register_blueprint(library_bp, url_prefix='/library')
    app.register_blueprint(search_bp, url_prefix='/search')  # Book search/discovery
    app.register_blueprint(series_bp, url_prefix='/series')
    app.register_blueprint(authors_bp, url_prefix='/authors')
    app.register_blueprint(downloads_bp, url_prefix='/downloads')
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
        config_service = get_config_service()
        download_service = get_download_management_service()
        automatic_download_service = get_automatic_download_service()
        logger.info("Download management services initialized (pipeline + automation)")
        
        # Initialize Audible Service Manager (includes series service)
        audible_manager = get_audible_service_manager()
        logger.info("Audible Service Manager initialized with series support")
        
        logger.info("Core services initialized (database, config, audible)")
        
        # Initialize search services
        logger.debug("Initializing search services...")
        try:
            from services.service_manager import get_search_engine_service, get_indexer_manager_service
            from api.manual_download_api import init_search_services as init_manual_search_api
            
            # Initialize services
            search_engine_service = get_search_engine_service()
            indexer_manager_service = get_indexer_manager_service()
            
            # Initialize manual search API (uses same search engine service)
            init_manual_search_api(
                auto_search_svc=automatic_download_service,
                manual_search_svc=search_engine_service,
                db_service=database_service
            )
            
            logger.info("Search services initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing search services: {e}")
        
        # Initialize image cache service and preload images in background
        try:
            from services.image_cache import get_image_cache_service
            import threading
            
            def preload_images():
                """Background thread to preload images into cache."""
                try:
                    from services.image_cache import preload_images_from_database
                    preload_images_from_database()
                except Exception as e:
                    logger.warning(f"Error preloading images: {e}")
            
            # Initialize cache service
            cache_service = get_image_cache_service()
            
            # Start image preloading in background thread
            preload_thread = threading.Thread(target=preload_images, daemon=True)
            preload_thread.start()
            
        except Exception as e:
            logger.warning(f"Error initializing image cache service: {e}")
            
    except Exception as e:
        logger.error(f"Error initializing services at startup: {e}")
    
    # API routes using service manager
    register_api_routes(app)
    
    # Error handlers
    register_error_handlers(app)
    
    logger.info("AuralArchive Flask application initialized successfully")
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
                logger.info(f"Added book to library: {book_data.get('Title', 'Unknown')}")
                return jsonify({'success': True, 'message': 'Book added to library'})
            else:
                return jsonify({'error': 'Failed to add book'}), 500
        
        except Exception as e:
            logger.error(f"Error adding book: {e}")
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
        
        except Exception as e:
            logger.error(f"Error updating book status: {e}")
            return jsonify({'error': 'Failed to update status'}), 500
    
    @app.route('/api/books/<int:book_id>', methods=['DELETE'])
    def api_delete_book(book_id):
        """API endpoint to delete book using service manager."""
        try:
            db_service = get_database_service()
            if db_service.delete_book(book_id):
                return jsonify({'success': True, 'message': 'Book deleted'})
            else:
                return jsonify({'error': 'Failed to delete book'}), 500
        
        except Exception as e:
            logger.error(f"Error deleting book: {e}")
            return jsonify({'error': 'Failed to delete book'}), 500
    
    @app.route('/api/stats')
    def api_stats():
        """API endpoint for library statistics."""
        try:
            db_service = get_database_service()
            stats = db_service.get_library_stats()
            return jsonify(stats)
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
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
        logger.error(f"Internal server error: {error}")
        return jsonify({'error': 'Internal server error'}), 500
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        logger.error(f"Unhandled exception: {e}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

# Create app instance
app, socketio = create_app()

# SocketIO Event Handlers
@socketio.on('connect')
def handle_connect():
    logging.getLogger("AuralArchiveLogger").info(f"SocketIO client connected: {request.sid}")
    socketio.emit('connection_status', {'status': 'connected', 'message': 'Connected to AuralArchive'})

@socketio.on('disconnect') 
def handle_disconnect():
    logging.getLogger("AuralArchiveLogger").info(f"SocketIO client disconnected: {request.sid}")

@socketio.on('ping')
def handle_ping():
    socketio.emit('pong', {'message': 'Server is alive'})

if __name__ == '__main__':
    logger.info("AuralArchive Starting...")
    
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
                logger.info("Wishlist auto-sync already running (15-minute intervals)")
            elif status.get('service_configured', False):
                # If service is configured but not auto-started, start it on startup
                success = wishlist_service.start_auto_sync("startup")
                if success:
                    logger.info("Wishlist auto-sync initialized successfully on server startup")
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
                logger.info("Download management service monitoring started")
                
            except Exception as e:
                logger.error(f"Error starting download management service: {e}")
            
            
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
                
                logger.info("All async audiobook management services started successfully")
                
            except Exception as e:
                logger.error(f"Error starting async services: {e}")
                
        except Exception as e:
            logger.error(f"Error initializing background services: {e}")
    
    # Start background services in separate thread
    import threading
    services_thread = threading.Thread(target=initialize_services, daemon=True)
    services_thread.start()
    
    # Run with SocketIO support  
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
