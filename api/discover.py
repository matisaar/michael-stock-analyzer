"""Generate random stock picks for discovery - uses the SAME scoring as the analyze endpoint"""
from http.server import BaseHTTPRequestHandler
import json
import random
from datetime import datetime
import yfinance as yf

# Diverse pool of ~200 stocks across sectors
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
    """Convert yfinance decimal ratio to percentage - SAME as analyze endpoint."""
    if val is None:
        return 0
    val = float(val)
    if abs(val) > 10:
        return val
    return val * 100


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
    return f'{n:.0f}'


def calculate_fair_value(info, price):
    """Calculate blended fair value - SAME logic as analyze endpoint."""
    eps = safe_get(info, 'trailingEps', 0)
    pe = safe_get(info, 'trailingPE', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)

    fair_values = []

    if target_price and target_price > 0:
        fair_values.append(target_price)

    if forward_pe and forward_pe > 0 and eps and eps > 0:
        growth_pe = min(forward_pe * 1.2, 30)
        fair_values.append(eps * growth_pe)

    # Growth-adjusted PE fair value (PEG-based)
    earnings_growth = info.get('earningsGrowth')
    if earnings_growth and float(earnings_growth) > 0 and eps and eps > 0:
        eg = float(earnings_growth)
        growth_pct = eg * 100 if eg < 1 else eg
        fair_pe_from_growth = min(growth_pct * 1.0, 40)
        fv = eps * fair_pe_from_growth
        if fv > 0:
            fair_values.append(fv)

    if pe and pe > 0 and pe < 25 and price > 0:
        fair_values.append(price * 1.1)
    elif pe and pe > 25 and price > 0:
        fair_values.append(price * 0.95)

    if eps and eps > 0 and not fair_values:
        sector = safe_get(info, 'sector', '')
        if 'Technology' in str(sector):
            fair_values.append(eps * 25)
        elif 'Consumer' in str(sector):
            fair_values.append(eps * 20)
        else:
            fair_values.append(eps * 18)

    return sum(fair_values) / len(fair_values) if fair_values else price


def calculate_score(data):
    """Calculate investment score - SAME logic as analyze endpoint."""
    score = 0

    roa = data.get('roa', 0) or 0
    roe = data.get('roe', 0) or 0
    cash = data.get('cash', 0) or 0
    debt = data.get('debt', 0) or 0
    price = data.get('price', 0) or 0
    fair_value = data.get('fair_value', price) or price
    profit_margin = data.get('profit_margin', 0) or 0
    ps_ratio = data.get('ps_ratio', 0) or 0
    fcf = data.get('fcf', 0) or 0

    roa_pct = to_pct(roa)
    roe_pct = to_pct(roe)

    if roa_pct > 10:
        score += 15
    elif roa_pct > 5:
        score += 7

    if roe_pct > 10:
        score += 15
    elif roe_pct > 5:
        score += 7

    if cash > 0 and cash >= debt:
        score += 15

    # Fair value upside (using blended fair value, not raw analyst target)
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        if upside > 30:
            score += 20
        elif upside > 10:
            score += 10
        elif upside > 0:
            score += 5

    pm_pct = to_pct(profit_margin)
    if pm_pct > 15:
        score += 10
    elif pm_pct > 5:
        score += 5

    if ps_ratio > 0 and ps_ratio < 2:
        score += 10

    if fcf > 0:
        score += 15

    return min(score, 100)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Pick 5 stocks from 5 different random sectors, keep top 3 by score
        sectors = random.sample(list(STOCK_POOLS.keys()), min(5, len(STOCK_POOLS)))
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

                # Calculate blended fair value (same as analyze endpoint)
                fair_value = calculate_fair_value(info, price)
                upside = ((fair_value - price) / price * 100) if price > 0 else 0

                # Calculate score using the SAME function as analyze endpoint
                score_data = {
                    'roa': roa,
                    'roe': roe,
                    'cash': cash,
                    'debt': debt,
                    'price': price,
                    'fair_value': fair_value,
                    'profit_margin': pm,
                    'ps_ratio': ps,
                    'fcf': fcf,
                }
                score = calculate_score(score_data)

                roa_pct = to_pct(roa) if roa is not None else None
                roe_pct = to_pct(roe) if roe is not None else None
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
                    'roa': round(roa_pct, 1) if roa_pct is not None else None,
                    'roe': round(roe_pct, 1) if roe_pct is not None else None,
                    'dividend_yield': round(to_pct(safe_get(info, 'dividendYield', None)), 2) if info.get('dividendYield') else None,
                })

            except Exception as e:
                print(f"Error scanning {symbol}: {e}")

        # Sort by score descending and keep top 3 — surface the strongest picks
        results.sort(key=lambda x: x['score'], reverse=True)
        results = results[:3]

        self.wfile.write(json.dumps({
            'picks': results,
            'timestamp': datetime.now().isoformat(),
        }).encode())
