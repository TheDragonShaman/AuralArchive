"""
Module Name: cleanup_manager.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Manages post-download cleanup, seeding handling, and retention for the
    download pipeline. Supports seeding-aware cleanup, client removal, and
    temp-directory maintenance for both torrent and Audible workflows.

Location:
    /services/download_management/cleanup_manager.py

"""

import os
import shutil
from typing import Optional

from utils.logger import get_module_logger


class CleanupManager:
    """
    Manages file cleanup after download completion.
    
    Handles:
    - Seeding mode (leave torrent active, copy file)
    - Non-seeding mode (remove torrent, move file)
    - Temp folder cleanup
    - Failed download cleanup
    """
    
    def __init__(self, *, logger=None):
        """Initialize cleanup manager."""
        self.logger = logger or get_module_logger("Service.DownloadManagement.CleanupManager")
        self._queue_manager = None
        self._client_selector = None
    
    def _get_queue_manager(self):
        """Lazy load QueueManager."""
        if self._queue_manager is None:
            from .queue_manager import QueueManager
            self._queue_manager = QueueManager()
        return self._queue_manager
    
    def _get_client_selector(self):
        """Lazy load ClientSelector."""
        if self._client_selector is None:
            from .client_selector import ClientSelector
            self._client_selector = ClientSelector()
        return self._client_selector
    
    def cleanup_after_import(self, download_id: int, download_data: dict,
                            seeding: bool = False, delete_source: bool = False):
        """
        Clean up files after successful import.
        
        Args:
            download_id: Download queue ID
            download_data: Download record data
            seeding: If True, leave torrent active (was copy not move)
            delete_source: If True, delete source files
        """
        try:
            download_type = download_data.get('download_type', 'torrent')
            self.logger.info("Cleanup start", extra={
                "download_id": download_id,
                "download_type": download_type,
                "seeding": seeding,
                "delete_source": delete_source
            })
            
            # Type-specific cleanup
            if download_type == 'audible':
                # Audible-specific cleanup: delete voucher files after conversion
                self._cleanup_audible_files(download_id, download_data)
            elif download_type == 'torrent':
                # Torrent-specific cleanup: handle seeding
                if seeding:
                    self.logger.debug("Seeding mode, keeping torrent", extra={
                        "download_id": download_id
                    })
                    # Only cleanup temp converted files
                    self._cleanup_temp_files(download_id, download_data)
                else:
                    # Not seeding - remove from client
                    if download_data.get('download_client_id'):
                        self.remove_from_client(
                            download_data['download_client'],
                            download_data['download_client_id'],
                            delete_files=delete_source
                        )
                    # Cleanup temp files
                    self._cleanup_temp_files(download_id, download_data)
            else:
                # NZB or other types - standard cleanup
                self._cleanup_temp_files(download_id, download_data)
            
            self.logger.info("Cleanup finished", extra={
                "download_id": download_id
            })

        except Exception as e:
            self.logger.exception("Error cleaning up download", extra={
                "download_id": download_id,
                "error": str(e)
            })
    
    def _cleanup_audible_files(self, download_id: int, download_data: dict):
        """
        Clean up Audible-specific files after successful conversion.
        
        Deletes:
        - Voucher files (.voucher)
        - Original AAX/AAXC files (after conversion to M4B)
        - Temporary working directory
        
        Args:
            download_id: Download queue ID
            download_data: Download record data
        """
        try:
            # Delete voucher file if present
            voucher_path = download_data.get('voucher_file_path')
            if voucher_path and os.path.exists(voucher_path):
                try:
                    os.remove(voucher_path)
                    self.logger.debug("Deleted voucher file", extra={
                        "download_id": download_id,
                        "voucher_path": voucher_path
                    })
                except Exception as e:
                    self.logger.warning("Failed to delete voucher", extra={
                        "download_id": download_id,
                        "voucher_path": voucher_path,
                        "error": str(e)
                    })
            
            # Delete original AAX/AAXC file (no longer needed after conversion)
            temp_file = download_data.get('temp_file_path')
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    self.logger.debug("Deleted original Audible file", extra={
                        "download_id": download_id,
                        "temp_file": temp_file
                    })
                except Exception as e:
                    self.logger.warning("Failed to delete temp file", extra={
                        "download_id": download_id,
                        "temp_file": temp_file,
                        "error": str(e)
                    })
            
            # Clean up working directory
            self._cleanup_temp_files(download_id, download_data)
            
            self.logger.debug("Completed Audible-specific cleanup", extra={
                "download_id": download_id
            })
            
        except Exception as e:
            self.logger.exception("Error during Audible cleanup", extra={
                "download_id": download_id,
                "error": str(e)
            })
    
    def cleanup_after_import_legacy(self, download_id: int, seeding: bool = False,
                            delete_source: bool = False):
        """
        Legacy cleanup method for backward compatibility.
        Fetches download data and calls new cleanup method.
        
        Args:
            download_id: Download queue ID
            seeding: If True, leave torrent active (was copy not move)
            delete_source: If True, delete source files
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            self.logger.warning("Download not found for legacy cleanup", extra={
                "download_id": download_id
            })
            return
        
        self.cleanup_after_import(download_id, download, seeding, delete_source)
    
    def remove_from_client(self, client_name: str, client_id: str,
                          delete_files: bool = False):
        """
        Remove download from client.
        
        Args:
            client_name: Client identifier (qbittorrent, etc.)
            client_id: Client's internal ID for download
            delete_files: If True, also delete downloaded files
        """
        try:
            client_selector = self._get_client_selector()
            client = client_selector.get_client(client_name)
            
            if not client:
                self.logger.error("Client not available", extra={
                    "client_name": client_name
                })
                return
            
            # Remove from client
            success = client.remove(client_id, delete_files=delete_files)
            
            if success:
                self.logger.info("Removed download from client", extra={
                    "client_name": client_name,
                    "client_id": client_id,
                    "delete_files": delete_files
                })
            else:
                self.logger.warning("Failed to remove from client", extra={
                    "client_name": client_name,
                    "client_id": client_id,
                    "delete_files": delete_files
                })
                
        except Exception as e:
            self.logger.exception("Error removing from client", extra={
                "client_name": client_name,
                "client_id": client_id,
                "error": str(e)
            })
    
    def cleanup_download_files(self, download_id: int):
        """
        Clean up all files for a download (used during cancellation).
        
        Args:
            download_id: Download queue ID
        """
        queue_manager = self._get_queue_manager()
        download = queue_manager.get_download(download_id)
        
        if not download:
            return
        
        try:
            # Remove from client
            if download.get('download_client_id'):
                self.remove_from_client(
                    download['download_client'],
                    download['download_client_id'],
                    delete_files=True
                )
            
            # Cleanup temp files
            self._cleanup_temp_files(download_id)
            
            self.logger.debug("Cleaned up all files for download", extra={
                "download_id": download_id
            })
            
        except Exception as e:
            self.logger.exception("Error cleaning up download files", extra={
                "download_id": download_id,
                "error": str(e)
            })
    
    def _cleanup_temp_files(self, download_id: int, download_data: dict = None):
        """
        Remove temporary working directories and files.
        
        Cleans up:
        - /data/working/downloads/{id}/ - Download working directory
        - /data/working/converting/{id}/ - Conversion working directory
        - Converted file if it exists
        
        Args:
            download_id: Download queue ID
            download_data: Optional download record data (if not provided, will fetch)
        """
        try:
            # Get download data if not provided
            if download_data is None:
                queue_manager = self._get_queue_manager()
                download_data = queue_manager.get_download(download_id)
                if not download_data:
                    self.logger.warning("Download not found for temp cleanup", extra={
                        "download_id": download_id
                    })
                    return
            
            # Clean up download working directory
            download_dir = f"/data/working/downloads/{download_id}"
            if os.path.exists(download_dir):
                try:
                    shutil.rmtree(download_dir)
                    self.logger.debug("Deleted download directory", extra={
                        "download_id": download_id,
                        "path": download_dir
                    })
                except Exception as e:
                    self.logger.warning("Failed to delete download directory", extra={
                        "download_id": download_id,
                        "path": download_dir,
                        "error": str(e)
                    })
            
            # Clean up conversion working directory
            conversion_dir = f"/data/working/converting/{download_id}"
            if os.path.exists(conversion_dir):
                try:
                    shutil.rmtree(conversion_dir)
                    self.logger.debug("Deleted conversion directory", extra={
                        "download_id": download_id,
                        "path": conversion_dir
                    })
                except Exception as e:
                    self.logger.warning("Failed to delete conversion directory", extra={
                        "download_id": download_id,
                        "path": conversion_dir,
                        "error": str(e)
                    })
            
            # Delete converted file if still in temp location
            converted_file = download_data.get('converted_file_path')
            if converted_file and os.path.exists(converted_file):
                # Only delete if it's in a temp directory (not the final library location)
                if '/data/working/' in converted_file or '/tmp/' in converted_file:
                    try:
                        os.remove(converted_file)
                        self.logger.debug("Deleted converted temp file", extra={
                            "download_id": download_id,
                            "path": converted_file
                        })
                    except Exception as e:
                        self.logger.warning("Failed to delete converted file", extra={
                            "download_id": download_id,
                            "path": converted_file,
                            "error": str(e)
                        })
            
            self.logger.debug("Cleaned up temp files", extra={
                "download_id": download_id
            })
            
        except Exception as e:
            self.logger.exception("Error cleaning up temp files", extra={
                "download_id": download_id,
                "error": str(e)
            })
    
    def check_seeding_complete(self, download_id: int, download_data: dict,
                              seed_ratio_limit: float = 2.0,
                              seed_time_limit_hours: int = 168) -> bool:
        """
        Check if torrent seeding is complete based on ratio and time goals.
        
        Args:
            download_id: Download queue ID
            download_data: Download record data
            seed_ratio_limit: Target seed ratio (default: 2.0)
            seed_time_limit_hours: Max seeding time in hours (default: 168 = 1 week)
        
        Returns:
            True if seeding is complete, False if still seeding
        """
        try:
            client_name = download_data.get('download_client')
            client_id = download_data.get('download_client_id')
            
            if not client_name or not client_id:
                self.logger.warning("Download missing client info", extra={
                    "download_id": download_id
                })
                return True  # No client info, consider complete
            
            # Get client instance
            client_selector = self._get_client_selector()
            client = client_selector.get_client(client_name)
            
            if not client:
                self.logger.warning("Client not available for seeding check", extra={
                    "client_name": client_name,
                    "download_id": download_id
                })
                return True  # Client not available, consider complete
            
            # Get torrent info from client
            torrent_info = client.get_torrent_info(client_id)
            
            if not torrent_info:
                self.logger.warning("Torrent not found in client", extra={
                    "client_name": client_name,
                    "client_id": client_id,
                    "download_id": download_id
                })
                return True  # Not found, consider complete
            
            # Check if torrent is still active
            state = torrent_info.get('state', '').lower()
            if state in ['error', 'missing', 'removed']:
                self.logger.debug("Torrent in terminal state", extra={
                    "client_id": client_id,
                    "state": state,
                    "download_id": download_id
                })
                return True
            
            # Check seed ratio
            ratio = torrent_info.get('ratio', 0.0)
            if ratio >= seed_ratio_limit:
                self.logger.debug("Seed ratio target met", extra={
                    "client_id": client_id,
                    "download_id": download_id,
                    "ratio": round(ratio, 2),
                    "seed_ratio_limit": seed_ratio_limit
                })
                return True
            
            # Check seeding time
            seeding_time = torrent_info.get('seeding_time', 0)  # in seconds
            seeding_hours = seeding_time / 3600
            if seeding_hours >= seed_time_limit_hours:
                self.logger.debug("Seed time target met", extra={
                    "client_id": client_id,
                    "download_id": download_id,
                    "hours": round(seeding_hours, 1),
                    "seed_time_limit_hours": seed_time_limit_hours
                })
                return True
            
            # Still seeding
            self.logger.debug("Torrent still seeding", extra={
                "client_id": client_id,
                "download_id": download_id,
                "ratio": round(ratio, 2),
                "seed_ratio_limit": seed_ratio_limit,
                "seeding_hours": round(seeding_hours, 1),
                "seed_time_limit_hours": seed_time_limit_hours
            })
            return False
            
        except Exception as e:
            self.logger.exception("Error checking seeding status", extra={
                "download_id": download_id,
                "error": str(e)
            })
            return True  # On error, consider complete to avoid getting stuck
    
    def finalize_seeding(self, download_id: int, download_data: dict,
                        delete_files: bool = True):
        """
        Finalize a completed seeding download.
        
        Removes torrent from client and optionally deletes source files.
        
        Args:
            download_id: Download queue ID
            download_data: Download record data
            delete_files: If True, delete the source torrent files
        """
        try:
            client_name = download_data.get('download_client')
            client_id = download_data.get('download_client_id')
            
            if client_name and client_id:
                self.remove_from_client(client_name, client_id, delete_files=delete_files)
                self.logger.debug("Finalized seeding", extra={
                    "download_id": download_id,
                    "client_name": client_name,
                    "client_id": client_id,
                    "delete_files": delete_files
                })
            
            # Clean up temp files
            self._cleanup_temp_files(download_id, download_data)
            
        except Exception as e:
            self.logger.exception("Error finalizing seeding", extra={
                "download_id": download_id,
                "error": str(e)
            })
    
    def cleanup_old_failed_downloads(self, days: int = 7):
        """
        Clean up failed downloads older than specified days.
        
        Args:
            days: Age threshold in days
        """
        # TODO: Implement scheduled cleanup
        self.logger.debug(f"Cleaning up failed downloads older than {days} days")
