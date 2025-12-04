import configparser
import os
import logging
from typing import Dict, Any

class ConfigDefaults:
    """Handles default configuration generation for AuralArchive"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.logger = logging.getLogger("ConfigService.Defaults")
    
    def ensure_config_exists(self):
        """Ensure configuration file exists, create default if not."""
        if not os.path.exists(self.config_file):
            self.logger.warning("Configuration file not found. Creating default...")
            self.generate_default_config()
    
    def generate_default_config(self):
        """Generate a complete default configuration file with all sections."""
        config = configparser.ConfigParser()
        
        # Add all configuration sections
        sections = [
            self._add_audible_config,
            self._add_jackett_config,
            self._add_qbittorrent_config,
            self._add_audiobookshelf_config,
            self._add_import_config,
            self._add_database_config,
            self._add_application_config,
            self._add_auto_search_config,
            self._add_media_management_config,
            self._add_authors_config,
            self._add_providers_config,
            self._add_indexer_defaults,
        ]

        for add_section in sections:
            add_section(config)
        
        try:
            with open(self.config_file, "w") as configfile:
                config.write(configfile)
            self.logger.info(f"Default configuration created at {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to create default configuration: {e}")
    
    def _add_audible_config(self, config: configparser.ConfigParser):
        """Add Audible API configuration section."""
        config["audible"] = {
            "username": "",
            "password": "",
            "country_code": "us",
            "max_results": "25",
            "cache_duration": "2",
            "auto_authenticate": "True",
            "download_directory": "",
            "download_format": "aaxc",
            "download_quality": "best",
            "aax_fallback_enabled": "true",
            "save_voucher": "true",
            "include_cover": "false",
            "include_chapters": "false",
            "include_pdf": "false",
            "concurrent_downloads": "1",
            "temp_dir_enabled": "true",
            "temp_directory": "/tmp/aural_archive_conversion"
        }
    
    def _add_jackett_config(self, config: configparser.ConfigParser):
        """Add Jackett configuration section."""
        config["jackett"] = {
            "enabled": "false",
            "api_key": "",
            "api_url": "http://localhost:9117/api/v2.0/indexers/all/results/torznab/",
            "indexers": "all",
            "host": "localhost",
            "port": "9117",
            "use_https": "false",
            "timeout": "30",
            "download_base_url": ""
        }
    
    def _add_qbittorrent_config(self, config: configparser.ConfigParser):
        """Add qBittorrent configuration section."""
        config["qbittorrent"] = {
            "enabled": "false",
            "qb_host": "localhost",
            "qb_port": "8080",
            "qb_username": "",
            "qb_password": "",
            "auto_download": "false",
            "category": "auralarchive"
        }
    
    def _add_audiobookshelf_config(self, config: configparser.ConfigParser):
        """Add AudioBookShelf configuration section."""
        config["audiobookshelf"] = {
            "abs_host": "http://localhost:13378",
            "abs_api_key": "",
            "abs_library_id": "",
            "abs_enabled": "false",
            "abs_sync_metadata": "true",
            "abs_sync_only_owned": "true",
            "abs_auto_sync": "false",
            "abs_auto_sync_enabled": "false",
            "abs_sync_frequency": "30min",
            "library_path": "/mnt/audiobooks",
            "naming_template": "standard",
            "include_asin_in_path": "false",
            "create_author_folders": "true",
            "create_series_folders": "true"
        }
    
    def _add_import_config(self, config: configparser.ConfigParser):
        """Add import service configuration section."""
        config["import"] = {
            "verify_after_import": "true",
            "create_backup_on_error": "true",
            "delete_source_after_import": "false",
            "use_hardlinks": "false",
            "import_directory": "/downloads/import"
        }
    
    def _add_database_config(self, config: configparser.ConfigParser):
        """Add database configuration section."""
        config["database"] = {
            "db_file": "database/auralarchive_database.db"
        }
    
    def _add_application_config(self, config: configparser.ConfigParser):
        """Add application settings section."""
        config["application"] = {
            "log_level": "INFO"
        }
    
    def _add_authors_config(self, config: configparser.ConfigParser):
        """Add author discovery and catalog configuration section."""
        config["authors"] = {
            "auto_add_missing": "false",
            "auto_add_limit": "0",
            "preferred_languages": "english,en"
        }

    def _add_auto_search_config(self, config: configparser.ConfigParser):
        """Add automatic search configuration section."""
        config["auto_search"] = {
            "auto_download_enabled": "false",
            "quality_threshold": "5",
            "scan_interval_seconds": "120",
            "max_batch_size": "2",
            "skip_book_ids": ""
        }
    
    def _add_media_management_config(self, config: configparser.ConfigParser):
        """Add media management configuration section."""
        config["media_management"] = {
            "monitor_dirs": "",
            "target_dir": "",
            "dir_template": "{author}/{series}/{title}",
            "file_template": "{title}",
            "mode": "automatic",
            "file_operation": "move",
            "monitor_interval": "1",
            "atomic": "false",
            "abs_enabled": "false",
            "abs_library": "",
            "abs_auto_scan": "true",
            "abs_auto_match": "true",
            "abs_provider": "audible"
        }
    
    def _add_providers_config(self, config: configparser.ConfigParser):
        """Add providers configuration sections."""
        config["prowlarr"] = {
            "enabled": "false",
            "host": "localhost",
            "port": "9696",
            "base_url": "",
            "api_key": "",
            "indexer_ids": "",
            "min_seeders": "1",
            "use_https": "false",
            "timeout": "30"
        }
        
        config["nzbhydra2"] = {
            "enabled": "false",
            "host": "localhost",
            "port": "5076",
            "api_key": "",
            "use_https": "false",
            "timeout": "30"
        }
        
        config["librivox"] = {
            "enabled": "false",
            "base_url": "https://librivox.org/api/feed",
            "timeout": "30",
            "max_results": "100"
        }

    def _add_indexer_defaults(self, config: configparser.ConfigParser):
        """Add sample indexer configuration sections."""
        config["indexer:jackett_sample"] = {
            "name": "Jackett - Sample",
            "enabled": "false",
            "type": "jackett",
            "protocol": "torznab",
            "feed_url": "http://localhost:9117/api/v2.0/indexers/audiobookbay/results/torznab",
            "api_key": "",
            "priority": "1",
            "categories": "3030",
            "verify_ssl": "true",
            "timeout": "30",
            "rate_limit_requests_per_second": "1",
            "rate_limit_max_concurrent": "1"
        }