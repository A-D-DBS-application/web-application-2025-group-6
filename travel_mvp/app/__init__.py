from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login_route'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Register template filter for accommodation formatting
    @app.template_filter('format_accommodation')
    def format_accommodation_filter(accommodation_type):
        from app.utils import format_accommodation_type
        return format_accommodation_type(accommodation_type)
    
    # Register template filter for budget range formatting
    @app.template_filter('format_budget')
    def format_budget_filter(budget_range):
        from app.utils import format_budget_range
        return format_budget_range(budget_range)

    # Register all blueprints
    from app.routes import main_bp
    from app.routes.auth_routes import auth_bp
    from app.routes.api_routes import api_bp
    from app.routes.itinerary_routes import itinerary_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(itinerary_bp)

    return app
