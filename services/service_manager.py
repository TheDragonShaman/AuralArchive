"""
Module Name: service_manager.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Centralized service initialization and access point for backend services.

Location:
    /services/service_manager.py

"""

import threading
from typing import Any, Dict, Optional

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Manager")


class ServiceManager:
    """
    Singleton service manager to handle all service instances
    Ensures each service is initialized only once and provides thread-safe access
    """
    _instance: Optional['ServiceManager'] = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, *, logger=None):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._services: Dict[str, Any] = {}
                    self.logger = logger or _LOGGER
                    ServiceManager._initialized = True

    def _log_initialized(self, service_name: str):
        self.logger.success("Service initialized", extra={"service": service_name})

    def _log_failed(self, service_name: str, error: Optional[Exception] = None):
        log_extra = {"service": service_name, "error": str(error) if error else None}
        if error:
            self.logger.exception("Service initialization failed", extra=log_extra)
        else:
            self.logger.error("Service initialization failed", extra=log_extra)

    def get_database_service(self):
        """Get or create DatabaseService instance"""
        if 'database' not in self._services:
            with self._lock:
                if 'database' not in self._services:
                    # Import here to avoid circular imports
                    from services.database import DatabaseService
                    self._services['database'] = DatabaseService()
                    self._log_initialized("database")
        return self._services['database']
    
    def get_audible_service(self):
        """Get or create AudibleService instance"""
        if 'audible' not in self._services:
            with self._lock:
                if 'audible' not in self._services:
                    # Import here to avoid circular imports
                    from services.audible.audible_catalog_service.audible_catalog_service import AudibleService
                    self._services['audible'] = AudibleService()
                    self._log_initialized("audible")
        return self._services['audible']
    
    def get_audible_wishlist_service(self):
        """Get or create AudibleWishlistService instance"""
        if 'audible_wishlist' not in self._services:
            with self._lock:
                if 'audible_wishlist' not in self._services:
                    # Import here to avoid circular imports
                    from services.audible.audible_wishlist_service.audible_wishlist_service import get_audible_wishlist_service
                    
                    # Get the config service
                    config_service = self.get_config_service()
                    
                    # Initialize wishlist service without auto-start (controlled by app.py)
                    self._services['audible_wishlist'] = get_audible_wishlist_service(
                        config_service=config_service,
                        sync_interval_minutes=15,
                        auto_start=False  # Don't auto-start, let app.py control startup
                    )
                    self._log_initialized("audible_wishlist")
        return self._services['audible_wishlist']
    
    def get_audible_metadata_sync_service(self):
        """Get or create AudibleMetadataSyncService instance"""
        if 'audible_metadata_sync' not in self._services:
            with self._lock:
                if 'audible_metadata_sync' not in self._services:
                    # Import here to avoid circular imports
                    from services.audible.audible_metadata_sync_service.audible_metadata_sync_service import AudibleMetadataSyncService
                    
                    # Initialize with logger
                    from utils.logger import get_module_logger
                    logger = get_module_logger("Service.Audible.MetadataSync")
                    
                    self._services['audible_metadata_sync'] = AudibleMetadataSyncService(logger=logger)
                    self._log_initialized("audible_metadata_sync")
        return self._services['audible_metadata_sync']
    
    def get_audible_service_manager(self):
        """Get or create AudibleServiceManager instance and initialize series service"""
        if 'audible_service_manager' not in self._services:
            with self._lock:
                if 'audible_service_manager' not in self._services:
                    # Import here to avoid circular imports
                    from services.audible.audible_service_manager import AudibleServiceManager
                    
                    # Get config service for initialization
                    config_service = self.get_config_service()
                    
                    # Create AudibleServiceManager
                    manager = AudibleServiceManager(config_service=config_service)
                    
                    # Initialize series service with database service
                    db_service = self.get_database_service()
                    success = manager.initialize_series_service(db_service)
                    
                    if success:
                        self.logger.debug(
                            "AudibleServiceManager initialized with series service",
                            extra={"service": "audible_service_manager", "series_initialized": True},
                        )
                    else:
                        self.logger.warning(
                            "AudibleServiceManager created but series service not initialized",
                            extra={"service": "audible_service_manager", "series_initialized": False},
                        )
                    
                    self._services['audible_service_manager'] = manager
        return self._services['audible_service_manager']
    
    def get_audiobookshelf_service(self):
        """Get or create AudioBookShelfService instance"""
        if 'audiobookshelf' not in self._services:
            with self._lock:
                if 'audiobookshelf' not in self._services:
                    # Import here to avoid circular imports
                    from services.audiobookshelf import AudioBookShelfService
                    self._services['audiobookshelf'] = AudioBookShelfService()
                    self._log_initialized("audiobookshelf")
        return self._services['audiobookshelf']
    
    def get_config_service(self):
        """Get or create ConfigService instance"""
        if 'config' not in self._services:
            with self._lock:
                if 'config' not in self._services:
                    # Import from modular directory
                    from services.config import ConfigService
                    self._services['config'] = ConfigService()
                    self._log_initialized("config")
        return self._services['config']
    
    def get_audiobook_config_manager(self):
        """Get ConfigService instance (legacy compatibility)"""
        # Return the main config service for backward compatibility
        return self.get_config_service()
    
    def get_metadata_service(self):
        """Get or create MetadataService instance"""
        if 'metadata' not in self._services:
            with self._lock:
                if 'metadata' not in self._services:
                    # Import here to avoid circular imports
                    from services.metadata import MetadataUpdateService
                    self._services['metadata'] = MetadataUpdateService()
                    self._log_initialized("metadata")
        return self._services['metadata']
    
    def get_metadata_update_service(self):
        """Get or create MetadataUpdateService instance"""
        if 'metadata_update' not in self._services:
            with self._lock:
                if 'metadata_update' not in self._services:
                    # Import from single file (separate from modular metadata service)
                    from services.metadata import MetadataUpdateService
                    self._services['metadata_update'] = MetadataUpdateService()
                    self._log_initialized("metadata_update")
        return self._services['metadata_update']
    












    # NEW SERVICE METHODS - AUDNEXUS
    def get_audnexus_service(self):
        """Get or create AudnexusService instance"""
        if 'audnexus' not in self._services:
            with self._lock:
                if 'audnexus' not in self._services:
                    try:
                        from services.audnexus import AudnexusService
                        self._services['audnexus'] = AudnexusService()
                        self._log_initialized("audnexus")
                    except Exception as exc:
                        self._log_failed("audnexus", exc)
                        return None
        return self._services.get('audnexus')
    
    def get_conversion_service(self):
        """Get or create ConversionService instance"""
        if 'conversion' not in self._services:
            with self._lock:
                if 'conversion' not in self._services:
                    try:
                        from services.conversion_service import ConversionService
                        self._services['conversion'] = ConversionService()
                        self._log_initialized("conversion")
                    except Exception as exc:
                        self._log_failed("conversion", exc)
                        return None
        return self._services.get('conversion')
    
    def get_hybrid_audiobook_service(self):
        """Get or create HybridAudiobookService instance"""
        if 'hybrid_audiobook' not in self._services:
            with self._lock:
                if 'hybrid_audiobook' not in self._services:
                    try:
                        from services.audnexus.hybrid_service import HybridAudiobookService
                        self._services['hybrid_audiobook'] = HybridAudiobookService()
                        self._log_initialized("hybrid_audiobook")
                    except Exception as exc:
                        self._log_failed("hybrid_audiobook", exc)
                        return None
        return self._services.get('hybrid_audiobook')
    
    def get_search_engine_service(self):
        """Get or create SearchEngineService instance"""
        if 'search_engine' not in self._services:
            with self._lock:
                if 'search_engine' not in self._services:
                    try:
                        from services.search_engine.search_engine_service import SearchEngineService
                        self._services['search_engine'] = SearchEngineService()
                        self._log_initialized("search_engine")
                    except Exception as exc:
                        self._log_failed("search_engine", exc)
                        return None
        return self._services.get('search_engine')
    
    def get_indexer_manager_service(self):
        """Get or create IndexerServiceManager instance"""
        if 'indexer_manager' not in self._services:
            with self._lock:
                if 'indexer_manager' not in self._services:
                    try:
                        from services.indexers import get_indexer_service_manager
                        self._services['indexer_manager'] = get_indexer_service_manager()
                        self._log_initialized("indexer_manager")
                    except Exception as exc:
                        self._log_failed("indexer_manager", exc)
                        return None
        return self._services.get('indexer_manager')
    
    def get_file_naming_service(self):
        """Get or create FileNamingService instance"""
        if 'file_naming' not in self._services:
            with self._lock:
                if 'file_naming' not in self._services:
                    try:
                        from services.file_naming import FileNamingService
                        self._services['file_naming'] = FileNamingService()
                        self._log_initialized("file_naming")
                    except Exception as exc:
                        self._log_failed("file_naming", exc)
                        return None
        return self._services.get('file_naming')
    
    def get_import_service(self):
        """Get or create ImportService instance"""
        if 'import' not in self._services:
            with self._lock:
                if 'import' not in self._services:
                    try:
                        from services.import_service import ImportService
                        self._services['import'] = ImportService()
                        self._log_initialized("import")
                    except Exception as exc:
                        self._log_failed("import", exc)
                        return None
        return self._services.get('import')
    
    def get_automatic_download_service(self):
        """Get or create AutomaticDownloadService instance"""
        if 'automatic_download' not in self._services:
            with self._lock:
                if 'automatic_download' not in self._services:
                    try:
                        from services.automation import AutomaticDownloadService
                        service = AutomaticDownloadService()
                        # Start automatically so it can react to config toggles immediately
                        service.start()
                        self._services['automatic_download'] = service
                        self._log_initialized("automatic_download")
                    except Exception as exc:
                        self._log_failed("automatic_download", exc)
                        return None
        return self._services.get('automatic_download')

    def get_download_management_service(self):
        """Get or create DownloadManagementService instance"""
        if 'download_management' not in self._services:
            with self._lock:
                if 'download_management' not in self._services:
                    try:
                        from services.download_management import DownloadManagementService
                        self._services['download_management'] = DownloadManagementService()
                        self._log_initialized("download_management")
                    except Exception as exc:
                        self._log_failed("download_management", exc)
                        return None
        return self._services.get('download_management')

    def get_status_service(self):
        """Get or create StatusService instance."""
        if 'status' not in self._services:
            with self._lock:
                if 'status' not in self._services:
                    try:
                        from services.status_service import StatusService
                        self._services['status'] = StatusService()
                        self._log_initialized("status")
                    except Exception as exc:
                        self._log_failed("status", exc)
                        return None
        return self._services.get('status')

    
    def reset_service(self, service_name: str):
        """Reset a specific service"""
        if service_name in self._services:
            with self._lock:
                if service_name in self._services:
                    del self._services[service_name]
                    self.logger.info("Reset service", extra={"service": service_name})
    
    def reset_all_services(self):
        """Reset all services"""
        with self._lock:
            self._services.clear()
            self.logger.info("Reset all services", extra={"service": "all"})
    
    def get_service_status(self) -> Dict[str, bool]:
        """Get status of all services"""
        return {
            service_name: service_name in self._services 
            for service_name in [
                # Core services
                'database', 'audible', 'audiobookshelf', 'config', 'audiobook_config',
                'metadata', 'metadata_update', 'audnexus', 'conversion', 'hybrid_audiobook',
                # Search services
                'search_engine', 'indexer_manager',
                # Communication services
                'event_bus', 'service_coordinator',
            ]
        }

    async def start_all_services(self):
        """Start all services that support async startup"""
        try:
            # Event bus and coordinator services removed
            self.logger.success("Async services started", extra={"services_started": []})
            
        except Exception as e:
            self.logger.error("Error starting services", extra={"error": str(e)})
            raise

    async def stop_all_services(self):
        """Stop all services that support async shutdown"""
        try:
            # Event bus services removed - no services to stop
            self.logger.success("Async services stopped", extra={"services_stopped": []})
            
        except Exception as e:
            self.logger.error("Error stopping services", extra={"error": str(e)})
            raise


# Global service manager instance
service_manager = ServiceManager()

# Convenience functions for easy access
def get_database_service():
    """Get DatabaseService instance"""
    return service_manager.get_database_service()

def get_audible_service():
    """Get AudibleService instance"""
    return service_manager.get_audible_service()

def get_audible_service_manager():
    """Get AudibleServiceManager instance"""
    return service_manager.get_audible_service_manager()

def get_audiobookshelf_service():
    """Get AudioBookShelfService instance"""
    return service_manager.get_audiobookshelf_service()

def get_config_service():
    """Get ConfigService instance"""
    return service_manager.get_config_service()

def get_audiobook_config_manager():
    """Get ConfigService instance (legacy compatibility)"""
    return service_manager.get_config_service()

def get_metadata_service():
    """Get MetadataService instance"""
    return service_manager.get_metadata_service()

def get_metadata_update_service():
    """Get MetadataUpdateService instance"""
    return service_manager.get_metadata_update_service()

def get_audnexus_service():
    """Get AudnexusService instance"""
    return service_manager.get_audnexus_service()

def get_hybrid_audiobook_service():
    """Get HybridAudiobookService instance"""
    return service_manager.get_hybrid_audiobook_service()

def get_audible_wishlist_service():
    """Get AudibleWishlistService instance"""
    return service_manager.get_audible_wishlist_service()

def get_audible_metadata_sync_service():
    """Get AudibleMetadataSyncService instance"""
    return service_manager.get_audible_metadata_sync_service()

def get_conversion_service():
    """Get ConversionService instance"""
    return service_manager.get_conversion_service()

def get_search_engine_service():
    """Get SearchEngineService instance"""
    return service_manager.get_search_engine_service()

def get_indexer_manager_service():
    """Get IndexerServiceManager instance"""
    return service_manager.get_indexer_manager_service()

def get_file_naming_service():
    """Get FileNamingService instance"""
    return service_manager.get_file_naming_service()

def get_import_service():
    """Get ImportService instance"""
    return service_manager.get_import_service()

def get_automatic_download_service():
    """Get AutomaticDownloadService instance"""
    return service_manager.get_automatic_download_service()

def get_download_management_service():
    """Get DownloadManagementService instance"""
    return service_manager.get_download_management_service()


def get_status_service():
    """Get StatusService instance."""
    return service_manager.get_status_service()

# Communication services removed
