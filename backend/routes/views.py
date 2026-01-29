# backend/routes/views.py
from flask import Blueprint, redirect, render_template, session, request, url_for
from backend.database import get_db_connection

# --- CONFIGURACIÓN ---
views_bp = Blueprint('views', __name__)

# Constantes de Identificación
ID_QUITO = 1
ID_GUAYAQUIL = 2

# ==============================================================================
# 1. VISTA PÚBLICA (Catálogo)
# ==============================================================================

@views_bp.route('/')
def index():
    """Página principal: Muestra productos con stock según la sucursal seleccionada."""
    sucursal = session.get('sucursal', 'Quito')
    id_suc_actual = ID_QUITO if sucursal == 'Quito' else ID_GUAYAQUIL
    
    productos = []
    error_msg = request.args.get('error') # Captura errores que vienen de acciones

    conn = None
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        # Left Join: Trae el producto aunque no tenga inventario (saldrá NULL -> 0)
        cursor.execute("""
            SELECT P.Id_producto, P.nombre, P.marca, P.precio, ISNULL(I.cantidad, 0) as cantidad 
            FROM PRODUCTO P
            LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
        """, (id_suc_actual,))
        
        productos = cursor.fetchall()
    except Exception as e:
        error_msg = f"Error de conexión: {str(e)}"
    finally:
        if conn: conn.close()

    return render_template('index.html', productos=productos, sucursal=sucursal, error=error_msg)


# ==============================================================================
# 2. VISTA ADMINISTRADOR (Dashboard)
# ==============================================================================

@views_bp.route('/dashboard')
def dashboard():
    """Panel de Control: Gestión de tablas según permisos."""
    
    # 1. Seguridad: Solo Admin
    if session.get('user_role') != 'admin':
        return redirect(url_for('auth.login'))
    
    # 2. Configuración
    sucursal = session.get('sucursal', 'Quito')
    tabla = request.args.get('tabla', 'PRODUCTO')
    error_msg = request.args.get('error')
    
    # Identificamos el ID numérico
    id_suc_actual = ID_GUAYAQUIL if sucursal == 'Guayaquil' else ID_QUITO

    datos = []
    columnas = []

    conn = None
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        # --- LÓGICA POR TABLA ---
        
        if tabla == 'PRODUCTO':
            # Muestra catálogo + Stock local + Nombre de la bodega actual
            cursor.execute("""
                SELECT 
                    P.Id_producto, P.nombre, P.marca, P.precio, 
                    ISNULL(I.cantidad, 0) as Stock,
                    ? as Bodega
                FROM PRODUCTO P
                LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
            """, (sucursal, id_suc_actual))

        elif tabla == 'SUCURSAL':
            cursor.execute("SELECT Id_sucursal, nombre, direccion, ciudad FROM SUCURSAL")

        elif tabla == 'LOGISTICA':
            if sucursal == 'Guayaquil':
                # GUAYAQUIL (Emisor): Ve lo que envió
                cursor.execute("""
                    SELECT E.Id_envio, P.nombre, E.cantidad, E.fecha_envio, E.estado 
                    FROM TRANSFERENCIA_ENVIO E
                    JOIN PRODUCTO P ON E.Id_producto = P.Id_producto
                    ORDER BY E.Id_envio DESC
                """)
            else:
                # QUITO (Receptor): Ve lo que llega (Replicado) vs lo que ya procesó (Local)
                # Cruzamos Envío (Global) con Recepción (Local)
                cursor.execute("""
                    SELECT 
                        E.Id_envio, 
                        P.nombre, 
                        E.cantidad, 
                        E.fecha_envio,
                        CASE 
                            WHEN R.Id_recepcion IS NOT NULL THEN 'RECIBIDO' 
                            ELSE 'EN CAMINO' 
                        END as Estado_Local
                    FROM TRANSFERENCIA_ENVIO E
                    JOIN PRODUCTO P ON E.Id_producto = P.Id_producto
                    LEFT JOIN TRANSFERENCIA_RECEPCION R ON E.Id_envio = R.Id_envio_original
                    ORDER BY E.Id_envio DESC
                """)

        elif tabla == 'INVENTARIO':
            # Vista global (si existe en SQL)
            cursor.execute("SELECT * FROM V_INVENTARIO_GLOBAL")

        elif tabla == 'FACTURA':
            # Reporte de ventas (si existe en SQL)
            cursor.execute("SELECT * FROM V_REPORTE_VENTAS")

        else:
            # Fallback para tablas simples (EMPLEADO, CLIENTE, etc.)
            # PRECAUCIÓN: Validar inputs en producción para evitar SQL Injection
            cursor.execute(f"SELECT * FROM {tabla}")
            
        # Obtenemos nombres de columnas y datos
        if cursor.description:
            columnas = [col[0] for col in cursor.description]
            datos = cursor.fetchall()
            
    except Exception as e:
        error_msg = f"Error al cargar {tabla}: {str(e)}"
    finally:
        if conn: conn.close()

    return render_template('dashboard.html', 
                           datos=datos, 
                           columnas=columnas, 
                           sucursal=sucursal, 
                           tabla_activa=tabla, 
                           error=error_msg)


# ==============================================================================
# 3. VISTA CLIENTE (Perfil)
# ==============================================================================

@views_bp.route('/perfil')
def perfil():
    """Perfil de Usuario: Datos personales e historial de compras."""
    
    # 1. Seguridad: Solo Clientes
    if 'user_id' not in session or session.get('user_role') != 'cliente':
        return redirect(url_for('auth.login'))

    sucursal = session.get('sucursal', 'Quito')
    id_cliente = session['user_id']
    id_suc_actual = ID_QUITO if sucursal == 'Quito' else ID_GUAYAQUIL

    cliente_info = None
    historial_facturas = []

    conn = None
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        # A. Datos del Cliente
        cursor.execute("SELECT * FROM CLIENTE WHERE Id_cliente = ? AND Id_sucursal = ?", 
                       (id_cliente, id_suc_actual))
        cliente_info = cursor.fetchone()

        # B. Historial: Cabeceras de Factura
        cursor.execute("""
            SELECT Id_factura, fecha, total 
            FROM FACTURA 
            WHERE Id_cliente = ? AND Id_sucursal = ?
            ORDER BY fecha DESC
        """, (id_cliente, id_suc_actual))
        facturas_raw = cursor.fetchall()

        # C. Historial: Detalles (Productos por factura)
        # Nota: Esto hace N consultas. Para alto tráfico usar un solo JOIN y procesar en Python.
        for f in facturas_raw:
            id_fact = f[0]
            cursor.execute("""
                SELECT P.nombre, P.marca, D.cantidad, D.precio_unidad, D.subtotal
                FROM DETALLE_FACTURA D
                JOIN PRODUCTO P ON D.Id_producto = P.Id_producto
                WHERE D.Id_factura = ? AND D.Id_sucursal = ?
            """, (id_fact, id_suc_actual))
            
            historial_facturas.append({
                'id': id_fact,
                'fecha': f[1],
                'total': f[2],
                'productos': cursor.fetchall()
            })

    except Exception as e:
        print(f"Error en perfil: {e}")
    finally:
        if conn: conn.close()

    return render_template('profile.html', 
                           cliente=cliente_info, 
                           facturas=historial_facturas, 
                           sucursal=sucursal)