import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


_LOGGER_INITIALIZED = False

def setup_logger(name="AuralArchiveLogger", log_file="auralarchive_web.log", level=logging.INFO):
    """Set up parent logger for the Flask application (idempotent)."""
    global _LOGGER_INITIALIZED
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Full path to log file
    log_path = os.path.join(log_dir, log_file)
    
    # Create parent logger
    parent_logger = logging.getLogger(name)

    # If already configured, just adjust level if needed and exit
    if _LOGGER_INITIALIZED and parent_logger.handlers:
        parent_logger.setLevel(level)
        return parent_logger

    parent_logger.setLevel(level)
    parent_logger.handlers.clear()
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    simple_formatter = logging.Formatter(
        '%(levelname)s - %(name)s - %(message)s'
    )
    
    # File handler (rotating)
    file_handler = RotatingFileHandler(
        log_path, 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(detailed_formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(detailed_formatter)
    
    # Add handlers to parent logger
    parent_logger.addHandler(file_handler)
    parent_logger.addHandler(console_handler)
    
    # Disable propagation to avoid duplicate logs
    parent_logger.propagate = False

    _LOGGER_INITIALIZED = True

    # Set up child logger configurations once
    setup_child_loggers(level)

    parent_logger.debug(f"Parent logger initialized - Log file: {log_path}")

    return parent_logger

def setup_child_loggers(level=logging.INFO):
    """Configure child loggers to inherit from parent but maintain their names."""
    
    # Define child logger patterns for your providers and services
    child_patterns = [
        "JackettProvider",
        "ProviderManager",
        "DownloadService",
        "qBittorrentClient",
        "ClientManager",
        "SearchProvider",
        "DownloadsRoute",
        "IndexerProvider.Jackett",
        "DownloadClient.qBittorrent",
        # Add more as needed for your other services
    ]
    
    # Configure the root logger to ensure child inheritance works
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    for pattern in child_patterns:
        child_logger = logging.getLogger(pattern)
        child_logger.setLevel(level)
        # Clear any existing handlers to avoid duplicates
        child_logger.handlers.clear()
        # Enable propagation to inherit from root/parent
        child_logger.propagate = True
    
    main_logger = logging.getLogger("AuralArchiveLogger")
    if main_logger:
        main_logger.debug(f"Configured {len(child_patterns)} child logger patterns")

def get_module_logger(module_name: str):
    """Get a logger for a specific module that uses standardized configuration."""
    # Get or create the main logger (this ensures setup_logger was called)
    main_logger = logging.getLogger("AuralArchiveLogger")
    
    # If main logger has no handlers, set it up
    if not main_logger.handlers:
        setup_logger()
    
    # Create module-specific logger
    module_logger = logging.getLogger(module_name)
    
    # If this module logger doesn't have handlers, configure it
    if not module_logger.handlers:
        # Copy handlers from main logger
        for handler in main_logger.handlers:
            module_logger.addHandler(handler)
        
        module_logger.setLevel(main_logger.level)
        module_logger.propagate = False  # Prevent duplicate logs
    
    return module_logger

def get_logger(name="AuralArchiveLogger"):
    """Get an existing logger instance."""
    return logging.getLogger(name)