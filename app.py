from flask import Flask, render_template, request, redirect, session, url_for
import pyodbc

app = Flask(__name__)
app.secret_key = 'techstore_secret_key_2026'

# ==========================================
# CONFIGURACIÓN DE CONEXIÓN Y NODOS
# ==========================================
NODOS = {
    'Quito': {
        'server': 'localhost', 
        'database': 'TechStore_Quito',
        'use_sql_auth': False 
    },
    'Guayaquil': {
        'server': '26.77.173.132', 
        'database': 'TechStore_Guayaquil',
        'use_sql_auth': True,
        'user': 'sa',
        'password': 'P@ssw0rd'
    }
}

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

# ==========================================
# RUTAS PRINCIPALES (VISTAS)
# ==========================================

@app.route('/')
def index():
    """VISTA CLIENTE: La Tienda Online"""
    sucursal = session.get('sucursal', 'Quito')
    id_suc = 1 if sucursal == 'Quito' else 2
    
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        # Mostrar productos (incluso si stock es 0 para que se vea como 'Agotado')
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

@app.route('/dashboard')
def dashboard():
    """VISTA ADMIN: Panel de Gestión de Tablas"""
    sucursal = session.get('sucursal', 'Quito')
    tabla = request.args.get('tabla', 'PRODUCTO')
    error_msg = request.args.get('error')
    id_suc = 2 if sucursal == 'Guayaquil' else 1

    datos, columnas = [], []
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        if tabla == 'PRODUCTO':
            # Vista Admin incluye Stock
            cursor.execute("""
                SELECT P.Id_producto, P.nombre, P.marca, P.precio, ISNULL(I.cantidad, 0) as Stock
                FROM PRODUCTO P
                LEFT JOIN INVENTARIO I ON P.Id_producto = I.Id_producto AND I.Id_sucursal = ?
            """, (id_suc,))
        else:
            # Consultas genéricas para otras tablas
            cursor.execute(f"SELECT * FROM {tabla}")
            
        columnas = [col[0] for col in cursor.description]
        datos = cursor.fetchall()
        conn.close()
    except Exception as e:
        error_msg = str(e)

    return render_template('dashboard.html', datos=datos, columnas=columnas, 
                           sucursal=sucursal, tabla_activa=tabla, error=error_msg)

# ==========================================
# RUTAS DE LÓGICA DE NEGOCIO (ACCIONES)
# ==========================================

@app.route('/cambiar_sucursal', methods=['POST'])
def cambiar_sucursal():
    session['sucursal'] = request.form['nueva_sucursal']
    # Redirección inteligente: Vuelve a la página desde donde se llamó (Dashboard o Tienda)
    return redirect(request.referrer or url_for('index'))

@app.route('/checkout', methods=['POST'])
def checkout():
    """Procesa la compra y registra al cliente si es nuevo."""
    sucursal = session.get('sucursal', 'Quito')
    id_suc = 1 if sucursal == 'Quito' else 2
    
    id_cliente = request.form['id_cliente']
    id_prod = request.form['id_producto']
    
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        # 1. Registrar Cliente (si no existe en este nodo)
        cursor.execute("SELECT 1 FROM CLIENTE WHERE Id_cliente = ? AND Id_sucursal = ?", (id_cliente, id_suc))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO CLIENTE (Id_cliente, nombre, direccion, telefono, correo, Id_sucursal)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id_cliente, request.form['nombre'], request.form['direccion'], 
                  request.form['telefono'], request.form['correo'], id_suc))

        # 2. Generar Factura
        id_factura = int(cursor.execute("SELECT ISNULL(MAX(Id_factura), 0) + 1 FROM FACTURA").fetchone()[0])
        precio = float(request.form['precio'])
        
        cursor.execute("""
            INSERT INTO FACTURA (Id_factura, Id_cliente, Id_sucursal, total, fecha)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (id_factura, id_cliente, id_suc, precio))

        # 3. Detalle y Descuento de Stock
        # Asegúrate de que tu columna se llame 'precio' o 'precio_unitario' en la BD
        cursor.execute("""
            INSERT INTO DETALLE_FACTURA (Id_factura, Id_producto, Id_sucursal, cantidad, precio)
            VALUES (?, ?, ?, 1, ?)
        """, (id_factura, id_prod, id_suc, precio))
        
        cursor.execute("""
            UPDATE INVENTARIO SET cantidad = cantidad - 1 
            WHERE Id_producto = ? AND Id_sucursal = ?
        """, (id_prod, id_suc))

        conn.commit()
        conn.close()
        # Volver a la tienda con mensaje de éxito (podrías implementarlo en el HTML)
        return redirect(url_for('index'))
        
    except Exception as e:
        return redirect(url_for('index', error=f"Error en compra: {str(e)}"))

# ==========================================
# RUTAS ADMINISTRATIVAS (GESTIÓN)
# ==========================================

@app.route('/add_product', methods=['POST'])
def add_product():
    sucursal = session.get('sucursal', 'Quito')
    
    if sucursal != 'Guayaquil':
        return redirect(url_for('dashboard', tabla='PRODUCTO', error="Acceso denegado: Solo Guayaquil registra productos."))

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        cursor.execute("INSERT INTO PRODUCTO (Id_producto, nombre, marca, precio) VALUES (?, ?, ?, ?)",
                       (request.form['id_producto'], request.form['nombre'], request.form['marca'], request.form['precio']))
        
        cursor.execute("INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (2, ?, ?)",
                       (request.form['id_producto'], request.form['stock']))
        
        conn.commit()
        conn.close()
        # CORRECCIÓN: Volver al Dashboard, no a la Tienda
        return redirect(url_for('dashboard', tabla='PRODUCTO'))
    
    except pyodbc.IntegrityError:
        return redirect(url_for('dashboard', tabla='PRODUCTO', error=f"El ID {request.form['id_producto']} ya existe."))
    except Exception as e:
        return redirect(url_for('dashboard', tabla='PRODUCTO', error=str(e)))

@app.route('/edit_product', methods=['POST'])
def edit_product():
    sucursal = session.get('sucursal', 'Quito')
    
    if sucursal != 'Guayaquil':
        return redirect(url_for('dashboard', tabla='PRODUCTO', error="Solo Guayaquil modifica productos."))

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE PRODUCTO SET nombre = ?, marca = ?, precio = ? 
            WHERE Id_producto = ?
        """, (request.form['nombre'], request.form['marca'], request.form['precio'], request.form['id_producto']))

        cursor.execute("""
            IF EXISTS (SELECT 1 FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = 2)
                UPDATE INVENTARIO SET cantidad = ? WHERE Id_producto = ? AND Id_sucursal = 2
            ELSE
                INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (2, ?, ?)
        """, (request.form['id_producto'], request.form['stock'], request.form['id_producto'], request.form['id_producto'], request.form['stock']))

        conn.commit()
        conn.close()
        return redirect(url_for('dashboard', tabla='PRODUCTO'))
    except Exception as e:
        return redirect(url_for('dashboard', tabla='PRODUCTO', error=f"Error al editar: {str(e)}"))

@app.route('/add_employee', methods=['POST'])
def add_employee():
    sucursal = session.get('sucursal', 'Quito')
    
    if sucursal != 'Guayaquil':
        return redirect(url_for('dashboard', tabla='EMPLEADO', error="Acceso denegado."))

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO EMPLEADO (Id_empleado, nombre, direccion, telefono, correo, Id_sucursal)
            VALUES (?, ?, ?, ?, ?, 2)
        """, (
            request.form['id_empleado'], request.form['nombre'], request.form['direccion'],
            request.form['telefono'], request.form['correo']
        ))
        
        conn.commit()
        conn.close()
        # CORRECCIÓN: Volver al Dashboard de Empleados
        return redirect(url_for('dashboard', tabla='EMPLEADO'))
    
    except pyodbc.IntegrityError:
        return redirect(url_for('dashboard', tabla='EMPLEADO', error="El ID de empleado ya existe."))
    except Exception as e:
        return redirect(url_for('dashboard', tabla='EMPLEADO', error=str(e)))

if __name__ == '__main__':
    app.run(debug=True, port=5000)