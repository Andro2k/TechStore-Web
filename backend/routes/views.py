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
                SELECT 
                    P.Id_producto, 
                    P.nombre, 
                    P.marca, 
                    P.precio, 
                    ISNULL(I.cantidad, 0) as Stock,
                    ? as Bodega   -- <--- ESTO AGREGA LA COLUMNA AL HTML AUTOMÁTICAMENTE
                FROM PRODUCTO P
                LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
            """, (sucursal, id_suc))
            
        # --- AGREGAR ESTO ---
        elif tabla == 'SUCURSAL':
            cursor.execute("SELECT Id_sucursal, nombre, direccion, ciudad FROM SUCURSAL")
        # --------------------
        elif tabla == 'LOGISTICA':
            if sucursal == 'Guayaquil':
                # Guayaquil ve lo que ha enviado
                cursor.execute("""
                    SELECT E.Id_envio, P.nombre, E.cantidad, E.fecha_envio, E.estado 
                    FROM TRANSFERENCIA_ENVIO E
                    JOIN PRODUCTO P ON E.Id_producto = P.Id_producto
                    ORDER BY E.Id_envio DESC
                """)
            else:
                # Quito ve lo que le llega (Replicado) y si ya lo recibió (Local)
                # Nota: Hacemos un LEFT JOIN para ver si ya está en la tabla de recepciones local
                cursor.execute("""
                    SELECT 
                        E.Id_envio, 
                        P.nombre, 
                        E.cantidad, 
                        E.fecha_envio,
                        CASE WHEN R.Id_recepcion IS NOT NULL THEN 'RECIBIDO' ELSE 'EN CAMINO' END as Estado_Local
                    FROM TRANSFERENCIA_ENVIO E
                    JOIN PRODUCTO P ON E.Id_producto = P.Id_producto
                    LEFT JOIN TRANSFERENCIA_RECEPCION R ON E.Id_envio = R.Id_envio_original
                    ORDER BY E.Id_envio DESC
                """)
        elif tabla == 'INVENTARIO':
            cursor.execute("SELECT * FROM V_INVENTARIO_GLOBAL")
        elif tabla == 'FACTURA':
            cursor.execute("SELECT * FROM V_REPORTE_VENTAS")
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

@views_bp.route('/perfil')
def perfil():
    """VISTA CLIENTE: Mi Perfil e Historial"""
    # 1. Seguridad: Solo clientes logueados
    if 'user_id' not in session or session.get('user_role') != 'cliente':
        return redirect(url_for('auth.login'))

    sucursal = session.get('sucursal', 'Quito')
    id_cliente = session['user_id']
    id_suc = 1 if sucursal == 'Quito' else 2

    cliente = None
    facturas = []

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        # A. Obtener datos personales
        cursor.execute("SELECT * FROM CLIENTE WHERE Id_cliente = ? AND Id_sucursal = ?", (id_cliente, id_suc))
        cliente = cursor.fetchone()

        # B. Obtener historial de facturas
        # Traemos la cabecera de la factura
        cursor.execute("""
            SELECT Id_factura, fecha, total 
            FROM FACTURA 
            WHERE Id_cliente = ? AND Id_sucursal = ?
            ORDER BY fecha DESC
        """, (id_cliente, id_suc))
        facturas_raw = cursor.fetchall()

        # C. Para cada factura, buscamos sus productos (Detalle)
        # Esto crea una estructura de datos anidada: [ {DatosFactura, Productos: []}, ... ]
        for f in facturas_raw:
            id_fact = f[0]
            cursor.execute("""
                SELECT P.nombre, P.marca, D.cantidad, D.precio_unidad, D.subtotal
                FROM DETALLE_FACTURA D
                JOIN PRODUCTO P ON D.Id_producto = P.Id_producto
                WHERE D.Id_factura = ? AND D.Id_sucursal = ?
            """, (id_fact, id_suc))
            detalles = cursor.fetchall()
            
            facturas.append({
                'id': id_fact,
                'fecha': f[1],
                'total': f[2],
                'productos': detalles
            })

        conn.close()
    except Exception as e:
        print(f"Error en perfil: {e}")

    return render_template('profile.html', cliente=cliente, facturas=facturas, sucursal=sucursal)