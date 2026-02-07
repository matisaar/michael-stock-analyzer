"""Get historical price performance for a stock - 1D, 1W, 1M, 3M, 6M, 1Y"""
from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime, timedelta
import yfinance as yf


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        # Extract symbol from path
        path = self.path.split('?')[0]
        symbol = path.rstrip('/').split('/')[-1].upper()

        if not symbol or len(symbol) > 10:
            self.wfile.write(json.dumps({'error': 'Invalid symbol'}).encode())
            return

        try:
            stock = yf.Ticker(symbol)
            # Get 13 months of history for accurate 1Y calculation
            hist = stock.history(period='13mo', interval='1d')

            if hist.empty or len(hist) < 2:
                self.wfile.write(json.dumps({'error': 'No price data available'}).encode())
                return

            current_price = float(hist['Close'].iloc[-1])
            today = hist.index[-1]

            def pct_change_since_date(target_date):
                """Calculate % change from the closest trading day to target date."""
                # Find the closest date at or before target
                mask = hist.index <= target_date
                if mask.any():
                    old_price = float(hist.loc[mask, 'Close'].iloc[-1])
                    if old_price > 0:
                        return round(((current_price - old_price) / old_price) * 100, 2)
                return None

            def pct_change_months_ago(months):
                """Calculate % change from N months ago (same day of month if possible)."""
                # Calculate target date: same day N months ago
                target_year = today.year
                target_month = today.month - months
                while target_month <= 0:
                    target_month += 12
                    target_year -= 1
                # Handle day overflow (e.g., Jan 31 -> Feb doesn't have 31)
                target_day = min(today.day, 28)  # Safe day that exists in all months
                try:
                    target_date = today.replace(year=target_year, month=target_month, day=target_day)
                except ValueError:
                    # Fallback to last day of target month
                    target_date = today - timedelta(days=months * 30)
                return pct_change_since_date(target_date)

            # 1D: compare to previous close
            prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else None
            change_1d = round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close else None

            # 1W: 7 calendar days ago
            change_1w = pct_change_since_date(today - timedelta(days=7))

            performance = {
                'symbol': symbol,
                'current_price': round(current_price, 2),
                'timeframes': {
                    '1D': change_1d,
                    '1W': change_1w,
                    '1M': pct_change_months_ago(1),
                    '3M': pct_change_months_ago(3),
                    '6M': pct_change_months_ago(6),
                    '1Y': pct_change_months_ago(12),
                },
                'week_52_high': round(float(hist['Close'].max()), 2),
                'week_52_low': round(float(hist['Close'].min()), 2),
                'off_high_pct': round(((current_price - float(hist['Close'].max())) / float(hist['Close'].max())) * 100, 1),
            }

            self.wfile.write(json.dumps(performance).encode())

        except Exception as e:
            self.wfile.write(json.dumps({'error': str(e)}).encode())
