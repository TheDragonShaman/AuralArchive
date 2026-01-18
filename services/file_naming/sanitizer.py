"""
Module Name: sanitizer.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Sanitizes file paths and names for cross-platform compatibility. Handles
    character replacement, length limits, invalid patterns, and optional
    Windows-safe substitutions.

Location:
    /services/file_naming/sanitizer.py

"""

import re
import unicodedata
from utils.logger import get_module_logger

_LOGGER = get_module_logger("Service.FileNaming.Sanitizer")


class PathSanitizer:
    """
    Sanitizes file paths and names for Linux/Unix systems.
    
    Features:
    - Invalid character replacement (focusing on Linux requirements)
    - Path length limits (Linux FS limits)
    - Unicode normalization
    - Path traversal prevention
    - Optional Windows compatibility
    """
    
    # Characters that cause issues on Linux (null byte and forward slash in filenames)
    # We also avoid some problematic characters for shell/terminal usage
    INVALID_CHARS = r'[\x00/]'  # Null byte and forward slash (used as path separator)
    
    # Characters to replace for better compatibility (not strictly invalid on Linux)
    PROBLEMATIC_CHARS = {
        '\t': ' ',      # Tab to space
        '\n': ' ',      # Newline to space
        '\r': ' ',      # Carriage return to space
    }
    
    # Reserved names on Windows (kept for optional Windows compatibility)
    # Not enforced by default on Linux
    WINDOWS_RESERVED_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    # Maximum filename length on most Linux filesystems (ext4, XFS, etc.)
    MAX_COMPONENT_LENGTH = 255
    
    # Maximum total path length on Linux
    MAX_PATH_LENGTH = 4096
    
    def __init__(self, windows_compatible: bool = False, *, logger=None):
        """
        Initialize path sanitizer.
        
        Args:
            windows_compatible: If True, apply Windows-compatible restrictions
                               (useful for network shares/compatibility)
        """
        self.logger = logger or _LOGGER
        self.windows_compatible = windows_compatible
        
        # Character replacement map for filenames (not paths)
        # On Linux, most characters are allowed except null and /
        # We replace some for better usability and shell compatibility
        self.replacements = {
            '/': '-',       # Forward slash is path separator (for filename components only)
            '\x00': '',     # Null byte - not allowed on any filesystem
        }
        
        # Additional replacements if Windows compatibility needed
        if windows_compatible:
            self.replacements.update({
                ':': ' -',      # Colon (invalid on Windows)
                '"': "'",       # Double quotes (invalid on Windows)
                '<': '[',       # Angle brackets (invalid on Windows)
                '>': ']',
                '|': '-',       # Pipe (invalid on Windows)
                '?': '',        # Question mark (invalid on Windows)
                '*': '',        # Asterisk (invalid on Windows, glob on Linux)
                '\\': '-',      # Backslash (path separator on Windows)
            })
    
    def sanitize_path(self, path: str) -> str:
        """
        Sanitize a complete file path.
        
        Args:
            path: Full file path to sanitize
            
        Returns:
            Sanitized path safe for all operating systems
        """
        try:
            # Normalize unicode characters
            path = unicodedata.normalize('NFC', path)
            
            # Check for path traversal attempts
            if '..' in path:
                self.logger.warning(f"Path traversal attempt detected: {path}")
                path = path.replace('..', '')
            
            # Split path into components and sanitize each
            import os
            
            # Check if path is absolute (starts with /)
            is_absolute = path.startswith(os.sep)
            
            components = path.split(os.sep)
            sanitized_components = [self.sanitize_path_component(comp) for comp in components if comp]
            
            # Rejoin with appropriate separator
            sanitized_path = os.sep.join(sanitized_components)
            
            # Restore absolute path if it was originally absolute
            if is_absolute and not sanitized_path.startswith(os.sep):
                sanitized_path = os.sep + sanitized_path
            
            # Check total path length
            if len(sanitized_path) > self.MAX_PATH_LENGTH:
                self.logger.warning(f"Path exceeds maximum length: {len(sanitized_path)} > {self.MAX_PATH_LENGTH}")
                # Truncate the path intelligently (keep base and truncate middle components)
                sanitized_path = self._truncate_path(sanitized_path)
            
            return sanitized_path
            
        except Exception as e:
            self.logger.error(f"Error sanitizing path: {e}")
            return "unknown_path"
    
    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename (no path separators).
        
        Args:
            filename: Filename to sanitize
            
        Returns:
            Sanitized filename
        """
        try:
            # Remove any path separators
            filename = filename.replace('/', '-').replace('\\', '-')
            
            # Sanitize as a path component
            return self.sanitize_path_component(filename)
            
        except Exception as e:
            self.logger.error(f"Error sanitizing filename: {e}")
            return "unknown_file"
    
    def sanitize_path_component(self, component: str) -> str:
        """
        Sanitize a single path component (folder or filename).
        
        Args:
            component: Single path component
            
        Returns:
            Sanitized component
        """
        try:
            # Skip empty components
            if not component or component.strip() == '':
                return ''
            
            # Normalize unicode
            component = unicodedata.normalize('NFC', component)
            
            # Replace problematic characters first (whitespace variants)
            for problematic, replacement in self.PROBLEMATIC_CHARS.items():
                component = component.replace(problematic, replacement)
            
            # Replace invalid/unwanted characters
            for invalid, replacement in self.replacements.items():
                component = component.replace(invalid, replacement)
            
            # Remove strictly invalid characters (null byte, etc.)
            component = re.sub(self.INVALID_CHARS, '', component)
            
            # Remove other control characters (optional - Linux allows them but they're problematic)
            component = ''.join(char for char in component if ord(char) >= 32 or char in '\t\n')
            
            # Remove leading/trailing spaces and dots (dots at start make files hidden on Linux)
            component = component.strip().strip('.')
            
            # Check for Windows reserved names only if Windows compatibility enabled
            if self.windows_compatible and component.upper() in self.WINDOWS_RESERVED_NAMES:
                component = f"_{component}"
                self.logger.debug(f"Windows reserved name detected, prefixed with underscore: {component}")
            
            # Ensure component isn't empty after sanitization
            if not component or component.strip() == '':
                component = 'unknown'
            
            # Truncate if too long (leave room for extension)
            if len(component) > self.MAX_COMPONENT_LENGTH:
                # If there's an extension, preserve it
                if '.' in component:
                    name, ext = component.rsplit('.', 1)
                    max_name_length = self.MAX_COMPONENT_LENGTH - len(ext) - 1
                    component = f"{name[:max_name_length]}.{ext}"
                else:
                    component = component[:self.MAX_COMPONENT_LENGTH]
                self.logger.debug(f"Truncated component to {self.MAX_COMPONENT_LENGTH} chars")
            
            # Replace multiple spaces with single space
            component = re.sub(r'\s+', ' ', component)
            
            # Remove trailing spaces (can cause issues on some systems)
            component = component.rstrip()
            
            return component
            
        except Exception as e:
            self.logger.error(f"Error sanitizing path component: {e}")
            return "unknown"
    
    def _truncate_path(self, path: str) -> str:
        """
        Intelligently truncate a path that's too long.
        
        Strategy:
        1. Keep the first component (base path)
        2. Keep the last component (filename)
        3. Truncate middle components if needed
        
        Args:
            path: Path to truncate
            
        Returns:
            Truncated path
        """
        import os
        components = path.split(os.sep)
        
        if len(components) <= 2:
            # Just truncate the last component
            if components:
                components[-1] = components[-1][:self.MAX_COMPONENT_LENGTH]
            return os.sep.join(components)
        
        # Keep first and last, truncate middle
        first = components[0]
        last = components[-1]
        middle = components[1:-1]
        
        # Calculate available space for middle components
        reserved_space = len(first) + len(last) + (len(os.sep) * 2)
        available_space = self.MAX_PATH_LENGTH - reserved_space
        
        # Truncate middle components proportionally
        if middle:
            space_per_component = available_space // len(middle)
            middle = [comp[:space_per_component] for comp in middle]
        
        truncated = os.sep.join([first] + middle + [last])
        
        # Final check
        if len(truncated) > self.MAX_PATH_LENGTH:
            # Just use first and last
            truncated = os.sep.join([first, last])
        
        return truncated
    
    def validate_path(self, path: str) -> tuple[bool, str]:
        """
        Validate a path without modifying it.
        
        Args:
            path: Path to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Check for empty path
            if not path or not path.strip():
                return False, "Path cannot be empty"
            
            # Check for path traversal
            if '..' in path:
                return False, "Path contains traversal sequence (..)"
            
            # Check for absolute path indicators (Linux paths start with /)
            if path.startswith('/'):
                return False, "Path appears to be absolute (should be relative)"
            
            # Check for Windows drive letters if Windows compatibility enabled
            if self.windows_compatible and re.match(r'^[a-zA-Z]:', path):
                return False, "Path contains Windows drive letter"
            
            # Check for invalid characters (null byte on Linux)
            if '\x00' in path:
                return False, "Path contains null byte"
            
            # Check total length
            if len(path) > self.MAX_PATH_LENGTH:
                return False, f"Path exceeds maximum length ({self.MAX_PATH_LENGTH} characters)"
            
            # Check individual components
            import os
            components = path.split(os.sep)
            for comp in components:
                if not comp:
                    continue
                
                if len(comp) > self.MAX_COMPONENT_LENGTH:
                    return False, f"Path component '{comp[:50]}...' exceeds maximum length"
                
                # Only check Windows reserved names if compatibility enabled
                if self.windows_compatible and comp.upper() in self.WINDOWS_RESERVED_NAMES:
                    return False, f"Path contains Windows reserved name: {comp}"
            
            return True, ""
            
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    def normalize_separators(self, path: str, target_separator: str = '/') -> str:
        """
        Normalize path separators to a specific type.
        
        Args:
            path: Path with mixed separators
            target_separator: Desired separator ('/' or '\\')
            
        Returns:
            Path with normalized separators
        """
        # Replace all separators with target
        normalized = path.replace('\\', target_separator).replace('/', target_separator)
        
        # Remove duplicate separators
        while (target_separator + target_separator) in normalized:
            normalized = normalized.replace(target_separator + target_separator, target_separator)
        
        return normalized
