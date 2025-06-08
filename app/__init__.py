from flask import Flask
from flask_login import LoginManager
import os
from app.models import db, User
from app.auth import auth
from app.profile import profile
from app.library import library
from app.stories import stories
from app.search import search

def create_app():
    app = Flask(__name__, 
                template_folder='../templates',  # Point to templates in root directory
                static_folder='../static')       # Point to static in root directory
    
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/scribe')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['COVER_SIZE'] = (512, 800)  # Width, Height

    # Initialize extensions
    db.init_app(app)
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(profile)
    app.register_blueprint(library)
    app.register_blueprint(stories)
    app.register_blueprint(search)

    # Create database tables
    with app.app_context():
        db.create_all()

    return app 