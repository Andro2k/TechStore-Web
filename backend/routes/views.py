# backend/routes/views.py
from flask import Blueprint, redirect, render_template, session, request, url_for
from backend.database import get_db_connection

# Creamos el Blueprint
views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    """VISTA CLIENTE: La Tienda Online"""
    sucursal = session.get('sucursal', 'Quito')
    id_suc = 1 if sucursal == 'Quito' else 2
    
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT P.Id_producto, P.nombre, P.marca, P.precio, ISNULL(I.cantidad, 0) as cantidad 
            FROM PRODUCTO P
            LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
        """, (id_suc,))
        productos = cursor.fetchall()
        conn.close()
        return render_template('index.html', productos=productos, sucursal=sucursal)
    except Exception as e:
        return render_template('index.html', productos=[], sucursal=sucursal, error=str(e))

@views_bp.route('/dashboard')
def dashboard():
    """VISTA ADMIN: Panel de Gestión"""
    if session.get('user_role') != 'admin':
        return redirect(url_for('auth.login'))
    
    sucursal = session.get('sucursal', 'Quito')
    tabla = request.args.get('tabla', 'PRODUCTO')
    error_msg = request.args.get('error')
    id_suc = 2 if sucursal == 'Guayaquil' else 1

    datos, columnas = [], []
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        if tabla == 'PRODUCTO':
            cursor.execute("""
                SELECT P.Id_producto, P.nombre, P.marca, P.precio, ISNULL(I.cantidad, 0) as Stock
                FROM PRODUCTO P
                LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
            """, (id_suc,))
        # --- Lógica de Vistas Distribuidas ---
        elif tabla == 'INVENTARIO':
            cursor.execute("SELECT * FROM DETALLE_FACTURA")
        elif tabla == 'FACTURA':
            cursor.execute("SELECT * FROM FACTURA")
        # -------------------------------------
        else:
            cursor.execute(f"SELECT * FROM {tabla}")
            
        columnas = [col[0] for col in cursor.description]
        datos = cursor.fetchall()
        conn.close()
    except Exception as e:
        error_msg = str(e)

    return render_template('dashboard.html', datos=datos, columnas=columnas, 
                           sucursal=sucursal, tabla_activa=tabla, error=error_msg)