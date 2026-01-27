# backend/config.py
import os

SECRET_KEY = 'techstore_secret_key_2026'

# Leemos las IPs desde las variables de entorno (que enviaremos desde el launcher)
SERVER_QUITO = os.environ.get('DB_SERVER_QUITO', '192.168.100.34')
SERVER_GUAYAQUIL = os.environ.get('DB_SERVER_GUAYAQUIL', '192.168.100.13')

NODOS = {
    'Quito': {
        'server': SERVER_QUITO, 
        'database': 'TechStore_Quito',
        'use_sql_auth': True,      # Recomiendo True si usas usuario 'sa' localmente también
        'user': 'sa',             
        'password': 'P@ssw0rd' # <--- Ajusta esto si tu SQL local tiene clave
    },
    'Guayaquil': {
        'server': SERVER_GUAYAQUIL, 
        'database': 'TechStore_Guayaquil',
        'use_sql_auth': True,
        'user': 'sa',
        'password': 'P@ssw0rd'
    }
}