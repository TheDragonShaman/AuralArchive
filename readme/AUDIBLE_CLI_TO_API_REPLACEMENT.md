# Audible CLI to Python API Replacement Plan

## Current Situation

AuralArchive currently uses **TWO separate Audible authentication systems**:

1. **Python `audible` package (0.8.2)** - ✅ Working
   - Uses: `auth/audible_auth.json`
   - Pattern: `with audible.Client(auth=self.auth) as client:`
   - Status: **Fully functional** for wishlist sync

2. **`audible-cli` command-line tool (0.3.3)** - ❌ Broken
   - Uses: Separate `~/.audible/` authentication
   - Pattern: `subprocess.run(['audible', ...])`
   - Status: **Not authenticated** (return code 2)

## Problem

Multiple services use CLI subprocess calls instead of the Python API:
- Library export/sync fails
- Metadata sync fails
- Book downloads fail
- Activation bytes retrieval fails

## Solution

Replace ALL CLI subprocess calls with Python API equivalents using the working authentication.

---

## Files That Need Replacement

### 1. Library Export (Metadata Sync)
**File**: `services/audible/audible_metadata_sync_service/audible_cli_helper.py`

**Current CLI Usage**:
```python
# Line 41: Library export
cmd = ['audible', 'library', 'export', '--format', 'json', '--output', temp_path]
subprocess.run(cmd, ...)

# Line 133: Version check
subprocess.run(['audible', '--version'], ...)
```

**API Replacement**:
```python
# Library fetch with pagination
with audible.Client(auth=self.auth) as client:
    # Page 1 to get total count
    response = client.get(
        "library",
        num_results=1000,
        page=1,
        response_groups="contributors, customer_rights, media, price, product_attrs, product_desc, product_extended_attrs, product_plan_details, product_plans, rating, sample, sku, series, reviews, ws4v, relationships, review_attrs, categories, category_ladders, claim_code_url, in_wishlist, listening_status, periodicals, provided_review, product_details"
    )
    
    items = response['items']
    total = response['total_results']
    
    # Calculate remaining pages
    total_pages = math.ceil(total / 1000)
    
    # Fetch remaining pages (can do in parallel if needed)
    for page in range(2, total_pages + 1):
        page_response = client.get("library", num_results=1000, page=page, response_groups=...)
        items.extend(page_response['items'])
    
    return items
```

**Parameters Available**:
- `page`: int (pagination)
- `num_results`: int (items per page, default 1000)
- `purchased_after`: datetime string (date filtering)
- `response_groups`: comma-separated string (metadata fields)

---

### 2. Book Downloads
**File**: `services/audible/audible_library_service/audible_library_service.py`

**Current CLI Usage**:

#### Single Book Download (Line 624):
```python
cmd = ['audible', 'download']
if asin:
    cmd.extend(['--asin', asin])
cmd.extend(['--output-dir', output_dir])
cmd.append('--aaxc')
cmd.extend(['--quality', quality])
cmd.append('--pdf')
cmd.append('--cover')
cmd.append('--chapter')

process = subprocess.Popen(cmd, ...)
```

#### Bulk Download (Line 754):
```python
cmd = ['audible', 'download', '--all']
cmd.extend(['--output-dir', output_dir])
cmd.append('--aaxc')
cmd.extend(['--quality', quality])
cmd.extend(['--start-date', start_date])
cmd.extend(['--end-date', end_date])
cmd.extend(['--jobs', str(jobs)])

subprocess.run(cmd, ...)
```

**API Replacement**:

The `audible` package has a `download` method. Need to investigate:
```python
# Single book download
with audible.Client(auth=self.auth) as client:
    # Get download link from content endpoint
    content_response = client.get(
        f"content/{asin}/licenserequest",
        asin=asin,
        quality=quality,  # 'Extreme', 'High', 'Normal'
        consumption_type='Download'
    )
    
    download_url = content_response['content_license']['content_metadata']['content_url']['offline_url']
    
    # Download file with progress tracking
    # Can use requests.get with stream=True for progress
    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get('content-length', 0))
        
        with open(output_path, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                progress = int((downloaded / total_size) * 100)
                # Emit progress updates
```

**Note**: Need to research if `audible` package has built-in download helpers or if we need to implement download logic ourselves.

---

### 3. Activation Bytes
**File**: `services/audible/audible_library_service/audible_library_service.py`

**Current CLI Usage** (Line 856):
```python
cmd = ['audible', 'activation-bytes']
if reload:
    cmd.append('--reload')
subprocess.run(cmd, ...)
```

**API Replacement**:
```python
# The audible package can extract activation bytes
with audible.Client(auth=self.auth) as client:
    # Activation bytes are stored in the auth object
    activation_bytes = client.auth.activation_bytes
    
    # Or get from user profile
    profile = client.get("user/profile")
    # Extract activation bytes from profile or license data
```

**Note**: Need to verify exact method - activation bytes might be in:
- `client.auth.activation_bytes`
- `client.activation_bytes()`
- Retrieved from license endpoint

---

### 4. Authentication Status Check
**File**: `services/audible/audible_library_service/auth_handler.py`

**Current CLI Usage** (Line 128):
```python
subprocess.run(['audible', 'manage', 'auth-file', 'list'], ...)
```

**API Replacement**:
```python
# Check if auth file exists and is valid
def check_authentication_status():
    auth_file = Path('auth/audible_auth.json')
    
    if not auth_file.exists():
        return {'authenticated': False, 'error': 'Auth file not found'}
    
    try:
        # Try to create client and make a test request
        with audible.Client(auth=audible.Authenticator.from_file(auth_file)) as client:
            # Test with a simple profile request
            profile = client.get("user/profile")
            return {
                'authenticated': True,
                'marketplace': client.auth.locale.country_code,
                'profile': profile
            }
    except Exception as e:
        return {'authenticated': False, 'error': str(e)}
```

---

### 5. Version Check
**File**: `services/audible/audible_library_service/format_converter.py`

**Current CLI Usage** (Line 98):
```python
subprocess.run(['audible', '--version'], ...)
```

**API Replacement**:
```python
import audible

def get_audible_version():
    return {
        'version': audible.__version__,
        'package': 'audible (Python)',
        'available': True
    }
```

---

## Research Reference: audible-cli Source Code

From `venv/lib/python3.13/site-packages/audible_cli/models.py`:

### Library Endpoint Discovery
```python
# The actual API call found in audible-cli source:
resp: httpx.Response = await api_client.get(
    "library",
    response_callback=full_response_callback,
    **request_params
)
```

### Pagination Pattern
```python
# From from_api_full_sync method:
1. Get page 1 with total count
2. total_pages = ceil(total_count / num_results)
3. Fetch pages 2-N in parallel with asyncio.gather
4. Combine all results
```

### Response Groups Available
```
"contributors, customer_rights, media, price, product_attrs, product_desc, 
product_extended_attrs, product_plan_details, product_plans, rating, sample, 
sku, series, reviews, ws4v, relationships, review_attrs, categories, 
category_ladders, claim_code_url, in_wishlist, listening_status, periodicals, 
provided_review, product_details"
```

---

## Working Example (Already in Codebase)

**File**: `services/audible/audible_service_manager.py`

```python
# Line 203: Successful pattern used for wishlist sync
with audible.Client(auth=self.auth) as client:
    response = client.get("wishlist", **params)
```

This proves the Python API works perfectly with our existing `auth/audible_auth.json`.

---

## Implementation Priority

### High Priority (Breaks current functionality)
1. **Library Export** - `audible_cli_helper.py`
   - Blocks metadata sync (full & quick)
   - Blocks library stats
   
2. **Authentication Check** - `auth_handler.py`
   - Affects all features that check auth status

### Medium Priority (New features)
3. **Book Downloads** - `audible_library_service.py`
   - Single book download
   - Bulk download
   
4. **Activation Bytes** - `audible_library_service.py`
   - Needed for DRM removal

### Low Priority (Nice to have)
5. **Version Check** - `format_converter.py`
   - Just informational

---

## Testing Strategy

For each replacement:

1. **Unit Test**: Test API call with known ASIN/data
2. **Integration Test**: Test full workflow (auth → fetch → process)
3. **Comparison Test**: Compare API output with old CLI output format
4. **Error Handling**: Test with invalid auth, network errors, etc.

### Test Cases

#### Library Export
```python
# Test pagination
- Library with < 1000 books (single page)
- Library with > 1000 books (multiple pages)
- Library with exactly 1000 books (boundary)

# Test filtering
- purchased_after filtering
- Response groups selection

# Test error handling
- Invalid auth
- Network timeout
- Malformed response
```

#### Downloads
```python
# Test single download
- Valid ASIN with AAXC format
- Different quality levels
- Include PDF/cover/chapters options

# Test bulk download
- Date range filtering
- Parallel job handling
- Error recovery (skip failed books)
```

---

## Migration Checklist

- [ ] Research `audible` package download methods
- [ ] Research activation bytes extraction
- [ ] Create new `AudibleApiHelper` class (replaces `AudibleCliHelper`)
- [ ] Implement library fetch with pagination
- [ ] Implement single book download
- [ ] Implement bulk download
- [ ] Implement activation bytes retrieval
- [ ] Update `audible_metadata_sync_service.py` to use new helper
- [ ] Update `audible_library_service.py` to use API downloads
- [ ] Update `auth_handler.py` to use API auth check
- [ ] Update `format_converter.py` to use package version
- [ ] Write unit tests for all new API methods
- [ ] Test full sync workflow
- [ ] Test quick sync workflow
- [ ] Test download workflows
- [ ] Remove/deprecate `audible_cli_helper.py`
- [ ] Update error messages (remove CLI references)
- [ ] Update documentation

---

## Benefits of This Change

1. **Single Authentication**: Only need `auth/audible_auth.json`
2. **Better Error Handling**: No subprocess return code guessing
3. **Better Progress Tracking**: Direct access to response data
4. **Faster**: No subprocess overhead
5. **More Maintainable**: Pure Python, no CLI dependency
6. **Better Type Safety**: Python types vs string parsing
7. **Async Support**: Can use `audible.AsyncClient` if needed

---

## Notes

- All CLI functionality CAN be replaced with Python API
- The `audible` package is well-maintained and feature-complete
- Current working wishlist sync proves our auth works
- Can keep CLI as optional fallback during migration
- Should add feature flag to toggle between CLI/API during testing
