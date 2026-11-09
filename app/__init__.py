import os
from datetime import timedelta
from urllib.parse import quote_plus

from dotenv import load_dotenv

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

from flask_wtf.csrf import CSRFProtect



BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Always the project-root .env, whatever folder the app is started from.
# override=True: the file on disk wins over stale copies, such as what VS Code put into an older terminal.
load_dotenv(os.path.join(os.path.dirname(BASE_DIR), '.env'), override=True)
csrf = CSRFProtect()
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    
    # LOCAL CONFIG
    # app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root@localhost/bucal_db'
    # app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    #CLOUD DATABASE CONFIG
    # No fallback: a known key lets anyone forge a logged-in session cookie
    app.config['SECRET_KEY'] = os.environ['SECRET_KEY']
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

    # SESSION COOKIE
    # Logged out after 30 idle minutes, since the cookie is re-signed on every request
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # HTTPS only unless FLASK_DEBUG=1. Browsers still accept it from the local dev server,
    # since they treat 127.0.0.1 and localhost as secure.
    app.config['SESSION_COOKIE_SECURE'] = not app.debug

    # FILE UPLOAD LIMIT
    # Whole request, so 1 MB above the 10 MB file limit (checked in routes.py) to leave room for the form around the file
    app.config['MAX_CONTENT_LENGTH'] = 11 * 1024 * 1024

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
        add_missing_columns()

    return app


def add_missing_columns():
    # create_all() only makes new tables, so columns added to existing tables go here
    columns = {c['name'] for c in inspect(db.engine).get_columns('calendar_events')}
    if 'end_date' not in columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE calendar_events ADD COLUMN end_date DATE NULL'))


    