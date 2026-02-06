"""Full stock analysis with Michael's criteria"""
from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from datetime import datetime

TRADIER_API_KEY = os.environ.get('TRADIER_API_KEY', '')
TRADIER_BASE_URL = 'https://sandbox.tradier.com/v1'

FMP_API_KEY = os.environ.get('FMP_API_KEY', 'IQX03P8pFuuM1hmPtDZSRax9F5OkDKGM')
FMP_BASE_URL = 'https://financialmodelingprep.com/api/v3'

def tradier_request(endpoint, params=None):
    if not TRADIER_API_KEY:
        return None
    headers = {
        'Authorization': f'Bearer {TRADIER_API_KEY}',
        'Accept': 'application/json'
    }
    try:
        url = f'{TRADIER_BASE_URL}{endpoint}'
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Tradier API error: {e}")
    return None

def fmp_request(endpoint, params=None):
    if not FMP_API_KEY:
        return None
    try:
        url = f'{FMP_BASE_URL}{endpoint}'
        params = params or {}
        params['apikey'] = FMP_API_KEY
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"FMP API error: {e}")
    return None

def format_number(n):
    if n is None:
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

def calculate_investment_score(data):
    score = 0
    checks = []
    
    roa = data.get('roa', 0) or 0
    roe = data.get('roe', 0) or 0
    cash = data.get('cash', 0) or 0
    debt = data.get('debt', 0) or 0
    price = data.get('price', 0) or 0
    fair_value = data.get('fair_value', price) or price
    profit_margin = data.get('profit_margin', 0) or 0
    ps_ratio = data.get('ps_ratio', 0) or 0
    fcf = data.get('fcf', 0) or 0
    
    if roa > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROA ({roa:.1f}%) > 10%'})
    elif roa > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROA ({roa:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROA ({roa:.1f}%) < 10%'})
    
    if roe > 10:
        score += 15
        checks.append({'pass': True, 'text': f'ROE ({roe:.1f}%) > 10%'})
    elif roe > 5:
        score += 7
        checks.append({'pass': 'warn', 'text': f'ROE ({roe:.1f}%) moderate'})
    else:
        checks.append({'pass': False, 'text': f'ROE ({roe:.1f}%) < 10%'})
    
    if cash >= debt:
        score += 15
        checks.append({'pass': True, 'text': f'Cash (${format_number(cash)}) covers debt'})
    else:
        checks.append({'pass': False, 'text': f'Debt exceeds cash'})
    
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
            checks.append({'pass': 'warn', 'text': f'Near fair value'})
        else:
            checks.append({'pass': False, 'text': f'Overvalued by {abs(upside):.0f}%'})
    
    if profit_margin > 15:
        score += 10
        checks.append({'pass': True, 'text': f'Strong margin ({profit_margin:.1f}%)'})
    elif profit_margin > 5:
        score += 5
        checks.append({'pass': 'warn', 'text': f'Margin ({profit_margin:.1f}%)'})
    elif profit_margin > 0:
        checks.append({'pass': 'warn', 'text': f'Low margin ({profit_margin:.1f}%)'})
    else:
        checks.append({'pass': False, 'text': 'Negative margin'})
    
    if 0 < ps_ratio < 2:
        score += 10
        checks.append({'pass': True, 'text': f'P/S ({ps_ratio:.2f}x) attractive'})
    elif ps_ratio > 0:
        checks.append({'pass': 'warn', 'text': f'P/S ({ps_ratio:.2f}x)'})
    
    if fcf > 0:
        score += 15
        checks.append({'pass': True, 'text': f'Positive FCF (${format_number(fcf)})'})
    else:
        checks.append({'pass': False, 'text': 'Negative FCF'})
    
    return score, checks

def calculate_fair_value(data):
    eps = data.get('eps', 0) or 0
    book_value = data.get('book_value_per_share', 0) or 0
    fcf = data.get('fcf', 0) or 0
    shares = data.get('shares_outstanding', 0) or 0
    growth_rate = data.get('growth_rate', 0.05)
    
    fair_values = []
    
    if eps > 0:
        pe_fair_value = eps * 15
        fair_values.append(pe_fair_value)
    
    if eps > 0 and book_value > 0:
        graham = (22.5 * eps * book_value) ** 0.5
        fair_values.append(graham)
    
    if fcf > 0 and shares > 0:
        discount_rate = 0.10
        terminal_multiple = 12
        fcf_per_share = fcf / shares
        
        dcf_value = 0
        for year in range(1, 6):
            future_fcf = fcf_per_share * ((1 + growth_rate) ** year)
            dcf_value += future_fcf / ((1 + discount_rate) ** year)
        
        terminal_value = (fcf_per_share * ((1 + growth_rate) ** 5) * terminal_multiple) / ((1 + discount_rate) ** 5)
        dcf_value += terminal_value
        fair_values.append(dcf_value)
    
    if fair_values:
        return sum(fair_values) / len(fair_values)
    
    return data.get('price', 0) * 1.3

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
        # Extract symbol from path
        symbol = self.path.split('/')[-1].split('?')[0].upper()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        result = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
        }
        
        # Get quote data
        quote = {'price': 0, 'name': symbol}
        
        if TRADIER_API_KEY:
            data = tradier_request('/markets/quotes', {'symbols': symbol})
            if data and 'quotes' in data and 'quote' in data['quotes']:
                q = data['quotes']['quote']
                quote = {
                    'price': q.get('last', 0),
                    'change_percent': q.get('change_percentage', 0),
                    'week_52_high': q.get('week_52_high', 0),
                    'week_52_low': q.get('week_52_low', 0),
                    'name': q.get('description', symbol),
                    'volume': q.get('volume', 0)
                }
        
        # Get fundamentals from FMP
        fundamentals = {}
        if FMP_API_KEY:
            # Get quote if we don't have it from Tradier
            if quote['price'] == 0:
                fmp_quote = fmp_request(f'/quote/{symbol}')
                if fmp_quote and len(fmp_quote) > 0:
                    q = fmp_quote[0]
                    quote = {
                        'price': q.get('price', 0),
                        'change_percent': q.get('changesPercentage', 0),
                        'week_52_high': q.get('yearHigh', 0),
                        'week_52_low': q.get('yearLow', 0),
                        'name': q.get('name', symbol),
                        'volume': q.get('volume', 0),
                        'market_cap': q.get('marketCap', 0)
                    }
            
            # Get ratios
            ratios = fmp_request(f'/ratios-ttm/{symbol}')
            if ratios and len(ratios) > 0:
                r = ratios[0]
                fundamentals['roa'] = (r.get('returnOnAssetsTTM') or 0) * 100
                fundamentals['roe'] = (r.get('returnOnEquityTTM') or 0) * 100
                fundamentals['profit_margin'] = (r.get('netProfitMarginTTM') or 0) * 100
                fundamentals['gross_margin'] = (r.get('grossProfitMarginTTM') or 0) * 100
                fundamentals['operating_margin'] = (r.get('operatingProfitMarginTTM') or 0) * 100
                fundamentals['ps_ratio'] = r.get('priceToSalesRatioTTM') or 0
                fundamentals['pb_ratio'] = r.get('priceBookValueRatioTTM') or 0
                fundamentals['pe_ratio'] = r.get('peRatioTTM') or 0
            
            # Get balance sheet
            balance = fmp_request(f'/balance-sheet-statement/{symbol}', {'limit': 1})
            if balance and len(balance) > 0:
                b = balance[0]
                fundamentals['cash'] = b.get('cashAndCashEquivalents') or 0
                fundamentals['debt'] = b.get('totalDebt') or 0
                fundamentals['total_assets'] = b.get('totalAssets') or 0
                fundamentals['total_equity'] = b.get('totalStockholdersEquity') or 0
            
            # Get cash flow
            cashflow = fmp_request(f'/cash-flow-statement/{symbol}', {'limit': 1})
            if cashflow and len(cashflow) > 0:
                c = cashflow[0]
                fundamentals['fcf'] = c.get('freeCashFlow') or 0
                fundamentals['operating_cf'] = c.get('operatingCashFlow') or 0
            
            # Get profile
            profile = fmp_request(f'/profile/{symbol}')
            if profile and len(profile) > 0:
                p = profile[0]
                quote['name'] = p.get('companyName') or quote.get('name', symbol)
                quote['industry'] = p.get('industry') or 'N/A'
                quote['sector'] = p.get('sector') or 'N/A'
                quote['market_cap'] = p.get('mktCap') or 0
                quote['website'] = p.get('website') or ''
                quote['description'] = p.get('description') or ''
                fundamentals['eps'] = p.get('eps') or 0
                if quote.get('price', 0) > 0 and quote.get('market_cap', 0) > 0:
                    fundamentals['shares_outstanding'] = quote['market_cap'] / quote['price']
            
            # Get DCF value
            dcf = fmp_request(f'/discounted-cash-flow/{symbol}')
            if dcf and len(dcf) > 0:
                fundamentals['dcf_value'] = dcf[0].get('dcf') or 0
        
        # Combine data for analysis
        analysis_data = {
            'price': quote.get('price', 0),
            'roa': fundamentals.get('roa', 0),
            'roe': fundamentals.get('roe', 0),
            'cash': fundamentals.get('cash', 0),
            'debt': fundamentals.get('debt', 0),
            'profit_margin': fundamentals.get('profit_margin', 0),
            'ps_ratio': fundamentals.get('ps_ratio', 0),
            'fcf': fundamentals.get('fcf', 0),
            'eps': fundamentals.get('eps', 0),
            'shares_outstanding': fundamentals.get('shares_outstanding', 0)
        }
        
        # Calculate fair value
        fair_value = fundamentals.get('dcf_value') or calculate_fair_value(analysis_data)
        analysis_data['fair_value'] = fair_value
        
        # Calculate investment score
        score, checks = calculate_investment_score(analysis_data)
        
        # Calculate upside
        price = quote.get('price', 0)
        upside = ((fair_value - price) / price * 100) if price > 0 else 0
        
        result.update({
            'quote': quote,
            'fundamentals': fundamentals,
            'fair_value': round(fair_value, 2),
            'upside_percent': round(upside, 1),
            'investment_score': score,
            'checklist': checks,
            'recommendation': get_recommendation(score, upside)
        })
        
        self.wfile.write(json.dumps(result).encode())
        return
