# backend/__init__.py
from flask import Flask

def create_app():
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    
    from .config import SECRET_KEY
    app.secret_key = SECRET_KEY

    # Importar Blueprints
    from .routes.views import views_bp
    from .routes.actions import actions_bp
    from .routes.auth import auth_bp  # <--- AGREGAR ESTO

    # Registrar Blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(auth_bp)   # <--- AGREGAR ESTO

    return app