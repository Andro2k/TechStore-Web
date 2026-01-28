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
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Acceso denegado."))

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        
        # Datos del formulario
        id_prod = request.form['id_producto']
        nombre = request.form['nombre']
        marca = request.form['marca']
        precio = request.form['precio']
        
        # Stocks ingresados
        stock_para_gye = int(request.form['stock_gye'])
        stock_para_uio = int(request.form['stock_uio'])
        stock_total_fisico = stock_para_gye + stock_para_uio

        # 1. CREAR PRODUCTO (Catálogo Global)
        cursor.execute("INSERT INTO PRODUCTO (Id_producto, nombre, marca, precio) VALUES (?, ?, ?, ?)",
                       (id_prod, nombre, marca, precio))
        
        # 2. INGRESAR TODO EL STOCK A BODEGA MATRIZ (Primero entra todo a GYE)
        # Si llegaron 100 laptops (50 para mi, 50 para Quito), fisicamente entraron 100 a mi bodega primero.
        if stock_total_fisico > 0:
            cursor.execute("INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (2, ?, ?)",
                           (id_prod, stock_total_fisico))
        
        # 3. EJECUTAR TRANSFERENCIA AUTOMÁTICA (Si se pidió enviar a Quito)
        if stock_para_uio > 0:
            # Llamamos al SP de envío que ya creamos. 
            # Este SP restará los 50 de GYE y creará el registro de envío.
            cursor.execute("EXEC sp_Enviar_A_Quito @IdProducto = ?, @Cantidad = ?", (id_prod, stock_para_uio))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
        
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=f"Error al agregar: {str(e)}"))

@actions_bp.route('/delete_product', methods=['POST'])
def delete_product():
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Solo Matriz puede eliminar."))

    id_prod = request.form['id_producto']

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()

        # Validar si tiene ventas (Integridad Referencial)
        # Nota: Revisamos localmente. Si hay ventas en Quito, la replicación podría fallar al borrar,
        # pero SQL Server suele proteger esto con Foreign Keys.
        
        # 1. Borrar de Inventario Local (Si existe)
        cursor.execute("DELETE FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = 2", (id_prod,))
        
        # 2. Borrar del Catálogo (Esto disparará la replicación de borrado a Quito)
        cursor.execute("DELETE FROM PRODUCTO WHERE Id_producto = ?", (id_prod,))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))

    except Exception as e:
        # Error común: FK Constraint (Ya se vendió el producto)
        if "REFERENCE" in str(e) or "conflicted" in str(e):
            mensaje = "No se puede eliminar: El producto ya tiene ventas o movimientos registrados."
        else:
            mensaje = f"Error al eliminar: {str(e)}"
            
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=mensaje))
    
@actions_bp.route('/delete_local_inventory', methods=['POST'])
def delete_local_inventory():
    # Esta acción es para que una sucursal "limpie" su bodega
    # No borra el producto del catálogo (porque eso es de Guayaquil), 
    # solo borra el registro de existencias local.
    
    sucursal = session.get('sucursal')
    # Validamos que NO sea Guayaquil (ellos usan delete_product)
    if sucursal == 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Usa el botón de eliminar global."))

    id_prod = request.form['id_producto']
    id_suc = 1  # Asumimos Quito (Nodo 1)

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        # Solo borramos de la tabla INVENTARIO local
        cursor.execute("DELETE FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = ?", (id_prod, id_suc))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))

    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=f"Error al retirar stock: {str(e)}"))
    
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

@actions_bp.route('/enviar_mercaderia', methods=['POST'])
def enviar_mercaderia():
    # 1. Solo Guayaquil puede enviar
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error="Solo la Matriz puede realizar envíos."))

    id_producto = request.form['id_producto']
    cantidad = request.form['cantidad']

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        
        # Llamamos al SP que creamos en SQL (Resta stock GYE e inserta en ENVIO)
        cursor.execute("EXEC sp_Enviar_A_Quito @IdProducto = ?, @Cantidad = ?", (id_producto, cantidad))
        
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='LOGISTICA'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error=f"Error en envío: {str(e)}"))

@actions_bp.route('/recibir_mercaderia', methods=['POST'])
def recibir_mercaderia():
    # 2. Solo Quito puede recibir
    if session.get('sucursal') != 'Quito':
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error="Solo la Sucursal puede confirmar recepciones."))

    id_envio = request.form['id_envio']
    usuario = session.get('user_name', 'Admin')

    try:
        conn = get_db_connection('Quito')
        cursor = conn.cursor()
        
        # Llamamos al SP que creamos en SQL (Verifica, Inserta Recepción y Suma Stock UIO)
        cursor.execute("EXEC sp_Recibir_De_Guayaquil @IdEnvio = ?, @Usuario = ?", (id_envio, usuario))
        
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='LOGISTICA'))
    except Exception as e:
        # Capturamos los errores personalizados del SP (ej. "Ya fue recibido")
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error=f"Error al recibir: {str(e)}"))