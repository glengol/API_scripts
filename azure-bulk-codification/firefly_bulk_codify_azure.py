#!/usr/bin/env python3
"""
Firefly Azure bulk codify with Windows compatibility:
- AWS-style CLI progress (per-item lines, ✓/✗, ETA)
- Resource Group filtering (server-side if supported, client-side fallback)
- pretty_hcl() formatter and aggregated output per asset type
- Fixed multi-line string handling for Terraform
- Windows-compatible file paths and batch scripts
- SSL certificate handling for Windows corporate environments

QUICK START FOR SSL ISSUES:
If you get SSL certificate errors, try these solutions in order:

1. QUICK FIX (not recommended for production):
   Set SSL_VERIFY = False in the config section below

2. INSTALL CERTIFICATES:
   pip install --upgrade certifi

3. DOWNLOAD CERTIFICATES:
   Download https://curl.se/ca/cacert.pem and set SSL_CERT_PATH to its location

4. CORPORATE PROXY:
   If behind a corporate proxy, you may need to configure proxy settings
"""

import json
import sys
import time
import re
import os
import ssl
from typing import Any, Dict, Iterable, List, Tuple
from pathlib import Path
import requests
from urllib3.exceptions import InsecureRequestWarning

# ================= CONFIG =================
# NOTE: ACCESS_KEY, SECRET_KEY, AZ_SUBSCRIPTION_ID, DATA_SOURCE_NAME, and RESOURCE_GROUPS
# are case-insensitive - you can input them in any case (upper, lower, mixed) and they'll
# be automatically normalized to the correct format.

BASE_URL = "https://api.firefly.ai/api/v1.0"
ACCESS_KEY = "ACCESS_KEY"
SECRET_KEY = "SECRET_KEY"

# SSL Configuration for Windows corporate environments
SSL_VERIFY = True  # Set to False if you have SSL certificate issues
SSL_CERT_PATH = None  # Path to custom certificate bundle if needed

AZ_SUBSCRIPTION_ID = "AZ_SUBSCRIPTION_ID"
DATA_SOURCE_NAME = "DATA_SOURCE_NAME"

# Optional inventory filters
ASSET_STATE = "unmanaged"   # unmanaged | codified | drifted | ghost
ASSET_TYPES: List[str] = [] # e.g., ["azurerm_linux_virtual_machine", "azurerm_storage_account"]
NAMES: List[str] = []       # exact name matches
RESOURCE_GROUPS: List[str] = ["RESOURCE_GROUPS"]  # e.g., ["rg-app-prod", "rg-data"]

# ================= CASE-INSENSITIVE CONFIG NORMALIZATION =================
def normalize_config():
    """
    Normalize configuration values to be case-insensitive.
    This allows users to input values in any case and they'll be converted to the correct format.
    """
    global ACCESS_KEY, SECRET_KEY, AZ_SUBSCRIPTION_ID, DATA_SOURCE_NAME, RESOURCE_GROUPS
    
    # Normalize keys and secrets (keep as-is, but strip whitespace)
    ACCESS_KEY = ACCESS_KEY.strip() if ACCESS_KEY else ""
    SECRET_KEY = SECRET_KEY.strip() if SECRET_KEY else ""
    
    # Normalize subscription ID (convert to lowercase)
    if AZ_SUBSCRIPTION_ID:
        AZ_SUBSCRIPTION_ID = AZ_SUBSCRIPTION_ID.strip().lower()
    
    # Normalize data source name (keep original case but strip whitespace)
    if DATA_SOURCE_NAME:
        DATA_SOURCE_NAME = DATA_SOURCE_NAME.strip()
    
    # Normalize resource groups (convert to lowercase, strip whitespace)
    if RESOURCE_GROUPS:
        RESOURCE_GROUPS = [rg.strip().lower() for rg in RESOURCE_GROUPS if rg.strip()]

# Apply normalization
normalize_config()

SIZE = 10000                 # inventory page size

# Output - Windows compatible paths
OUT_DIR = Path("codified_assets")
INCLUDE_PROVIDER = True
INCLUDE_IMPORTS = True
AUTO_TERRAFORM_FMT = True   # set True if terraform is installed
OUT_IMPORT_CMDS = "import_commands.bat"  # Changed to .bat for Windows

# =============== HTTP helpers ===============
def setup_session():
    """Setup requests session with Windows SSL handling"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    
    # Handle SSL certificate issues common in Windows corporate environments
    if not SSL_VERIFY:
        print("WARNING: SSL verification disabled. This is not recommended for production use.", file=sys.stderr)
        session.verify = False
        # Suppress SSL warnings when verification is disabled
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    elif SSL_CERT_PATH and os.path.exists(SSL_CERT_PATH):
        session.verify = SSL_CERT_PATH
        print(f"Using custom SSL certificate bundle: {SSL_CERT_PATH}", file=sys.stderr)
    else:
        # Try to use Windows certificate store
        try:
            # Create SSL context that uses Windows certificate store
            ssl_context = ssl.create_default_context()
            session.verify = True
        except Exception as e:
            print(f"SSL context creation failed: {e}", file=sys.stderr)
            print("Consider setting SSL_VERIFY = False if you continue to have certificate issues", file=sys.stderr)
    
    return session

SESSION = setup_session()

class APIError(RuntimeError):
    pass

def _raise(resp: requests.Response) -> None:
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise APIError(f"HTTP {resp.status_code}: {resp.text}") from e

def test_ssl_connection() -> bool:
    """Test SSL connection to Firefly API"""
    try:
        url = f"{BASE_URL}/login"
        # Just test the connection without sending data
        response = SESSION.get(url, timeout=10)
        return True
    except requests.exceptions.SSLError as e:
        print(f"SSL Error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Connection Error: {e}", file=sys.stderr)
        return False

def login(access_key: str, secret_key: str) -> str:
    url = f"{BASE_URL}/login"
    try:
        r = SESSION.post(url, data=json.dumps({"accessKey": access_key, "secretKey": secret_key}))
        _raise(r)
        tok = r.json().get("accessToken")
        if not tok:
            raise APIError("Missing accessToken in login response")
        SESSION.headers.update({"Authorization": f"Bearer {tok}"})
        return tok
    except requests.exceptions.SSLError as e:
        print(f"SSL Certificate Error: {e}", file=sys.stderr)
        print("\nTo fix SSL certificate issues on Windows:", file=sys.stderr)
        print("1. Set SSL_VERIFY = False in the config (not recommended for production)", file=sys.stderr)
        print("2. Install certificates using: pip install --upgrade certifi", file=sys.stderr)
        print("3. Or download certificates from: https://curl.se/ca/cacert.pem", file=sys.stderr)
        print("4. Set SSL_CERT_PATH to the path of the certificate file", file=sys.stderr)
        raise APIError(f"SSL Certificate verification failed: {e}")

# =============== Integrations (resolve subscription) ===============
def resolve_subscription_id_by_name(name: str) -> str:
    # Try a couple of endpoints that may exist in different deployments.
    for url in (f"{BASE_URL}/integrations/azurerm",):
        r = SESSION.get(url)
        if r.status_code == 200:
            items = r.json() or []
            for it in items:
                if it.get("name") == name:
                    sid = it.get("accountNumber") or it.get("providerId") or it.get("accountId")
                    if sid:
                        return sid
    raise APIError(f"Data source '{name}' not found for provider 'azurerm'")

# =============== Inventory ===============
def inventory(provider_ids: List[str]) -> List[Dict[str, Any]]:
    url = f"{BASE_URL}/inventory"
    payload: Dict[str, Any] = {
        "size": SIZE,
        "providerTypes": {"provider": ["azurerm"]},
        "providerIds": provider_ids,
    }
    if ASSET_STATE:
        payload["assetState"] = ASSET_STATE
    if ASSET_TYPES:
        payload["assetTypes"] = ASSET_TYPES
    if NAMES:
        payload["names"] = NAMES
    if RESOURCE_GROUPS:
        payload["resourceGroups"] = RESOURCE_GROUPS  # server-side if supported

    r = SESSION.post(url, data=json.dumps(payload))
    _raise(r)
    body = r.json()
    items = body.get("responseObjects", [])

    # client-side RG fallback in case server ignores key
    if RESOURCE_GROUPS:
        rgs = {rg.lower() for rg in RESOURCE_GROUPS}
        def in_rg(a: Dict[str, Any]) -> bool:
            rid = (a.get("resourceId") or "").lower()
            return any(f"/resourcegroups/{rg}/" in rid for rg in rgs)
        items = [a for a in items if in_rg(a)]
    return items

# =============== Codify call (AWS-style) ===============
def codify_one(req: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}/codify"
    r = SESSION.post(url, data=json.dumps(req))
    _raise(r)
    return r.json()

def codify_assets(assets: List[Dict[str, Any]], sleep_sec: float = 0.02) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Codify all assets with detailed progress logging (per-item line + periodic ETA).
    Returns list of (request, response) tuples for successes.
    """
    total = len(assets)
    ok = 0
    fail = 0
    out: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    t0 = time.time()

    for idx, req in enumerate(assets, start=1):
        at = req.get("assetType", "?")
        aid = (req.get("assetId") or "")[:150]
        print(f"    [{idx}/{total}] {at} → {aid}", flush=True)

        missing = [k for k in ("assetType", "assetId", "iacType", "provider", "accountNumber") if not req.get(k)]
        if missing:
            print(f"      ✗ skip (missing {missing})", flush=True)
            fail += 1
            continue

        try:
            t_call = time.time()
            resp = codify_one(req)
            dt = time.time() - t_call
            out.append((req, resp))
            ok += 1
            print(f"      ✓ ok ({dt:.2f}s)", flush=True)
        except APIError as e:
            fail += 1
            msg = str(e)
            if len(msg) > 300:
                msg = msg[:300] + "…"
            print(f"      ✗ failed: {msg}", flush=True)

        if sleep_sec > 0:
            time.sleep(sleep_sec)

        if idx % 25 == 0 or idx == total:
            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0.0
            remaining = total - idx
            eta = remaining / rate if rate > 0 else 0.0
            print(f"    — progress: {idx}/{total} | ok={ok} fail={fail} | {rate:.1f}/s | ETA ~{eta:.0f}s", flush=True)

    elapsed = time.time() - t0
    print(f"    Done codifying: ok={ok}, fail={fail}, total={total}, elapsed={elapsed:.1f}s", flush=True)
    return out

# =============== Formatting + output (AWS-style) ===============
def _strip_headers(hcl: str) -> str:
    out: List[str] = []
    for ln in hcl.splitlines():
        if ln.strip().startswith("# ---"):
            continue
        out.append(ln)
    return "\n".join(out) + ("\n" if hcl and not hcl.endswith("\n") else "")

def fix_multiline_strings(hcl: str) -> str:
    """
    Fix multi-line strings in HCL by converting them to proper heredoc syntax
    or by escaping newlines within quoted strings.
    """
    # First, handle strings that contain \r\n sequences and should be heredocs
    def fix_complex_strings(text):
        # Pattern to match strings with \r\n sequences OR very long content
        pattern = r'(\w+\s*=\s*)"([^"]*(?:\\r\\n|\\n|Import-Module)[^"]*)"'
        
        def replacement(match):
            key = match.group(1).strip()
            content = match.group(2)
            
            # Use heredoc for complex patterns, very long strings, or specific markers
            if (any(marker in content for marker in ['<!--', '<policies>', 'Server=tcp:', 'Driver={', 'ODBC Driver', 'Import-Module', '$array', 'foreach('])
                or len(content) > 100 or content.count('\\r\\n') > 1):
                clean_content = content.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '  ')
                return f'{key} = <<EOF\n{clean_content}\nEOF'
            else:
                return match.group(0)  # Keep as is for simple strings
        
        return re.sub(pattern, replacement, text, flags=re.DOTALL)
    
    # Apply the fix
    result = fix_complex_strings(hcl)
    
    # Handle strings that are broken across lines due to our formatting
    lines = result.split('\n')
    final_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if this line contains an opening quote without a closing quote
        if '=' in line and '"' in line and not line.strip().startswith('EOF'):
            # Count quotes in the line
            quote_count = line.count('"')
            
            # If odd number of quotes, this might be start of a multi-line string
            if quote_count % 2 == 1:
                # Look for the closing quote in subsequent lines
                full_content = line
                j = i + 1
                found_closing = False
                
                # Look ahead for closing quote (max 20 lines)
                while j < len(lines) and j < i + 20:
                    next_line = lines[j]
                    full_content += '\n' + next_line
                    if '"' in next_line:
                        found_closing = True
                        break
                    j += 1
                
                if found_closing:
                    # Extract key and content
                    eq_pos = line.find('=')
                    quote_pos = line.find('"', eq_pos)
                    if eq_pos != -1 and quote_pos != -1:
                        key_part = line[:quote_pos].strip()
                        
                        # Get content between quotes across all lines
                        content_start = line[quote_pos + 1:]
                        content_parts = [content_start]
                        
                        for k in range(i + 1, j + 1):
                            if k == j:  # Last line with closing quote
                                close_quote_pos = lines[k].rfind('"')
                                if close_quote_pos != -1:
                                    content_parts.append(lines[k][:close_quote_pos])
                                else:
                                    content_parts.append(lines[k])
                            else:
                                content_parts.append(lines[k].strip())
                        
                        full_content_str = '\n'.join(content_parts)
                        
                        # Always use heredoc for anything with special markers or that's multiline
                        if (any(marker in full_content_str for marker in ['<!--', '<policies>', 'Server=tcp:', 'Driver={', 'ODBC Driver', 'Import-Module', '$array', 'foreach('])
                            or len(full_content_str) > 100 or '\n' in full_content_str):
                            # Use heredoc
                            clean_content = full_content_str.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '  ')
                            final_lines.append(f'{key_part} = <<EOF')
                            final_lines.append(clean_content)
                            final_lines.append('EOF')
                        else:
                            # Escape and keep as single line
                            escaped_content = full_content_str.replace('\n', '\\n').replace('\r', '')
                            final_lines.append(f'{key_part} = "{escaped_content}"')
                        
                        # Skip processed lines
                        i = j + 1
                        continue
        
        # If we reach here, it's a normal line
        final_lines.append(line)
        i += 1
    
    return '\n'.join(final_lines)

def fix_duplicate_id_lines_in_file(file_path: Path) -> None:
    """
    Fix duplicate id = lines in a Terraform file.
    This is a post-processing step that runs after the file is written.
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # Check if the file has duplicate id = lines
        if "id = \n  id =" in content:
            # Use regex to fix the duplicate lines
            fixed_content = re.sub(r'(\bid\s*=\s*)\n\s*(\bid\s*=\s*[^\n]+)', r'\2', content)
            
            # Write the fixed content back
            file_path.write_text(fixed_content, encoding="utf-8")
    except Exception as e:
        print(f"    Error fixing {file_path.name}: {e}", file=sys.stderr)

def pretty_hcl(hcl: str) -> str:
    """
    Format HCL code with proper Terraform indentation and structure.
    """
    hcl = _strip_headers(hcl).strip()
    
    # First, fix multi-line strings
    hcl = fix_multiline_strings(hcl)

    # Handle problematic quotes in strings that break parsing
    # Fix nested quotes that appear in PowerShell content
    hcl = re.sub(r'Import-Module\s+"([^"]*)"([^"]*)"([^"]*)"', r'Import-Module \1\2\3', hcl)
    
    # Convert JSON-style keys:  "Key": -> "Key" =
    hcl = re.sub(r'"([^"]+)"\s*:', r'"\1" =', hcl)
    # Also handle unquoted keys with a colon:  key: -> key =
    hcl = re.sub(r'(?<!")\b([A-Za-z0-9_]+)\b\s*:', r'\1 =', hcl)

    # Fix malformed URLs (https =// should be https://)
    hcl = re.sub(r'https\s*=\s*//', 'https://', hcl)
    hcl = re.sub(r'Server=tcp\s*=\s*', 'Server=tcp:', hcl)

    # Fix the provider block issue first
    hcl = re.sub(r'\bprovider\s*\n\s*{', 'provider "azurerm" {', hcl)
    hcl = re.sub(r'\}provider\s+"([^"]+)"\s*{', r'}\n\nprovider "\1" {', hcl)  # Fix merged provider blocks
    
    # Fix any stray provider blocks
    hcl = re.sub(r'\}\s*provider\s*{', '}\n\nprovider "azurerm" {', hcl)
    
    # AGGRESSIVE LINE BREAKING for single-line HCL
    # Step 1: Break after opening braces
    hcl = re.sub(r'\{\s*', '{\n', hcl)
    
    # Step 2: Break before closing braces
    hcl = re.sub(r'\s*\}', '\n}', hcl)
    
    # Step 3: Handle very long quoted strings that should be heredocs BEFORE other processing
    # Look for extremely long strings that are likely to be code/scripts
    def handle_long_strings(text):
        # More aggressive pattern - catch any string longer than 200 chars OR with specific markers
        pattern = r'(\w+\s*=\s*)"([^"]{200,}|[^"]*(?:Import-Module|PowerShell|$array|foreach|Server=tcp|Driver={)[^"]*)"'
        
        def replacement(match):
            key = match.group(1).strip()
            content = match.group(2)
            
            # Always use heredoc for very long strings or scripts
            clean_content = content.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\\t', '  ')
            return f'{key} = <<EOF\n{clean_content}\nEOF'
        
        return re.sub(pattern, replacement, text, flags=re.DOTALL)
    
    hcl = handle_long_strings(hcl)
    
    # Step 4: Break after key-value assignments when followed by another key
    # BUT preserve quoted strings with special content
    # Look for pattern: value  key = or value  "key" = or value  key {
    # but not if we're inside a complex quoted string
    hcl = re.sub(r'(=\s*(?:"[^"]*(?:\\r\\n|\\n)[^"]*"|"[^"]*"|[^"\s{][^{]*?))\s+([a-zA-Z_"]\w*(?:\s*=|\s*{))', r'\1\n\2', hcl)
    
    # Step 5: Break after closing values when followed by keys
    hcl = re.sub(r'((?:true|false|\d+|"[^"]*"|\]|\)))\s+([a-zA-Z_"]\w*\s*[={])', r'\1\n\2', hcl)
    
    # Step 6: Break after closing arrays/objects when followed by keys
    hcl = re.sub(r'(\])\s+([a-zA-Z_"]\w*\s*[={])', r'\1\n\2', hcl)
    
    # Step 7: Break inside blocks when there are multiple properties
    # This handles cases like: key1 = "value"  key2 = "value"
    # But avoid breaking inside complex quoted strings AND avoid breaking import blocks
    # Modified to exclude import blocks from this aggressive line breaking
    hcl = re.sub(r'([^{\n"])\s{2,}([a-zA-Z_"][^=]*=)', r'\1\n\2', hcl)
    
    # Step 7: Ensure spacing around equals signs
    hcl = re.sub(r'\s*=\s*', ' = ', hcl)
    
    # Step 8: Fix double equals that might have been created
    hcl = re.sub(r'\s*=\s*=\s*', ' = ', hcl)
    
    # Step 9: Clean up multiple newlines and spaces
    hcl = re.sub(r'\n\s*\n', '\n', hcl)
    hcl = re.sub(r' {2,}', ' ', hcl)
    
    # Step 10: Fix duplicate id = lines in import blocks - FINAL FIX
    # This is the key fix for the reported issue - apply at the very end
    # Use a comprehensive approach to handle all variations
    
    # First, handle the most common case: empty id = followed by id = with value
    hcl = re.sub(r'(\bid\s*=\s*)\n\s*(\bid\s*=\s*[^\n]+)', r'\2', hcl)
    
    # Then handle any remaining cases where id = is followed by another id = on the next line
    hcl = re.sub(r'(\bid\s*=\s*)\n\s*(\bid\s*=\s*)', r'\1', hcl)
    
    # Final cleanup: ensure proper spacing after id = in import blocks
    hcl = re.sub(r'(\bid\s*=\s*)([^"\s])', r'\1\2', hcl)
    
    # Now apply proper indentation
    lines = hcl.split('\n')
    formatted_lines = []
    indent_level = 0
    in_heredoc = False
    heredoc_marker = ""
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            continue  # Skip empty lines for now
            
        # Handle heredoc
        if not in_heredoc and '<<' in stripped:
            marker_match = re.search(r'<<(\w+)', stripped)
            if marker_match:
                heredoc_marker = marker_match.group(1)
                in_heredoc = True
                formatted_lines.append("  " * indent_level + stripped)
                continue
        
        if in_heredoc:
            if stripped == heredoc_marker:
                in_heredoc = False
                heredoc_marker = ""
                formatted_lines.append(stripped)
            else:
                formatted_lines.append(stripped)
            continue
        
        # Handle closing braces
        if stripped == '}':
            indent_level = max(0, indent_level - 1)
            formatted_lines.append("  " * indent_level + stripped)
            continue
        
        # Add current line with proper indentation
        formatted_lines.append("  " * indent_level + stripped)
        
        # Handle opening braces
        if stripped.endswith('{'):
            indent_level += 1
    
    # Join and final cleanup
    result = '\n'.join(formatted_lines)
    
    # Ensure resource/data blocks are properly formatted
    result = re.sub(
        r'^(\s*)(resource|data)\s+(".*?")\s+(".*?")\s*{',
        r'\1\2 \3 \4 {',
        result,
        flags=re.MULTILINE
    )
    
    # Note: Duplicate id = lines will be fixed in post-processing
    
    return result.strip() + '\n'

def format_block_content(lines: List[str]) -> List[str]:
    """Format content within a block (like tags, app_settings, etc.)"""
    if len(lines) < 2:
        return lines
    
    # Get the base indentation from the first line
    first_line = lines[0]
    base_indent = len(first_line) - len(first_line.lstrip())
    
    result = [first_line]  # Opening line
    
    # Process middle lines (the content)
    for line in lines[1:-1]:
        stripped = line.strip()
        if stripped:
            # Add proper indentation for content
            result.append(" " * (base_indent + 2) + stripped)
        else:
            result.append("")
    
    # Add closing line
    if lines[-1].strip() == '}':
        result.append(" " * base_indent + "}")
    else:
        result.append(lines[-1])
    
    return result

def extract_resource_name(hcl_content: str) -> str:
    """
    Extract the resource name from HCL content.
    Looks for patterns like: resource "azurerm_virtual_machine_extension" "mdewindows"
    or import blocks like: to = azurerm_virtual_machine_extension.mdewindows
    Returns the resource name (e.g., "mdewindows") or empty string if not found.
    """
    # Pattern to match resource definitions
    resource_pattern = r'resource\s+"[^"]+"\s+"([^"]+)"'
    match = re.search(resource_pattern, hcl_content)
    if match:
        return match.group(1)
    
    # Pattern to match import blocks
    import_pattern = r'to\s*=\s*[^.]*\.([^"]+)'
    match = re.search(import_pattern, hcl_content)
    if match:
        return match.group(1)
    
    return ""

def make_unique_resource_name(hcl_content: str, existing_names: set, base_name: str) -> tuple[str, str]:
    """
    Make a resource name unique by adding a counter if needed.
    Returns (unique_name, modified_hcl_content)
    """
    if base_name not in existing_names:
        existing_names.add(base_name)
        return base_name, hcl_content
    
    # Find a unique name by adding a counter
    counter = 1
    while True:
        unique_name = f"{base_name}_{counter}"
        if unique_name not in existing_names:
            existing_names.add(unique_name)
            # Replace the resource name in the HCL content
            modified_hcl = re.sub(
                r'(resource\s+"[^"]+"\s+")[^"]+(")',
                rf'\1{unique_name}\2',
                hcl_content
            )
            return unique_name, modified_hcl
        counter += 1

def write_outputs(items: Iterable[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
    """
    Write Terraform by asset type into OUT_DIR/<asset_type>.tf.
    Also writes provider.tf once and import_commands.bat (Windows batch file).
    Handles duplicate resource names by adding counters.
    """
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    per_type: Dict[str, List[str]] = {}
    provider_written = False
    import_cmds_path = out_dir / OUT_IMPORT_CMDS
    
    # Track resource names per asset type to avoid duplicates
    resource_names_per_type: Dict[str, set] = {}
    # Track the mapping of original names to unique names
    name_mapping_per_type: Dict[str, Dict[str, str]] = {}

    # Windows batch file header
    with import_cmds_path.open("w", encoding="utf-8") as bat:
        bat.write("@echo off\n")
        bat.write("REM Terraform import commands for Azure resources\n")
        bat.write("REM Generated by firefly_bulk_codify_azure_windows.py\n\n")
        
        for req, resp in items:
            asset_type = (req.get("assetType") or "misc").strip()
            buf = per_type.setdefault(asset_type, [])
            
            # Initialize resource names set for this asset type if not exists
            if asset_type not in resource_names_per_type:
                resource_names_per_type[asset_type] = set()
                name_mapping_per_type[asset_type] = {}

            # provider block (once)
            if INCLUDE_PROVIDER and not provider_written:
                pb = resp.get("providerBlock")
                if pb:
                    # Clean up the provider block before writing
                    cleaned_pb = pb.strip()
                    
                    # Check if it's a malformed or empty provider block
                    if (cleaned_pb == '}' or 
                        cleaned_pb == 'provider {' or 
                        'provider' not in cleaned_pb or
                        len(cleaned_pb.split('\n')) < 3):
                        # Create a proper provider block
                        cleaned_pb = 'provider "azurerm" {\n  features {}\n}'
                    else:
                        # Try to format the existing block
                        try:
                            cleaned_pb = pretty_hcl(pb)
                            # Double-check the result
                            if not cleaned_pb.strip() or cleaned_pb.strip() == '}':
                                cleaned_pb = 'provider "azurerm" {\n  features {}\n}'
                        except:
                            # If formatting fails, use default
                            cleaned_pb = 'provider "azurerm" {\n  features {}\n}'
                    
                    (out_dir / "provider.tf").write_text(cleaned_pb + '\n', encoding="utf-8")
                    provider_written = True

            # resource HCL
            cr = resp.get("codifiedResult") or ""
            unique_resource_name = None
            if cr:
                # Check for duplicate resource names and make them unique
                formatted_cr = pretty_hcl(cr)
                resource_name = extract_resource_name(formatted_cr)
                if resource_name:
                    unique_resource_name, modified_cr = make_unique_resource_name(
                        formatted_cr, 
                        resource_names_per_type[asset_type], 
                        resource_name
                    )
                    # Store the mapping for use with import blocks
                    name_mapping_per_type[asset_type][resource_name] = unique_resource_name
                    if unique_resource_name != resource_name:
                        print(f"    Renamed duplicate resource: {resource_name} → {unique_resource_name}", file=sys.stderr)
                    buf.append(modified_cr)
                else:
                    # Always add the content even if we can't extract the resource name
                    # This matches the original script behavior
                    buf.append(formatted_cr)

            # import blocks + commands
            if INCLUDE_IMPORTS:
                ib = resp.get("importBlocks") or ""
                if ib and unique_resource_name:
                    # Use the same unique name that was assigned to the resource
                    formatted_ib = pretty_hcl(ib)
                    import_resource_name = extract_resource_name(formatted_ib)
                    if import_resource_name:
                        # Use the mapping to get the correct unique name
                        target_name = name_mapping_per_type[asset_type].get(import_resource_name, import_resource_name)
                        
                        # Replace the import block resource name
                        modified_ib = re.sub(
                            r'(to\s*=\s*[^.]*\.)[^"\s]+',
                            rf'\1{target_name}',
                            formatted_ib
                        )
                        if target_name != import_resource_name:
                            print(f"    Updated import block: {import_resource_name} → {target_name}", file=sys.stderr)
                        buf.append(modified_ib)
                    else:
                        buf.append(formatted_ib)
                elif ib:
                    buf.append(pretty_hcl(ib))
                        
                ic = resp.get("importCommand") or ""
                if ic:
                    bat.write(ic + "\n")

    # Write per-type files
    written = 0
    for asset_type, chunks in per_type.items():
        safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", asset_type).strip("_") or "misc"
        file_path = out_dir / f"{safe_name}.tf"
        file_path.write_text("".join(chunks), encoding="utf-8")
        
        # Post-process to fix duplicate id = lines
        fix_duplicate_id_lines_in_file(file_path)
        
        written += 1

    # Ensure we have a proper provider.tf file even if none was written or it's malformed
    provider_path = out_dir / "provider.tf"
    if not provider_written:
        provider_path.write_text('provider "azurerm" {\n  features {}\n}\n', encoding="utf-8")
    else:
        # Check if the existing provider.tf is valid
        if provider_path.exists():
            content = provider_path.read_text(encoding="utf-8").strip()
            # If it's just a closing brace or otherwise malformed, replace it
            if content == '}' or content == 'provider {' or len(content) < 10:
                provider_path.write_text('provider "azurerm" {\n  features {}\n}\n', encoding="utf-8")

    if AUTO_TERRAFORM_FMT:
        try:
            import shutil, subprocess
            if shutil.which("terraform"):
                # Windows-compatible terraform fmt command
                subprocess.run(["terraform", "fmt", str(out_dir)], check=False, shell=True)
        except Exception:
            pass

    # Print summary of duplicate resource handling
    total_duplicates = 0
    for asset_type, names in resource_names_per_type.items():
        duplicates = [name for name in names if '_' in name and name.split('_')[-1].isdigit()]
        if duplicates:
            total_duplicates += len(duplicates)
            print(f"    {asset_type}: {len(duplicates)} duplicate resources renamed", file=sys.stderr)
    
    if total_duplicates > 0:
        print(f"    Total duplicate resources handled: {total_duplicates}", file=sys.stderr)

    print(f"Wrote {written} .tf files to: {out_dir}")
    print(f"Helper import commands: {import_cmds_path}")

# =============== Main ===============
def main() -> None:
    print("[0/7] Testing SSL connection…", file=sys.stderr)
    if not test_ssl_connection():
        print("SSL connection test failed. Please check your SSL configuration.", file=sys.stderr)
        return
    
    print("[1/7] Authenticating…", file=sys.stderr)
    login(ACCESS_KEY, SECRET_KEY)

    print("[2/7] Resolve subscription…", file=sys.stderr)
    if AZ_SUBSCRIPTION_ID:
        sub = AZ_SUBSCRIPTION_ID
    elif DATA_SOURCE_NAME:
        sub = resolve_subscription_id_by_name(DATA_SOURCE_NAME)
    else:
        raise APIError("Set AZ_SUBSCRIPTION_ID or DATA_SOURCE_NAME")

    provider_ids = [sub]

    print("[3/7] Listing inventory…", file=sys.stderr)
    assets = inventory(provider_ids)
    if not assets:
        print("No assets returned.", file=sys.stderr)
        return

    print("[4/7] Filtering assets…", file=sys.stderr)
    print(f"    matched assets: {len(assets)}", file=sys.stderr)

    # Build codify requests (AWS-style)
    reqs: List[Dict[str, Any]] = []
    for a in assets:
        reqs.append({
            "assetType": a.get("assetType"),
            "assetId": a.get("assetId"),
            "iacType": "terraform",
            "provider": "azurerm",
            "accountNumber": sub,
        })

    print(f"[5/7] Codifying assets (total: {len(reqs)})…", file=sys.stderr)
    codified_pairs = codify_assets(reqs, sleep_sec=0.02)

    # Add resource group requests if RESOURCE_GROUPS is specified (after main assets)
    if RESOURCE_GROUPS:
        print(f"[5.5/7] Adding resource group requests for: {RESOURCE_GROUPS}", file=sys.stderr)
        rg_reqs = []
        for rg in RESOURCE_GROUPS:
            # Use the correct asset ID format from inspection data
            rg_asset_id = f"arn:azurerm::::/subscriptions/{sub}/resourceGroups/{rg}"
            rg_reqs.append({
                "assetType": "azurerm_resource_group",
                "assetId": rg_asset_id,
                "iacType": "terraform",
                "provider": "azurerm",
                "accountNumber": sub,
            })
            print(f"    Resource group asset ID: {rg_asset_id}", file=sys.stderr)
        
        # Try to codify resource groups separately
        print(f"    Attempting to codify {len(rg_reqs)} resource groups...", file=sys.stderr)
        rg_codified_pairs = codify_assets(rg_reqs, sleep_sec=0.02)
        
        # Add successful resource group codifications to the main list
        codified_pairs.extend(rg_codified_pairs)
        print(f"    Successfully codified {len(rg_codified_pairs)} resource groups", file=sys.stderr)

    print("[6/7] Writing outputs…", file=sys.stderr)
    write_outputs(codified_pairs)

if __name__ == "__main__":
    try:
        main()
    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        sys.exit(130)
