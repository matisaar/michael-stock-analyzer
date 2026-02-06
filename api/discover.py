"""Generate random stock picks for discovery - pulls 3 random stocks from different pools"""
from http.server import BaseHTTPRequestHandler
import json
import random
from datetime import datetime
import yfinance as yf

# Diverse pool of ~200 stocks across sectors, sizes, and styles
STOCK_POOLS = {
    'large_cap_tech': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'AMD', 'INTC', 'CSCO', 'QCOM', 'TXN', 'IBM', 'NOW', 'UBER', 'SHOP'],
    'finance': ['JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'SCHW', 'BLK', 'AXP', 'C', 'USB', 'PNC', 'COF', 'PYPL', 'SQ', 'COIN', 'HOOD', 'SOFI', 'ALLY'],
    'healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD', 'MRNA', 'REGN', 'ISRG', 'DXCM', 'VEEV', 'ZBH', 'HCA', 'CVS'],
    'consumer': ['WMT', 'COST', 'HD', 'MCD', 'SBUX', 'NKE', 'TGT', 'LOW', 'TJX', 'LULU', 'CMG', 'DPZ', 'YUM', 'ROST', 'DG', 'DLTR', 'KR', 'EL', 'DECK', 'CROX'],
    'energy_materials': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PSX', 'VLO', 'OXY', 'LIN', 'APD', 'ECL', 'NEM', 'FCX', 'FSLR', 'ENPH', 'NEE', 'DUK', 'SO', 'D', 'AEP'],
    'industrial': ['CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'BA', 'UPS', 'FDX', 'UNP', 'WM', 'ETN', 'ITW', 'EMR', 'GD', 'NOC', 'MMM', 'JCI', 'ROK', 'FAST'],
    'media_telecom': ['DIS', 'NFLX', 'CMCSA', 'T', 'VZ', 'TMUS', 'SPOT', 'ROKU', 'WBD', 'PARA', 'LYV', 'RBLX', 'EA', 'TTWO', 'MTCH', 'SNAP', 'PINS', 'ZM', 'DKNG', 'CHTR'],
    'small_mid_cap': ['PLTR', 'SNOW', 'CRWD', 'DDOG', 'NET', 'ZS', 'MDB', 'HUBS', 'BILL', 'PCTY', 'PAYC', 'FIVE', 'TOST', 'CAVA', 'BROS', 'SHAK', 'WING', 'DUOL', 'MNDY', 'GTLB'],
    'reits_dividend': ['O', 'AMT', 'PLD', 'SPG', 'EQIX', 'PSA', 'DLR', 'VICI', 'WELL', 'AVB', 'KO', 'PEP', 'PG', 'CL', 'CLX', 'GIS', 'K', 'SJM', 'MO', 'PM'],
    'international_adr': ['TSM', 'BABA', 'NVO', 'ASML', 'TM', 'SONY', 'SAP', 'MELI', 'SE', 'NU', 'GLOB', 'WIX', 'GRAB', 'CPNG', 'JD', 'PDD', 'BIDU', 'NIO', 'LI', 'XPEV'],
}

def safe_get(info, key, default=0):
    val = info.get(key)
    return val if val is not None else default

def to_pct(val):
    if val is None:
        return 0
    val = float(val)
    if abs(val) > 10:
        return val
    return val * 100

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        # Pick 3 stocks from 3 different random sectors
        sectors = random.sample(list(STOCK_POOLS.keys()), min(3, len(STOCK_POOLS)))
        picks = []
        for sector in sectors:
            stock = random.choice(STOCK_POOLS[sector])
            picks.append((stock, sector))
        
        results = []
        for symbol, sector in picks:
            try:
                stock = yf.Ticker(symbol)
                info = stock.info
                
                if not info:
                    continue
                
                price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
                if price == 0:
                    continue
                
                roa = safe_get(info, 'returnOnAssets', None)
                roe = safe_get(info, 'returnOnEquity', None)
                cash = safe_get(info, 'totalCash', 0)
                debt = safe_get(info, 'totalDebt', 0)
                fcf = safe_get(info, 'freeCashflow', 0)
                pe = safe_get(info, 'trailingPE', 0)
                ps = safe_get(info, 'priceToSalesTrailing12Months', 0)
                pm = safe_get(info, 'profitMargins', None)
                target = safe_get(info, 'targetMeanPrice', 0)
                
                # Quick score
                score = 0
                roa_pct = to_pct(roa)
                roe_pct = to_pct(roe)
                
                if roa_pct > 10: score += 15
                elif roa_pct > 5: score += 7
                if roe_pct > 10: score += 15
                elif roe_pct > 5: score += 7
                if cash > 0 and cash >= debt: score += 15
                if fcf and fcf > 0: score += 15
                pm_pct = to_pct(pm)
                if pm_pct > 15: score += 10
                elif pm_pct > 5: score += 5
                if ps > 0 and ps < 2: score += 10
                
                # Upside from analyst target
                if target and target > 0 and price > 0:
                    upside = ((target - price) / price) * 100
                    if upside > 30: score += 20
                    elif upside > 10: score += 10
                    elif upside > 0: score += 5
                else:
                    upside = 0
                
                score = min(score, 100)
                sector_label = sector.replace('_', ' ').title()
                
                results.append({
                    'symbol': symbol,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', symbol),
                    'price': round(price, 2),
                    'score': score,
                    'upside': round(upside, 1),
                    'sector': safe_get(info, 'sector', sector_label),
                    'industry': safe_get(info, 'industry', ''),
                    'market_cap': safe_get(info, 'marketCap', 0),
                    'pe_ratio': round(pe, 1) if pe else None,
                    'roa': round(roa_pct, 1) if roa is not None else None,
                    'roe': round(roe_pct, 1) if roe is not None else None,
                    'dividend_yield': round(to_pct(safe_get(info, 'dividendYield', None)), 2) if info.get('dividendYield') else None,
                })
                
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
        
        self.wfile.write(json.dumps({
            'picks': results,
            'timestamp': datetime.now().isoformat(),
        }).encode())
