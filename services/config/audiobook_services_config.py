"""
Audiobook Services Configuration Manager
Handles configuration for all audiobook management services
"""
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from utils.logger import get_module_logger

@dataclass
class IndexerConfig:
    """Configuration for indexer services"""
    enabled: bool = False
    host: str = "localhost"
    port: int = 9117
    api_key: str = ""
    use_https: bool = False
    timeout: int = 30

@dataclass
class ClientConfig:
    """Configuration for download clients"""
    enabled: bool = False
    host: str = "localhost"
    port: int = 8080
    username: str = ""
    password: str = ""
    use_https: bool = False
    download_path: str = "/downloads/audiobooks"

@dataclass
class ProcessingConfig:
    """Configuration for file processing"""
    enabled: bool = True
    library_path: str = "/audiobooks"
    organization_strategy: str = "author_series_title"
    extract_archives: bool = True
    validate_audio_files: bool = True

class AudiobookServicesConfigManager:
    """
    Manages configuration for all audiobook management services
    Provides unified configuration access and validation
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration manager"""
        self.logger = get_module_logger(self.__class__.__name__)
        
        # Set default config path
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                     'config', 'audiobook_services_config.json')
        
        self.config_path = Path(config_path)
        self._config_data: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self._config_data = json.load(f)
                self.logger.info(f"Loaded audiobook services configuration from {self.config_path}")
            else:
                self.logger.warning(f"Configuration file not found: {self.config_path}")
                self._create_default_config()
        except Exception as e:
            self.logger.error(f"Error loading configuration: {e}")
            self._create_default_config()
    
    def _create_default_config(self):
        """Create default configuration"""
        self.logger.info("Creating default audiobook services configuration")
        
        default_config = {
            "indexers": {
                "jackett": asdict(IndexerConfig(port=9117)),
                "prowlarr": asdict(IndexerConfig(port=9696)),
                "nzbhydra2": asdict(IndexerConfig(port=5076)),
                "librivox": {
                    "enabled": True,
                    "base_url": "https://librivox.org/api",
                    "timeout": 30,
                    "max_results": 100
                }
            },
            "clients": {
                "qbittorrent": asdict(ClientConfig(port=8080)),
                "transmission": asdict(ClientConfig(port=9091)),
                "deluge": asdict(ClientConfig(port=58846))
            },
            "download_coordination": {
                "selector": {
                    "prefer_torrent": True,
                    "min_seeds": 2,
                    "max_size_gb": 10,
                    "preferred_formats": ["mp3", "m4a", "m4b"],
                    "quality_preference": ["320kbps", "256kbps", "192kbps"]
                },
                "queue": {
                    "max_concurrent_downloads": 3,
                    "retry_failed_after_hours": 24,
                    "max_retries": 3,
                    "check_interval_seconds": 60,
                    "cleanup_completed_after_hours": 168
                },
                "coordinator": {
                    "search_timeout_seconds": 120,
                    "download_timeout_hours": 12,
                    "enable_automatic_downloads": False,
                    "require_user_approval": True
                }
            },
            "file_processing": {
                "processor": asdict(ProcessingConfig()),
                "organizer": asdict(ProcessingConfig()),
                "validator": asdict(ProcessingConfig())
            }
        }
        
        self._config_data = default_config
        self.save_config()
    
        """Get configuration for specific indexer"""
        return self._config_data.get("indexers", {}).get(indexer_name, {})
    
        """Get configuration for specific client"""
        return self._config_data.get("clients", {}).get(client_name, {})
    
        """Get download coordination configuration"""
        return self._config_data.get("download_coordination", {})
    
        """Get file processing configuration"""
        return self._config_data.get("file_processing", {})
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration"""
        return self._config_data.get("monitoring", {})
    
    def update_indexer_config(self, indexer_name: str, config: Dict[str, Any]):
        """Update configuration for specific indexer"""
        if "indexers" not in self._config_data:
            self._config_data["indexers"] = {}
        self._config_data["indexers"][indexer_name] = config
        self.save_config()
    
    def update_client_config(self, client_name: str, config: Dict[str, Any]):
        """Update configuration for specific client"""
        if "clients" not in self._config_data:
            self._config_data["clients"] = {}
        self._config_data["clients"][client_name] = config
        self.save_config()
    
    def update_download_coordination_config(self, config: Dict[str, Any]):
        """Update download coordination configuration"""
        self._config_data["download_coordination"] = config
        self.save_config()
    
    def update_file_processing_config(self, config: Dict[str, Any]):
        """Update file processing configuration"""
        self._config_data["file_processing"] = config
        self.save_config()
    
    def save_config(self):
        """Save configuration to file"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info("Configuration saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            raise
    
    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return validation results"""
        results = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        try:
            # Validate indexer configurations
            for indexer_name, config in self._config_data.get("indexers", {}).items():
                if config.get("enabled", False):
                    if not config.get("host"):
                        results["errors"].append(f"Indexer {indexer_name}: Host is required")
                        results["valid"] = False
                    
                    if not isinstance(config.get("port"), int):
                        results["errors"].append(f"Indexer {indexer_name}: Port must be an integer")
                        results["valid"] = False
                    
                    if indexer_name != "librivox" and not config.get("api_key"):
                        results["warnings"].append(f"Indexer {indexer_name}: API key is recommended")
            
            # Validate client configurations
            for client_name, config in self._config_data.get("clients", {}).items():
                if config.get("enabled", False):
                    if not config.get("host"):
                        results["errors"].append(f"Client {client_name}: Host is required")
                        results["valid"] = False
                    
                    if not isinstance(config.get("port"), int):
                        results["errors"].append(f"Client {client_name}: Port must be an integer")
                        results["valid"] = False
                    
                    if not config.get("download_path"):
                        results["errors"].append(f"Client {client_name}: Download path is required")
                        results["valid"] = False
            
            # Validate file processing configuration
            file_config = self._config_data.get("file_processing", {})
            organizer_config = file_config.get("organizer", {})
            
            if organizer_config.get("enabled", False):
                library_path = organizer_config.get("library_path")
                if not library_path:
                    results["errors"].append("File organizer: Library path is required")
                    results["valid"] = False
                elif not os.path.isdir(library_path):
                    results["warnings"].append(f"Library path does not exist: {library_path}")
            
        except Exception as e:
            results["valid"] = False
            results["errors"].append(f"Configuration validation error: {str(e)}")
        
        return results
    
    def get_enabled_services(self) -> Dict[str, list]:
        """Get list of enabled services by category"""
        enabled = {
            "indexers": [],
            "clients": [],
            "processing": []
        }
        
        # Check enabled indexers
        for name, config in self._config_data.get("indexers", {}).items():
            if config.get("enabled", False):
                enabled["indexers"].append(name)
        
        # Check enabled clients
        for name, config in self._config_data.get("clients", {}).items():
            if config.get("enabled", False):
                enabled["clients"].append(name)
        
        # Check enabled processing services
        for name, config in self._config_data.get("file_processing", {}).items():
            if config.get("enabled", False):
                enabled["processing"].append(name)
        
        return enabled
    
    def get_full_config(self) -> Dict[str, Any]:
        """Get complete configuration data"""
        return self._config_data.copy()
    
    def reload_config(self):
        """Reload configuration from file"""
        self._load_config()
        self.logger.info("Configuration reloaded from file")

# Global config manager instance
audiobook_config_manager = AudiobookServicesConfigManager()
