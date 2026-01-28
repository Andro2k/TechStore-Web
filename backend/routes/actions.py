# backend/routes/actions.py
from flask import Blueprint, request, redirect, session, url_for
from backend.database import get_db_connection

actions_bp = Blueprint('actions', __name__)

@actions_bp.route('/cambiar_sucursal', methods=['POST'])
def cambiar_sucursal():
    session['sucursal'] = request.form['nueva_sucursal']
    # Nota: usamos 'views.index' porque ahora index está dentro del blueprint 'views'
    return redirect(request.referrer or url_for('views.index'))

@actions_bp.route('/checkout', methods=['POST'])
def checkout():
    sucursal = session.get('sucursal', 'Quito')
    id_suc = 1 if sucursal == 'Quito' else 2
    
    # Datos del formulario
    id_prod = request.form['id_producto']
    cantidad_compra = int(request.form['cantidad'])
    precio_unitario = float(request.form['precio_unitario'])
    total_factura = precio_unitario * cantidad_compra

    conn = None
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        # 1. VALIDAR STOCK DISPONIBLE (Seguridad Backend)
        cursor.execute("SELECT cantidad FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = ?", (id_prod, id_suc))
        row = cursor.fetchone()
        if not row or row[0] < cantidad_compra:
            conn.close()
            return redirect(url_for('views.index', error=f"Error: Stock insuficiente. Disponibles: {row[0] if row else 0}"))

        # 2. IDENTIFICAR AL CLIENTE
        id_cliente = None
        
        if 'user_id' in session and session.get('user_role') == 'cliente':
            # CASO A: Usuario ya logueado
            id_cliente = session['user_id']
        else:
            # CASO B: Usuario Invitado (Registrar o Actualizar)
            id_cliente = request.form['id_cliente']
            nombre = request.form['nombre']
            correo = request.form['correo']

            # Verificamos si existe
            cursor.execute("SELECT 1 FROM CLIENTE WHERE Id_cliente = ? AND Id_sucursal = ?", (id_cliente, id_suc))
            if not cursor.fetchone():
                # Insertar nuevo
                cursor.execute("""
                    INSERT INTO CLIENTE (Id_cliente, nombre, direccion, telefono, correo, Id_sucursal)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (id_cliente, nombre, request.form['direccion'], request.form['telefono'], correo, id_suc))
            
            # Auto-Login para el invitado
            session['user_id'] = id_cliente
            session['user_name'] = nombre
            session['user_role'] = 'cliente'
            session['user_email'] = correo

        # 3. CREAR FACTURA
        # Generar ID Factura (Max + 1)
        id_factura = int(cursor.execute("SELECT ISNULL(MAX(Id_factura), 0) + 1 FROM FACTURA").fetchone()[0])
        
        cursor.execute("""
            INSERT INTO FACTURA (Id_factura, Id_cliente, Id_sucursal, total, fecha)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (id_factura, id_cliente, id_suc, total_factura))

        # 4. INSERTAR DETALLE (Con la cantidad seleccionada)
        cursor.execute("""
            INSERT INTO DETALLE_FACTURA (Id_factura, Id_producto, Id_sucursal, cantidad, precio_unidad, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_factura, id_prod, id_suc, cantidad_compra, precio_unitario, total_factura))
        
        # 5. ACTUALIZAR INVENTARIO (Restar cantidad)
        cursor.execute("""
            UPDATE INVENTARIO SET cantidad = cantidad - ? 
            WHERE Id_producto = ? AND Id_sucursal = ?
        """, (cantidad_compra, id_prod, id_suc))

        conn.commit()
        conn.close()
        
        return redirect(url_for('views.index'))
        
    except Exception as e:
        if conn: conn.close()
        # Imprime el error en consola para depuración y lo muestra en la web
        print(f"Error Checkout: {e}")
        return redirect(url_for('views.index', error=f"Error en compra: {str(e)}"))

@actions_bp.route('/add_product', methods=['POST'])
def add_product():
    sucursal_actual = session.get('sucursal', 'Quito')
    
    if sucursal_actual != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Acceso denegado. Solo Nodo Gestión."))

    try:
        conn = get_db_connection(sucursal_actual)
        cursor = conn.cursor()
        
        # --- CORRECCIÓN CRÍTICA AQUÍ ---
        # Activamos XACT_ABORT ON para esta sesión de Python específicamente.
        # Esto es OBLIGATORIO para transacciones distribuidas (Linked Servers).
        cursor.execute("SET XACT_ABORT ON")
        # -------------------------------
        
        # Datos del formulario
        id_prod = request.form['id_producto']
        target_sucursal = request.form['target_sucursal'] 
        stock = request.form['stock']
        nombre = request.form['nombre']
        marca = request.form['marca']
        precio = request.form['precio']

        # 1. INSERTAR EN CATALOGO (Local - Guayaquil)
        cursor.execute("INSERT INTO PRODUCTO (Id_producto, nombre, marca, precio) VALUES (?, ?, ?, ?)",
                       (id_prod, nombre, marca, precio))
        
        # 2. INSERTAR EL STOCK
        if target_sucursal == '2':
            # Local (Guayaquil)
            cursor.execute("INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (2, ?, ?)",
                           (id_prod, stock))
        
        elif target_sucursal == '1':
            # Remoto (Quito) - Linked Server
            # Al tener XACT_ABORT ON, SQL Server permitirá la transacción anidada
            query_remota = """
                INSERT INTO [LAPTOP].[TechStore_Quito].[dbo].[INVENTARIO] 
                (Id_sucursal, Id_producto, cantidad) VALUES (1, ?, ?)
            """
            cursor.execute(query_remota, (id_prod, stock))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
        
    except Exception as e:
        # Si algo falla (ej. Quito apagado), XACT_ABORT ON asegura que el 
        # INSERT del producto local también se cancele automáticamente.
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=str(e)))

@actions_bp.route('/edit_product', methods=['POST'])
def edit_product():
    sucursal = session.get('sucursal', 'Quito')
    if sucursal != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Solo Guayaquil modifica."))

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        cursor.execute("UPDATE PRODUCTO SET nombre = ?, marca = ?, precio = ? WHERE Id_producto = ?", 
                       (request.form['nombre'], request.form['marca'], request.form['precio'], request.form['id_producto']))
        cursor.execute("""
            IF EXISTS (SELECT 1 FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = 2)
                UPDATE INVENTARIO SET cantidad = ? WHERE Id_producto = ? AND Id_sucursal = 2
            ELSE
                INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (2, ?, ?)
        """, (request.form['id_producto'], request.form['stock'], request.form['id_producto'], request.form['id_producto'], request.form['stock']))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=str(e)))

@actions_bp.route('/add_employee', methods=['POST'])
def add_employee():
    sucursal = session.get('sucursal', 'Quito')
    if sucursal != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='EMPLEADO', error="Acceso denegado."))
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO EMPLEADO (Id_empleado, nombre, direccion, telefono, correo, Id_sucursal) VALUES (?, ?, ?, ?, ?, 2)", 
                       (request.form['id_empleado'], request.form['nombre'], request.form['direccion'], request.form['telefono'], request.form['correo']))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='EMPLEADO'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='EMPLEADO', error=str(e)))