from update_prices import get_db_connection, log_error
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import time

def backfill_ticker_batch(tickers, start_date, end_date, batch_size=100):
    """Récupère et stocke les données historiques pour un lot de tickers."""
    try:
        data = yf.download(tickers, start=start_date, end=end_date, group_by='ticker')
        conn = get_db_connection()
        if not conn:
            return
        cursor = conn.cursor()
        inserts = []
        for t in tickers:
            for date, price in data.get((t, 'Close'), {}).items():
                price_date = date.date()
                inserts.append((t, price_date, float(price)))
        cursor.executemany("INSERT INTO prices (ticker, price_date, price) VALUES (%s, %s, %s) ON CONFLICT (ticker, price_date) DO NOTHING", inserts)
        conn.commit()
        conn.close()
        print(f"Backfill complété pour {len(tickers)} tickers")
    except Exception as e:
        log_error("Backfill batch", str(e))

def backfill_all_tickers(start_date, end_date):
    """Récupère tous les tickers depuis le fichier CSV et effectue le backfill par lots."""
    try:
        df = pd.read_csv("/app/data/tickers.csv")
        all_tickers = df["Symbol"].tolist()
        for i in range(0, len(all_tickers), 100):
            batch = all_tickers[i:i+100]
            backfill_ticker_batch(batch, start_date, end_date)
            time.sleep(5)  # Délai pour respecter les limites de taux
    except Exception as e:
        log_error("Backfill tous les tickers", str(e))

if __name__ == "__main__":
    start_date = '2020-01-01'
    end_date = (datetime.now().date() - timedelta(days=1)).isoformat()
    backfill_all_tickers(start_date, end_date)
