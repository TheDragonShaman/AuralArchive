"""
Module Name: management.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Singleton configuration manager with defaults, validation, and backup helpers.
Location:
    /services/config/management.py

"""

import configparser
import json
import os
import tempfile
import threading
from typing import Dict, Any, Optional, Set

from .defaults import ConfigDefaults
from .validation import ConfigValidation
from .export_import import ConfigExportImport
from utils.logger import get_module_logger
from utils.path_resolver import get_path_resolver


def _get_default_config_dir():
    """Get config directory using path resolver."""
    return get_path_resolver().get_config_dir()


class ConfigService:
    """Enhanced singleton service for configuration management with modular components."""

    _instance: Optional["ConfigService"] = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config_file: str = "config.txt",
        *,
        logger=None,
        defaults: Optional[ConfigDefaults] = None,
        validation: Optional[ConfigValidation] = None,
        export_import: Optional[ConfigExportImport] = None,
    ):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    # Use path resolver for config directory
                    base_dir = _get_default_config_dir()

                    if os.path.isabs(config_file):
                        self.config_file = config_file
                    else:
                        self.config_file = os.path.join(base_dir, os.path.basename(config_file))
                    self.logger = logger or get_module_logger("Service.Config.Service")

                    # Initialize modular components
                    self.defaults = defaults or ConfigDefaults(self.config_file, logger=self.logger)
                    self.validation = validation or ConfigValidation(logger=self.logger)
                    self.export_import = export_import or ConfigExportImport(self.config_file, logger=self.logger)

                    # Ensure config exists
                    self.defaults.ensure_config_exists()

                    ConfigService._initialized = True
    
    def load_config(self) -> configparser.ConfigParser:
        """Load configuration from disk with duplicate section recovery.

        Uses a raw parser with interpolation disabled to tolerate '%' characters
        in values (e.g., titles/paths) without blowing up the parser.
        """
        parser = configparser.RawConfigParser(interpolation=None)
        try:
            with open(self.config_file, "r", encoding="utf-8") as config_handle:
                parser.read_file(config_handle)
            return parser
        except configparser.DuplicateSectionError as duplicate_error:
            self.logger.warning(
                "Duplicate section detected; attempting automatic recovery",
                extra={"config_file": self.config_file, "error": str(duplicate_error)},
            )
            return self._recover_from_duplicate_sections()
        except FileNotFoundError:
            self.logger.error(
                "Configuration file not found",
                extra={"config_file": self.config_file},
            )
            return parser
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.exception(
                "Failed to load configuration",
                extra={"config_file": self.config_file},
            )
            return parser
    
    def get_config_value(self, section: str, key: str, fallback: str = None) -> Optional[str]:
        """Get a specific configuration value."""
        try:
            config = self.load_config()
            return config.get(section.lower(), key.lower(), fallback=fallback)
        except Exception as exc:
            self.logger.exception(
                "Failed to read config value",
                extra={"section": section, "key": key, "config_file": self.config_file},
            )
            return fallback
    
    def get_config_bool(self, section: str, key: str, fallback: bool = False) -> bool:
        """Get a configuration value as boolean."""
        value = self.get_config_value(section, key)
        if value is None:
            return fallback
        return value.lower() in ('true', '1', 'yes', 'on')
    
    def get_config_int(self, section: str, key: str, fallback: int = 0) -> int:
        """Get a configuration value as integer."""
        value = self.get_config_value(section, key)
        if value is None:
            return fallback
        try:
            return int(value)
        except ValueError:
            return fallback
    
    def update_config(self, section: str, key: str, value: str) -> bool:
        """Update a configuration value."""
        try:
            config = self.load_config()
            section = section.lower()
            key = key.lower()
            
            if not config.has_section(section):
                config.add_section(section)

            config.set(section, key, self._coerce_value(value))

            self._write_config(config)
            
            self.logger.info(
                "Updated configuration value",
                extra={"section": section, "key": key, "value": value, "config_file": self.config_file},
            )
            return True
        
        except Exception as exc:
            self.logger.exception(
                "Failed to update configuration value",
                extra={"section": section, "key": key, "config_file": self.config_file},
            )
            return False
    
    def update_multiple_config(self, updates: Dict[str, str]) -> bool:
        """Update multiple configuration values at once."""
        try:
            config = self.load_config()

            # If config failed to load and is empty while file exists, avoid
            # clobbering the file with a near-empty set of updates.
            if not config.sections() and os.path.exists(self.config_file):
                self.logger.error(
                    "Config load returned empty; aborting multi-update to prevent reset",
                    extra={"config_file": self.config_file},
                )
                return False

            for config_key, value in updates.items():
                if '.' not in config_key:
                    continue
                    
                section, key = config_key.split('.', 1)
                section = section.lower()
                key = key.lower()
                
                if not config.has_section(section):
                    config.add_section(section)
                
                config.set(section, key, self._coerce_value(value))
                self.logger.debug(
                    "Updated configuration value",
                    extra={
                        "section": section,
                        "key": key,
                        "value": value,
                        "config_file": self.config_file,
                    },
                )
            
            self._write_config(config)
            self.logger.info(
                "Updated multiple configuration values",
                extra={"count": len(updates), "config_file": self.config_file},
            )
            return True
        
        except Exception as exc:
            self.logger.exception(
                "Failed to update multiple configuration values",
                extra={"config_file": self.config_file},
            )
            return False
    
    def list_config(self) -> Dict[str, Dict[str, str]]:
        """Get all configuration as a dictionary."""
        try:
            config = self.load_config()
            return {section: dict(config.items(section)) for section in config.sections()}
        except Exception as exc:
            self.logger.exception(
                "Failed to list configuration",
                extra={"config_file": self.config_file},
            )
            return {}
    
    # Service-specific helper methods
    def update_section(self, section: str, values: Dict[str, Any]) -> bool:
        """Add or replace values within a configuration section."""
        try:
            config = self.load_config()
            section_name = section.lower()

            if not config.has_section(section_name):
                config.add_section(section_name)

            for key, value in values.items():
                if value is None:
                    continue
                config.set(section_name, key.lower(), self._coerce_value(value))

            self._write_config(config)
            self.logger.info(
                "Updated configuration section",
                extra={"section": section_name, "count": len(values), "config_file": self.config_file},
            )
            return True
        except Exception as exc:
            self.logger.exception(
                "Failed to update configuration section",
                extra={"section": section, "config_file": self.config_file},
            )
            return False

    def remove_section(self, section: str) -> bool:
        """Remove an entire configuration section if it exists."""
        try:
            config = self.load_config()
            section_name = section.lower()

            if not config.has_section(section_name):
                return True

            config.remove_section(section_name)
            self._write_config(config)
            self.logger.info(
                "Removed configuration section",
                extra={"section": section_name, "config_file": self.config_file},
            )
            return True
        except Exception as exc:
            self.logger.exception(
                "Failed to remove configuration section",
                extra={"section": section, "config_file": self.config_file},
            )
            return False

    def get_audiobookshelf_config(self) -> Dict[str, str]:
        """Get AudioBookShelf specific configuration."""
        config = self.load_config()
        if config.has_section('audiobookshelf'):
            return dict(config.items('audiobookshelf'))
        return {}
    
    def update_audiobookshelf_config(self, abs_config: Dict[str, str]) -> bool:
        """Update AudioBookShelf configuration."""
        updates = {}
        for key, value in abs_config.items():
            updates[f'audiobookshelf.{key}'] = value
        
        return self.update_multiple_config(updates)
    
    def is_audiobookshelf_enabled(self) -> bool:
        """Check if AudioBookShelf integration is enabled."""
        return self.get_config_bool('audiobookshelf', 'abs_enabled', False)
    
    def enable_audiobookshelf(self, enabled: bool = True) -> bool:
        """Enable or disable AudioBookShelf integration."""
        return self.update_config('audiobookshelf', 'abs_enabled', str(enabled).lower())
    
    def is_abs_connection_established(self) -> bool:
        """Check if AudioBookShelf connection is established."""
        return self.get_config_bool('audiobookshelf', 'abs_connection_established', False)

    def set_abs_connection_status(self, established: bool) -> bool:
        """Set AudioBookShelf connection status."""
        return self.update_config('audiobookshelf', 'abs_connection_established', str(established).lower())

    def get_abs_auto_sync_frequency(self) -> str:
        """Get AudioBookShelf auto-sync frequency."""
        return self.get_config_value('audiobookshelf', 'abs_auto_sync_frequency', 'daily')

    def is_author_catalog_auto_add_enabled(self) -> bool:
        """Check if author catalog results should be auto-added to the library."""
        return self.get_config_bool('authors', 'auto_add_missing', False)

    def set_author_catalog_auto_add(self, enabled: bool) -> bool:
        """Enable or disable automatic addition of missing author books."""
        return self.update_config('authors', 'auto_add_missing', str(enabled).lower())

    def get_author_catalog_auto_add_limit(self) -> int:
        """Get optional limit for auto-adding author catalog results."""
        return self.get_config_int('authors', 'auto_add_limit', 0)

    def get_author_preferred_languages(self) -> Optional[Set[str]]:
        """Return a normalized set of preferred languages for author catalog filtering."""

        raw_value = self.get_config_value('authors', 'preferred_languages', '')
        if raw_value is None:
            raw_value = ''

        normalized_tokens: Set[str] = set()

        for token in raw_value.replace(';', ',').split(','):
            clean_token = token.strip().lower()
            if not clean_token:
                continue
            if clean_token in {'*', 'all'}:
                return None
            normalized_tokens.add(clean_token)

        if not normalized_tokens:
            return {'english', 'en'}

        return normalized_tokens
    
    def get_download_config(self) -> Dict[str, str]:
        """Get download client configuration (qBittorrent + Jackett)."""
        config = self.load_config()
        download_config = {}
        
        if config.has_section('qbittorrent'):
            download_config.update(dict(config.items('qbittorrent')))
        
        if config.has_section('jackett'):
            download_config.update(dict(config.items('jackett')))
        
        return download_config
    
    # Delegate methods to modular components
    def export_config(self) -> Dict[str, Any]:
        """Export configuration for backup/transfer."""
        config_dict = self.list_config()
        return self.export_import.export_config(config_dict)
    
    def import_config(self, config_data: Dict[str, Any]) -> bool:
        """Import configuration from backup/transfer."""
        return self.export_import.import_config(config_data)
    
    def backup_config(self, backup_dir: str = None) -> str:
        """Create a backup of the current configuration."""
        return self.export_import.backup_config(backup_dir)
    
    def restore_config(self, backup_path: str) -> bool:
        """Restore configuration from backup."""
        return self.export_import.restore_config(backup_path)
    
    def reset_to_defaults(self) -> bool:
        """Reset configuration to default values."""
        return self.export_import.reset_to_defaults(self.defaults)
    
    def validate_config(self) -> Dict[str, bool]:
        """Validate configuration sections and return status."""
        config_dict = self.list_config()
        return self.validation.validate_config(config_dict)
    
    # NEW METHODS FOR SERVICE INTEGRATION
    def get(self, key: str, default=None):
        """Get configuration value by key with dot notation support."""
        try:
            config = self.load_config()
            
            # Support dot notation (section.key)
            if '.' in key:
                section, option = key.split('.', 1)
                if config.has_section(section) and config.has_option(section, option):
                    return config.get(section, option)
            else:
                # Check all sections for the key
                for section in config.sections():
                    if config.has_option(section, key):
                        return config.get(section, key)
            
            return default
        except Exception as e:
            self.logger.exception(
                "Error getting config key",
                extra={"key": key, "config_file": self.config_file},
            )
            return default
    
    def list_clients(self) -> list:
        """Return list of configured download clients."""
        try:
            config = self.load_config()
            clients = []
            
            # Check common client sections
            client_sections = ['qbittorrent', 'transmission', 'deluge']
            
            for section in client_sections:
                if config.has_section(section):
                    enabled = config.getboolean(section, 'enabled', fallback=False)
                    if enabled:
                        clients.append(section)
            
            return clients
        except Exception as e:
            self.logger.exception(
                "Error listing enabled clients",
                extra={"config_file": self.config_file},
            )
            return []
    
    def get_jackett_config(self) -> Dict[str, Any]:
        """Get Jackett indexer configuration."""
        try:
            config = self.load_config()
            if config.has_section('jackett'):
                return {
                    'enabled': config.getboolean('jackett', 'enabled', fallback=False),
                    'host': config.get('jackett', 'host', fallback='localhost'),
                    'port': config.getint('jackett', 'port', fallback=9117),
                    'api_key': config.get('jackett', 'api_key', fallback=''),
                    'use_https': config.getboolean('jackett', 'use_https', fallback=False),
                    'timeout': config.getint('jackett', 'timeout', fallback=30)
                }
            return {'enabled': False}
        except Exception as e:
            self.logger.exception(
                "Error getting Jackett config",
                extra={"config_file": self.config_file},
            )
            return {'enabled': False}
    
    def get_prowlarr_config(self) -> Dict[str, Any]:
        """Get Prowlarr indexer configuration."""
        try:
            config = self.load_config()
            if config.has_section('prowlarr'):
                return {
                    'enabled': config.getboolean('prowlarr', 'enabled', fallback=False),
                    'host': config.get('prowlarr', 'host', fallback='localhost'),
                    'port': config.getint('prowlarr', 'port', fallback=9696),
                    'api_key': config.get('prowlarr', 'api_key', fallback=''),
                    'use_https': config.getboolean('prowlarr', 'use_https', fallback=False),
                    'timeout': config.getint('prowlarr', 'timeout', fallback=30)
                }
            return {'enabled': False}
        except Exception as e:
            self.logger.exception(
                "Error getting Prowlarr config",
                extra={"config_file": self.config_file},
            )
            return {'enabled': False}
    
    def get_nzbhydra_config(self) -> Dict[str, Any]:
        """Get NZBHydra2 indexer configuration."""
        try:
            config = self.load_config()
            if config.has_section('nzbhydra2'):
                return {
                    'enabled': config.getboolean('nzbhydra2', 'enabled', fallback=False),
                    'host': config.get('nzbhydra2', 'host', fallback='localhost'),
                    'port': config.getint('nzbhydra2', 'port', fallback=5076),
                    'api_key': config.get('nzbhydra2', 'api_key', fallback=''),
                    'use_https': config.getboolean('nzbhydra2', 'use_https', fallback=False),
                    'timeout': config.getint('nzbhydra2', 'timeout', fallback=30)
                }
            return {'enabled': False}
        except Exception as e:
            self.logger.exception(
                "Error getting NZBHydra2 config",
                extra={"config_file": self.config_file},
            )
            return {'enabled': False}
    
    def get_librivox_config(self) -> Dict[str, Any]:
        """Get LibriVox indexer configuration."""
        try:
            config = self.load_config()
            if config.has_section('librivox'):
                return {
                    'enabled': config.getboolean('librivox', 'enabled', fallback=True),
                    'base_url': config.get('librivox', 'base_url', fallback='https://librivox.org/api/feed'),
                    'timeout': config.getint('librivox', 'timeout', fallback=30),
                    'max_results': config.getint('librivox', 'max_results', fallback=100)
                }
            return {'enabled': True, 'base_url': 'https://librivox.org/api/feed', 'timeout': 30, 'max_results': 100}
        except Exception as e:
            self.logger.exception(
                "Error getting LibriVox config",
                extra={"config_file": self.config_file},
            )
            return {'enabled': True}
    
    def get_section(self, section_name: str) -> Dict[str, Any]:
        """Get all configuration values from a specific section."""
        try:
            config = self.load_config()
            if not config.has_section(section_name):
                return {}
            
            section_dict = {}
            for key, value in config.items(section_name):
                # Try to convert common types
                if value.lower() in ('true', 'false'):
                    section_dict[key] = config.getboolean(section_name, key)
                elif value.isdigit():
                    section_dict[key] = config.getint(section_name, key)
                else:
                    section_dict[key] = value
            
            return section_dict
        except Exception as e:
            self.logger.exception(
                "Error getting configuration section",
                extra={"section": section_name, "config_file": self.config_file},
            )
            return {}

    # ------------------------------------------------------------------
    # Indexer configuration helpers
    # ------------------------------------------------------------------
    def list_indexers_config(self) -> Dict[str, Dict[str, Any]]:
        """Return all configured indexers keyed by indexer identifier."""
        config = self.load_config()
        indexers = self._extract_indexer_sections(config)

        if indexers:
            return indexers

        legacy_path = os.path.join(os.path.dirname(self.config_file), 'indexers.json')
        if not os.path.exists(legacy_path):
            return {}

        if self._migrate_legacy_indexers(legacy_path):
            config = self.load_config()
            return self._extract_indexer_sections(config)

        return {}

    def get_indexer_config(self, indexer_key: str) -> Dict[str, Any]:
        """Get configuration dictionary for a specific indexer."""
        config = self.load_config()
        section_name = self._get_indexer_section_name(indexer_key)
        if not config.has_section(section_name):
            return {}
        return self._parse_indexer_section(config, section_name)

    def set_indexer_config(self, indexer_key: str, config_data: Dict[str, Any]) -> bool:
        """Persist configuration for a specific indexer."""
        section_name = self._get_indexer_section_name(indexer_key)
        try:
            config = self.load_config()
            if config.has_section(section_name):
                config.remove_section(section_name)
            config.add_section(section_name)

            normalized = self._normalize_indexer_config(config_data)
            for key, value in normalized.items():
                config.set(section_name, key, value)

            self._write_config(config)
            self.logger.info(
                "Saved indexer configuration",
                extra={"indexer": indexer_key, "config_file": self.config_file},
            )
            return True
        except Exception as exc:
            self.logger.exception(
                "Failed to save indexer configuration",
                extra={"indexer": indexer_key, "config_file": self.config_file},
            )
            return False

    def delete_indexer_config(self, indexer_key: str) -> bool:
        """Remove configuration for a specific indexer."""
        section_name = self._get_indexer_section_name(indexer_key)
        try:
            config = self.load_config()
            if not config.has_section(section_name):
                return True
            config.remove_section(section_name)
            self._write_config(config)
            self.logger.info(
                "Removed indexer configuration",
                extra={"indexer": indexer_key, "config_file": self.config_file},
            )
            return True
        except Exception as exc:
            self.logger.exception(
                "Failed to remove indexer configuration",
                extra={"indexer": indexer_key, "config_file": self.config_file},
            )
            return False

    # AudiobookServicesConfigManager compatibility methods
    def get_full_config(self) -> Dict[str, Any]:
        """Get complete configuration (compatibility method)."""
        return self.list_config()
    
    def get_enabled_services(self) -> Dict[str, bool]:
        """Get status of enabled services."""
        services = {}
        config = self.load_config()
        
        # Check common service sections
        service_sections = ['audiobookshelf', 'qbittorrent', 'jackett', 'prowlarr', 'nzbhydra2', 'librivox']
        
        for section in service_sections:
            if config.has_section(section):
                services[section] = config.getboolean(section, 'enabled', fallback=False)
            else:
                services[section] = False
        
        return services
    
        """Get configuration for specific indexer."""
        indexer_map = {
            'jackett': self.get_jackett_config,
            'prowlarr': self.get_prowlarr_config,
            'nzbhydra2': self.get_nzbhydra_config,
            'librivox': self.get_librivox_config
        }
        
        if indexer_name in indexer_map:
            return indexer_map[indexer_name]()
        else:
            return self.get_section(indexer_name)
    
    def update_indexer_config(self, indexer_name: str, config_data: Dict[str, Any]) -> bool:
        """Update configuration for specific indexer."""
        try:
            updates = {}
            for key, value in config_data.items():
                updates[f'{indexer_name}.{key}'] = value
            
            return self.update_multiple_config(updates)
        except Exception as e:
            self.logger.exception(
                "Error updating indexer config",
                extra={"indexer": indexer_name, "config_file": self.config_file},
            )
            return False
    
        """Get configuration for specific download client."""
        return self.get_section(client_name)
    
    def update_client_config(self, client_name: str, config_data: Dict[str, Any]) -> bool:
        """Update configuration for specific download client."""
        try:
            updates = {}
            for key, value in config_data.items():
                updates[f'{client_name}.{key}'] = value
            
            return self.update_multiple_config(updates)
        except Exception as e:
            self.logger.exception(
                "Error updating client config",
                extra={"client": client_name, "config_file": self.config_file},
            )
            return False
    
        """Get download coordination configuration."""
        config = {}
        config.update(self.get_section('download'))
        config.update(self.get_section('auto_search'))
        return config
    
    def update_download_coordination_config(self, config_data: Dict[str, Any]) -> bool:
        """Update download coordination configuration."""
        try:
            # Separate config by likely sections
            download_keys = ['enable_completed_handling', 'remove_completed', 'check_interval']
            auto_search_keys = ['auto_download_enabled', 'quality_threshold']
            
            updates = {}
            for key, value in config_data.items():
                if key in download_keys:
                    updates[f'download.{key}'] = value
                elif key in auto_search_keys:
                    updates[f'auto_search.{key}'] = value
                else:
                    # Default to download section
                    updates[f'download.{key}'] = value
            
            return self.update_multiple_config(updates)
        except Exception as e:
            self.logger.exception(
                "Error updating download coordination config",
                extra={"config_file": self.config_file},
            )
            return False
    
        """Get file processing configuration."""
        config = {}
        config.update(self.get_section('media_management'))
        config.update(self.get_section('metadata'))
        return config
    
    def update_file_processing_config(self, config_data: Dict[str, Any]) -> bool:
        """Update file processing configuration."""
        try:
            # Separate config by likely sections
            media_keys = ['monitor_dirs', 'target_dir', 'dir_template', 'file_template', 'mode', 'file_operation', 'monitor_interval', 'atomic']
            metadata_keys = ['primary_source', 'write_metadata', 'scrape_additional', 'download_cover_art', 'cover_art_size', 'cover_art_format']
            
            updates = {}
            for key, value in config_data.items():
                if key in media_keys:
                    updates[f'media_management.{key}'] = value
                elif key in metadata_keys:
                    updates[f'metadata.{key}'] = value
                else:
                    # Default to media_management section
                    updates[f'media_management.{key}'] = value
            
            return self.update_multiple_config(updates)
        except Exception as e:
            self.logger.exception(
                "Error updating file processing config",
                extra={"config_file": self.config_file},
            )
            return False
    
    def reload_config(self) -> bool:
        """Reload configuration (no-op for file-based config)."""
        # File-based config is always fresh, so this is a no-op
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _write_config(self, config: configparser.ConfigParser) -> None:
        """Persist the current configuration parser to disk."""
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=os.path.dirname(self.config_file),
                prefix=os.path.basename(self.config_file) + ".",
                suffix=".tmp",
            ) as configfile:
                temp_path = configfile.name
                config.write(configfile)
                configfile.flush()
                os.fsync(configfile.fileno())
            os.replace(temp_path, self.config_file)
        except FileNotFoundError:
            with open(self.config_file, "w", encoding="utf-8") as configfile:
                config.write(configfile)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @staticmethod
    def _coerce_value(value: Any) -> str:
        """Normalize configuration values to strings."""
        if isinstance(value, bool):
            return 'true' if value else 'false'
        return '' if value is None else str(value)

    def _recover_from_duplicate_sections(self) -> configparser.ConfigParser:
        """Attempt to repair duplicate sections by rewriting a clean copy."""
        recovery_parser = configparser.ConfigParser(strict=False)
        try:
            with open(self.config_file, "r", encoding="utf-8") as config_handle:
                recovery_parser.read_file(config_handle)

            cleaned_parser = configparser.ConfigParser()
            for section in recovery_parser.sections():
                cleaned_parser[section] = {key: value for key, value in recovery_parser.items(section)}

            self._write_config(cleaned_parser)
            self.logger.info(
                "Duplicate sections removed; configuration rewritten",
                extra={"config_file": self.config_file},
            )
            return cleaned_parser
        except Exception as exc:
            self.logger.exception(
                "Failed to recover configuration from duplicate sections",
                extra={"config_file": self.config_file},
            )
            return configparser.ConfigParser()

    # ------------------------------------------------------------------
    # Indexer helper methods
    # ------------------------------------------------------------------
    def _extract_indexer_sections(self, config: configparser.ConfigParser) -> Dict[str, Dict[str, Any]]:
        indexers: Dict[str, Dict[str, Any]] = {}
        for section in config.sections():
            if not section.startswith('indexer:'):
                continue
            key = section.split(':', 1)[1]
            indexers[key] = self._parse_indexer_section(config, section)
        return indexers

    def _parse_indexer_section(self, config: configparser.ConfigParser, section: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        items = dict(config.items(section))

        data['name'] = items.get('name', '')
        data['enabled'] = config.getboolean(section, 'enabled', fallback=False)
        data['feed_url'] = items.get('feed_url', '')
        data['base_url'] = items.get('base_url', '')
        data['api_key'] = items.get('api_key', '')
        data['session_id'] = items.get('session_id', '')
        data['type'] = items.get('type', 'jackett')
        data['protocol'] = items.get('protocol', 'torznab')
        data['search_type'] = items.get('search_type', 'all').lower() or 'all'
        data['priority'] = config.getint(section, 'priority', fallback=999)
        categories = items.get('categories', '')
        if categories:
            data['categories'] = [cat.strip() for cat in categories.split(',') if cat.strip()]
        else:
            data['categories'] = []
        data['verify_ssl'] = config.getboolean(section, 'verify_ssl', fallback=True)
        data['timeout'] = config.getint(section, 'timeout', fallback=30)

        rps = items.get('rate_limit_requests_per_second') or items.get('rate_limit.request_per_second')
        max_concurrent = items.get('rate_limit_max_concurrent') or items.get('rate_limit.max_concurrent')
        data['rate_limit'] = {
            'requests_per_second': int(rps) if self._is_int(rps) else 1,
            'max_concurrent': int(max_concurrent) if self._is_int(max_concurrent) else 1
        }

        return data

    @staticmethod
    def _is_int(value: Any) -> bool:
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False

    def _normalize_indexer_config(self, config_data: Dict[str, Any]) -> Dict[str, str]:
        normalized: Dict[str, str] = {}

        normalized['name'] = self._coerce_value(config_data.get('name', ''))
        normalized['enabled'] = self._coerce_value(config_data.get('enabled', False))
        normalized['feed_url'] = self._coerce_value(config_data.get('feed_url', ''))
        normalized['base_url'] = self._coerce_value(config_data.get('base_url', ''))
        normalized['api_key'] = self._coerce_value(config_data.get('api_key', ''))
        normalized['session_id'] = self._coerce_value(config_data.get('session_id', ''))
        normalized['type'] = self._coerce_value(config_data.get('type', 'jackett')).lower()
        normalized['protocol'] = self._coerce_value(config_data.get('protocol', 'torznab')).lower()
        normalized['search_type'] = self._coerce_value(str(config_data.get('search_type', 'all')).lower()) or 'all'
        normalized['priority'] = self._coerce_value(config_data.get('priority', 999))

        categories = config_data.get('categories') or []
        if isinstance(categories, (list, tuple)):
            categories_value = ','.join(str(cat).strip() for cat in categories if str(cat).strip())
        else:
            categories_value = self._coerce_value(categories)
        normalized['categories'] = categories_value

        normalized['verify_ssl'] = self._coerce_value(config_data.get('verify_ssl', True))
        normalized['timeout'] = self._coerce_value(config_data.get('timeout', 30))

        rate_limit = config_data.get('rate_limit') or {}
        normalized['rate_limit_requests_per_second'] = self._coerce_value(rate_limit.get('requests_per_second', 1))
        normalized['rate_limit_max_concurrent'] = self._coerce_value(rate_limit.get('max_concurrent', 1))

        return normalized

    @staticmethod
    def _get_indexer_section_name(indexer_key: str) -> str:
        return f"indexer:{indexer_key.strip().lower()}"

    def _migrate_legacy_indexers(self, legacy_path: str) -> bool:
        """Migrate indexer data from legacy JSON file to config.txt."""
        try:
            with open(legacy_path, 'r', encoding='utf-8') as legacy_file:
                legacy_indexers = json.load(legacy_file)
        except Exception as exc:
            self.logger.exception(
                "Failed to read legacy indexers.json",
                extra={"legacy_path": legacy_path},
            )
            return False

        migrated_any = False
        for key, config_data in legacy_indexers.items():
            if not isinstance(config_data, dict):
                continue
            if self.set_indexer_config(key, config_data):
                migrated_any = True

        if migrated_any:
            try:
                backup_path = f"{legacy_path}.legacy"
                os.replace(legacy_path, backup_path)
                self.logger.info(
                    "Migrated legacy indexers.json to config.txt",
                    extra={"backup_path": backup_path, "legacy_path": legacy_path, "config_file": self.config_file},
                )
            except OSError as exc:
                self.logger.warning(
                    "Migrated indexers but failed to archive legacy file",
                    extra={"legacy_path": legacy_path, "backup_error": str(exc)},
                )

        return migrated_any