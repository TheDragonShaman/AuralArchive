"""
Module Name: config.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Loads environment configuration and central application defaults.

Location:
    /config/config.py

"""

# Bottleneck: .env loading minimal; primary cost is downstream imports.
# Upgrade: centralize validation of critical env vars.

import os
from dotenv import load_dotenv

from utils.logger import get_module_logger
from utils.path_resolver import get_path_resolver

# Load environment variables from .env file
load_dotenv()

_LOGGER = get_module_logger("Config.Config")


def _resolve_config_dir() -> str:
    """Get config directory using path resolver."""
    return get_path_resolver().get_config_dir()


class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    _CONFIG_DIR = _resolve_config_dir()
    DATABASE_URL = os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.join(_CONFIG_DIR, 'auralarchive_database.db')}"
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.environ.get('LOG_FILE') or 'auralarchive_web.log'
    
    # SocketIO configuration
    SOCKETIO_ASYNC_MODE = 'threading'
    
    # Application settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file upload

    # Debug utilities (protected with shared secret token)
    AUDIBLE_DEBUG_TOKEN = os.environ.get('AUDIBLE_DEBUG_TOKEN')
    
    # Monitor settings
    MONITOR_ENABLED = os.environ.get('MONITOR_ENABLED', 'true').lower() == 'true'
    
    # Authentication settings
    # User credentials are stored in config/config.txt as hashed passwords
    # Session lifetime: remember me = 30 days, otherwise session-only
    REMEMBER_COOKIE_DURATION = 30 * 24 * 60 * 60  # 30 days in seconds
    SESSION_COOKIE_SECURE = False  # Set to True if using HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Download Client Configuration
    # Multiple clients can be configured with priority (1-10, lower = higher priority)
    # The system will try clients in priority order and failover to next if one fails
    DOWNLOAD_CLIENTS = {
        'qbittorrent': {
            'enabled': False,  # Set to True to enable
            'priority': 1,     # Lower number = higher priority (1-10)
            'type': 'torrent',
            'host': 'localhost',
            'port': 8080,
            'username': 'admin',
            'password': 'adminadmin',
            'use_ssl': False,
            'verify_cert': True,
            'category': 'audiobooks',  # Optional category for organized downloads
            'save_path': None  # Optional custom save path (None = client default)
        },
        'deluge': {
            'enabled': False,
            'priority': 2,
            'type': 'torrent',
            'host': 'localhost',
            'port': 8112,
            'username': 'admin',
            'password': 'deluge',
            'use_ssl': False,
            'verify_cert': True
        },
        'transmission': {
            'enabled': False,
            'priority': 3,
            'type': 'torrent',
            'host': 'localhost',
            'port': 9091,
            'username': '',
            'password': '',
            'use_ssl': False,
            'verify_cert': True
        }
    }
    
    # Download Queue Settings
    DOWNLOAD_QUEUE_SETTINGS = {
        'enabled': True,
        'poll_interval': 30,        # Seconds between queue checks
        'monitor_interval': 60,     # Seconds between download progress checks
        'max_retries': 3,           # Maximum retry attempts per download
        'retry_delay': 300,         # Seconds to wait before retry (5 minutes)
        'auto_remove_completed': True,  # Auto-remove from client after successful import
        'auto_remove_failed': False     # Auto-remove from client after failed download
    }
    
    # Indexer Configuration
    # Multiple indexers can be configured with priority (1-10, lower = higher priority)
    # Supports Jackett and Prowlarr (Torznab)
    # Simply copy/paste the full Torznab feed URL from your indexer
    INDEXERS = {
        'jackett_audiobookbay': {
            'enabled': False,  # Set to True to enable
            'priority': 1,     # Lower number = higher priority (1-10)
            'type': 'jackett',
            'protocol': 'torznab',
            'feed_url': 'http://localhost:9117/api/v2.0/indexers/audiobookbay/results/torznab',  # Full Torznab feed URL
            'api_key': '',     # Get from Jackett dashboard
            'categories': ['3030'],  # 3030 = Audiobooks category
            'timeout': 30,
            'verify_ssl': True
        },
        'jackett_all': {
            'enabled': False,
            'priority': 2,
            'type': 'jackett',
            'protocol': 'torznab',
            'feed_url': 'http://localhost:9117/api/v2.0/indexers/all/results/torznab',  # Search all configured indexers
            'api_key': '',     # Same API key as above
            'categories': ['3030'],
            'timeout': 30,
            'verify_ssl': True
        },
        'prowlarr': {
            'enabled': False,
            'priority': 3,
            'type': 'prowlarr',
            'protocol': 'torznab',
            'feed_url': 'http://localhost:9696/api/v2.0/indexers/all/results/torznab',  # Prowlarr Torznab URL
            'api_key': '',     # Get from Prowlarr settings
            'categories': ['3030'],
            'timeout': 30,
            'verify_ssl': True
        }
    }
    
    # Indexer Search Settings
    INDEXER_SEARCH_SETTINGS = {
        'parallel_search': True,      # Search all indexers in parallel
        'max_results_per_indexer': 100,  # Limit results per indexer
        'search_timeout': 60,         # Max seconds for entire search operation
        'min_seeders': 1,             # Minimum seeders for torrent results
        'prefer_verified': True,      # Prefer verified/trusted releases
        'cache_results': True,        # Cache search results in database
        'cache_ttl': 3600            # Cache time-to-live in seconds (1 hour)
    }


_LOGGER.info(
    "Config loaded",
    extra={
        "log_level": Config.LOG_LEVEL,
        "log_file": Config.LOG_FILE,
        "monitor_enabled": Config.MONITOR_ENABLED,
        "socketio_async_mode": Config.SOCKETIO_ASYNC_MODE,
    },
)
