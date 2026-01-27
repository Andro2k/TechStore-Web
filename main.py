import sys
import socket
import threading
import webbrowser
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel, 
                             QComboBox, QPushButton, QSpinBox, QMessageBox)
from PyQt6.QtCore import Qt

# Importamos la función que crea la app desde tu nueva carpeta backend
from backend import create_app

class ServerLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.server_thread = None

    def init_ui(self):
        self.setWindowTitle("TechStore Launcher")
        self.setGeometry(100, 100, 380, 280)

        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(25, 25, 25, 25)

        # Título
        title = QLabel("🚀 Configuración de Servidor")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Selector de Adaptador/IP
        layout.addWidget(QLabel("Selecciona el Adaptador (Red):"))
        self.combo_ip = QComboBox()
        self.combo_ip.addItems(self.get_local_ips())
        layout.addWidget(self.combo_ip)

        # Selector de Puerto
        layout.addWidget(QLabel("Puerto de conexión:"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1024, 65535)
        self.spin_port.setValue(5000)
        layout.addWidget(self.spin_port)

        layout.addStretch()

        # Botón de Inicio
        self.btn_start = QPushButton("INICIAR SISTEMA")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_server)
        layout.addWidget(self.btn_start)

        # Estado
        self.lbl_status = QLabel("Esperando configuración...")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #6c757d; font-size: 12px; margin-top: 10px;")
        layout.addWidget(self.lbl_status)

        self.setLayout(layout)

    def get_local_ips(self):
        """Detecta las IPs disponibles (WiFi, Ethernet, VPN, Localhost)"""
        ips = ['127.0.0.1', '0.0.0.0']
        try:
            hostname = socket.gethostname()
            info = socket.getaddrinfo(hostname, None)
            for item in info:
                ip = item[4][0]
                # Filtramos IPv6 y duplicados
                if ':' not in ip and ip not in ips:
                    ips.append(ip)
        except Exception:
            pass
        return ips

    def start_server(self):
        ip = self.combo_ip.currentText()
        port = self.spin_port.value()

        # Bloquear interfaz para evitar doble clic
        self.btn_start.setEnabled(False)
        self.btn_start.setText("🟢 Ejecutándose...")
        self.combo_ip.setEnabled(False)
        self.spin_port.setEnabled(False)
        
        url = f"http://{ip}:{port}"
        self.lbl_status.setText(f"Disponible en: {url}")
        self.lbl_status.setStyleSheet("color: #198754; font-weight: bold; margin-top: 10px;")

        # Abrir navegador automáticamente
        webbrowser.open(url)

        # Lanzar Flask en un hilo secundario
        self.server_thread = threading.Thread(target=self.run_flask, args=(ip, port))
        self.server_thread.daemon = True 
        self.server_thread.start()

    def run_flask(self, host_ip, port_num):
        try:
            # 1. Creamos la app usando la factoría de tu backend
            app = create_app()
            
            # 2. Ejecutamos Flask sin reloader (incompatible con hilos)
            app.run(host=host_ip, port=port_num, debug=False, use_reloader=False)
        except Exception as e:
            print(f"Error crítico al iniciar Flask: {e}")

if __name__ == '__main__':
    qt_app = QApplication(sys.argv)
    window = ServerLauncher()
    window.show()
    sys.exit(qt_app.exec())