"""
Module Name: auth.py
Author: TheDragonShaman
Created: January 18, 2026
Description:
    Authentication routes for login, logout, and initial user setup.

Location:
    /routes/auth.py
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from auth.auth import has_users, create_user, verify_user, get_user
from utils.logger import get_module_logger

logger = get_module_logger("Routes.Auth")

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup():
    """Initial setup page for creating the first user"""
    # If users already exist, redirect to login
    if has_users():
        logger.info("Setup attempted but users already exist, redirecting to login")
        return redirect(url_for('auth.login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        accept_terms = request.form.get('accept_terms')
        
        # Validation - Terms acceptance
        if not accept_terms:
            logger.warning(f"Setup validation failed: terms not accepted")
            return render_template('setup.html', error='You must accept the disclaimer and terms of use to continue')
        
        # Validation
        if not username or len(username) < 3:
            logger.warning(f"Setup validation failed: username too short")
            return render_template('setup.html', error='Username must be at least 3 characters')
        
        if not password or len(password) < 6:
            logger.warning(f"Setup validation failed: password too short")
            return render_template('setup.html', error='Password must be at least 6 characters')
        
        if password != confirm_password:
            logger.warning(f"Setup validation failed: passwords don't match")
            return render_template('setup.html', error='Passwords do not match')
        
        # Create user
        success, message = create_user(username, password)
        
        if success:
            logger.success(f"First user created during setup: {username}")
            # Log the user in immediately
            user = get_user(username)
            login_user(user)
            return redirect(url_for('main.index'))
        else:
            logger.error(f"Failed to create user during setup: {message}")
            return render_template('setup.html', error=message)
    
    return render_template('setup.html')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    # If no users exist, redirect to setup
    if not has_users():
        logger.info("Login attempted but no users exist, redirecting to setup")
        return redirect(url_for('auth.setup'))
    
    # If already logged in, redirect to main page
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'
        
        if not username or not password:
            logger.warning("Login attempt with missing credentials")
            return render_template('login.html', error='Please provide both username and password', username=username)
        
        # Verify credentials
        if verify_user(username, password):
            user = get_user(username)
            login_user(user, remember=remember)
            
            # Get next page from query string
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            
            return redirect(url_for('main.index'))
        else:
            logger.warning(f"Failed login attempt for user: {username}")
            return render_template('login.html', error='Invalid username or password', username=username)
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Logout the current user"""
    username = current_user.username if current_user.is_authenticated else 'Unknown'
    logout_user()
    logger.success(f"User logged out: {username}")
    return redirect(url_for('auth.login'))
