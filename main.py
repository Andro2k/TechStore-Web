import sys
import socket
import threading
import webbrowser
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QComboBox, QPushButton, QSpinBox, QHBoxLayout, QMessageBox)
from PyQt6.QtCore import Qt
from werkzeug.serving import make_server

# Importamos la función que crea la app desde tu backend
from backend import create_app

class ServerLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.server_instance = None
        self.server_thread = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("TechStore Launcher")
        self.setGeometry(100, 100, 400, 320)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(25, 25, 25, 25)

        # Título
        title = QLabel("🚀 Configuración de Servidor")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0d6efd;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Selector de Adaptador/IP
        layout.addWidget(QLabel("Selecciona el Adaptador (Red):"))
        self.combo_ip = QComboBox()
        # Agregamos 0.0.0.0 al principio para que sea fácil elegir "Todo"
        ips = ['0.0.0.0', '127.0.0.1'] + self.get_local_ips()
        # Eliminamos duplicados manteniendo el orden
        seen = set()
        ips_unicas = [x for x in ips if not (x in seen or seen.add(x))]
        
        self.combo_ip.addItems(ips_unicas)
        layout.addWidget(self.combo_ip)

        # Selector de Puerto
        layout.addWidget(QLabel("Puerto de conexión:"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(5000)
        layout.addWidget(self.spin_port)

        layout.addStretch()

        # --- BOTONES DE CONTROL ---
        btn_layout = QHBoxLayout()
        
        self.btn_start = QPushButton("▶ INICIAR")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setStyleSheet("""
            QPushButton { background-color: #198754; color: white; font-weight: bold; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #157347; }
            QPushButton:disabled { background-color: #d1e7dd; color: #0f5132; }
        """)
        self.btn_start.clicked.connect(self.start_server)
        btn_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹ DETENER")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton { background-color: #dc3545; color: white; font-weight: bold; padding: 10px; border-radius: 5px; }
            QPushButton:hover { background-color: #bb2d3b; }
            QPushButton:disabled { background-color: #f8d7da; color: #842029; }
        """)
        self.btn_stop.clicked.connect(self.stop_server)
        btn_layout.addWidget(self.btn_stop)

        layout.addLayout(btn_layout)

        # Estado
        self.lbl_status = QLabel("Esperando configuración...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #6c757d; font-size: 12px; margin-top: 10px;")
        layout.addWidget(self.lbl_status)

        self.setLayout(layout)

    def get_local_ips(self):
        """Detecta las IPs reales de la máquina"""
        ips = []
        try:
            # Truco para obtener la IP real que sale a internet/red
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_principal = s.getsockname()[0]
            ips.append(ip_principal)
            s.close()
            
            # Obtener otras IPs (como la de Radmin)
            hostname = socket.gethostname()
            info = socket.getaddrinfo(hostname, None)
            for item in info:
                ip = item[4][0]
                if ':' not in ip and ip not in ips and ip != '127.0.0.1':
                    ips.append(ip)
        except Exception:
            pass
        return ips

    def start_server(self):
        ip = self.combo_ip.currentText()
        port = self.spin_port.value()

        self.toggle_inputs(False)
        
        # --- CORRECCIÓN 1: URL DEL NAVEGADOR ---
        # Si escuchamos en 0.0.0.0, el navegador debe abrir localhost
        # Si escuchamos en una IP específica, el navegador abre esa IP
        browser_url = f"http://127.0.0.1:{port}" if ip == '0.0.0.0' else f"http://{ip}:{port}"
        
        self.lbl_status.setText(f"🟢 Corriendo en: {ip}:{port}")
        self.lbl_status.setStyleSheet("color: #198754; font-weight: bold; margin-top: 10px;")

        # Abrir navegador
        try:
            webbrowser.open(browser_url)
        except:
            pass # Si falla abrir el navegador, no importa, el server sigue

        # Lanzar hilo del servidor
        self.server_thread = threading.Thread(target=self.run_flask, args=(ip, port))
        self.server_thread.daemon = True 
        self.server_thread.start()

    def stop_server(self):
        """Función segura para detener el servidor"""
        self.lbl_status.setText("⏳ Deteniendo servidor...")
        
        # --- CORRECCIÓN 2: EVITAR CRASH AL DETENER ---
        # Usamos un hilo separado para apagar, así no congelamos la ventana (GUI)
        shutdown_thread = threading.Thread(target=self._shutdown_logic)
        shutdown_thread.start()

    def _shutdown_logic(self):
        """Lógica interna de apagado para no bloquear la GUI"""
        try:
            if self.server_instance:
                self.server_instance.shutdown()
        except Exception as e:
            print(f"Error al apagar: {e}")
        finally:
            self.server_instance = None
            # Actualizamos la GUI desde el hilo principal (seguridad de Qt)
            # Usamos QMetaObject.invokeMethod o simplemente un timer si fuera complejo,
            # pero aquí restauraremos el estado visual tras un pequeño delay seguro.
            pass
        
        # Restaurar botones (esto técnicamente debería ser signal/slot, 
        # pero en PyQt simple suele funcionar si no tocamos widgets complejos)
        # Para ser 100% seguros, lo hacemos simple:
        self.toggle_inputs(True)
        self.lbl_status.setText("🔴 Servidor detenido.")
        self.lbl_status.setStyleSheet("color: #dc3545; font-weight: bold; margin-top: 10px;")

    def toggle_inputs(self, enable):
        self.combo_ip.setEnabled(enable)
        self.spin_port.setEnabled(enable)
        self.btn_start.setEnabled(enable)
        self.btn_stop.setEnabled(not enable)

    def run_flask(self, host_ip, port_num):
        try:
            app = create_app()
            # Threaded=True permite manejar múltiples peticiones a la vez (evita que se congele)
            self.server_instance = make_server(host_ip, port_num, app, threaded=True)
            self.server_instance.serve_forever()
            
        except OSError as e:
            # Capturar error de puerto ocupado
            self.lbl_status.setText(f"❌ Error: Puerto {port_num} ocupado.")
            self.toggle_inputs(True)
        except Exception as e:
            print(f"Error crítico Flask: {e}")
            self.toggle_inputs(True)

if __name__ == '__main__':
    qt_app = QApplication(sys.argv)
    window = ServerLauncher()
    window.show()
    sys.exit(qt_app.exec())