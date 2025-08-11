FROM python:3.12
WORKDIR /app

# Installer les outils réseau
RUN apt-get update && apt-get install -y inetutils-ping netcat-openbsd inetutils-telnet && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "update_prices.py"]
