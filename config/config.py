import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Basic Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Database configuration
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'sqlite:///database/auralarchive_database.db'
    
    # Logging configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.environ.get('LOG_FILE') or 'auralarchive_web.log'
    
    # SocketIO configuration
    SOCKETIO_ASYNC_MODE = 'threading'
    
    # Application settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file upload
    
    # Monitor settings
    MONITOR_ENABLED = os.environ.get('MONITOR_ENABLED', 'true').lower() == 'true'
    
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
        },
        'sabnzbd': {
            'enabled': False,
            'priority': 4,
            'type': 'usenet',
            'host': 'localhost',
            'port': 8080,
            'api_key': '',  # SABnzbd uses API key instead of username/password
            'use_ssl': False,
            'verify_cert': True,
            'category': 'audiobooks'
        },
        'nzbget': {
            'enabled': False,
            'priority': 5,
            'type': 'usenet',
            'host': 'localhost',
            'port': 6789,
            'username': 'nzbget',
            'password': 'tegbzn6789',
            'use_ssl': False,
            'verify_cert': True,
            'category': 'audiobooks'
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
    # Supports Jackett, Prowlarr (Torznab), and NZBHydra2 (Newznab)
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
        },
        'nzbhydra2': {
            'enabled': False,
            'priority': 4,
            'type': 'nzbhydra2',
            'protocol': 'newznab',
            'feed_url': 'http://localhost:5076/api',  # NZBHydra2 Newznab URL
            'api_key': '',     # Get from NZBHydra2 config
            'categories': ['3030', '7020'],  # Multiple categories for usenet
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
