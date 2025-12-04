"""
AudioBookShelf Server Information
File: services/audiobookshelf/serverinfo.py
Handles server status and information retrieval
"""
import logging
from typing import Dict, Tuple

class AudioBookShelfServerInfo:
    """Handles AudioBookShelf server information and status."""
    
    def __init__(self, connection):
        self.connection = connection
        self.logger = logging.getLogger("AudioBookShelfServerInfo")
    
    def get_server_info(self) -> Tuple[bool, Dict, str]:
        """Get AudioBookShelf server information."""
        try:
            if not self.connection.ensure_authenticated():
                return False, {}, "Authentication failed"
            
            base_url = self.connection.get_base_url()
            url = f"{base_url}/me"
            
            response = self.connection.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                server_settings = data.get('serverSettings', {})
                user_info = data.get('user', {})
                
                server_info = {
                    'version': server_settings.get('version', 'Unknown'),
                    'buildNumber': server_settings.get('buildNumber', 'Unknown'),
                    'language': server_settings.get('language', 'en-us'),
                    'logLevel': server_settings.get('logLevel', 'info'),
                    'username': user_info.get('username', 'Unknown'),
                    'userType': user_info.get('type', 'Unknown'),
                    'isActive': user_info.get('isActive', False),
                    'createdAt': user_info.get('createdAt', 0)
                }
                return True, server_info, "Server info retrieved successfully"
            else:
                return False, {}, f"Failed to get server info: HTTP {response.status_code}"
        
        except Exception as e:
            self.logger.error(f"Error getting server info: {e}")
            return False, {}, f"Error: {str(e)}"
    
    def get_server_status(self) -> Tuple[bool, Dict, str]:
        """Get basic server status information."""
        try:
            success, info, message = self.get_server_info()
            
            if success:
                status = {
                    'online': True,
                    'version': info.get('version', 'Unknown'),
                    'user': info.get('username', 'Unknown'),
                    'active': info.get('isActive', False)
                }
                return True, status, "Server is online"
            else:
                status = {
                    'online': False,
                    'version': 'Unknown',
                    'user': 'Unknown',
                    'active': False
                }
                return False, status, message
        
        except Exception as e:
            self.logger.error(f"Error getting server status: {e}")
            return False, {'online': False}, f"Error: {str(e)}"