"""
Module Name: export_import.py
Author: TheDragonShaman
Created: August 26, 2025
Last Modified: December 24, 2025
Description:
    Handle backup, restore, export, and import for config files.
Location:
    /services/config/export_import.py

"""

import os
import json
import configparser
import shutil
from typing import Dict, Any
from datetime import datetime

from utils.logger import get_module_logger


class ConfigExportImport:
    """Handle configuration backup, restore, export, and import operations."""

    def __init__(self, config_file: str, logger=None):
        self.config_file = config_file
        self.logger = logger or get_module_logger("Service.Config.ExportImport")
    
    def export_config(self, config_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Export configuration for backup/transfer."""
        try:
            export_data = {
                'config': config_data,
                'exported_at': self._get_timestamp(),
                'version': '1.0.0'
            }
            self.logger.info("Configuration exported", extra={"config_file": self.config_file})
            return export_data
        except Exception as exc:
            self.logger.exception(
                "Failed to export configuration",
                extra={"config_file": self.config_file},
            )
            return {}
    
    def import_config(self, config_data: Dict[str, Any]) -> bool:
        """Import configuration from backup/transfer."""
        try:
            if 'config' not in config_data:
                self.logger.error("Invalid configuration data format")
                return False
            
            config = configparser.ConfigParser()
            
            # Rebuild configuration from imported data
            for section_name, section_data in config_data['config'].items():
                config.add_section(section_name)
                for key, value in section_data.items():
                    config.set(section_name, key, str(value))
            
            # Write to file
            with open(self.config_file, "w") as configfile:
                config.write(configfile)
            
            self.logger.info("Configuration imported", extra={"config_file": self.config_file})
            return True
        
        except Exception as exc:
            self.logger.exception(
                "Failed to import configuration",
                extra={"config_file": self.config_file},
            )
            return False
    
    def backup_config(self, backup_dir: str = None) -> str:
        """Create a backup of the current configuration."""
        try:
            if backup_dir is None:
                backup_dir = os.path.dirname(self.config_file)
            
            backup_filename = f"config_backup_{self._get_timestamp()}.txt"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Copy current config to backup location
            shutil.copy2(self.config_file, backup_path)
            
            self.logger.info(
                "Configuration backed up",
                extra={"backup_path": backup_path, "config_file": self.config_file},
            )
            return backup_path
        
        except Exception as exc:
            self.logger.exception(
                "Failed to backup configuration",
                extra={"config_file": self.config_file, "backup_dir": backup_dir},
            )
            return ""
    
    def restore_config(self, backup_path: str) -> bool:
        """Restore configuration from backup."""
        try:
            if not os.path.exists(backup_path):
                self.logger.error(f"Backup file not found: {backup_path}")
                return False
            
            # Create backup of current config before restore
            current_backup = self.backup_config()
            if current_backup:
                self.logger.info(
                    "Backed up current config before restore",
                    extra={"backup_path": current_backup, "config_file": self.config_file},
                )
            
            # Copy backup to current config location
            shutil.copy2(backup_path, self.config_file)
            
            self.logger.info(
                "Configuration restored",
                extra={"backup_path": backup_path, "config_file": self.config_file},
            )
            return True
        
        except Exception as exc:
            self.logger.exception(
                "Failed to restore configuration",
                extra={"config_file": self.config_file, "backup_path": backup_path},
            )
            return False
    
    def reset_to_defaults(self, defaults_generator) -> bool:
        """Reset configuration to default values."""
        try:
            # Backup current config
            backup_file = f"{self.config_file}.backup.{self._get_timestamp()}"
            if os.path.exists(self.config_file):
                os.rename(self.config_file, backup_file)
                self.logger.info(
                    "Current config backed up before reset",
                    extra={"backup_path": backup_file, "config_file": self.config_file},
                )
            
            # Generate new default config
            defaults_generator.generate_default_config()
            self.logger.info(
                "Configuration reset to defaults",
                extra={"config_file": self.config_file},
            )
            return True
        
        except Exception as exc:
            self.logger.exception(
                "Failed to reset configuration",
                extra={"config_file": self.config_file},
            )
            return False
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for backups/exports."""
        return datetime.now().strftime('%Y%m%d_%H%M%S')