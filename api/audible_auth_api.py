"""
Module Name: audible_auth_api.py
Author: TheDragonShaman
Created: June 24, 2025
Last Modified: December 23, 2025
Description:
    REST API endpoints for Audible authentication. Handles login initiation,
    OTP verification, status checks, and revocation for the modal-based flow
    without persisting user credentials in the UI.

Location:
    /api/audible_auth_api.py

Audible Authentication API
==========================

REST API endpoints for Audible login and token lifecycle.

Endpoints:
- POST   /api/audible/auth/start        - Start authentication (username/password)
- POST   /api/audible/auth/submit-otp   - Submit OTP for pending session
- GET    /api/audible/auth/status       - Check current auth status
- POST   /api/audible/auth/revoke       - Revoke authentication and clear state
"""

import os
import uuid
from pathlib import Path

import audible
from flask import Blueprint, jsonify, request

from utils.logger import get_module_logger
from utils.paths import resolve_audible_auth_file

audible_auth_api = Blueprint('audible_auth_api', __name__)
logger = get_module_logger("API.Audible.Auth")

# Store pending authentication sessions (in-memory only)
# Session expires when OTP is submitted or authentication completes
_pending_auth_sessions = {}


@audible_auth_api.route('/api/audible/auth/start', methods=['POST'])
def start_authentication():
    """
    Start authentication flow with username/password.
    Returns session ID if OTP is needed, or success if not.
    
    Request JSON:
        {
            "username": "email@example.com",
            "password": "password123",
            "country_code": "us"
        }
    
    Response JSON:
        Success without OTP:
        {
            "success": true,
            "requires_otp": false,
            "account": {
                "name": "John Doe",
                "marketplace": "US"
            }
        }
        
        Success with OTP required:
        {
            "success": true,
            "requires_otp": true,
            "session_id": "uuid-here",
            "message": "Please enter your OTP code"
        }
        
        Error:
        {
            "success": false,
            "error": "Error message"
        }
    """
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        country_code = data.get('country_code', 'us')
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Username and password are required'
            }), 400
        
        logger.info(f"Starting authentication for {username} in {country_code}")
        
        # Create session ID for this auth attempt
        session_id = str(uuid.uuid4())
        
        # Flag to track if OTP was requested
        otp_requested = False
        auth_exception = None
        
        # Custom OTP callback that signals we need OTP from user
        def otp_callback():
            nonlocal otp_requested
            otp_requested = True
            logger.info(f"OTP required for session {session_id}")
            # Raise special exception to signal OTP needed
            raise Exception("OTP_REQUIRED")
        
        # Custom CAPTCHA callback
        def captcha_callback(captcha_url):
            logger.warning(f"CAPTCHA required: {captcha_url}")
            raise Exception(f"CAPTCHA required. Please visit Audible website first to establish trust, then try again.")
        
        # Custom CVF callback (reject - we prefer OTP)
        def cvf_callback():
            logger.warning("CVF challenge detected")
            raise Exception("CVF challenge detected. Please enable 2FA on your Audible account for better security.")
        
        # Custom approval callback
        def approval_callback():
            logger.warning("Approval alert detected")
            raise Exception("Approval required. Please check your email/SMS from Amazon and approve the login, then try again.")
        
        try:
            # Attempt authentication
            auth = audible.Authenticator.from_login(
                username=username,
                password=password,
                locale=country_code,
                with_username=False,
                otp_callback=otp_callback,
                captcha_callback=captcha_callback,
                cvf_callback=cvf_callback,
                approval_callback=approval_callback
            )
            
            # If we get here, authentication succeeded without OTP
            logger.info("Authentication successful without OTP")
            
            # Save auth file
            auth_file = resolve_audible_auth_file()
            os.makedirs(os.path.dirname(auth_file), exist_ok=True)
            auth.to_file(auth_file, encryption=False)
            logger.info(f"Auth file saved to {auth_file}")
            
            # Get account info
            with audible.Client(auth=auth) as client:
                account_info = client.get("1.0/account/information")
            
            return jsonify({
                'success': True,
                'requires_otp': False,
                'account': {
                    'name': account_info.get('name'),
                    'marketplace': account_info.get('marketplace')
                }
            })
            
        except Exception as e:
            error_msg = str(e)
            
            # Check if OTP is required
            if "OTP_REQUIRED" in error_msg or otp_requested:
                # Store session for OTP submission
                _pending_auth_sessions[session_id] = {
                    'username': username,
                    'password': password,
                    'country_code': country_code,
                    'waiting_for_otp': True
                }
                logger.info(f"OTP required, created session {session_id}")
                
                return jsonify({
                    'success': True,
                    'requires_otp': True,
                    'session_id': session_id,
                    'message': 'Please enter your OTP code'
                })
            
            # Other errors
            logger.error(f"Authentication failed: {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
    except Exception as e:
        logger.error(f"Authentication start error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'Authentication error: {str(e)}'
        }), 500


@audible_auth_api.route('/api/audible/auth/submit-otp', methods=['POST'])
def submit_otp():
    """
    Submit OTP code for pending authentication session.
    
    Request JSON:
        {
            "session_id": "uuid-here",
            "otp_code": "123456"
        }
    
    Response JSON:
        Success:
        {
            "success": true,
            "account": {
                "name": "John Doe",
                "marketplace": "US"
            }
        }
        
        Error:
        {
            "success": false,
            "error": "Error message"
        }
    """
    try:
        data = request.json
        session_id = data.get('session_id')
        otp_code = data.get('otp_code')
        
        if not session_id or not otp_code:
            return jsonify({
                'success': False,
                'error': 'Session ID and OTP code are required'
            }), 400
        
        # Get pending session
        session = _pending_auth_sessions.get(session_id)
        if not session:
            logger.warning(f"Invalid or expired session: {session_id}")
            return jsonify({
                'success': False,
                'error': 'Invalid or expired session. Please start authentication again.'
            }), 400
        
        # Extract credentials from session
        username = session['username']
        password = session['password']
        country_code = session['country_code']
        
        logger.info(f"Submitting OTP for session {session_id}")
        
        # Custom OTP callback that returns the user-provided code
        def otp_callback():
            return otp_code
        
        try:
            # Retry authentication with OTP
            auth = audible.Authenticator.from_login(
                username=username,
                password=password,
                locale=country_code,
                with_username=False,
                otp_callback=otp_callback
            )
            
            # Save auth file
            auth_file = resolve_audible_auth_file()
            os.makedirs(os.path.dirname(auth_file), exist_ok=True)
            auth.to_file(auth_file, encryption=False)
            logger.info(f"Auth file saved to {auth_file}")
            
            # Get account info
            with audible.Client(auth=auth) as client:
                account_info = client.get("1.0/account/information")
            
            # Clean up session (authentication successful)
            del _pending_auth_sessions[session_id]
            logger.info(f"Authentication successful for session {session_id}")
            
            return jsonify({
                'success': True,
                'account': {
                    'name': account_info.get('name'),
                    'marketplace': account_info.get('marketplace')
                }
            })
            
        except Exception as e:
            logger.error(f"OTP verification failed: {e}")
            # Clean up session on error
            if session_id in _pending_auth_sessions:
                del _pending_auth_sessions[session_id]
            
            return jsonify({
                'success': False,
                'error': f'OTP verification failed: {str(e)}'
            }), 400
        
    except Exception as e:
        logger.error(f"OTP submission error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': f'OTP submission error: {str(e)}'
        }), 500


@audible_auth_api.route('/api/audible/auth/status', methods=['GET'])
def get_auth_status():
    """
    Check if user is currently authenticated with Audible.
    
    Response JSON:
        Authenticated:
        {
            "authenticated": true,
            "account": {
                "name": "John Doe",
                "marketplace": "US"
            }
        }
        
        Not authenticated:
        {
            "authenticated": false
        }
    """
    try:
        auth_file = Path(resolve_audible_auth_file())
        
        if not auth_file.exists():
            return jsonify({'authenticated': False})
        
        # Try to load auth and verify it works
        auth = audible.Authenticator.from_file(str(auth_file))
        
        # Test with a simple API call
        with audible.Client(auth=auth) as client:
            account_info = client.get("1.0/account/information")
        
        return jsonify({
            'authenticated': True,
            'account': {
                'name': account_info.get('name'),
                'marketplace': account_info.get('marketplace')
            }
        })
            
    except Exception as e:
        logger.error(f"Auth status check failed: {e}")
        return jsonify({
            'authenticated': False,
            'error': str(e)
        })


@audible_auth_api.route('/api/audible/auth/revoke', methods=['POST'])
def revoke_authentication():
    """
    Revoke Audible authentication by deleting auth file.
    
    Response JSON:
        {
            "success": true,
            "message": "Authentication revoked successfully"
        }
    """
    try:
        auth_file = Path(resolve_audible_auth_file())
        
        if auth_file.exists():
            os.remove(auth_file)
            logger.info("Audible authentication revoked - auth file deleted")
        
        # Also clear any pending sessions
        _pending_auth_sessions.clear()
        
        return jsonify({
            'success': True,
            'message': 'Authentication revoked successfully'
        })
        
    except Exception as e:
        logger.error(f"Failed to revoke authentication: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
