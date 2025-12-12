#!/usr/bin/env python3
"""
OCIsize
Query OCI registries for container image sizes across platforms.
"""
import sys
import argparse
import threading
import time
from core import get_image_sizes

class Spinner:
    def __init__(self, message="Loading"):
        self.message = message
        self.spinning = False
        self.thread = None

        self.frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self._can_spin = self._check_terminal()
    
    def _check_terminal(self):
        # Don't show if output is being piped
        if not sys.stdout.isatty():
            return False
        
        if sys.stderr.isatty():
            return True
        
        import os
        term = os.environ.get('TERM', '')
        if term and term != 'dumb':
            return True
        
        return False
    
    def _spin(self):
        idx = 0
        while self.spinning:
            frame = self.frames[idx % len(self.frames)]
            sys.stderr.write(f'\r{frame} {self.message}')
            sys.stderr.flush()
            time.sleep(0.1)
            idx += 1
    
    def start(self):
        if self._can_spin:
            self.spinning = True
            self.thread = threading.Thread(target=self._spin)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self, final_message=None):
        if self.spinning:
            self.spinning = False
            if self.thread:
                self.thread.join()
            # Clear the line
            sys.stderr.write('\r' + ' ' * (len(self.message) + 3) + '\r')
            sys.stderr.flush()
            if final_message:
                sys.stderr.write(f'{final_message}\n')
                sys.stderr.flush()

def format_table(platforms, image_name):
    if not platforms:
        return "No platforms found"
    
    # Calculate column widths
    platform_width = max(len(p['platform']) for p in platforms)
    platform_width = max(platform_width, len('PLATFORM'))
    size_width = max(len(p['size']) for p in platforms)
    size_width = max(size_width, len('SIZE'))
    
    # Build table
    lines = []
    lines.append(f"Image: {image_name}")
    lines.append("")
    lines.append(f"{'PLATFORM':<{platform_width}}  {'SIZE':<{size_width}}")
    lines.append("-" * (platform_width + size_width + 2))
    
    for platform in platforms:
        lines.append(f"{platform['platform']:<{platform_width}}  {platform['size']:<{size_width}}")
    
    return "\n".join(lines)

def format_json(platforms, image_name):
    import json
    return json.dumps({
        'image': image_name,
        'platforms': platforms
    }, indent=2)

def format_csv(platforms, image_name):
    lines = [f"# Image: {image_name}", "platform,size"]
    for platform in platforms:
        lines.append(f"{platform['platform']},{platform['size']}")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(
        prog='ocisize',
        description='Query OCI registries for container image sizes across platforms',
        epilog='Examples:\n'
               '  ocisize nginx:latest\n'
               '  ocisize ghcr.io/immich-app/immich-server:v2.3.1\n'
               '  ocisize --format json lscr.io/linuxserver/jellyfin:amd64-10.11.4',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'image',
        help='Container image name (e.g., nginx:latest, quay.io/repo/image:tag)'
    )
    
    parser.add_argument(
        '-f', '--format',
        choices=['table', 'json', 'csv'],
        default='table',
        help='Output format (default: table)'
    )
    
    parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='Suppress error messages and spinner'
    )

    args = parser.parse_args()
    
    spinner = None
    if not args.quiet:
        spinner = Spinner(f"Fetching manifest for {args.image}")
        spinner.start()
    
    try:
        platforms = get_image_sizes(args.image)
        
        if spinner:
            spinner.stop('')
        
        if args.format == 'json':
            output = format_json(platforms, args.image)
        elif args.format == 'csv':
            output = format_csv(platforms, args.image)
        else:
            output = format_table(platforms, args.image)
        
        print(output)
        return 0
    
    except Exception as e:
        if spinner:
            spinner.stop('✗ Failed')
        
        if not args.quiet:
            print(f"Error: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
