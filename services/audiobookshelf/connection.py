"""
AudioBookShelf Connection Management
File: services/audiobookshelf/connection.py            if response.status_code == 200:
                data = response.json()
                # AudioBookShelf /api/me returns user data directly
                username = data.get('username', 'Unknown')
                # Try to get server info from a different endpoint or handle missing version
                version = 'Unknown'
                
                return True, f"Connected as '{username}' (Server version: {version})"authentication, session management, and basic connectivity
"""
import requests
import logging
from typing import Tuple
from services.config import ConfigService

class AudioBookShelfConnection:
    """Manages connections and authentication to AudioBookShelf server."""
    
    def __init__(self):
        self.logger = logging.getLogger("AudioBookShelfConnection")
        self.config_service =ConfigService()
        self.session = requests.Session()
        self.auth_token = None
        self._setup_session()
    
    def _setup_session(self):
        """Setup requests session with default headers."""
        self.session.headers.update({
            'User-Agent': 'AuralArchive/1.0.0',
            'Content-Type': 'application/json'
        })
    
    def get_config(self) -> dict:
        """Get AudioBookShelf configuration from config service."""
        try:
            return {
                'abs_host': self.config_service.get_config_value('audiobookshelf', 'abs_host', ''),
                'abs_username': self.config_service.get_config_value('audiobookshelf', 'abs_username', ''),
                'abs_password': self.config_service.get_config_value('audiobookshelf', 'abs_password', ''),
                'abs_api_key': self.config_service.get_config_value('audiobookshelf', 'abs_api_key', ''),
                'abs_library_id': self.config_service.get_config_value('audiobookshelf', 'abs_library_id', '')
            }
        except Exception as e:
            self.logger.error(f"Error getting AudioBookShelf config: {e}")
            return {}
    
    def get_base_url(self) -> str:
        """Get the base URL for AudioBookShelf API."""
        config = self.get_config()
        host = config.get('abs_host', '').rstrip('/')
        if not host:
            return ""
        
        # Ensure protocol is included
        if not host.startswith(('http://', 'https://')):
            host = f"http://{host}"
        
        return f"{host}/api"
    
    def test_connection(self, host: str = None, api_key: str = None) -> Tuple[bool, str]:
        """Test connection to AudioBookShelf server."""
        try:
            # Use provided host or get from config
            if host:
                base_url = host.rstrip('/')
                if not base_url.startswith(('http://', 'https://')):
                    base_url = f"http://{base_url}"
            else:
                base_url = self.get_base_url()
                if not base_url:
                    return False, "AudioBookShelf host not configured"
            
            # Use provided API key or ensure authenticated with config
            if api_key:
                # Test with provided API key
                headers = {
                    'Authorization': f'Bearer {api_key}',
                    'User-Agent': 'AuralArchive/1.0.0',
                    'Content-Type': 'application/json'
                }
            else:
                if not self.ensure_authenticated():
                    return False, "Authentication failed - check credentials or API key"
                headers = self.session.headers
            
            # Test with the /me endpoint
            url = f"{base_url}/api/me"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                user_info = data.get('user', {})
                server_info = data.get('serverSettings', {})
                
                username = user_info.get('username', 'Unknown')
                version = server_info.get('version', 'Unknown')
                
                return True, f"Connected as '{username}' (Server v{version})"
            elif response.status_code == 401:
                return False, "Authentication failed - check credentials or API key"
            elif response.status_code == 404:
                return False, "API endpoint not found - check AudioBookShelf version and URL"
            else:
                return False, f"Connection failed: HTTP {response.status_code}"
        
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to AudioBookShelf server - check host/port"
        except requests.exceptions.Timeout:
            return False, "Connection timeout - server may be slow or unreachable"
        except Exception as e:
            self.logger.error(f"Connection test error: {e}")
            return False, f"Connection error: {str(e)}"
    
    def ensure_authenticated(self) -> bool:
        """Ensure we have a valid authentication token."""
        config = self.get_config()
        api_key = config.get('abs_api_key', '')
        
        if api_key:
            # Use API key authentication
            self.session.headers['Authorization'] = f'Bearer {api_key}'
            return True
        else:
            # Use username/password authentication
            if not self.auth_token:
                return self._authenticate()
            return True
    
    def _authenticate(self) -> bool:
        """Authenticate with AudioBookShelf server using username/password."""
        try:
            config = self.get_config()
            username = config.get('abs_username', '')
            password = config.get('abs_password', '')
            
            if not username or not password:
                return False
            
            base_url = self.get_base_url()
            if not base_url:
                return False
            
            # Login endpoint
            login_url = f"{base_url}/login"
            login_data = {
                "username": username,
                "password": password
            }
            
            response = self.session.post(login_url, json=login_data, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get('token')
                if self.auth_token:
                    # Update session headers with auth token
                    self.session.headers['Authorization'] = f'Bearer {self.auth_token}'
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return False