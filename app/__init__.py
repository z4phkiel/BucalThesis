import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

from flask_wtf.csrf import CSRFProtect



load_dotenv()
csrf = CSRFProtect()
db = SQLAlchemy()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def create_app():
    app = Flask(__name__)
    
    # LOCAL CONFIG
    # app.config['SECRET_KEY'] = 'sample_secret_key'
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root@localhost/bucal_db'
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    #CLOUD DATABASE CONFIG
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'sample_secret_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        f"mysql+pymysql://{os.environ['DB_USER']}:{quote_plus(os.environ['DB_PASSWORD'])}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        "connect_args": {"ssl": {"ca": os.path.join(BASE_DIR, "ca.pem")}},
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # FILE UPLOAD LIMIT
    app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 # 10 MB LIMIT

    db.init_app(app)
    csrf.init_app(app)

    from app.routes import main_bp, restrict_mobile_access
    app.before_request(restrict_mobile_access)
    app.register_blueprint(main_bp)

    @app.errorhandler(403)
    def forbidden(error):
        return render_template('error_pages/403.html'), 403
            
    with app.app_context():
        db.create_all()
        
    return app


    