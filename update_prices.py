import yfinance as yf
import pandas as pd
import redis
import time
import os
import psycopg2
import smtplib
import json
import schedule
from datetime import datetime, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
POSTGRES_DB = os.getenv("POSTGRES_DB")

# Fichier de stockage des erreurs
ERROR_LOG_FILE = "/app/data/error_log.json"

# Connexion à Redis
redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

# Connexion PostgreSQL avec retries
def get_db_connection(max_retries=5):
    """Établit une connexion à la base de données PostgreSQL avec tentatives de reconnexion."""
    for attempt in range(max_retries):
        try:
            return psycopg2.connect(
                dbname=POSTGRES_DB,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host='db'
            )
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"⚠️ Tentative {attempt + 1}/{max_retries} de connexion PostgreSQL échouée, attente 5s")
                time.sleep(5)
            else:
                log_error("Connexion PostgreSQL", str(e))
                return None

# Vérifier/créer la table prices
def ensure_prices_table():
    """Vérifie ou crée la table prices si elle n'existe pas."""
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prices (
                    id SERIAL PRIMARY KEY,
                    ticker VARCHAR(20) NOT NULL,
                    price_date DATE NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    inserted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (ticker, price_date)
                )
            """)
            conn.commit()
            print("✅ Table 'prices' vérifiée/créée avec succès")
        except Exception as e:
            log_error("Création table prices", str(e))
        finally:
            conn.close()

# Charger l'historique des erreurs
def load_error_log():
    """Charge l'historique des erreurs depuis un fichier JSON."""
    try:
        with open(ERROR_LOG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Sauvegarder l'historique des erreurs
def save_error_log(error_log):
    """Sauvegarde l'historique des erreurs dans un fichier JSON."""
    with open(ERROR_LOG_FILE, "w") as f:
        json.dump(error_log, f)

# Fonction pour limiter les emails
def send_alert(subject, body, min_errors=10):
    """Envoie une alerte par email si le seuil d'erreurs est atteint."""
    now = time.time()
    error_log = load_error_log()

    error_count = error_log.get(subject, {}).get("count", 0) + 1
    last_sent = error_log.get(subject, {}).get("last_sent", 0)

    if error_count < min_errors or (now - last_sent < 3600):
        print(f"⚠️ {subject} : {error_count} erreurs (email non envoyé)")
        error_log[subject] = {"count": error_count, "last_sent": last_sent}
        save_error_log(error_log)
        return

    msg = EmailMessage()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER
    msg['Subject'] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print(f"📧 Email d'alerte envoyé : {subject} ({error_count} erreurs)")
        error_log[subject] = {"count": 0, "last_sent": now}
        save_error_log(error_log)
    except Exception as e:
        print(f"❌ Échec de l'envoi de l'alerte : {e}")

def log_error(context, error):
    """Enregistre et signale une erreur."""
    print(f"❌ [{context}] {error}")
    send_alert("Erreur robot ydatabot", f"{context} : {error}")

# Fonction de mise à jour des prix
def fetch_price(ticker):
    """Récupère le prix de clôture du ticker donné et le stocke dans la base de données."""
    try:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        stock = yf.Ticker(ticker)
        history = stock.history(start=yesterday, end=yesterday)
        if not history.empty:
            price = history['Close'].iloc[0]
            price_date = yesterday
            conn = get_db_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO prices (ticker, price_date, price) VALUES (%s, %s, %s) ON CONFLICT (ticker, price_date) DO NOTHING", (ticker, price_date, float(price)))
                conn.commit()
                conn.close()
            print(f"🔹 Mise à jour {ticker} : {price} le {price_date}")
        else:
            print(f"ℹ️ {ticker} : Données de prix non disponibles, ignoré")
    except Exception as e:
        error_str = str(e)
        if "No data found" in error_str or "404" in error_str or "possibly delisted" in error_str:
            print(f"ℹ️ {ticker} : Données de prix non disponibles, ignoré")
            with open("/app/data/invalid_tickers.txt", "a") as f:
                f.write(f"{ticker}\n")
        elif "Too many requests" in error_str:
            print(f"⚠️ {ticker} : Limite de taux atteinte, pause de 60s")
            time.sleep(60)
        else:
            log_error(f"Récupération prix {ticker}", error_str)

# Lire la liste des tickers depuis le fichier CSV
def load_tickers():
    """Charge la liste des tickers depuis le fichier CSV avec validation."""
    try:
        df = pd.read_csv("/app/data/tickers.csv")
        if "Symbol" not in df.columns or "marketcap" not in df.columns:
            raise ValueError("Colonnes 'Symbol' ou 'marketcap' manquantes dans tickers.csv")
        df["marketcap"] = pd.to_numeric(df["marketcap"], errors="coerce")
        df = df.dropna(subset=["marketcap"]).sort_values(by="marketcap", ascending=False)
        top_daily = df.iloc[:1000]["Symbol"].tolist()
        weekly = df.iloc[1000:5000]["Symbol"].tolist()
        monthly = df.iloc[5000:]["Symbol"].tolist()
        return top_daily, weekly, monthly
    except Exception as e:
        log_error("Chargement des tickers", str(e))
        return [], [], []

# Fonction principale pour exécuter le bot
def run_bot():
    """Exécute le bot selon le planning quotidien, hebdomadaire et mensuel."""
    ensure_prices_table()
    top_daily, weekly, monthly = load_tickers()

    today = datetime.now().strftime("%A")
    day_of_month = datetime.now().strftime("%d")

    for ticker in top_daily:
        fetch_price(ticker)
        time.sleep(0.5)  # Délai pour éviter les limites de taux

    if today == "Sunday":
        for ticker in weekly:
            fetch_price(ticker)
            time.sleep(0.5)

    if day_of_month == "01":
        for ticker in monthly:
            fetch_price(ticker)
            time.sleep(0.5)

    print(f"💤 Prochaine mise à jour dans 24h...")

if __name__ == "__main__":
    run_bot()

