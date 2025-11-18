"""Flask app and CLI for CastMail2List"""

import argparse
import logging
import threading
from logging.config import dictConfig

from flask import Flask
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from .config import AppConfig
from .imap_worker import poll_imap
from .models import User, db
from .seeder import seed_database
from .utils import compile_scss, get_version_info
from .views.auth import auth
from .views.general import general
from .views.lists import lists
from .views.messages import messages


def configure_logging(debug: bool) -> None:
    """Configure logging"""
    dictConfig(
        {
            "version": 1,
            "formatters": {
                "default": {
                    "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
                }
            },
            "handlers": {
                "wsgi": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://flask.logging.wsgi_errors_stream",
                    "formatter": "default",
                }
            },
            "root": {"level": "DEBUG" if debug else "INFO", "handlers": ["wsgi"]},
        }
    )


def create_app(
    config_overrides: dict | None = None,
    start_imap: bool = True,
    yaml_config_path: str | None = None,
) -> Flask:
    """Create Flask app

    Parameters:
    - config_overrides: optional dict to update app.config before DB init (useful for tests)
    - start_imap: whether to start the background IMAP polling thread
    - yaml_config_path: optional path to YAML configuration file
    """
    app = Flask(__name__)

    # Load config from YAML, if provided
    if yaml_config_path:
        appconfig = AppConfig.from_yaml_and_env(yaml_config_path)
    else:
        appconfig = AppConfig()  # default config

    app.config.from_object(appconfig)

    # apply overrides early so DB and other setup use them
    if config_overrides:
        app.config.update(config_overrides)

    # Debug logging of config (without sensitive info)
    logging.debug("App configuration:\n%s", app.config)

    # Translations
    Babel(app, default_locale=app.config.get("LANGUAGE", "en"))
    logging.info("Language set to: %s", app.config.get("LANGUAGE", "en"))
    app.jinja_env.globals["current_language"] = app.config.get("LANGUAGE", "en")

    # Database
    db.init_app(app)
    Migrate(app, db)
    with app.app_context():
        db.create_all()

    # Trust headers from reverse proxy (1 layer by default)
    app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Secure session cookie config
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax"
    )

    # Set up rate limiting
    app.config.setdefault("RATE_LIMIT_DEFAULT", "20 per 1 minute")
    app.config.setdefault("RATE_LIMIT_LOGIN", "2 per 10 seconds")
    app.config.setdefault("RATELIMIT_STORAGE_URI", "memory://")
    limiter = Limiter(
        get_remote_address,
        default_limits=[app.config.get("RATE_LIMIT_DEFAULT", "")],
        storage_uri=app.config.get("RATE_LIMIT_STORAGE_URI"),
    )
    limiter.init_app(app)

    if app.config.get("RATE_LIMIT_STORAGE_URI") == "memory://" and not app.debug:
        logging.warning(
            "Rate limiting is using in-memory storage. Limits may not work with multiple processes."
        )

    # Enable CSRF protection
    CSRFProtect(app)

    # Configure Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    # User loader function for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register views and routes
    app.register_blueprint(auth)
    app.register_blueprint(general)
    app.register_blueprint(messages)
    app.register_blueprint(lists)

    # Inject variables into templates
    @app.context_processor
    def inject_vars():
        return {
            "version_info": get_version_info(),
        }

    # start background IMAP thread unless disabled or in testing
    if start_imap and not app.config.get("TESTING", False):
        t = threading.Thread(target=poll_imap, args=(app,), daemon=True)
        t.start()

    return app


def main():
    """Run the app"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-H", "--host", default="127.0.0.1")
    parser.add_argument("-p", "--port", default=5000, type=int)
    parser.add_argument("--debug", action="store_true", help="Run in debug mode (development only)")
    parser.add_argument("-c", "--config", type=str, help="Path to YAML configuration file")
    parser.add_argument(
        "--seed-only",
        type=str,
        metavar="SEED_FILE",
        help="Seed the database with a seed file and exit",
    )
    parser.add_argument(
        "--seed",
        type=str,
        metavar="SEED_FILE",
        help="Seed the database with a seed file and continue to start the server",
    )
    parser.add_argument(
        "--create-admin",
        nargs=2,
        metavar=("USERNAME", "PASSWORD"),
        help="Create an admin user and exit (usage: --create-admin admin secret)",
    )
    args = parser.parse_args()

    # Configure logging
    configure_logging(args.debug)

    # Create Flask app
    app = create_app(yaml_config_path=args.config)

    # Compile SCSS to CSS
    scss_files = [("castmail2list/static/scss/main.scss", "castmail2list/static/css/main.scss.css")]
    compile_scss("sass", scss_files)

    # Seed database if requested
    if args.seed_only:
        seed_database(app, seed_file=args.seed_only)
        print("Database seeded (seed-only).")
        return
    if args.seed:
        seed_database(app, seed_file=args.seed)

    # Create admin user if requested
    if args.create_admin:
        username, password = args.create_admin
        # run inside app context to access DB
        with app.app_context():
            existing = User.query.filter_by(username=username).first()
            if existing:
                logging.error("Error: user '%s' already exists", username)
                return
            new_user = User(
                username=username, password=generate_password_hash(password), role="admin"
            )
            db.session.add(new_user)
            db.session.commit()
            logging.info("Admin user '%s' created", username)
        return

    # Run the Flask app
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        extra_files=[bundle[0] for bundle in scss_files],  # watch SCSS file for changes
    )


if __name__ == "__main__":
    main()
