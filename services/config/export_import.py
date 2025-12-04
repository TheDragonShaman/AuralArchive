import os
import json
import logging
import configparser
import shutil
from typing import Dict, Any
from datetime import datetime

class ConfigExportImport:
    """Handles configuration backup, restore, export, and import operations"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.logger = logging.getLogger("ConfigService.ExportImport")
    
    def export_config(self, config_data: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """Export configuration for backup/transfer."""
        try:
            export_data = {
                'config': config_data,
                'exported_at': self._get_timestamp(),
                'version': '1.0.0'
            }
            self.logger.info("Configuration exported successfully")
            return export_data
        except Exception as e:
            self.logger.error(f"Failed to export configuration: {e}")
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
            
            self.logger.info("Configuration imported successfully")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to import configuration: {e}")
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
            
            self.logger.info(f"Configuration backed up to: {backup_path}")
            return backup_path
        
        except Exception as e:
            self.logger.error(f"Failed to backup configuration: {e}")
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
                self.logger.info(f"Current config backed up before restore: {current_backup}")
            
            # Copy backup to current config location
            shutil.copy2(backup_path, self.config_file)
            
            self.logger.info(f"Configuration restored from: {backup_path}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to restore configuration: {e}")
            return False
    
    def reset_to_defaults(self, defaults_generator) -> bool:
        """Reset configuration to default values."""
        try:
            # Backup current config
            backup_file = f"{self.config_file}.backup.{self._get_timestamp()}"
            if os.path.exists(self.config_file):
                os.rename(self.config_file, backup_file)
                self.logger.info(f"Current config backed up to: {backup_file}")
            
            # Generate new default config
            defaults_generator.generate_default_config()
            self.logger.info("Configuration reset to defaults")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to reset configuration: {e}")
            return False
    
    def _get_timestamp(self) -> str:
        """Get current timestamp for backups/exports."""
        return datetime.now().strftime('%Y%m%d_%H%M%S')