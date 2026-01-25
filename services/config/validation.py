"""
Module Name: validation.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Validate configuration sections for AuralArchive services.
Location:
    /services/config/validation.py

"""

import os
from typing import Dict

from utils.logger import get_module_logger


class ConfigValidation:
    """Handle configuration validation for all AuralArchive services."""

    def __init__(self, logger=None, **_kwargs):
        # Accept extra kwargs defensively to avoid instantiation errors from legacy call sites
        self.logger = logger or get_module_logger("Service.Config.Validation")
    
    def validate_config(self, config: Dict[str, Dict[str, str]]) -> Dict[str, bool]:
        """Validate configuration sections and return status."""
        validation_results = {}
        
        try:
            # Validate directories
            directories = config.get('directories', {})
            validation_results['directories'] = self._validate_directories(directories)
            
            # Validate audiobookshelf
            abs_config = config.get('audiobookshelf', {})
            validation_results['audiobookshelf'] = self._validate_audiobookshelf(abs_config)
            
            # Validate qbittorrent
            qb_config = config.get('qbittorrent', {})
            validation_results['qbittorrent'] = self._validate_qbittorrent(qb_config)
            
            # Validate jackett
            jackett_config = config.get('jackett', {})
            validation_results['jackett'] = self._validate_jackett(jackett_config)
            
            # Validate audible
            audible_config = config.get('audible', {})
            validation_results['audible'] = self._validate_audible(audible_config)
            
        except Exception as exc:
            self.logger.exception(
                "Error during configuration validation",
                extra={"config_sections": list(config.keys()) if config else []},
            )
        
        return validation_results
    
    def _validate_directories(self, directories: Dict[str, str]) -> bool:
        """Validate directory configuration."""
        required_dirs = ['source_dir', 'import_dir', 'library_dir']
        
        for dir_key in required_dirs:
            dir_path = directories.get(dir_key, '')
            if not dir_path:
                self.logger.warning(f"Missing directory configuration: {dir_key}")
                return False
            
            # Check if directory exists or can be created
            try:
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, exist_ok=True)
                    self.logger.info("Created directory", extra={"path": dir_path})
            except Exception as exc:
                self.logger.exception(
                    "Cannot create directory",
                    extra={"path": dir_path},
                )
                return False
        
        self.logger.debug("Directory configuration validation passed")
        return True
    
    def _validate_audiobookshelf(self, abs_config: Dict[str, str]) -> bool:
        """Validate AudioBookShelf configuration."""
        if not abs_config.get('abs_enabled', 'false').lower() == 'true':
            return True  # Not enabled, so considered valid
        
        host = abs_config.get('abs_host', '')
        if not host:
            self.logger.warning(
                "AudioBookShelf host not configured",
                extra={"abs_enabled": abs_config.get('abs_enabled')},
            )
            return False
        
        # Basic URL validation
        if not (host.startswith('http://') or host.startswith('https://')):
            self.logger.warning(
                "Invalid AudioBookShelf URL format",
                extra={"abs_host": host},
            )
            return False
        
        self.logger.debug("AudioBookShelf configuration validation passed")
        return True
    
    def _validate_qbittorrent(self, qb_config: Dict[str, str]) -> bool:
        """Validate qBittorrent configuration."""
        host = qb_config.get('qb_host', '')
        port = qb_config.get('qb_port', '')
        username = qb_config.get('qb_username', '')
        password = qb_config.get('qb_password', '')
        
        if not all([host, port, username, password]):
            self.logger.warning("Incomplete qBittorrent configuration", extra=qb_config)
            return False
        
        try:
            port_int = int(port)
            if port_int < 1 or port_int > 65535:
                self.logger.warning(
                    "Invalid qBittorrent port value",
                    extra={"qb_port": port},
                )
                return False
        except ValueError:
            self.logger.warning(
                "Invalid qBittorrent port format",
                extra={"qb_port": port},
            )
            return False
        
        self.logger.debug("qBittorrent configuration validation passed")
        return True
    
    def _validate_jackett(self, jackett_config: Dict[str, str]) -> bool:
        """Validate Jackett configuration."""
        url = jackett_config.get('jackett_url', '')
        api_key = jackett_config.get('jackett_api_key', '')
        
        if not url or not api_key:
            self.logger.warning("Incomplete Jackett configuration", extra=jackett_config)
            return False
        
        # Basic URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            self.logger.warning(
                "Invalid Jackett URL format",
                extra={"jackett_url": url},
            )
            return False
        
        self.logger.debug("Jackett configuration validation passed")
        return True
    
    def _validate_audible(self, audible_config: Dict[str, str]) -> bool:
        """Validate Audible configuration."""
        max_results = audible_config.get('max_results', '25')
        region = audible_config.get('default_region', 'us')
        
        try:
            max_results_int = int(max_results)
            if max_results_int < 5 or max_results_int > 100:
                self.logger.warning(
                    "Invalid max_results value",
                    extra={"max_results": max_results},
                )
                return False
        except ValueError:
            self.logger.warning(
                "Invalid max_results format",
                extra={"max_results": max_results},
            )
            return False
        
        valid_regions = ['us', 'uk', 'ca', 'au', 'de', 'fr', 'jp', 'in']
        if region not in valid_regions:
            self.logger.warning("Invalid region", extra={"region": region})
            return False
        
        self.logger.debug("Audible configuration validation passed")
        return True