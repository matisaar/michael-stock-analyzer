"""Bug report endpoint - logs reports and optionally emails via Formspree"""
from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime

FORMSPREE_ID = os.environ.get('FORMSPREE_ID', '') or 'meelqaqa'

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
            
            # Always log to Vercel function logs (Vercel dashboard > Deployments > Functions > Logs)
            print(f"===== BUG REPORT =====")
            print(f"Time: {timestamp}")
            print(f"Message: {message}")
            print(f"Page: {page}")
            print(f"UA: {user_agent}")
            print(f"======================")
            
            email_sent = False
            email_error = None
            fid = FORMSPREE_ID
            try:
                import urllib.request
                formspree_data = json.dumps({
                    'message': f"BUG REPORT\n\n{message}\n\nPage: {page}\nTime: {timestamp}",
                    '_subject': 'Bosdet Labs Bug Report'
                }).encode()
                
                req = urllib.request.Request(
                    f'https://formspree.io/f/{fid}',
                    data=formspree_data,
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json'}
                )
                urllib.request.urlopen(req, timeout=10)
                email_sent = True
            except Exception as email_err:
                email_error = str(email_err)
                print(f"Formspree error: {email_err}")
            
            self.wfile.write(json.dumps({'ok': True, 'email_sent': email_sent, 'logged': True, 'fid': fid, 'v': 2, 'email_error': email_error}).encode())
            
        except Exception as e:
            print(f"Bug report error: {e}")
            self.wfile.write(json.dumps({'ok': True, 'logged': True}).encode())
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
