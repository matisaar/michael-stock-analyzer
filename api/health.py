"""Health check endpoint for Vercel serverless function"""
from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            'status': 'ok',
            'timestamp': datetime.now().isoformat(),
            'tradier_configured': bool(os.environ.get('TRADIER_API_KEY')),
            'fmp_configured': bool(os.environ.get('FMP_API_KEY'))
        }
        
        self.wfile.write(json.dumps(response).encode())
        return
