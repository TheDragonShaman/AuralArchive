import os
import logging
from typing import Dict

class ConfigValidation:
    """Handles configuration validation for all AuralArchive services"""
    
    def __init__(self):
        self.logger = logging.getLogger("ConfigService.Validation")
    
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
            
        except Exception as e:
            self.logger.error(f"Error during configuration validation: {e}")
        
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
                    self.logger.info(f"Created directory: {dir_path}")
            except Exception as e:
                self.logger.error(f"Cannot create directory {dir_path}: {e}")
                return False
        
        self.logger.debug("Directory configuration validation passed")
        return True
    
    def _validate_audiobookshelf(self, abs_config: Dict[str, str]) -> bool:
        """Validate AudioBookShelf configuration."""
        if not abs_config.get('abs_enabled', 'false').lower() == 'true':
            return True  # Not enabled, so considered valid
        
        host = abs_config.get('abs_host', '')
        if not host:
            self.logger.warning("AudioBookShelf host not configured")
            return False
        
        # Basic URL validation
        if not (host.startswith('http://') or host.startswith('https://')):
            self.logger.warning(f"Invalid AudioBookShelf URL format: {host}")
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
            self.logger.warning("Incomplete qBittorrent configuration")
            return False
        
        try:
            port_int = int(port)
            if port_int < 1 or port_int > 65535:
                self.logger.warning(f"Invalid qBittorrent port: {port}")
                return False
        except ValueError:
            self.logger.warning(f"Invalid qBittorrent port format: {port}")
            return False
        
        self.logger.debug("qBittorrent configuration validation passed")
        return True
    
    def _validate_jackett(self, jackett_config: Dict[str, str]) -> bool:
        """Validate Jackett configuration."""
        url = jackett_config.get('jackett_url', '')
        api_key = jackett_config.get('jackett_api_key', '')
        
        if not url or not api_key:
            self.logger.warning("Incomplete Jackett configuration")
            return False
        
        # Basic URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            self.logger.warning(f"Invalid Jackett URL format: {url}")
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
                self.logger.warning(f"Invalid max_results value: {max_results}")
                return False
        except ValueError:
            self.logger.warning(f"Invalid max_results format: {max_results}")
            return False
        
        valid_regions = ['us', 'uk', 'ca', 'au', 'de', 'fr', 'jp', 'in']
        if region not in valid_regions:
            self.logger.warning(f"Invalid region: {region}")
            return False
        
        self.logger.debug("Audible configuration validation passed")
        return True