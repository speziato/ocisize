from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import sys
import os
from core import get_image_sizes

def load_html():
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        return f.read()

HTML_CONTENT = load_html()

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" %
                         (self.address_string(),
                          self.log_date_time_string(),
                          format % args))

    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode())
        
        elif parsed_path.path == '/api/ocisize':
            query_params = parse_qs(parsed_path.query)
            image = query_params.get('image', [''])[0]
            
            if not image:
                self.send_json_response({'error': 'No image parameter provided'}, 400)
                return
            
            try:
                result = get_image_sizes(image)
                self.send_json_response({'image': image, 'platforms': result})
            except Exception as e:
                self.send_json_response({'error': str(e)}, 500)
        
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def run_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, RequestHandler)
    print(f'Server running on port {port}...')
    httpd.serve_forever()


if __name__ == '__main__':
    import os
    port = int(os.environ.get('HTTP_PORT', 8080))
    run_server(port)
