"""Bug report endpoint - sends email via Formspree"""
from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime

# Using Formspree for free email forwarding
# Sign up at formspree.io, create a form, and put the form ID here
FORMSPREE_ID = os.environ.get('FORMSPREE_ID', '')

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length)) if content_length > 0 else {}
            
            message = body.get('message', '').strip()
            page = body.get('page', 'unknown')
            user_agent = self.headers.get('User-Agent', 'unknown')
            timestamp = datetime.now().isoformat()
            
            if not message:
                self.wfile.write(json.dumps({'ok': False, 'error': 'Empty message'}).encode())
                return
            
            if FORMSPREE_ID:
                import urllib.request
                formspree_data = json.dumps({
                    'message': message,
                    'page': page,
                    'user_agent': user_agent,
                    'timestamp': timestamp,
                    '_subject': 'Bosdet Labs Bug Report'
                }).encode()
                
                req = urllib.request.Request(
                    f'https://formspree.io/f/{FORMSPREE_ID}',
                    data=formspree_data,
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
                )
                urllib.request.urlopen(req, timeout=5)
            
            # Always log to Vercel function logs (visible in Vercel dashboard)
            print(f"[BUG REPORT] {timestamp}")
            print(f"  Message: {message}")
            print(f"  Page: {page}")
            print(f"  UA: {user_agent}")
            
            self.wfile.write(json.dumps({'ok': True}).encode())
            
        except Exception as e:
            print(f"Bug report error: {e}")
            # Still return success to user - report is logged in Vercel function logs
            self.wfile.write(json.dumps({'ok': True}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
