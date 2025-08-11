import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

print(f"📧 Tentative d'envoi d'un email depuis {EMAIL_USER}...")

def send_alert(subject, body):
    msg = EmailMessage()
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_USER
    msg['Subject'] = subject
    msg.set_content(body)

    try:
        print("📡 Connexion au serveur SMTP...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ Email envoyé avec succès!")
    except Exception as e:
        print(f"❌ Erreur d'envoi d'email: {e}")

send_alert("Test Email", "Ceci est un test de l'envoi d'email depuis Docker")
