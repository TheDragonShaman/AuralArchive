"""
Module Name: auth.py
Author: TheDragonShaman
Created: January 18, 2026
Description:
    Authentication utilities for user login and password management.
    Passwords are hashed using bcrypt and stored in config.txt.

Location:
    /auth/auth.py
"""

import os
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from utils.logger import get_module_logger
from utils.paths import resolve_users_file

logger = get_module_logger("Core.Auth")

# Use a separate file for user credentials (JSON format)
USERS_FILE_PATH = resolve_users_file()


class User(UserMixin):
    """Simple user class for Flask-Login"""
    def __init__(self, username):
        self.id = username
        self.username = username


def load_users_from_config():
    """Load users from users.json file"""
    try:
        if not os.path.exists(USERS_FILE_PATH):
            logger.info("No users file found, will create on first user setup")
            return {}
        
        with open(USERS_FILE_PATH, 'r') as f:
            users_data = json.load(f)
            return users_data
    except json.JSONDecodeError:
        logger.error("Users file is corrupted, starting fresh")
        return {}
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        return {}


def save_users_to_config(users):
    """Save users to users.json file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(USERS_FILE_PATH), exist_ok=True)
        
        # Write to file
        with open(USERS_FILE_PATH, 'w') as f:
            json.dump(users, f, indent=4)
        
        logger.success("Users saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving users: {e}")
        return False


def has_users():
    """Check if any users exist in the system"""
    users = load_users_from_config()
    return len(users) > 0


def create_user(username, password):
    """Create a new user with hashed password"""
    users = load_users_from_config()
    
    if username in users:
        logger.warning(f"Attempted to create duplicate user: {username}")
        return False, "Username already exists"
    
    # Hash the password
    password_hash = generate_password_hash(password)
    
    # Add user
    users[username] = {
        'password_hash': password_hash,
        'created_at': None  # Could add timestamp if needed
    }
    
    # Save to config
    if save_users_to_config(users):
        logger.success(f"User created: {username}")
        return True, "User created successfully"
    else:
        return False, "Error saving user to config"


def verify_user(username, password):
    """Verify username and password"""
    users = load_users_from_config()
    
    if username not in users:
        logger.warning(f"Login attempt for non-existent user: {username}")
        return False
    
    user_data = users[username]
    password_hash = user_data.get('password_hash')
    
    if not password_hash:
        logger.error(f"User {username} has no password hash")
        return False
    
    # Verify password
    is_valid = check_password_hash(password_hash, password)
    
    if is_valid:
        logger.success(f"Successful login: {username}")
    else:
        logger.warning(f"Failed login attempt: {username}")
    
    return is_valid


def get_user(username):
    """Get a User object by username"""
    users = load_users_from_config()
    
    if username in users:
        return User(username)
    
    return None


def change_password(username, old_password, new_password):
    """Change user password"""
    users = load_users_from_config()
    
    if username not in users:
        return False, "User not found"
    
    # Verify old password
    if not verify_user(username, old_password):
        return False, "Current password is incorrect"
    
    # Hash new password
    password_hash = generate_password_hash(new_password)
    
    # Update user
    users[username]['password_hash'] = password_hash
    
    # Save to config
    if save_users_to_config(users):
        logger.success(f"Password changed for user: {username}")
        return True, "Password changed successfully"
    else:
        return False, "Error saving password"


def delete_user(username):
    """Delete a user"""
    users = load_users_from_config()
    
    if username not in users:
        return False, "User not found"
    
    del users[username]
    
    if save_users_to_config(users):
        logger.success(f"User deleted: {username}")
        return True, "User deleted successfully"
    else:
        return False, "Error deleting user"


def get_all_users():
    """Get list of all usernames"""
    users = load_users_from_config()
    return list(users.keys())
