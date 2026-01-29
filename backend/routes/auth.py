# backend/routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session
from backend.database import get_db_connection

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        sucursal_seleccionada = request.form['sucursal']
        
        # Guardamos la elección en sesión
        session['sucursal'] = sucursal_seleccionada
        
        try:
            # 1. Intentamos conectar a la sede seleccionada
            conn = get_db_connection(sucursal_seleccionada)
            cursor = conn.cursor()
            
            # --- VALIDACIÓN DE EMPLEADO (ADMIN) ---
            cursor.execute("SELECT Id_empleado, nombre FROM EMPLEADO WHERE correo = ?", (correo,))
            empleado = cursor.fetchone()
            
            if empleado:
                # ¡Éxito! Es empleado de esta sede
                session['user_id'] = empleado[0]
                session['user_name'] = empleado[1]
                session['user_role'] = 'admin'
                session['assigned_branch'] = sucursal_seleccionada 
                
                conn.close()
                return redirect(url_for('views.dashboard'))
            
            # --- VALIDACIÓN DE CLIENTE (GLOBAL) ---
            # Los clientes son globales, así que deberían poder entrar en cualquier lado
            cursor.execute("SELECT Id_cliente, nombre FROM CLIENTE WHERE correo = ?", (correo,))
            cliente = cursor.fetchone()
            
            if cliente:
                session['user_id'] = cliente[0]
                session['user_name'] = cliente[1]
                session['user_role'] = 'cliente'
                session['user_email'] = correo
                conn.close()
                return redirect(url_for('views.index'))

            conn.close()

            # --- INTELIGENCIA DE ERROR: ¿ESTÁ EN LA OTRA SEDE? ---
            # Si llegamos aquí, no se encontró en la sede seleccionada.
            # Vamos a buscar en la "otra" sede para dar un mensaje útil.
            
            otra_sede = 'Guayaquil' if sucursal_seleccionada == 'Quito' else 'Quito'
            try:
                conn_otra = get_db_connection(otra_sede)
                cursor_otra = conn_otra.cursor()
                cursor_otra.execute("SELECT nombre FROM EMPLEADO WHERE correo = ?", (correo,))
                empleado_otro = cursor_otra.fetchone()
                conn_otra.close()

                if empleado_otro:
                    return render_template('login.html', 
                        error=f"⚠️ Error de Sede: El usuario '{empleado_otro[0]}' pertenece a {otra_sede}. Cambia la opción en el selector.")
            except:
                pass # Si falla la conexión a la otra sede, ignoramos esta validación extra.

            # Si no está en ninguna parte
            return render_template('login.html', error="❌ Credenciales incorrectas o usuario no registrado.")
            
        except Exception as e:
            return render_template('login.html', error=f"Error de conexión con {sucursal_seleccionada}: {str(e)}")

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    # Mantenemos la sucursal seleccionada para comodidad del usuario
    sucursal_actual = session.get('sucursal', 'Quito')
    session.clear()
    session['sucursal'] = sucursal_actual
    return redirect(url_for('auth.login'))