"""
Module Name: defaults.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Generate and persist default configuration for AuralArchive.
Location:
    /services/config/defaults.py

"""

import configparser
import os
from typing import Dict, Any

from utils.logger import get_module_logger


class ConfigDefaults:
    """Handle default configuration generation for AuralArchive."""

    def __init__(self, config_file: str, logger=None):
        self.config_file = config_file
        self.logger = logger or get_module_logger("Service.Config.Defaults")
    
    def ensure_config_exists(self):
        """Ensure configuration file exists, create default if not."""
        if not os.path.exists(self.config_file):
            self.logger.warning(
                "Configuration file not found; creating default configuration",
                extra={"config_file": self.config_file},
            )
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
            self._add_download_management_config,
            self._add_application_config,
            self._add_auto_search_config,
            self._add_media_management_config,
            self._add_authors_config,
            # Providers/indexer samples removed from defaults
        ]

        for add_section in sections:
            add_section(config)
        
        try:
            with open(self.config_file, "w") as configfile:
                config.write(configfile)
            self.logger.info(
                "Default configuration created",
                extra={"config_file": self.config_file},
            )
        except Exception as exc:
            self.logger.exception(
                "Failed to create default configuration",
                extra={"config_file": self.config_file},
            )
    
    def _add_audible_config(self, config: configparser.ConfigParser):
        """Add Audible API configuration section."""
        config["audible"] = {
            "username": "",
            "password": "",
            "country_code": "us",
            "max_results": "25",
            "cache_duration": "2",
            "auto_authenticate": "True",
            "download_format": "aaxc",
            "download_quality": "best",
            "aax_fallback_enabled": "true",
            "save_voucher": "true",
            "include_cover": "false",
            "include_chapters": "false",
            "include_pdf": "false",
            "concurrent_downloads": "1"
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
            "abs_sync_frequency": "30min",
            "library_path": "",
            "naming_template": "simple",
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
            "import_directory": ""
        }
    
    def _add_download_management_config(self, config: configparser.ConfigParser):
        """Add download management configuration section."""
        config["download_management"] = {
            "downloads_path": "",
            "import_path": "",
            "library_path": "",
            "seeding_enabled": "false",
            "delete_source_after_import": "false",
            "max_concurrent_downloads": "2",
            "monitoring_interval": "2",
            "auto_start_monitoring": "true",
            "monitor_seeding": "true",
            "retry_search_max": "3",
            "retry_download_max": "2",
            "retry_conversion_max": "1",
            "retry_import_max": "2",
            "retry_backoff_seconds": "10"
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
    