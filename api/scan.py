"""Scan multiple stocks"""
from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def parse_number(text):
    if not text or text == 'N/A' or text == '--' or text == '∞':
        return 0
    text = str(text).replace(',', '').replace('$', '').replace('%', '').replace('(', '-').replace(')', '').strip()
    try:
        multiplier = 1
        if text.endswith('T'):
            multiplier = 1e12
            text = text[:-1]
        elif text.endswith('B'):
            multiplier = 1e9
            text = text[:-1]
        elif text.endswith('M'):
            multiplier = 1e6
            text = text[:-1]
        elif text.endswith('K'):
            multiplier = 1e3
            text = text[:-1]
        return float(text) * multiplier
    except:
        return 0

def format_number(n):
    if n is None or n == 0:
        return '0'
    n = float(n)
    if abs(n) >= 1e12:
        return f'{n/1e12:.1f}T'
    if abs(n) >= 1e9:
        return f'{n/1e9:.1f}B'
    if abs(n) >= 1e6:
        return f'{n/1e6:.0f}M'
    if abs(n) >= 1e3:
        return f'{n/1e3:.0f}K'
    return f'{n:.0f}'

def quick_scrape(symbol):
    """Quick scrape - just get basic quote data"""
    data = {
        'symbol': symbol.upper(),
        'name': symbol.upper(),
        'price': 0,
        'change_percent': 0,
        'pe_ratio': 0,
        'market_cap': 0,
    }
    
    try:
        url = f'https://finance.yahoo.com/quote/{symbol}'
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Company name
        title = soup.find('title')
        if title:
            match = re.match(r'^(.+?)\s*\(', title.text)
            if match:
                data['name'] = match.group(1).strip()
        
        # Price
        price_el = soup.find('fin-streamer', {'data-field': 'regularMarketPrice'})
        if price_el:
            data['price'] = parse_number(price_el.get('data-value') or price_el.text)
        
        # Change percent
        change_el = soup.find('fin-streamer', {'data-field': 'regularMarketChangePercent'})
        if change_el:
            data['change_percent'] = parse_number(change_el.get('data-value') or change_el.text)
        
        # Get PE and market cap from quote table
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].text.strip().lower()
                value = cells[1].text.strip()
                
                if 'market cap' in label:
                    data['market_cap'] = parse_number(value)
                elif 'pe ratio' in label:
                    data['pe_ratio'] = parse_number(value)
    except Exception as e:
        print(f"Error scraping {symbol}: {e}")
    
    return data

def calculate_quick_score(data):
    """Quick score based on available data"""
    score = 30  # Base score
    
    pe = data.get('pe_ratio', 0)
    if pe > 0:
        if pe < 15:
            score += 25  # Low PE is good
        elif pe < 25:
            score += 10
    
    price = data.get('price', 0)
    if price > 0:
        score += 15  # Has price data
    
    if data.get('market_cap', 0) > 1e9:
        score += 10  # Large cap
    
    return min(score, 100)

def calculate_upside(data):
    """Estimate upside based on PE"""
    pe = data.get('pe_ratio', 0)
    if pe > 0 and pe < 15:
        return ((15 - pe) / pe) * 100
    elif pe > 20:
        return -((pe - 15) / pe) * 50
    return 10  # Default 10% upside estimate

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Parse query params
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        symbols_param = params.get('symbols', [''])[0]
        
        if symbols_param:
            tickers = [s.strip().upper() for s in symbols_param.split(',')][:20]
        else:
            # Default popular stocks
            tickers = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX', 'DIS', 'AMD']
        
        opportunities = []
        
        for symbol in tickers:
            try:
                data = quick_scrape(symbol)
                if data and data['price'] > 0:
                    score = calculate_quick_score(data)
                    upside = calculate_upside(data)
                    
                    opportunities.append({
                        'symbol': symbol,
                        'name': data['name'],
                        'price': data['price'],
                        'score': score,
                        'upside': round(upside, 1),
                    })
            except Exception as e:
                print(f"Error with {symbol}: {e}")
        
        # Sort by score
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        
        result = {
            'opportunities': opportunities,
            'scanned': len(tickers),
            'timestamp': datetime.now().isoformat(),
            'source': 'Yahoo Finance (scraped)'
        }
        
        self.wfile.write(json.dumps(result).encode())
