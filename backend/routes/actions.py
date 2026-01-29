# backend/routes/actions.py
from flask import Blueprint, request, redirect, session, url_for
from backend.database import get_db_connection

# --- CONFIGURACIÓN ---
actions_bp = Blueprint('actions', __name__)
ID_QUITO = 1
ID_GUAYAQUIL = 2

# ==============================================================================
# 1. GESTIÓN DE SESIÓN Y NAVEGACIÓN
# ==============================================================================
@actions_bp.route('/cambiar_sucursal', methods=['POST'])
def cambiar_sucursal():
    # [NUEVO] CANDADO 2: Si es empleado, IMPEDIR el cambio
    if session.get('user_role') == 'admin':
        session['sucursal'] = session.get('assigned_branch', session.get('sucursal'))
        return redirect(request.referrer or url_for('views.dashboard'))

    # Si es cliente o invitado, sí dejamos cambiar
    session['sucursal'] = request.form['nueva_sucursal']
    return redirect(request.referrer or url_for('views.index'))

# ==============================================================================
# 2. PROCESOS DE VENTA (CHECKOUT)
# ==============================================================================
@actions_bp.route('/checkout', methods=['POST'])
def checkout():
    # --- NUEVA SEGURIDAD: BLOQUEAR EMPLEADOS ---
    if session.get('user_role') == 'admin':
        return redirect(url_for('views.index', error="⛔ Los empleados no pueden realizar compras con su cuenta de trabajo."))

    sucursal = session.get('sucursal', 'Quito')
    id_suc_actual = ID_QUITO if sucursal == 'Quito' else ID_GUAYAQUIL
    
    # Datos del formulario
    id_prod = request.form['id_producto']
    cantidad_compra = int(request.form['cantidad'])
    precio_unitario = float(request.form['precio_unitario'])
    total_factura = precio_unitario * cantidad_compra

    conn = None
    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()

        # A. Validar Stock Disponible (Local)
        cursor.execute("SELECT cantidad FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = ?", (id_prod, id_suc_actual))
        row = cursor.fetchone()
        
        if not row or row[0] < cantidad_compra:
            conn.close()
            return redirect(url_for('views.index', error=f"Stock insuficiente. Disponibles: {row[0] if row else 0}"))

        # B. Identificar o Registrar Cliente
        id_cliente = None
        nombre_cliente = ""
        
        if 'user_id' in session and session.get('user_role') == 'cliente':
            id_cliente = session['user_id']
        else:
            # --- REGISTRO DE CLIENTE NUEVO (LÓGICA DISTRIBUIDA) ---
            id_cliente = request.form['id_cliente']
            nombre_cliente = request.form['nombre']
            correo = request.form['correo']
            direccion = request.form['direccion']
            telefono = request.form['telefono']
            
            if sucursal == 'Quito':
                # EN QUITO: Usamos el SP que envía datos a Guayaquil vía Linked Server [MiniPC]
                cursor.execute("""
                    EXEC sp_RegistrarClienteNuevo 
                    @IdCliente = ?, @Nombre = ?, @Direccion = ?, @Telefono = ?, @Correo = ?
                """, (id_cliente, nombre_cliente, direccion, telefono, correo))
            else:
                # EN GUAYAQUIL: Insertamos directo (es la Matriz)
                # Primero verificamos si existe para no duplicar error
                cursor.execute("SELECT 1 FROM CLIENTE WHERE Id_cliente = ?", (id_cliente,))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO CLIENTE (Id_cliente, nombre, direccion, telefono, correo, Id_sucursal)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (id_cliente, nombre_cliente, direccion, telefono, correo, ID_GUAYAQUIL))
            
            # Auto-Login en sesión
            session['user_id'] = id_cliente
            session['user_name'] = nombre_cliente
            session['user_role'] = 'cliente'

        # C. Generar Factura (ID Manual simple para el ejemplo)
        # Nota: En producción real, usar IDENTITY o Secuencias es mejor.
        row_fact = cursor.execute("SELECT ISNULL(MAX(Id_factura), 0) + 1 FROM FACTURA").fetchone()
        id_factura = int(row_fact[0])
        
        cursor.execute("""
            INSERT INTO FACTURA (Id_factura, Id_cliente, Id_sucursal, total, fecha)
            VALUES (?, ?, ?, ?, GETDATE())
        """, (id_factura, id_cliente, id_suc_actual, total_factura))

        # D. Insertar Detalle
        cursor.execute("""
            INSERT INTO DETALLE_FACTURA (Id_factura, Id_producto, Id_sucursal, cantidad, precio_unidad, subtotal)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (id_factura, id_prod, id_suc_actual, cantidad_compra, precio_unitario, total_factura))
        
        # E. Actualizar Inventario Local
        cursor.execute("""
            UPDATE INVENTARIO SET cantidad = cantidad - ? 
            WHERE Id_producto = ? AND Id_sucursal = ?
        """, (cantidad_compra, id_prod, id_suc_actual))

        conn.commit()
        return redirect(url_for('views.index'))
        
    except Exception as e:
        print(f"Error Checkout: {e}")
        return redirect(url_for('views.index', error=f"Error en compra: {str(e)}"))
    finally:
        if conn: conn.close()

# ==============================================================================
# 3. GESTIÓN DE INVENTARIO (PRODUCTOS)
# ==============================================================================
@actions_bp.route('/add_product', methods=['POST'])
def add_product():
    #Agregar producto nuevo. Solo permitido en Matriz (Guayaquil).
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Acceso denegado."))

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        
        # Datos básicos
        id_prod = request.form['id_producto']
        stock_gye = int(request.form['stock_gye'])
        stock_uio = int(request.form['stock_uio'])
        stock_total_fisico = stock_gye + stock_uio

        # 1. Crear en Catálogo Global
        cursor.execute("INSERT INTO PRODUCTO (Id_producto, nombre, marca, precio) VALUES (?, ?, ?, ?)",
                       (id_prod, request.form['nombre'], request.form['marca'], request.form['precio']))
        
        # 2. Ingresar todo a Bodega Matriz (Físico)
        if stock_total_fisico > 0:
            cursor.execute("INSERT INTO INVENTARIO (Id_sucursal, Id_producto, cantidad) VALUES (?, ?, ?)",
                           (ID_GUAYAQUIL, id_prod, stock_total_fisico))
        
        # 3. Transferencia Automática a Quito (si aplica)
        if stock_uio > 0:
            cursor.execute("EXEC sp_Enviar_A_Quito @IdProducto = ?, @Cantidad = ?", (id_prod, stock_uio))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
        
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=f"Error al agregar: {str(e)}"))

@actions_bp.route('/edit_product', methods=['POST'])
def edit_product():
    """Editar detalles del producto. Solo Guayaquil."""
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Solo Guayaquil modifica."))

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        
        # Actualizar info
        cursor.execute("UPDATE PRODUCTO SET nombre = ?, marca = ?, precio = ? WHERE Id_producto = ?", 
                       (request.form['nombre'], request.form['marca'], request.form['precio'], request.form['id_producto']))
        
        # Actualizar stock local (Upsert simple)
        cursor.execute("""
            MERGE INVENTARIO AS target
            USING (SELECT ? AS id_suc, ? AS id_prod) AS source
            ON (target.Id_sucursal = source.id_suc AND target.Id_producto = source.id_prod)
            WHEN MATCHED THEN
                UPDATE SET cantidad = ?
            WHEN NOT MATCHED THEN
                INSERT (Id_sucursal, Id_producto, cantidad) VALUES (source.id_suc, source.id_prod, ?);
        """, (ID_GUAYAQUIL, request.form['id_producto'], request.form['stock'], request.form['stock']))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=str(e)))

@actions_bp.route('/delete_product', methods=['POST'])
def delete_product():
    """Eliminación Global (Matriz)."""
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Solo Matriz puede eliminar."))

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        id_prod = request.form['id_producto']

        # --- PASO 1: Eliminar Referencias (Limpieza de Historial) ---
        # ¡ADVERTENCIA!: Esto borrará este producto de todas las facturas históricas en Guayaquil.    
        # 1.1 Borrar de Envíos Logísticos
        cursor.execute("DELETE FROM TRANSFERENCIA_ENVIO WHERE Id_producto = ?", (id_prod,))     
        # 1.2 Borrar de Detalles de Factura (Ventas Locales Guayaquil)
        cursor.execute("DELETE FROM DETALLE_FACTURA WHERE Id_producto = ? AND Id_sucursal = ?", (id_prod, ID_GUAYAQUIL))       
        # 1.3 Borrar de Inventario (Stock Local Guayaquil)
        cursor.execute("DELETE FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = ?", (id_prod, ID_GUAYAQUIL))
        cursor.execute("DELETE FROM PRODUCTO WHERE Id_producto = ?", (id_prod,))

        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
        
    except Exception as e:
        # Si aún falla (ej. si hay referencias en otra tabla que olvidamos), mostramos el error
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=f"Error crítico: {str(e)}"))

@actions_bp.route('/delete_local_inventory', methods=['POST'])
def delete_local_inventory():
    """Eliminación Local (Sucursales). Solo limpia stock, no el producto."""
    sucursal = session.get('sucursal')
    if sucursal == 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error="Usa el botón de eliminar global."))

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM INVENTARIO WHERE Id_producto = ? AND Id_sucursal = ?", 
                       (request.form['id_producto'], ID_QUITO))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='PRODUCTO'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='PRODUCTO', error=f"Error: {str(e)}"))

# ==============================================================================
# 4. RECURSOS HUMANOS (EMPLEADOS)
# ==============================================================================
@actions_bp.route('/add_employee', methods=['POST'])
def add_employee():
    sucursal = session.get('sucursal', 'Quito')
    id_sucursal_destino = ID_QUITO if sucursal == 'Quito' else ID_GUAYAQUIL

    try:
        conn = get_db_connection(sucursal)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO EMPLEADO (Id_empleado, nombre, direccion, telefono, correo, Id_sucursal) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form['id_empleado'], request.form['nombre'], request.form['direccion'], 
            request.form['telefono'], request.form['correo'], id_sucursal_destino
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='EMPLEADO'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='EMPLEADO', error=f"Error RRHH: {str(e)}"))

# ==============================================================================
# 5. LOGÍSTICA (ENVÍOS Y RECEPCIONES)
# ==============================================================================
@actions_bp.route('/enviar_mercaderia', methods=['POST'])
def enviar_mercaderia():
    if session.get('sucursal') != 'Guayaquil':
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error="Solo Matriz envía."))

    try:
        conn = get_db_connection('Guayaquil')
        cursor = conn.cursor()
        cursor.execute("EXEC sp_Enviar_A_Quito @IdProducto = ?, @Cantidad = ?", 
                       (request.form['id_producto'], request.form['cantidad']))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='LOGISTICA'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error=f"Error Envío: {str(e)}"))

@actions_bp.route('/recibir_mercaderia', methods=['POST'])
def recibir_mercaderia():
    if session.get('sucursal') != 'Quito':
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error="Solo Sucursal recibe."))

    try:
        conn = get_db_connection('Quito')
        cursor = conn.cursor()
        cursor.execute("EXEC sp_Recibir_De_Guayaquil @IdEnvio = ?, @Usuario = ?", 
                       (request.form['id_envio'], session.get('user_name', 'Admin')))
        conn.commit()
        conn.close()
        return redirect(url_for('views.dashboard', tabla='LOGISTICA'))
    except Exception as e:
        return redirect(url_for('views.dashboard', tabla='LOGISTICA', error=f"Error Recepción: {str(e)}"))