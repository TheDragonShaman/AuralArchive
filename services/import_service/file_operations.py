"""
Module Name: file_operations.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Handles atomic file moves and copies with optional checksum verification
    for the import service. Encapsulates disk checks and cleanup of
    partially moved files.

Location:
    /services/import_service/file_operations.py

"""

import os
import shutil
import hashlib
from typing import Tuple

from utils.logger import get_module_logger


_LOGGER = get_module_logger("Service.Import.FileOperations")


class FileOperations:
    """
    Handles file system operations for importing.
    
    Features:
    - Atomic file moves
    - File verification (checksums)
    - Directory creation
    - Disk space checks
    """
    
    def __init__(self, *, logger=None):
        self.logger = logger or _LOGGER
    
    def move_file_atomic(self, source: str, destination: str, verify: bool = True) -> Tuple[bool, str]:
        """
        Move a file atomically with optional verification.
        
        Args:
            source: Source file path
            destination: Destination file path
            verify: Whether to verify file after move
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Verify source exists
            if not os.path.exists(source):
                return False, f"Source file does not exist: {source}"
            
            # Get source file size for disk space check
            source_size = os.path.getsize(source)
            
            # Check destination disk space
            dest_dir = os.path.dirname(destination)
            if not self._check_disk_space(dest_dir, source_size):
                return False, f"Insufficient disk space at destination"
            
            # Create destination directory if needed
            os.makedirs(dest_dir, exist_ok=True)
            
            # Calculate source checksum if verification requested
            source_checksum = None
            if verify:
                source_checksum = self._calculate_checksum(source)
            
            # Perform atomic move
            # On Linux, shutil.move uses os.rename when on same filesystem (atomic)
            # Otherwise it copies then deletes (not atomic but safe)
            try:
                shutil.move(source, destination)
            except Exception as e:
                return False, f"File move failed: {str(e)}"
            
            # Verify the move if requested
            if verify:
                if not os.path.exists(destination):
                    return False, "Destination file does not exist after move"
                
                dest_checksum = self._calculate_checksum(destination)
                if source_checksum != dest_checksum:
                    # Checksums don't match - corruption during move
                    self.logger.error(f"Checksum mismatch after move: {source} -> {destination}")
                    # Attempt to delete corrupted file
                    try:
                        os.remove(destination)
                    except:
                        pass
                    return False, "File verification failed - checksums don't match"
            
            self.logger.info("Successfully moved file", extra={"source": source, "destination": destination})
            return True, "File moved successfully"
            
        except Exception as e:
            self.logger.error(f"Error during file move: {e}")
            return False, f"File move error: {str(e)}"
    
    def copy_file_atomic(self, source: str, destination: str, verify: bool = True) -> Tuple[bool, str]:
        """
        Copy a file atomically with verification (for seeding preservation).
        
        This is an alias for copy_file with a name that matches the move_file_atomic pattern.
        Used when importing torrents that need to continue seeding - copies instead of moving
        so the original file remains in place for the torrent client.
        
        Args:
            source: Source file path
            destination: Destination file path
            verify: Whether to verify file after copy
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        return self.copy_file(source, destination, verify)
    
    def copy_file(self, source: str, destination: str, verify: bool = True) -> Tuple[bool, str]:
        """
        Copy a file (non-destructive alternative to move).
        
        Args:
            source: Source file path
            destination: Destination file path
            verify: Whether to verify file after copy
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Verify source exists
            if not os.path.exists(source):
                return False, f"Source file does not exist: {source}"
            
            # Get source file size
            source_size = os.path.getsize(source)
            
            # Check destination disk space
            dest_dir = os.path.dirname(destination)
            if not self._check_disk_space(dest_dir, source_size):
                return False, f"Insufficient disk space at destination"
            
            # Create destination directory if needed
            os.makedirs(dest_dir, exist_ok=True)
            
            # Calculate source checksum if verification requested
            source_checksum = None
            if verify:
                source_checksum = self._calculate_checksum(source)
            
            # Copy file
            shutil.copy2(source, destination)  # copy2 preserves metadata
            
            # Verify the copy if requested
            if verify:
                if not os.path.exists(destination):
                    return False, "Destination file does not exist after copy"
                
                dest_checksum = self._calculate_checksum(destination)
                if source_checksum != dest_checksum:
                    self.logger.error(f"Checksum mismatch after copy: {source} -> {destination}")
                    try:
                        os.remove(destination)
                    except:
                        pass
                    return False, "File verification failed - checksums don't match"
            
            self.logger.info("Successfully copied file", extra={"source": source, "destination": destination})
            return True, "File copied successfully"
            
        except Exception as e:
            self.logger.error(f"Error during file copy: {e}")
            return False, f"File copy error: {str(e)}"
    
    def _calculate_checksum(self, file_path: str, algorithm: str = 'sha256') -> str:
        """
        Calculate file checksum.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm ('sha256', 'md5')
            
        Returns:
            Hex digest of checksum
        """
        hash_func = hashlib.sha256() if algorithm == 'sha256' else hashlib.md5()
        
        try:
            with open(file_path, 'rb') as f:
                # Read in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_func.update(chunk)
            
            return hash_func.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating checksum for {file_path}: {e}")
            return ""
    
    def _check_disk_space(self, path: str, required_bytes: int) -> bool:
        """
        Check if there's enough disk space at the destination.
        
        Args:
            path: Directory path to check
            required_bytes: Required space in bytes
            
        Returns:
            True if enough space, False otherwise
        """
        try:
            probe_path = path or '/'
            probe_path = os.path.abspath(probe_path)

            # Walk up the directory tree until we find an existing directory
            while not os.path.exists(probe_path):
                parent = os.path.dirname(probe_path)
                if not parent or parent == probe_path:
                    probe_path = '/'
                    break
                probe_path = parent

            stat = os.statvfs(probe_path)
            available_bytes = stat.f_bavail * stat.f_frsize
            
            # Add 10% buffer for safety
            required_with_buffer = required_bytes * 1.1
            
            if available_bytes < required_with_buffer:
                self.logger.warning(
                    f"Insufficient disk space: {available_bytes / (1024**3):.2f} GB available, "
                    f"{required_with_buffer / (1024**3):.2f} GB required"
                )
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking disk space: {e}")
            # Return True to allow operation to proceed (fail later if actually out of space)
            return True
    
    def get_file_size(self, file_path: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            file_path: Path to file
            
        Returns:
            File size in bytes, or 0 if error
        """
        try:
            return os.path.getsize(file_path)
        except Exception as e:
            self.logger.error(f"Error getting file size for {file_path}: {e}")
            return 0
    
    def delete_file(self, file_path: str) -> Tuple[bool, str]:
        """
        Safely delete a file.
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            if not os.path.exists(file_path):
                return False, "File does not exist"
            
            os.remove(file_path)
            self.logger.info(f"Deleted file: {file_path}")
            return True, "File deleted successfully"
            
        except Exception as e:
            self.logger.error(f"Error deleting file {file_path}: {e}")
            return False, f"Delete error: {str(e)}"
