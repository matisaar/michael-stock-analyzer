"""Recommendation engine - Rule #1 Investing principles (Phil Town)
Finds stocks with: strong moat, Big 5 growth ≥10%, ROIC ≥10%, margin of safety."""
from http.server import BaseHTTPRequestHandler
import json
import os
import random
from datetime import datetime
import yfinance as yf

# Large universe of quality candidates across sectors
STOCK_POOLS = {
    'Technology': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'AMD', 'CSCO', 'QCOM', 'TXN', 'NOW', 'UBER', 'SHOP', 'CRWD', 'DDOG', 'NET', 'HUBS', 'INTU', 'SNPS', 'CDNS', 'KLAC', 'LRCX', 'AMAT', 'MRVL', 'PANW', 'FTNT'],
    'Financial Services': ['JPM', 'V', 'MA', 'BAC', 'GS', 'MS', 'SCHW', 'BLK', 'AXP', 'PNC', 'COF', 'PYPL', 'MCO', 'SPGI', 'ICE', 'CME', 'MSCI', 'FIS', 'AJG', 'MMC'],
    'Healthcare': ['UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'AMGN', 'REGN', 'ISRG', 'DXCM', 'VEEV', 'HCA', 'SYK', 'EW', 'IDXX', 'WST', 'ZTS', 'A'],
    'Consumer Cyclical': ['HD', 'MCD', 'SBUX', 'NKE', 'TJX', 'LULU', 'CMG', 'ROST', 'ORLY', 'AZO', 'TSCO', 'POOL', 'DECK', 'BKNG', 'LOW', 'DPZ', 'YUM', 'CPRT', 'ULTA', 'RH'],
    'Consumer Defensive': ['COST', 'WMT', 'PG', 'KO', 'PEP', 'CL', 'MNST', 'SJM', 'HSY', 'CHD', 'CLX', 'KMB', 'GIS', 'K', 'MDLZ', 'EL', 'STZ', 'BF-B', 'KR', 'WBA'],
    'Industrials': ['CAT', 'DE', 'HON', 'GE', 'RTX', 'UNP', 'WM', 'ETN', 'ITW', 'EMR', 'ROK', 'FAST', 'SHW', 'ECL', 'CTAS', 'ODFL', 'VRSK', 'GWW', 'ROP', 'TT'],
    'Communication': ['DIS', 'NFLX', 'CMCSA', 'TMUS', 'EA', 'TTWO', 'GOOGL', 'META', 'SPOT', 'LYV', 'RBLX', 'CHTR', 'OMC', 'IPG', 'WPP', 'ZM', 'MTCH', 'DKNG', 'PARA', 'WBD'],
    'Real Estate': ['AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'DLR', 'O', 'WELL', 'SPG', 'VICI'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'LIN', 'APD', 'FSLR', 'NEE', 'OKE'],
}

ALL_CANDIDATES = []
for sector, tickers in STOCK_POOLS.items():
    for t in tickers:
        ALL_CANDIDATES.append((t, sector))


def safe_get(info, key, default=0):
    val = info.get(key)
    return val if val is not None else default


def to_pct(val):
    if val is None:
        return None
    val = float(val)
    if abs(val) > 10:
        return val
    return val * 100


def calculate_roic(info):
    """ROIC = Net Income / Invested Capital. Core Rule #1 metric."""
    net_income = safe_get(info, 'netIncomeToCommon', 0)
    if not net_income:
        return None
    bv_ps = safe_get(info, 'bookValue', 0)
    shares = safe_get(info, 'sharesOutstanding', 0)
    total_debt = safe_get(info, 'totalDebt', 0)
    total_cash = safe_get(info, 'totalCash', 0)
    equity = bv_ps * shares if bv_ps and shares else 0
    invested_capital = equity + total_debt - total_cash
    if invested_capital <= 0:
        return None
    return (net_income / invested_capital) * 100


def calculate_sticker_price(info, price):
    """Phil Town's Rule #1 Sticker Price.
    Sticker = EPS × (1+g)^10 × min(2g, 50) / 1.15^10
    MOS = Sticker / 2"""
    eps = safe_get(info, 'trailingEps', 0)
    if not eps or eps <= 0:
        return None

    growth_rate = None
    # Try analyst earnings growth
    eg = info.get('earningsGrowth')
    if eg is not None:
        eg_f = float(eg)
        if eg_f > 0:
            growth_rate = eg_f if eg_f < 1 else eg_f / 100

    # Try forward vs trailing EPS
    if growth_rate is None:
        fwd = safe_get(info, 'forwardEps', 0)
        if fwd and eps and fwd > eps:
            growth_rate = (fwd - eps) / eps

    # Try revenue growth as last resort
    if growth_rate is None:
        rg = info.get('revenueGrowth')
        if rg is not None:
            rg_f = float(rg)
            if rg_f > 0:
                growth_rate = rg_f if rg_f < 1 else rg_f / 100

    if growth_rate is None or growth_rate <= 0:
        return None

    growth_rate = min(growth_rate, 0.30)  # Cap conservatively

    future_eps = eps * (1 + growth_rate) ** 10
    future_pe = min(2 * growth_rate * 100, 50)
    future_price = future_eps * future_pe
    sticker_price = future_price / (1.15 ** 10)
    mos_price = sticker_price / 2

    return {
        'sticker': round(sticker_price, 2),
        'mos_price': round(mos_price, 2),
        'growth_rate': round(growth_rate * 100, 1),
    }


def rule1_score(info, price):
    """Score a stock 0-100 based purely on Rule #1 Investing principles.

    Scoring breakdown (100 pts max):
    - ROIC ≥ 10%: up to 20 pts
    - ROE ≥ 15% (moat indicator): up to 15 pts
    - Revenue growth ≥ 10%: up to 15 pts
    - EPS growth ≥ 10%: up to 15 pts
    - FCF positive & growing: up to 10 pts
    - Price ≤ MOS price (margin of safety): up to 20 pts
    - Debt < Equity (financial fortress): up to 5 pts
    """
    score = 0

    # 1. ROIC (20 pts) — the #1 Rule #1 metric
    roic = calculate_roic(info)
    if roic is not None:
        if roic >= 15:
            score += 20
        elif roic >= 10:
            score += 14
        elif roic >= 5:
            score += 6

    # 2. ROE (15 pts) — moat indicator
    roe = to_pct(info.get('returnOnEquity'))
    if roe is not None:
        if roe >= 20:
            score += 15
        elif roe >= 15:
            score += 12
        elif roe >= 10:
            score += 6

    # 3. Revenue Growth (15 pts)
    rg = to_pct(info.get('revenueGrowth'))
    if rg is not None:
        if rg >= 15:
            score += 15
        elif rg >= 10:
            score += 12
        elif rg >= 5:
            score += 6

    # 4. EPS Growth (15 pts)
    eg = to_pct(info.get('earningsGrowth'))
    if eg is not None:
        if eg >= 15:
            score += 15
        elif eg >= 10:
            score += 12
        elif eg >= 5:
            score += 6

    # 5. FCF health (10 pts)
    fcf = safe_get(info, 'freeCashflow', 0)
    revenue = safe_get(info, 'totalRevenue', 0)
    if fcf and fcf > 0:
        score += 5
        if revenue and revenue > 0:
            fcf_margin = fcf / revenue * 100
            if fcf_margin >= 15:
                score += 5
            elif fcf_margin >= 10:
                score += 3

    # 6. Margin of Safety (20 pts) — Phil Town's sticker price
    sticker_data = calculate_sticker_price(info, price)
    mos_price = None
    sticker_price = None
    if sticker_data:
        mos_price = sticker_data['mos_price']
        sticker_price = sticker_data['sticker']
        if price <= mos_price:
            score += 20  # ON SALE — below MOS
        elif price <= sticker_price * 0.75:
            score += 14  # Good deal
        elif price <= sticker_price:
            score += 7   # Fair value

    # 7. Financial fortress (5 pts)
    cash = safe_get(info, 'totalCash', 0)
    debt = safe_get(info, 'totalDebt', 0)
    if cash > 0 and debt >= 0 and (debt == 0 or cash >= debt * 0.5):
        score += 5

    # Determine moat
    has_moat = (roic is not None and roic >= 10) and (roe is not None and roe >= 15)

    return {
        'score': min(score, 100),
        'roic': round(roic, 1) if roic else None,
        'roe': round(roe, 1) if roe else None,
        'revenue_growth': round(rg, 1) if rg else None,
        'eps_growth': round(eg, 1) if eg else None,
        'has_moat': has_moat,
        'sticker_price': sticker_price,
        'mos_price': mos_price,
        'growth_rate': sticker_data['growth_rate'] if sticker_data else None,
    }


def build_profile(watchlist):
    """Extract preferences from user's watchlist."""
    if not watchlist:
        return None

    sectors = {}
    scores = []

    for item in watchlist:
        s = item.get('sector', '')
        if s:
            sectors[s] = sectors.get(s, 0) + 1
        sc = item.get('score', 0)
        if sc:
            scores.append(sc)

    avg_score = sum(scores) / len(scores) if scores else 50
    top_sectors = sorted(sectors.items(), key=lambda x: -x[1])
    top_sector_names = [s[0] for s in top_sectors[:3]]

    return {
        'sectors': sectors,
        'top_sectors': top_sector_names,
        'avg_score': avg_score,
        'count': len(watchlist),
        'saved_symbols': set(item.get('symbol', '') for item in watchlist),
    }


def pick_candidates(profile, max_candidates=20):
    """Pick candidate stocks, favoring user's sectors but casting wide net."""
    saved = profile['saved_symbols']
    top_sectors = profile['top_sectors']

    sector_matches = []
    others = []

    for ticker, sector in ALL_CANDIDATES:
        if ticker in saved:
            continue
        matched = False
        for ts in top_sectors:
            if ts.lower() in sector.lower() or sector.lower() in ts.lower():
                matched = True
                break
        if matched:
            sector_matches.append((ticker, sector))
        else:
            others.append((ticker, sector))

    random.shuffle(sector_matches)
    random.shuffle(others)

    # Grab more candidates than we need, then let Rule #1 scoring sort them
    candidates = sector_matches[:12] + others[:8]
    return candidates[:max_candidates]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except Exception:
            body = {}

        watchlist = body.get('watchlist', [])

        if not watchlist:
            self.wfile.write(json.dumps({
                'recommendations': [],
                'message': 'Save some stocks first — we\'ll find Rule #1 quality picks based on your watchlist.',
                'profile': None,
            }).encode())
            return

        self._generate_recommendations(watchlist)

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        self.wfile.write(json.dumps({
            'recommendations': [],
            'message': 'Use POST with your watchlist.',
            'profile': None,
        }).encode())

    def _generate_recommendations(self, watchlist):
        profile = build_profile(watchlist)
        candidates = pick_candidates(profile)

        recommendations = []
        for ticker, sector in candidates:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if not info:
                    continue

                price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
                if not price:
                    continue

                # Score using Rule #1 principles
                r1 = rule1_score(info, price)
                score = r1['score']

                # Only recommend stocks scoring ≥ 30 (has some Rule #1 merit)
                if score < 30:
                    continue

                # Calculate upside from sticker price
                upside = 0
                if r1['sticker_price'] and price > 0:
                    upside = ((r1['sticker_price'] - price) / price) * 100

                recommendations.append({
                    'symbol': ticker,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', ticker),
                    'sector': safe_get(info, 'sector', sector),
                    'price': round(price, 2),
                    'score': score,
                    'upside': round(upside, 1),
                    'roic': r1['roic'],
                    'roe': r1['roe'],
                    'revenue_growth': r1['revenue_growth'],
                    'eps_growth': r1['eps_growth'],
                    'has_moat': r1['has_moat'],
                    'mos_price': r1['mos_price'],
                    'market_cap': safe_get(info, 'marketCap', 0),
                })

            except Exception as e:
                print(f"Recommend error {ticker}: {e}")
                continue

        # Sort by Rule #1 score (best first), then by upside
        recommendations.sort(key=lambda x: (-x['score'], -x['upside']))
        top_recs = recommendations[:6]

        self.wfile.write(json.dumps({
            'recommendations': top_recs,
            'profile': {
                'top_sectors': profile['top_sectors'],
                'avg_score': round(profile['avg_score']),
                'watchlist_count': profile['count'],
            },
            'analyzed': len(candidates),
            'timestamp': datetime.now().isoformat(),
        }).encode())
