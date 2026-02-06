"""Recommendation engine - finds stocks similar to user's watchlist profile"""
from http.server import BaseHTTPRequestHandler
import json
import os
import random
import urllib.request
import urllib.parse
from datetime import datetime
import yfinance as yf

SUPABASE_URL = 'https://uhmoslyaavuswzlqeyml.supabase.co'
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')

# Same stock pools as discover.py
STOCK_POOLS = {
    'Technology': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'ORCL', 'CRM', 'ADBE', 'AMD', 'INTC', 'CSCO', 'QCOM', 'TXN', 'IBM', 'NOW', 'UBER', 'SHOP', 'PLTR', 'SNOW', 'CRWD', 'DDOG', 'NET', 'ZS', 'MDB', 'HUBS'],
    'Financial Services': ['JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'SCHW', 'BLK', 'AXP', 'C', 'USB', 'PNC', 'COF', 'PYPL', 'SQ', 'COIN', 'HOOD', 'SOFI', 'ALLY'],
    'Healthcare': ['UNH', 'JNJ', 'LLY', 'PFE', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'BMY', 'AMGN', 'GILD', 'MRNA', 'REGN', 'ISRG', 'DXCM', 'VEEV', 'ZBH', 'HCA', 'CVS'],
    'Consumer': ['WMT', 'COST', 'HD', 'MCD', 'SBUX', 'NKE', 'TGT', 'LOW', 'TJX', 'LULU', 'CMG', 'DPZ', 'YUM', 'ROST', 'DG', 'DLTR', 'KR', 'EL', 'DECK', 'CROX'],
    'Energy': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PSX', 'VLO', 'OXY', 'LIN', 'APD', 'ECL', 'NEM', 'FCX', 'FSLR', 'ENPH', 'NEE', 'DUK', 'SO', 'D', 'AEP'],
    'Industrials': ['CAT', 'DE', 'HON', 'GE', 'RTX', 'LMT', 'BA', 'UPS', 'FDX', 'UNP', 'WM', 'ETN', 'ITW', 'EMR', 'GD', 'NOC', 'MMM', 'JCI', 'ROK', 'FAST'],
    'Communication': ['DIS', 'NFLX', 'CMCSA', 'T', 'VZ', 'TMUS', 'SPOT', 'ROKU', 'WBD', 'PARA', 'LYV', 'RBLX', 'EA', 'TTWO', 'MTCH', 'SNAP', 'PINS', 'ZM', 'DKNG', 'CHTR'],
}

ALL_CANDIDATES = []
for sector, tickers in STOCK_POOLS.items():
    for t in tickers:
        ALL_CANDIDATES.append((t, sector))


def get_watchlist():
    """Fetch user's watchlist from Supabase."""
    url = SUPABASE_URL + '/rest/v1/watchlist?select=*'
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': 'Bearer ' + SUPABASE_KEY,
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Watchlist fetch error: {e}")
        return []


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


def calculate_fair_value(info, price):
    eps = safe_get(info, 'trailingEps', 0)
    forward_pe = safe_get(info, 'forwardPE', 0)
    target_price = safe_get(info, 'targetMeanPrice', 0)
    pe = safe_get(info, 'trailingPE', 0)
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
    if pe and pe > 0 and pe < 25 and price > 0:
        fair_values.append(price * 1.1)
    elif pe and pe > 25 and price > 0:
        fair_values.append(price * 0.95)
    if eps and eps > 0 and not fair_values:
        sector = safe_get(info, 'sector', '')
        mult = 25 if 'Technology' in str(sector) else (20 if 'Consumer' in str(sector) else 18)
        fair_values.append(eps * mult)
    return sum(fair_values) / len(fair_values) if fair_values else price


def calculate_score(info, price, fair_value):
    score = 0
    roa = to_pct(safe_get(info, 'returnOnAssets', 0))
    roe = to_pct(safe_get(info, 'returnOnEquity', 0))
    cash = safe_get(info, 'totalCash', 0)
    debt = safe_get(info, 'totalDebt', 0)
    fcf = safe_get(info, 'freeCashflow', 0)
    pm = to_pct(safe_get(info, 'profitMargins', 0))
    ps = safe_get(info, 'priceToSalesTrailing12Months', 0)
    if roa > 10: score += 15
    elif roa > 5: score += 7
    if roe > 10: score += 15
    elif roe > 5: score += 7
    if cash > 0 and cash >= debt: score += 15
    if price > 0 and fair_value > 0:
        upside = ((fair_value - price) / price) * 100
        if upside > 30: score += 20
        elif upside > 10: score += 10
        elif upside > 0: score += 5
    if pm > 15: score += 10
    elif pm > 5: score += 5
    if ps > 0 and ps < 2: score += 10
    if fcf and fcf > 0: score += 15
    return min(score, 100)


def build_profile(watchlist):
    """Extract investment profile from watchlist."""
    if not watchlist:
        return None

    sectors = {}
    industries = {}
    scores = []

    for item in watchlist:
        s = item.get('sector', '')
        if s:
            sectors[s] = sectors.get(s, 0) + 1
        ind = item.get('industry', '')
        if ind:
            industries[ind] = industries.get(ind, 0) + 1
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


def pick_candidates(profile, max_candidates=15):
    """Pick candidate stocks to evaluate based on the profile."""
    saved = profile['saved_symbols']
    top_sectors = profile['top_sectors']

    # Stocks from user's preferred sectors (not already saved)
    sector_matches = []
    diversification = []

    for ticker, sector in ALL_CANDIDATES:
        if ticker in saved:
            continue
        # Check if this sector matches any of user's top sectors
        matched = False
        for ts in top_sectors:
            if ts.lower() in sector.lower() or sector.lower() in ts.lower():
                matched = True
                break
        if matched:
            sector_matches.append((ticker, sector, 'sector_match'))
        else:
            diversification.append((ticker, sector, 'diversify'))

    # Pick: 10 from matching sectors, 5 from diversification
    random.shuffle(sector_matches)
    random.shuffle(diversification)

    candidates = sector_matches[:10] + diversification[:5]

    # If not enough sector matches, fill with diversification
    if len(candidates) < max_candidates:
        remaining = [c for c in diversification if c not in candidates]
        candidates.extend(remaining[:max_candidates - len(candidates)])

    return candidates[:max_candidates]


def generate_reason(profile, candidate_sector, score, upside, match_type):
    """Generate a human-readable recommendation reason."""
    reasons = []

    if match_type == 'sector_match':
        count = profile['sectors'].get(candidate_sector, 0)
        if count > 0:
            reasons.append(f"You like {candidate_sector} stocks")
        else:
            # Fuzzy match
            for s in profile['top_sectors']:
                if s.lower() in candidate_sector.lower() or candidate_sector.lower() in s.lower():
                    reasons.append(f"Similar to your {s} picks")
                    break
    else:
        reasons.append("Diversifies your portfolio")

    if score >= 70:
        reasons.append("strong fundamentals")
    elif score >= 50:
        reasons.append("solid quality score")

    if upside > 20:
        reasons.append(f"{upside:.0f}% upside potential")

    return ' • '.join(reasons) if reasons else "Matches your investment style"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # 1. Fetch watchlist
        watchlist = get_watchlist()

        if not watchlist:
            self.wfile.write(json.dumps({
                'recommendations': [],
                'message': 'Save some stocks first! We\u2019ll analyze your preferences and find similar opportunities.',
                'profile': None,
            }).encode())
            return

        # 2. Build profile
        profile = build_profile(watchlist)

        # 3. Pick candidates
        candidates = pick_candidates(profile)

        # 4. Analyze candidates and score them
        recommendations = []
        for ticker, sector, match_type in candidates:
            try:
                stock = yf.Ticker(ticker)
                info = stock.info
                if not info:
                    continue

                price = safe_get(info, 'currentPrice') or safe_get(info, 'regularMarketPrice', 0)
                if not price:
                    continue

                fair_value = calculate_fair_value(info, price)
                score = calculate_score(info, price, fair_value)
                upside = ((fair_value - price) / price * 100) if price > 0 else 0

                # Calculate recommendation relevance score
                relevance = 0

                # Sector match bonus
                if match_type == 'sector_match':
                    relevance += 30
                else:
                    relevance += 15  # diversification bonus

                # Score similarity to user's average
                score_diff = abs(score - profile['avg_score'])
                if score_diff < 15:
                    relevance += 25
                elif score_diff < 30:
                    relevance += 10

                # Quality bonus
                if score >= 60:
                    relevance += 20
                elif score >= 40:
                    relevance += 10

                # Upside bonus
                if upside > 20:
                    relevance += 15
                elif upside > 0:
                    relevance += 5

                reason = generate_reason(profile, sector, score, upside, match_type)

                recommendations.append({
                    'symbol': ticker,
                    'name': safe_get(info, 'longName') or safe_get(info, 'shortName', ticker),
                    'sector': safe_get(info, 'sector', sector),
                    'price': round(price, 2),
                    'score': score,
                    'upside': round(upside, 1),
                    'relevance': relevance,
                    'reason': reason,
                    'match_type': match_type,
                    'market_cap': safe_get(info, 'marketCap', 0),
                })

            except Exception as e:
                print(f"Recommend error {ticker}: {e}")
                continue

        # 5. Sort by relevance, return top 6
        recommendations.sort(key=lambda x: (-x['relevance'], -x['score']))
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
