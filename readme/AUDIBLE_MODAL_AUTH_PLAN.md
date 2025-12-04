# Audible Modal Authentication Implementation Plan

## Goal
Replace the current credential storage in `config.txt` with a secure modal-based authentication flow that:
1. **Never stores** username/password in any configuration file
2. Uses modal popups for credentials and OTP
3. Only stores the resulting `audible_auth.json` authentication token file
4. Provides a better UX with step-by-step modals

## Security Improvement
**Current (INSECURE)**:
- Username/password stored in `config/config.txt` (plain text)
- Credentials persist on disk indefinitely
- Risk if config file is exposed

**New (SECURE)**:
- Credentials only in memory during authentication
- Only auth token stored (`auth/audible_auth.json`)
- Token can be revoked and regenerated
- No plain text credentials on disk

---

## User Flow

### Current Flow (Remove This)
```
Settings → Audible Tab → Enter credentials in form → Save → Auto-authenticate on startup
```

### New Flow (Implement This)
```
Settings → Audible Tab → "Authenticate with Audible" button

Click button → Modal 1: Credentials
  ├─ Email input
  ├─ Password input (not stored)
  └─ Country/Region dropdown
  
Submit credentials → Modal 2: OTP (if 2FA enabled)
  ├─ "Enter the 6-digit code from your authenticator app"
  ├─ OTP input field
  └─ Auto-submit on 6 digits or Enter key
  
Authentication success → Modal 3: Success
  ├─ "✅ Successfully authenticated!"
  ├─ Shows account name
  ├─ Shows marketplace
  └─ Close button

Authentication stored as token file only
No credentials saved anywhere
```

---

## Implementation Components

### 1. Backend API Endpoint
**File**: `api/audible_auth_api.py` (NEW)

```python
from flask import Blueprint, request, jsonify
import audible
from services.audible.audible_service_manager import AudibleServiceManager
from utils.logger import Logger

audible_auth_api = Blueprint('audible_auth_api', __name__)
logger = Logger('audible_auth_api')

# Store pending authentication sessions (in-memory only)
_pending_auth_sessions = {}

@audible_auth_api.route('/api/audible/auth/start', methods=['POST'])
def start_authentication():
    """
    Start authentication flow with username/password.
    Returns session ID if OTP is needed, or success if not.
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
        
        # Create session ID for this auth attempt
        import uuid
        session_id = str(uuid.uuid4())
        
        # Flag to track if OTP was requested
        otp_requested = False
        otp_code = None
        
        # Custom OTP callback that sets flag and waits for OTP submission
        def otp_callback():
            nonlocal otp_requested
            otp_requested = True
            # Store pending session
            _pending_auth_sessions[session_id] = {
                'username': username,
                'password': password,
                'country_code': country_code,
                'waiting_for_otp': True,
                'otp_code': None
            }
            # Return empty string to pause authentication
            # We'll complete it when user submits OTP
            raise Exception("OTP_REQUIRED")
        
        # Custom CAPTCHA callback (show URL for user to solve)
        def captcha_callback(captcha_url):
            # For now, reject CAPTCHA (can implement modal later)
            raise Exception(f"CAPTCHA required. Please visit Audible website first to establish trust.")
        
        # Custom CVF callback (reject - we prefer OTP)
        def cvf_callback():
            raise Exception("CVF challenge detected. Please enable 2FA on your Audible account instead.")
        
        try:
            # Attempt authentication
            auth = audible.Authenticator.from_login(
                username=username,
                password=password,
                locale=country_code,
                with_username=False,
                otp_callback=otp_callback,
                captcha_callback=captcha_callback,
                cvf_callback=cvf_callback
            )
            
            # If we get here, authentication succeeded without OTP
            # Save auth file
            auth_file = 'auth/audible_auth.json'
            auth.to_file(auth_file, encryption=False)
            
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
            if "OTP_REQUIRED" in error_msg:
                return jsonify({
                    'success': True,
                    'requires_otp': True,
                    'session_id': session_id,
                    'message': 'Please enter your OTP code'
                })
            
            # Other errors
            return jsonify({
                'success': False,
                'error': error_msg
            }), 400
        
    except Exception as e:
        logger.error(f"Authentication start failed: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@audible_auth_api.route('/api/audible/auth/submit-otp', methods=['POST'])
def submit_otp():
    """
    Submit OTP code for pending authentication session.
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
            return jsonify({
                'success': False,
                'error': 'Invalid or expired session'
            }), 400
        
        # Extract credentials from session
        username = session['username']
        password = session['password']
        country_code = session['country_code']
        
        # Custom OTP callback that returns the user-provided code
        def otp_callback():
            return otp_code
        
        # Retry authentication with OTP
        auth = audible.Authenticator.from_login(
            username=username,
            password=password,
            locale=country_code,
            with_username=False,
            otp_callback=otp_callback
        )
        
        # Save auth file
        auth_file = 'auth/audible_auth.json'
        auth.to_file(auth_file, encryption=False)
        
        # Get account info
        with audible.Client(auth=auth) as client:
            account_info = client.get("1.0/account/information")
        
        # Clean up session
        del _pending_auth_sessions[session_id]
        
        return jsonify({
            'success': True,
            'account': {
                'name': account_info.get('name'),
                'marketplace': account_info.get('marketplace')
            }
        })
        
    except Exception as e:
        logger.error(f"OTP submission failed: {e}")
        # Clean up session on error
        if session_id in _pending_auth_sessions:
            del _pending_auth_sessions[session_id]
        
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@audible_auth_api.route('/api/audible/auth/status', methods=['GET'])
def get_auth_status():
    """
    Check if user is currently authenticated with Audible.
    """
    try:
        service_manager = AudibleServiceManager()
        
        if service_manager.auth:
            # Get account info to verify auth is valid
            with audible.Client(auth=service_manager.auth) as client:
                account_info = client.get("1.0/account/information")
            
            return jsonify({
                'authenticated': True,
                'account': {
                    'name': account_info.get('name'),
                    'marketplace': account_info.get('marketplace')
                }
            })
        else:
            return jsonify({
                'authenticated': False
            })
            
    except Exception as e:
        return jsonify({
            'authenticated': False,
            'error': str(e)
        })

@audible_auth_api.route('/api/audible/auth/revoke', methods=['POST'])
def revoke_authentication():
    """
    Revoke Audible authentication by deleting auth file.
    """
    try:
        import os
        auth_file = 'auth/audible_auth.json'
        
        if os.path.exists(auth_file):
            os.remove(auth_file)
            logger.info("Audible authentication revoked")
        
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
```

---

### 2. Frontend Modal HTML
**File**: `templates/settings/audible.html` (UPDATE)

Replace credential input form with:

```html
<!-- Authentication Status Section -->
<div class="auth-status-section">
    <h5>Authentication Status</h5>
    <div id="auth-status-display" class="auth-status-display">
        <div class="spinner"></div>
        <span>Checking authentication status...</span>
    </div>
    
    <div class="auth-actions">
        <button type="button" class="btn btn-primary" id="authenticate-btn" onclick="showAuthenticationModal()">
            <i class="fas fa-key"></i>
            Authenticate with Audible
        </button>
        <button type="button" class="btn btn-danger" id="revoke-btn" onclick="revokeAuthentication()" style="display: none;">
            <i class="fas fa-sign-out-alt"></i>
            Revoke Authentication
        </button>
    </div>
</div>

<!-- Country Selection (no longer stores credentials) -->
<div class="form-group">
    <label for="audible-country">Default Country/Region</label>
    <select id="audible-country" name="country_code" class="form-control">
        <option value="us">United States</option>
        <option value="uk">United Kingdom</option>
        <option value="de">Germany</option>
        <option value="fr">France</option>
        <option value="ca">Canada</option>
        <option value="au">Australia</option>
        <option value="jp">Japan</option>
        <option value="in">India</option>
    </select>
    <small class="form-help">Your Audible marketplace region</small>
</div>

<!-- Authentication Modal 1: Credentials -->
<div id="audible-auth-modal" class="modal" style="display: none;">
    <div class="modal-content">
        <div class="modal-header">
            <h3>Authenticate with Audible</h3>
            <button class="modal-close" onclick="closeAuthModal()">&times;</button>
        </div>
        <div class="modal-body">
            <p class="modal-description">Enter your Audible credentials. Your password will not be stored.</p>
            
            <form id="audible-auth-form" onsubmit="submitAudibleCredentials(event)">
                <div class="form-group">
                    <label for="auth-email">Email</label>
                    <input type="email" id="auth-email" class="form-control" required autofocus>
                </div>
                
                <div class="form-group">
                    <label for="auth-password">Password</label>
                    <input type="password" id="auth-password" class="form-control" required>
                    <small class="form-help">Not stored - only used for authentication</small>
                </div>
                
                <div class="form-group">
                    <label for="auth-country">Country/Region</label>
                    <select id="auth-country" class="form-control" required>
                        <option value="us">United States</option>
                        <option value="uk">United Kingdom</option>
                        <option value="de">Germany</option>
                        <option value="fr">France</option>
                        <option value="ca">Canada</option>
                        <option value="au">Australia</option>
                        <option value="jp">Japan</option>
                        <option value="in">India</option>
                    </select>
                </div>
                
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeAuthModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary" id="submit-credentials-btn">
                        Continue
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Authentication Modal 2: OTP -->
<div id="audible-otp-modal" class="modal" style="display: none;">
    <div class="modal-content">
        <div class="modal-header">
            <h3>Two-Factor Authentication</h3>
        </div>
        <div class="modal-body">
            <p class="modal-description">Enter the 6-digit code from your authenticator app</p>
            
            <form id="audible-otp-form" onsubmit="submitAudibleOTP(event)">
                <div class="form-group">
                    <label for="auth-otp">OTP Code</label>
                    <input type="text" id="auth-otp" class="form-control otp-input" 
                           maxlength="6" pattern="[0-9]{6}" required autofocus
                           placeholder="000000">
                </div>
                
                <div class="form-actions">
                    <button type="button" class="btn btn-secondary" onclick="closeOTPModal()">Cancel</button>
                    <button type="submit" class="btn btn-primary" id="submit-otp-btn">
                        Verify
                    </button>
                </div>
            </form>
        </div>
    </div>
</div>

<!-- Authentication Modal 3: Success -->
<div id="audible-success-modal" class="modal" style="display: none;">
    <div class="modal-content">
        <div class="modal-header">
            <h3>✅ Authentication Successful</h3>
        </div>
        <div class="modal-body">
            <div class="success-info">
                <p><strong>Account:</strong> <span id="success-account-name"></span></p>
                <p><strong>Marketplace:</strong> <span id="success-marketplace"></span></p>
            </div>
            
            <div class="form-actions">
                <button type="button" class="btn btn-primary" onclick="closeSuccessModal()">
                    Close
                </button>
            </div>
        </div>
    </div>
</div>
```

---

### 3. Frontend JavaScript
**File**: `templates/settings/audible.html` (ADD TO SCRIPT SECTION)

```javascript
// Authentication session state
let authSessionId = null;

// Check authentication status on page load
async function checkAuthenticationStatus() {
    try {
        const response = await fetch('/api/audible/auth/status');
        const data = await response.json();
        
        const statusDisplay = document.getElementById('auth-status-display');
        const authenticateBtn = document.getElementById('authenticate-btn');
        const revokeBtn = document.getElementById('revoke-btn');
        
        if (data.authenticated) {
            statusDisplay.innerHTML = `
                <div class="auth-status-authenticated">
                    <i class="fas fa-check-circle"></i>
                    <div>
                        <strong>Authenticated</strong>
                        <p>Account: ${data.account.name}</p>
                        <p>Marketplace: ${data.account.marketplace}</p>
                    </div>
                </div>
            `;
            authenticateBtn.style.display = 'none';
            revokeBtn.style.display = 'inline-block';
        } else {
            statusDisplay.innerHTML = `
                <div class="auth-status-unauthenticated">
                    <i class="fas fa-exclamation-circle"></i>
                    <span>Not authenticated</span>
                </div>
            `;
            authenticateBtn.style.display = 'inline-block';
            revokeBtn.style.display = 'none';
        }
    } catch (error) {
        console.error('Error checking auth status:', error);
    }
}

// Show authentication modal
function showAuthenticationModal() {
    const modal = document.getElementById('audible-auth-modal');
    modal.style.display = 'flex';
    document.getElementById('auth-email').focus();
}

// Close authentication modal
function closeAuthModal() {
    const modal = document.getElementById('audible-auth-modal');
    modal.style.display = 'none';
    document.getElementById('audible-auth-form').reset();
}

// Submit credentials
async function submitAudibleCredentials(event) {
    event.preventDefault();
    
    const email = document.getElementById('auth-email').value;
    const password = document.getElementById('auth-password').value;
    const country = document.getElementById('auth-country').value;
    
    const submitBtn = document.getElementById('submit-credentials-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Authenticating...';
    
    try {
        const response = await fetch('/api/audible/auth/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: email,
                password: password,
                country_code: country
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (data.requires_otp) {
                // Store session ID and show OTP modal
                authSessionId = data.session_id;
                closeAuthModal();
                showOTPModal();
            } else {
                // Success without OTP
                closeAuthModal();
                showSuccessModal(data.account);
                checkAuthenticationStatus();
            }
        } else {
            showNotification(data.error || 'Authentication failed', 'error');
        }
    } catch (error) {
        showNotification('Authentication error: ' + error.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Continue';
    }
}

// Show OTP modal
function showOTPModal() {
    const modal = document.getElementById('audible-otp-modal');
    modal.style.display = 'flex';
    
    const otpInput = document.getElementById('auth-otp');
    otpInput.focus();
    
    // Auto-submit when 6 digits entered
    otpInput.addEventListener('input', function(e) {
        if (this.value.length === 6) {
            document.getElementById('audible-otp-form').dispatchEvent(new Event('submit'));
        }
    });
}

// Close OTP modal
function closeOTPModal() {
    const modal = document.getElementById('audible-otp-modal');
    modal.style.display = 'none';
    document.getElementById('audible-otp-form').reset();
    authSessionId = null;
}

// Submit OTP
async function submitAudibleOTP(event) {
    event.preventDefault();
    
    const otpCode = document.getElementById('auth-otp').value;
    
    if (!authSessionId) {
        showNotification('Invalid session. Please try again.', 'error');
        closeOTPModal();
        return;
    }
    
    const submitBtn = document.getElementById('submit-otp-btn');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
    
    try {
        const response = await fetch('/api/audible/auth/submit-otp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: authSessionId,
                otp_code: otpCode
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            closeOTPModal();
            showSuccessModal(data.account);
            checkAuthenticationStatus();
        } else {
            showNotification(data.error || 'OTP verification failed', 'error');
            document.getElementById('auth-otp').value = '';
            document.getElementById('auth-otp').focus();
        }
    } catch (error) {
        showNotification('OTP verification error: ' + error.message, 'error');
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Verify';
    }
}

// Show success modal
function showSuccessModal(account) {
    const modal = document.getElementById('audible-success-modal');
    document.getElementById('success-account-name').textContent = account.name;
    document.getElementById('success-marketplace').textContent = account.marketplace;
    modal.style.display = 'flex';
}

// Close success modal
function closeSuccessModal() {
    const modal = document.getElementById('audible-success-modal');
    modal.style.display = 'none';
}

// Revoke authentication
async function revokeAuthentication() {
    if (!confirm('Are you sure you want to revoke Audible authentication?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/audible/auth/revoke', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification('Authentication revoked successfully', 'success');
            checkAuthenticationStatus();
        } else {
            showNotification(data.error || 'Failed to revoke authentication', 'error');
        }
    } catch (error) {
        showNotification('Error revoking authentication: ' + error.message, 'error');
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    checkAuthenticationStatus();
});
```

---

### 4. CSS Styling (Aural Glow Theme)
**File**: `static/css/components.css` (ADD)

```css
/* Authentication Modal Styles */
.auth-status-section {
    margin: 20px 0;
    padding: 20px;
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 8px;
}

.auth-status-display {
    margin: 15px 0;
    padding: 15px;
    background: var(--bg-primary);
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 15px;
}

.auth-status-authenticated {
    display: flex;
    align-items: center;
    gap: 15px;
    color: var(--success-color, #4ade80);
}

.auth-status-authenticated i {
    font-size: 32px;
}

.auth-status-unauthenticated {
    display: flex;
    align-items: center;
    gap: 15px;
    color: var(--warning-color, #fbbf24);
}

.auth-status-unauthenticated i {
    font-size: 24px;
}

.auth-actions {
    display: flex;
    gap: 10px;
    margin-top: 15px;
}

/* OTP Input Styling */
.otp-input {
    font-size: 24px;
    text-align: center;
    letter-spacing: 10px;
    font-weight: bold;
    font-family: monospace;
}

/* Success Info */
.success-info {
    padding: 20px;
    background: var(--bg-primary);
    border-radius: 6px;
    margin: 15px 0;
}

.success-info p {
    margin: 10px 0;
    font-size: 16px;
}

.success-info strong {
    color: var(--text-secondary);
    display: inline-block;
    min-width: 120px;
}

/* Modal Descriptions */
.modal-description {
    color: var(--text-secondary);
    margin-bottom: 20px;
    font-size: 14px;
}
```

---

## Configuration File Changes

### Remove from config/config.txt
```json
{
    "audible": {
        "username": "",  // REMOVE
        "password": "",  // REMOVE
        "country_code": "us"  // KEEP - this is just default, not credentials
    }
}
```

---

## Migration Strategy

1. **Add new API blueprint** to `app.py`
2. **Update Audible settings template** with modals
3. **Keep old credential fields** initially (with deprecation warning)
4. **Add migration notice** to UI: "Credentials are no longer stored in config"
5. **Test authentication flow** thoroughly
6. **Remove old credential storage** after confirmation it works

---

## Security Benefits

✅ **No credentials on disk** - Only auth tokens stored
✅ **Token-based auth** - Can be revoked anytime  
✅ **Time-limited exposure** - Credentials only in memory during auth
✅ **Clear UX** - Users know credentials aren't stored
✅ **2FA support** - Built-in OTP flow
✅ **Auditable** - Can log auth attempts without exposing credentials

---

## Testing Checklist

- [ ] Test auth flow WITHOUT 2FA
- [ ] Test auth flow WITH 2FA (OTP)
- [ ] Test OTP auto-submit on 6 digits
- [ ] Test canceling auth at each step
- [ ] Test with invalid credentials
- [ ] Test with wrong OTP
- [ ] Test auth status display
- [ ] Test revoke authentication
- [ ] Test re-authentication after revoke
- [ ] Verify credentials not in config after auth
- [ ] Verify auth token file created
- [ ] Test auth persistence across app restarts

---

## Future Enhancements

1. **CAPTCHA Support**: Add modal for CAPTCHA challenges
2. **CVF Support**: Add modal for email verification codes
3. **Auto-refresh tokens**: Refresh expired tokens automatically
4. **Multiple accounts**: Support multiple Audible marketplace accounts
5. **Session timeout**: Clear pending sessions after X minutes
