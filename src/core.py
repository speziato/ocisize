"""
Core OCI registry query functionality.
Shared between web UI and CLI.
"""
import json
import urllib.request
import urllib.error
import sys

def parse_image_name(image):
    """
    Parse image name into registry, repository, and tag.
    Examples:
      nginx:latest -> (registry-1.docker.io, library/nginx, latest)
      quay.io/prometheus/prometheus:v2.45.0 -> (quay.io, prometheus/prometheus, v2.45.0)
      registry:5000/image:latest -> (registry:5000, image, latest)
      localhost:5000/repo/image:tag -> (localhost:5000, repo/image, tag)
    """

    if ':' in image and '/' in image:
        # Need to distinguish between registry:port and image:tag
        # If there's a : before the first /, it's registry:port
        first_slash = image.index('/')
        first_colon = image.index(':')
        if first_colon < first_slash:
            # registry:port/repo:tag format
            parts = image.rsplit(':', 1)
            image = parts[0]
            tag = parts[1]
        else:
            # registry/repo:tag format
            image, tag = image.rsplit(':', 1)
    elif ':' in image and '/' not in image:
        # Simple image:tag with no registry
        image, tag = image.rsplit(':', 1)
    else:
        tag = 'latest'
    
    # Check if registry is specified
    # Registry indicators: contains '.', contains ':', or is 'localhost'
    if '/' in image:
        first_part = image.split('/')[0]
        # Check if first part looks like a registry
        is_registry = (
            '.' in first_part or           # domain.com
            ':' in first_part           # hostname:port
        )
        
        if is_registry:
            parts = image.split('/', 1)
            registry = parts[0]
            repository = parts[1] if len(parts) > 1 else ''
        else:
            # Docker Hub with namespace
            registry = 'registry-1.docker.io'
            repository = image
    else:
        # Docker Hub official image (no / at all)
        registry = 'registry-1.docker.io'
        repository = f'library/{image}'
    
    return registry, repository, tag

def format_size(bytes_size):
    units = ['', 'K', 'M', 'G', 'T', 'P']
    unit_index = 0
    size = float(bytes_size)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)}"
    else:
        return f"{size:.2f}{units[unit_index]}"

def parse_www_authenticate(header):
    """Parse WWW-Authenticate header to extract realm, service, and scope."""
    import re
    
    match = re.search(r'Bearer\s+(.+)', header)
    if not match:
        return None
    
    params = {}
    for param in re.findall(r'(\w+)="([^"]+)"', match.group(1)):
        params[param[0]] = param[1]
    
    return params

def get_auth_token(repository, www_authenticate):
    params = parse_www_authenticate(www_authenticate)
    if not params or 'realm' not in params:
        return None
    
    # Build token request URL
    realm = params['realm']
    token_params = []
    
    if 'service' in params:
        token_params.append(f"service={params['service']}")
    
    # Use the scope from WWW-Authenticate or construct it
    if 'scope' in params:
        token_params.append(f"scope={params['scope']}")
    else:
        # Construct scope for pull access
        token_params.append(f"scope=repository:{repository}:pull")
    
    token_url = f"{realm}?{'&'.join(token_params)}"
    
    try:
        req = urllib.request.Request(token_url)
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode())
            # Token can be in 'token' or 'access_token' field
            return data.get('token') or data.get('access_token')
    except Exception as e:
        print(f"Failed to get auth token: {e}", file=sys.stderr)
        return None

def fetch_manifest(registry, repository, tag, token=None):
    """Fetch manifest from OCI registry with optional authentication."""
    url = f"https://{registry}/v2/{repository}/manifests/{tag}"
    
    # Accept both manifest list and individual manifests
    headers = {
        'Accept': 'application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json'
    }
    
    # Add authorization header if token is provided
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            # Authentication required - try to get token
            www_authenticate = e.headers.get('WWW-Authenticate')
            if www_authenticate and not token:
                # First 401, try to get token
                auth_token = get_auth_token(repository, www_authenticate)
                if auth_token:
                    # Retry with token
                    return fetch_manifest(registry, repository, tag, auth_token)
            raise Exception(f"Authentication failed for {registry}/{repository}")
        elif e.code == 404:
            raise Exception(f"Image not found: {repository}:{tag}")
        else:
            raise Exception(f"HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")

def build_platform_string(platform_info: any):
    parts = []
    if platform_info.get('os'):
        parts.append(platform_info['os'])
    if platform_info.get('architecture'):
        parts.append(platform_info['architecture'])
    if platform_info.get('variant'):
        parts.append(platform_info['variant'])
    if platform_info.get('os.version'):
        parts.append(platform_info['os.version'])
    
    platform_str = '/'.join(parts) if parts else 'unknown'

    return platform_str

def get_formatted_manifest_size(platform_manifest: any):
    total_size = 0
    layers = platform_manifest.get('layers', [])
    for layer in layers:
        total_size += layer.get('size', 0)
    return format_size(total_size)
                    
def get_image_sizes(image):
    """
    Query OCI registry and get platform sizes.
    Returns a list of dicts with platform and size.
    """
    try:
        registry, repository, tag = parse_image_name(image)
        manifest = fetch_manifest(registry, repository, tag)
        
        platforms = []
        
        # Check if it's a manifest list (multi-platform)
        if manifest.get('mediaType') in [
            'application/vnd.docker.distribution.manifest.list.v2+json',
            'application/vnd.oci.image.index.v1+json'
        ]:
            # Multi-platform manifest
            for item in manifest.get('manifests', []):
                platform_info = item.get('platform', {})
                
                if platform_info.get('architecture') == 'unknown':
                    continue

                platform_str = build_platform_string(platform_info)
                
                digest = item.get('digest')
                if digest:
                    # Fetch individual platform manifest
                    platform_manifest = fetch_manifest(registry, repository, digest)
                    
                    platform_size = get_formatted_manifest_size(platform_manifest)
                    
                    platforms.append({
                        'platform': platform_str,
                        'size': platform_size
                    })
        else:
            # Single platform manifest
            platform_info = manifest.get('platform', {})
            
            platform_str = build_platform_string(platform_info)
            
            # Calculate total size from layers
            platform_size = get_formatted_manifest_size(manifest)
            
            platforms.append({
                'platform': platform_str,
                'size': platform_size
            })
        
        # Sort by platform name
        platforms.sort(key=lambda x: x['platform'])
        
        return platforms
    
    except Exception as e:
        raise Exception(f"Failed to fetch image data: {str(e)}")