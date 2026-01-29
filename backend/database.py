# backend/database.py
import pyodbc
from .config import NODOS

def get_db_connection(sucursal_name):
    """Establece la conexión a SQL Server según el nodo seleccionado."""
    config = NODOS.get(sucursal_name, NODOS['Quito'])
    
    if config.get('use_sql_auth'):
        conn_str = (
            'DRIVER={ODBC Driver 17 for SQL Server};'
            f'SERVER={config["server"]},1433;'
            f'DATABASE={config["database"]};'
            f'UID={config["user"]};'
            f'PWD={config["password"]};'
        )
    else:
        conn_str = (
            'DRIVER={ODBC Driver 17 for SQL Server};'
            f'SERVER={config["server"]};'
            f'DATABASE={config["database"]};'
            'Trusted_Connection=yes;'
        )
    
    return pyodbc.connect(conn_str, timeout=30)