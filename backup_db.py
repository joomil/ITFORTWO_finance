import os
import shutil
from datetime import datetime

BACKUP_DIR = "/opt/itfortwo/ydatabot/backups"
DB_FILE = "/opt/itfortwo/ydatabot/data.db"

if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

backup_file = os.path.join(BACKUP_DIR, f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db")
shutil.copy(DB_FILE, backup_file)
print(f"✅ Backup enregistré : {backup_file}")
