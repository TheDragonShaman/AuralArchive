"""
Module Name: path_resolver.py
Author: TheDragonShaman
Created: Jan 19 2026
Description:
    Universal path resolution for Docker and bare metal environments.
    Auto-detects environment and returns appropriate paths.
    
Location:
    /utils/path_resolver.py
"""

import os
from pathlib import Path
from typing import Optional

from utils.logger import get_module_logger

_LOGGER = get_module_logger("Utils.PathResolver")


class PathResolver:
    """
    Resolves file system paths for Docker and bare metal environments.
    
    Priority order:
    1. Explicit environment variable override (highest)
    2. Docker detection (/.dockerenv or DOCKER_CONTAINER env var)
    3. Bare metal defaults (relative paths)
    """
    
    def __init__(self):
        self._is_docker = self._detect_docker()
        if self._is_docker:
            _LOGGER.info("Docker environment detected")
        else:
            _LOGGER.info("Bare metal environment detected")
    
    def _detect_docker(self) -> bool:
        """
        Detect if running in Docker container.
        
        Uses multiple detection methods:
        1. DOCKER_CONTAINER environment variable
        2. /.dockerenv file (standard Docker marker)
        3. Writable /config directory (legacy detection)
        """
        # Method 1: Explicit env var
        if os.getenv('DOCKER_CONTAINER'):
            _LOGGER.debug("Docker detected via DOCKER_CONTAINER env var")
            return True
        
        # Method 2: Docker marker file
        if os.path.exists('/.dockerenv'):
            _LOGGER.debug("Docker detected via /.dockerenv file")
            return True
        
        # Method 3: Writable /config (legacy fallback)
        if os.path.exists('/config') and os.access('/config', os.W_OK):
            _LOGGER.debug("Docker detected via writable /config directory")
            return True
        
        return False
    
    def _resolve_path(
        self,
        env_var: str,
        docker_path: str,
        bare_metal_path: str,
        create_if_missing: bool = True
    ) -> str:
        """
        Resolve a path based on environment.
        
        Args:
            env_var: Environment variable name for user override
            docker_path: Absolute path to use in Docker
            bare_metal_path: Relative path to use on bare metal
            create_if_missing: Whether to create directory if it doesn't exist
            
        Returns:
            Resolved absolute path
        """
        # Priority 1: User override
        override = os.getenv(env_var)
        if override:
            path = override
            if not os.path.isabs(path):
                # Make relative paths absolute from project root
                project_root = os.path.dirname(os.path.dirname(__file__))
                path = os.path.normpath(os.path.join(project_root, path))
            _LOGGER.debug(f"Using override path from {env_var}: {path}")
            
            if create_if_missing:
                os.makedirs(path, exist_ok=True)
            return path
        
        # Priority 2: Docker
        if self._is_docker:
            path = docker_path
            _LOGGER.debug(f"Using Docker path: {path}")
            
            if create_if_missing:
                os.makedirs(path, exist_ok=True)
            return path
        
        # Priority 3: Bare metal
        project_root = os.path.dirname(os.path.dirname(__file__))
        path = os.path.normpath(os.path.join(project_root, bare_metal_path))
        _LOGGER.debug(f"Using bare metal path: {path}")
        
        if create_if_missing:
            os.makedirs(path, exist_ok=True)
        return path
    
    def get_config_dir(self) -> str:
        """Get configuration directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_CONFIG_DIR',
            docker_path='/config',
            bare_metal_path='config'
        )
    
    def get_downloads_dir(self) -> str:
        """Get downloads directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_DOWNLOADS_DIR',
            docker_path='/downloads',
            bare_metal_path='downloads'
        )
    
    def get_import_dir(self) -> str:
        """Get import directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_IMPORT_DIR',
            docker_path='/import',
            bare_metal_path='import'
        )
    
    def get_conversion_dir(self) -> str:
        """Get conversion output directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_CONVERSION_DIR',
            docker_path='/app/conversion',
            bare_metal_path='conversion'
        )
    
    def get_cache_dir(self) -> str:
        """Get cache directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_CACHE_DIR',
            docker_path='/app/static/cache',
            bare_metal_path='static/cache'
        )
    
    def get_logs_dir(self) -> str:
        """Get logs directory path."""
        return self._resolve_path(
            env_var='AURALARCHIVE_LOGS_DIR',
            docker_path='/app/logs',
            bare_metal_path='logs'
        )
    
    def get_auth_dir(self) -> str:
        """Get authentication directory path (same as config for Docker compatibility)."""
        return self.get_config_dir()
    
    def is_docker(self) -> bool:
        """Check if running in Docker environment."""
        return self._is_docker


# Singleton instance
_path_resolver: Optional[PathResolver] = None


def get_path_resolver() -> PathResolver:
    """Get or create the global PathResolver instance."""
    global _path_resolver
    if _path_resolver is None:
        _path_resolver = PathResolver()
    return _path_resolver
