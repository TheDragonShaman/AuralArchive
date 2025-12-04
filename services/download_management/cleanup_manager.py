"""
Cleanup Manager
===============

Manages file cleanup and seeding for completed downloads.

Features:
- Seeding support (copy vs move)
- Temp file cleanup
- Client torrent management
- Retention policies
"""

import logging
import os
import shutil
from typing import Optional

logger = logging.getLogger("DownloadManagement.CleanupManager")


class CleanupManager:
    """
    Manages file cleanup after download completion.
    
    Handles:
    - Seeding mode (leave torrent active, copy file)
    - Non-seeding mode (remove torrent, move file)
    - Temp folder cleanup
    - Failed download cleanup
    """
    
    def __init__(self):
        """Initialize cleanup manager."""
        self.logger = logging.getLogger("DownloadManagement.CleanupManager")
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
            
            # Type-specific cleanup
            if download_type == 'audible':
                # Audible-specific cleanup: delete voucher files after conversion
                self._cleanup_audible_files(download_id, download_data)
            elif download_type == 'torrent':
                # Torrent-specific cleanup: handle seeding
                if seeding:
                    self.logger.debug(f"Download {download_id} in seeding mode - keeping torrent")
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
            
        except Exception as e:
            self.logger.error(f"Error cleaning up download {download_id}: {e}")
    
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
                    self.logger.debug(f"Deleted voucher file: {voucher_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete voucher {voucher_path}: {e}")
            
            # Delete original AAX/AAXC file (no longer needed after conversion)
            temp_file = download_data.get('temp_file_path')
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    self.logger.debug(f"Deleted original Audible file: {temp_file}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete temp file {temp_file}: {e}")
            
            # Clean up working directory
            self._cleanup_temp_files(download_id, download_data)
            
            self.logger.debug(f"Completed Audible-specific cleanup for download {download_id}")
            
        except Exception as e:
            self.logger.error(f"Error during Audible cleanup for {download_id}: {e}")
    
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
            self.logger.warning(f"Download {download_id} not found")
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
                self.logger.error(f"Client {client_name} not available")
                return
            
            # Remove from client
            success = client.remove(client_id, delete_files=delete_files)
            
            if success:
                self.logger.debug(
                    f"Removed {client_id} from {client_name} "
                    f"(delete_files={delete_files})"
                )
            else:
                self.logger.warning(f"Failed to remove {client_id} from {client_name}")
                
        except Exception as e:
            self.logger.error(f"Error removing from client: {e}")
    
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
            
            self.logger.debug(f"Cleaned up all files for download {download_id}")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up download files: {e}")
    
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
                    self.logger.warning(f"Download {download_id} not found")
                    return
            
            # Clean up download working directory
            download_dir = f"/data/working/downloads/{download_id}"
            if os.path.exists(download_dir):
                try:
                    shutil.rmtree(download_dir)
                    self.logger.debug(f"Deleted download directory: {download_dir}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete download dir {download_dir}: {e}")
            
            # Clean up conversion working directory
            conversion_dir = f"/data/working/converting/{download_id}"
            if os.path.exists(conversion_dir):
                try:
                    shutil.rmtree(conversion_dir)
                    self.logger.debug(f"Deleted conversion directory: {conversion_dir}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete conversion dir {conversion_dir}: {e}")
            
            # Delete converted file if still in temp location
            converted_file = download_data.get('converted_file_path')
            if converted_file and os.path.exists(converted_file):
                # Only delete if it's in a temp directory (not the final library location)
                if '/data/working/' in converted_file or '/tmp/' in converted_file:
                    try:
                        os.remove(converted_file)
                        self.logger.debug(f"Deleted converted temp file: {converted_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete converted file {converted_file}: {e}")
            
            self.logger.debug(f"Cleaned up temp files for download {download_id}")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up temp files for {download_id}: {e}")
    
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
                self.logger.warning(f"Download {download_id} missing client info")
                return True  # No client info, consider complete
            
            # Get client instance
            client_selector = self._get_client_selector()
            client = client_selector.get_client(client_name)
            
            if not client:
                self.logger.warning(f"Client {client_name} not available")
                return True  # Client not available, consider complete
            
            # Get torrent info from client
            torrent_info = client.get_torrent_info(client_id)
            
            if not torrent_info:
                self.logger.warning(f"Torrent {client_id} not found in {client_name}")
                return True  # Not found, consider complete
            
            # Check if torrent is still active
            state = torrent_info.get('state', '').lower()
            if state in ['error', 'missing', 'removed']:
                self.logger.debug(f"Torrent {client_id} in terminal state: {state}")
                return True
            
            # Check seed ratio
            ratio = torrent_info.get('ratio', 0.0)
            if ratio >= seed_ratio_limit:
                self.logger.debug(
                    f"Torrent {client_id} reached seed ratio: {ratio:.2f} >= {seed_ratio_limit}"
                )
                return True
            
            # Check seeding time
            seeding_time = torrent_info.get('seeding_time', 0)  # in seconds
            seeding_hours = seeding_time / 3600
            if seeding_hours >= seed_time_limit_hours:
                self.logger.debug(
                    f"Torrent {client_id} reached seed time: {seeding_hours:.1f}h >= {seed_time_limit_hours}h"
                )
                return True
            
            # Still seeding
            self.logger.debug(
                f"Torrent {client_id} still seeding: ratio={ratio:.2f}/{seed_ratio_limit}, "
                f"time={seeding_hours:.1f}h/{seed_time_limit_hours}h"
            )
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking seeding status for {download_id}: {e}")
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
                self.logger.debug(f"Finalized seeding for download {download_id}")
            
            # Clean up temp files
            self._cleanup_temp_files(download_id, download_data)
            
        except Exception as e:
            self.logger.error(f"Error finalizing seeding for {download_id}: {e}")
    
    def cleanup_old_failed_downloads(self, days: int = 7):
        """
        Clean up failed downloads older than specified days.
        
        Args:
            days: Age threshold in days
        """
        # TODO: Implement scheduled cleanup
        self.logger.debug(f"Cleaning up failed downloads older than {days} days")
