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
    """Score a stock 0-100 using the same criteria as the analyze API.
    This ensures consistency between For You recommendations and stock details.

    Scoring breakdown (100 pts max):
    - ROA > 10%: up to 15 pts
    - ROE > 10%: up to 15 pts
    - Cash ≥ Debt: up to 15 pts
    - Undervalued (fair value upside): up to 20 pts
    - Profit margin > 15%: up to 10 pts
    - P/S ratio < 2: up to 10 pts
    - Positive FCF: up to 15 pts
    """
    score = 0

    # 1. ROA (15 pts) — same as analyze
    roa = to_pct(info.get('returnOnAssets'))
    if roa is not None:
        if roa > 10:
            score += 15
        elif roa > 5:
            score += 7

    # 2. ROE (15 pts) — same threshold as analyze (10%)
    roe = to_pct(info.get('returnOnEquity'))
    if roe is not None:
        if roe > 10:
            score += 15
        elif roe > 5:
            score += 7

    # 3. Cash vs Debt (15 pts)
    cash = safe_get(info, 'totalCash', 0)
    debt = safe_get(info, 'totalDebt', 0)
    if cash > 0 and cash >= debt:
        score += 15

    # 4. Fair value / Undervalued (20 pts)
    sticker_data = calculate_sticker_price(info, price)
    mos_price = None
    sticker_price = None
    upside_for_display = 0
    
    # Calculate fair value similar to analyze API
    eps = safe_get(info, 'trailingEps', 0)
    pe = safe_get(info, 'trailingPE', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)
    earnings_growth = info.get('earningsGrowth')
    
    fair_values = []
    if target_price and target_price > 0:
        fair_values.append(target_price)
    if forward_pe and forward_pe > 0 and eps and eps > 0:
        fair_values.append(eps * min(forward_pe * 1.2, 30))
    if earnings_growth and float(earnings_growth) > 0 and eps and eps > 0:
        eg = float(earnings_growth)
        gp = eg * 100 if eg < 1 else eg
        fv = eps * min(gp, 40)
        if fv > 0:
            fair_values.append(fv)
    
    fair_value = sum(fair_values) / len(fair_values) if fair_values else price
    
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        upside_for_display = upside
        if upside > 30:
            score += 20
        elif upside > 10:
            score += 10
        elif upside > 0:
            score += 5

    if sticker_data:
        mos_price = sticker_data['mos_price']
        sticker_price = sticker_data['sticker']

    # 5. Profit margin (10 pts)
    pm = to_pct(info.get('profitMargins'))
    if pm is not None:
        if pm > 15:
            score += 10
        elif pm > 5:
            score += 5

    # 6. P/S ratio (10 pts)
    ps = safe_get(info, 'priceToSalesTrailing12Months', 0)
    if ps > 0 and ps < 2:
        score += 10

    # 7. FCF (15 pts)
    fcf = safe_get(info, 'freeCashflow', 0)
    if fcf and fcf > 0:
        score += 15

    # Calculate ROIC for display (not used in scoring, but shown in UI)
    roic = calculate_roic(info)

    # Determine moat
    has_moat = (roic is not None and roic >= 10) and (roe is not None and roe >= 15)

    # Revenue and EPS growth for display
    rg = to_pct(info.get('revenueGrowth'))
    eg = to_pct(info.get('earningsGrowth'))

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
        'upside': round(upside_for_display, 1),
    }


def build_profile(watchlist):
    """Extract deep investment profile from user's watchlist.
    Learns: sector preference, score range, price tier, and investment style."""
    if not watchlist:
        return None

    sectors = {}
    scores = []
    prices = []

    for item in watchlist:
        s = item.get('sector', '')
        if s:
            sectors[s] = sectors.get(s, 0) + 1
        sc = item.get('score', 0)
        if sc:
            scores.append(sc)
        p = item.get('price_at_save', 0) or item.get('price', 0)
        if p and p > 0:
            prices.append(p)

    avg_score = sum(scores) / len(scores) if scores else 50
    top_sectors = sorted(sectors.items(), key=lambda x: -x[1])
    top_sector_names = [s[0] for s in top_sectors[:3]]

    # Sector weights (normalized): how much the user cares about each sector
    total_sector_saves = sum(sectors.values()) if sectors else 1
    sector_weights = {s: c / total_sector_saves for s, c in sectors.items()}

    # Price tier: what price range does user tend to save?
    avg_price = sum(prices) / len(prices) if prices else 200
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 1000

    # Score preference: user tends to save stocks in this range
    min_score = min(scores) if scores else 0
    max_score = max(scores) if scores else 100

    return {
        'sectors': sectors,
        'sector_weights': sector_weights,
        'top_sectors': top_sector_names,
        'avg_score': avg_score,
        'min_score': min_score,
        'max_score': max_score,
        'avg_price': avg_price,
        'min_price': min_price,
        'max_price': max_price,
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
                quality_score = r1['score']

                # Only recommend stocks with some Rule #1 merit
                if quality_score < 25:
                    continue

                # ── ADAPTIVE AFFINITY SCORING ──
                # Combines Rule #1 quality (60%) with user preference fit (40%)
                affinity = 0
                max_affinity = 40

                # Sector affinity (up to 15 pts): weighted by how much user saves from this sector
                stock_sector = safe_get(info, 'sector', sector)
                sector_w = profile['sector_weights']
                best_match = 0
                for user_sector, weight in sector_w.items():
                    if user_sector.lower() in stock_sector.lower() or stock_sector.lower() in user_sector.lower():
                        best_match = max(best_match, weight)
                affinity += best_match * 15

                # Score range affinity (up to 10 pts): is this stock's quality near what user tends to save?
                score_mid = (profile['min_score'] + profile['max_score']) / 2
                score_range = max(profile['max_score'] - profile['min_score'], 20)
                score_dist = abs(quality_score - score_mid)
                if score_dist <= score_range / 2:
                    affinity += 10
                elif score_dist <= score_range:
                    affinity += 5

                # Price tier affinity (up to 10 pts): does this stock fit user's typical price range?
                price_mid = profile['avg_price']
                price_range = max(profile['max_price'] - profile['min_price'], 50)
                price_dist = abs(price - price_mid)
                if price_dist <= price_range * 0.5:
                    affinity += 10
                elif price_dist <= price_range:
                    affinity += 5
                elif price_dist <= price_range * 2:
                    affinity += 2

                # Diversification bonus (up to 5 pts): if user has few sectors, nudge new ones
                if stock_sector not in profile['sectors'] and len(profile['sectors']) < 3:
                    affinity += 5

                # Combine: 60% Rule #1 quality + 40% affinity
                final_score = int(quality_score * 0.6 + min(affinity, max_affinity) * 0.4 / max_affinity * 100 * 0.4)

                # Use the upside calculated in rule1_score (based on fair value, same as analyze API)
                upside = r1.get('upside', 0)

                recommendations.append({
                    'symbol': ticker,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', ticker),
                    'sector': stock_sector,
                    'price': round(price, 2),
                    'score': quality_score,
                    'upside': round(upside, 1),
                    'roic': r1['roic'],
                    'roe': r1['roe'],
                    'revenue_growth': r1['revenue_growth'],
                    'eps_growth': r1['eps_growth'],
                    'has_moat': r1['has_moat'],
                    'mos_price': r1['mos_price'],
                    'market_cap': safe_get(info, 'marketCap', 0),
                    '_final': final_score,
                })

            except Exception as e:
                print(f"Recommend error {ticker}: {e}")
                continue

        # Sort by combined score (Rule #1 quality + affinity), then by upside
        recommendations.sort(key=lambda x: (-x['_final'], -x['score'], -x['upside']))
        top_recs = recommendations[:6]

        # Remove internal scoring field from output
        for r in top_recs:
            r.pop('_final', None)

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
