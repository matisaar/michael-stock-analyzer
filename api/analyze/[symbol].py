"""Analyze a stock by scraping Yahoo Finance"""
from http.server import BaseHTTPRequestHandler
import json
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

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

def scrape_yahoo(symbol):
    """Scrape Yahoo Finance for stock data"""
    data = {
        'symbol': symbol.upper(),
        'name': symbol.upper(),
        'price': 0,
        'change_percent': 0,
        'market_cap': 0,
        'pe_ratio': 0,
        'eps': 0,
        'week_52_high': 0,
        'week_52_low': 0,
        'roa': 0,
        'roe': 0,
        'profit_margin': 0,
        'gross_margin': 0,
        'cash': 0,
        'debt': 0,
        'ps_ratio': 0,
        'pb_ratio': 0,
        'fcf': 0,
    }
    
    # Scrape main quote page
    try:
        url = f'https://finance.yahoo.com/quote/{symbol}'
        resp = requests.get(url, headers=HEADERS, timeout=15)
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
        
        # Parse table rows for quote data
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].text.strip().lower()
                value = cells[1].text.strip()
                
                if 'market cap' in label:
                    data['market_cap'] = parse_number(value)
                elif 'pe ratio' in label:
                    data['pe_ratio'] = parse_number(value)
                elif '52 week' in label:
                    parts = value.replace(' ', '').split('-')
                    if len(parts) == 2:
                        data['week_52_low'] = parse_number(parts[0])
                        data['week_52_high'] = parse_number(parts[1])
                elif label.startswith('eps'):
                    data['eps'] = parse_number(value)
    except Exception as e:
        print(f"Quote error: {e}")
    
    # Scrape key statistics page
    try:
        url = f'https://finance.yahoo.com/quote/{symbol}/key-statistics'
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for row in soup.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) >= 2:
                label = cells[0].text.strip().lower()
                value = cells[1].text.strip()
                
                if 'return on assets' in label:
                    data['roa'] = parse_number(value)
                elif 'return on equity' in label:
                    data['roe'] = parse_number(value)
                elif 'profit margin' in label and 'operating' not in label and 'gross' not in label:
                    data['profit_margin'] = parse_number(value)
                elif 'gross margin' in label or 'gross profit' in label:
                    data['gross_margin'] = parse_number(value)
                elif 'total cash' in label and 'per share' not in label:
                    data['cash'] = parse_number(value)
                elif 'total debt' in label:
                    data['debt'] = parse_number(value)
                elif 'price/sales' in label:
                    data['ps_ratio'] = parse_number(value)
                elif 'price/book' in label:
                    data['pb_ratio'] = parse_number(value)
                elif 'levered free cash' in label:
                    data['fcf'] = parse_number(value)
    except Exception as e:
        print(f"Stats error: {e}")
    
    return data

def calculate_score(data):
    """Calculate investment score based on Michael's criteria"""
    score = 0
    checks = []
    
    roa = data.get('roa', 0)
    roe = data.get('roe', 0)
    cash = data.get('cash', 0)
    debt = data.get('debt', 0)
    price = data.get('price', 0)
    fair_value = data.get('fair_value', price)
    profit_margin = data.get('profit_margin', 0)
    ps_ratio = data.get('ps_ratio', 0)
    fcf = data.get('fcf', 0)
    
    # ROA check
    if roa > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROA ({roa:.1f}%) > 10%'})
    elif roa > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROA ({roa:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa:.1f}%) < 10%'})
    
    # ROE check
    if roe > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROE ({roe:.1f}%) > 10%'})
    elif roe > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROE ({roe:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROE ({roe:.1f}%) < 10%'})
    
    # Cash vs Debt
    if cash > 0 and cash >= debt:
        score += 15
        checks.append({'pass': True, 'text': f'Cash (${format_number(cash)}) covers debt'})
    elif debt > 0:
        checks.append({'pass': False, 'text': f'Debt (${format_number(debt)}) exceeds cash'})
    else:
        checks.append({'pass': 'warn', 'text': 'Cash/Debt data unavailable'})
    
    # Fair value check
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        if upside > 30:
            score += 20
            checks.append({'pass': True, 'text': f'{upside:.0f}% undervalued'})
        elif upside > 10:
            score += 10
            checks.append({'pass': 'warn', 'text': f'{upside:.0f}% below fair value'})
        elif upside > 0:
            score += 5
            checks.append({'pass': 'warn', 'text': 'Near fair value'})
        else:
            checks.append({'pass': False, 'text': f'Overvalued by {abs(upside):.0f}%'})
    
    # Profit margin
    if profit_margin > 15:
        score += 10
        checks.append({'pass': True, 'text': f'Strong margin ({profit_margin:.1f}%)'})
    elif profit_margin > 5:
        score += 5
        checks.append({'pass': 'warn', 'text': f'Margin ({profit_margin:.1f}%)'})
    elif profit_margin > 0:
        checks.append({'pass': 'warn', 'text': f'Low margin ({profit_margin:.1f}%)'})
    else:
        checks.append({'pass': False, 'text': 'Negative/no margin data'})
    
    # P/S ratio
    if ps_ratio > 0 and ps_ratio < 2:
        score += 10
        checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) attractive'})
    elif ps_ratio > 0:
        checks.append({'pass': 'warn', 'text': f'P/S ({ps_ratio:.2f}x) high'})
    
    # FCF
    if fcf > 0:
        score += 15
        checks.append({'pass': True, 'text': f'Positive FCF (${format_number(fcf)})'})
    else:
        checks.append({'pass': False, 'text': 'Negative/no FCF data'})
    
    return score, checks

def calculate_fair_value(data):
    """Estimate fair value"""
    eps = data.get('eps', 0)
    price = data.get('price', 0)
    
    fair_values = []
    
    # P/E method (assuming fair P/E of 15)
    if eps > 0:
        fair_values.append(eps * 15)
    
    # If we have P/E, estimate based on growth
    pe = data.get('pe_ratio', 0)
    if pe > 0 and price > 0:
        # If PE is low, stock might be undervalued
        if pe < 15:
            fair_values.append(price * (15 / pe))
        else:
            fair_values.append(price * 0.9)  # Slightly overvalued
    
    if fair_values:
        return sum(fair_values) / len(fair_values)
    
    return price * 1.1  # Default: assume 10% upside

def get_recommendation(score, upside):
    if score >= 70 and upside > 30:
        return {'signal': 'STRONG BUY', 'color': '#00d374', 'reason': 'High score with significant undervaluation'}
    elif score >= 60 and upside > 15:
        return {'signal': 'BUY', 'color': '#00d374', 'reason': 'Good fundamentals and undervalued'}
    elif score >= 50 and upside > 0:
        return {'signal': 'HOLD', 'color': '#ffb800', 'reason': 'Decent fundamentals, fair price'}
    elif score >= 40:
        return {'signal': 'WATCH', 'color': '#ffb800', 'reason': 'Some concerns, monitor closely'}
    else:
        return {'signal': 'AVOID', 'color': '#ff5252', 'reason': 'Does not meet investment criteria'}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Get symbol from path
        symbol = self.path.split('/')[-1].split('?')[0].upper()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Scrape data
        data = scrape_yahoo(symbol)
        
        if not data or data['price'] == 0:
            self.wfile.write(json.dumps({
                'error': f'Could not find data for {symbol}',
                'symbol': symbol
            }).encode())
            return
        
        # Calculate fair value
        fair_value = calculate_fair_value(data)
        data['fair_value'] = fair_value
        
        # Calculate score
        score, checks = calculate_score(data)
        
        # Calculate upside
        price = data['price']
        upside = ((fair_value - price) / price * 100) if price > 0 else 0
        
        result = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'quote': {
                'name': data['name'],
                'price': data['price'],
                'change_percent': data['change_percent'],
                'market_cap': data['market_cap'],
                'week_52_high': data['week_52_high'],
                'week_52_low': data['week_52_low'],
                'industry': 'Stock',
            },
            'fundamentals': {
                'pe_ratio': data['pe_ratio'],
                'ps_ratio': data['ps_ratio'],
                'pb_ratio': data['pb_ratio'],
                'eps': data['eps'],
                'roa': data['roa'],
                'roe': data['roe'],
                'profit_margin': data['profit_margin'],
                'gross_margin': data['gross_margin'],
                'cash': data['cash'],
                'debt': data['debt'],
                'fcf': data['fcf'],
            },
            'fair_value': round(fair_value, 2),
            'upside_percent': round(upside, 1),
            'investment_score': score,
            'checklist': checks,
            'recommendation': get_recommendation(score, upside),
            'source': 'Yahoo Finance (scraped)'
        }
        
        self.wfile.write(json.dumps(result).encode())
