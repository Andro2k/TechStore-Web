# backend/routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from backend.database import get_db_connection

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        sucursal = session.get('sucursal', 'Quito')
        
        try:
            conn = get_db_connection(sucursal)
            cursor = conn.cursor()
            
            # 1. ¿Es EMPLEADO (Admin)?
            cursor.execute("SELECT Id_empleado, nombre FROM EMPLEADO WHERE correo = ?", (correo,))
            empleado = cursor.fetchone()
            
            if empleado:
                session['user_id'] = empleado[0]
                session['user_name'] = empleado[1]
                session['user_role'] = 'admin'
                conn.close()
                return redirect(url_for('views.dashboard'))

            # 2. ¿Es CLIENTE?
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
            return render_template('login.html', error="Correo no registrado.")
            
        except Exception as e:
            return render_template('login.html', error=f"Error de conexión: {str(e)}")

    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    # Guardamos la sucursal actual para no perder la configuración
    sucursal_actual = session.get('sucursal', 'Quito')
    session.clear()
    session['sucursal'] = sucursal_actual
    return redirect(url_for('auth.login'))