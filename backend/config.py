# backend/config.py
import os

SECRET_KEY = 'techstore_secret_key_2026'

SERVER_QUITO = os.environ.get('DB_SERVER_QUITO', '26.248.18.42')
SERVER_GUAYAQUIL = os.environ.get('DB_SERVER_GUAYAQUIL', '26.77.173.132')

NODOS = {
    'Quito': {
        'server': SERVER_QUITO, 
        'database': 'TechStore_Quito',
        'use_sql_auth': True,
        'user': 'sa',             
        'password': 'P@ssw0rd'
    },
    'Guayaquil': {
        'server': SERVER_GUAYAQUIL, 
        'database': 'TechStore_Guayaquil',
        'use_sql_auth': True,
        'user': 'sa',
        'password': 'P@ssw0rd'
    }
}