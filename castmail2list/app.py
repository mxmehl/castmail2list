"""Flask app and CLI for CastMail2List"""

import argparse
import logging
from datetime import datetime
from logging.config import dictConfig
from pathlib import Path

from flask import Flask
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate, check, downgrade, migrate, upgrade
from flask_wtf import CSRFProtect
from sqlalchemy.exc import OperationalError
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import __version__
from .config import AppConfig
from .imap_worker import initialize_imap_polling
from .models import AlembicVersion, User, db
from .seeder import seed_database
from .utils import (
    compile_scss_on_startup,
    get_app_bin_dir,
    get_list_subscribers,
    get_user_config_path,
    get_version_info,
    is_email_a_list,
)
from .views.api import api1
from .views.auth import auth
from .views.general import general
from .views.lists import lists
from .views.logs import logs
from .views.messages import messages
from .views.subscribers import subscribers

SCSS_FILES = [("static/scss/main.scss", "static/css/main.scss.css")]


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


def backup_sqlite_database(config_database_uri: str) -> None:
    """Backup the existing database file if it's SQLite"""
    if not config_database_uri.startswith("sqlite:///"):
        logging.warning("Database is not SQLite, skipping backup")
        return

    # Get the absolute SQLite database file path
    db_path = Path(config_database_uri.replace("sqlite:///", ""))
    if not db_path.is_absolute():
        app_path = Path(__file__).parent.resolve()
        db_path = (app_path / db_path).resolve()

    # Create backup file path with timestamp
    date = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup-{date}"

    # Copy database file to backup location
    try:
        Path(db_path).copy(backup_path)
        logging.info("Database backed up to %s", backup_path)
    except FileNotFoundError:
        logging.warning("Database file not found, skipping backup")


def create_app(
    config_overrides: dict | None = None,
    yaml_config_path: str | None = None,
    one_off_call: bool = False,
    debug: bool = False,
) -> Flask:
    """Create Flask app

    Args:
        config_overrides (dict): optional dict to update app.config before DB init (e.g. for tests)
        yaml_config_path (str): optional path to YAML configuration file
        one_off_call (bool): if True, indicates this is a one-off call (e.g. for CLI commands)
        debug (bool): if True, enable debug mode

    Returns:
        Flask: the Flask application
    """
    app = Flask(__name__)
    logging.debug("Executable bin path: %s", get_app_bin_dir())

    # Load config from YAML, if provided
    if yaml_config_path:
        appconfig = AppConfig.from_yaml_and_env(yaml_config_path)
    else:
        appconfig = AppConfig()  # default config

    app.config.from_object(appconfig)

    # Enable debug mode if requested
    app.debug = debug
    app.config["DEBUG"] = debug

    # apply overrides early so DB and other setup use them
    if config_overrides:
        app.config.update(config_overrides)

    # Translations
    Babel(app, default_locale=app.config.get("LANGUAGE", "en"))
    logging.info("Language set to: %s", app.config.get("LANGUAGE", "en"))
    app.jinja_env.globals["current_language"] = app.config.get("LANGUAGE", "en")

    # Database
    # default to SQLite in config dir if no DATABASE_URI set
    if not app.config.get("DATABASE_URI"):
        app.config["DATABASE_URI"] = "sqlite:///" + get_user_config_path(file="castmail2list.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["DATABASE_URI"]
    logging.info("Using database at %s", app.config["SQLALCHEMY_DATABASE_URI"])
    # Initialize the database
    migrations_dir = str(Path(__file__).parent.resolve() / "migrations")
    db.init_app(app)
    Migrate(app=app, db=db, directory=migrations_dir)

    # Trust headers from reverse proxy (1 layer by default)
    app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
    )

    # Secure session cookie config
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax"
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
        return db.session.get(User, int(user_id))

    # Register views and routes
    app.register_blueprint(api1)
    app.register_blueprint(auth)
    app.register_blueprint(general)
    app.register_blueprint(lists)
    app.register_blueprint(logs)
    app.register_blueprint(messages)
    app.register_blueprint(subscribers)

    # Inject variables and functions into templates
    @app.context_processor
    def inject_vars():
        return {
            "version_info": get_version_info(debug=app.debug),
        }

    app.jinja_env.globals.update(
        get_list_subscribers=get_list_subscribers, is_email_a_list=is_email_a_list
    )

    # ---------------
    # From here on, only for permanently running app, not one-off calls
    if one_off_call:
        return app

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

    # Start background IMAP thread unless in testing
    initialize_imap_polling(app)

    # Compile SCSS files on startup
    app.config["SCSS_FILES"] = compile_scss_on_startup(scss_files=SCSS_FILES)

    # Debug logging of config
    logging.debug("App configuration:\n%s", app.config)

    return app


def create_app_wrapper(app_config_path: str, debug: bool, one_off: bool) -> Flask:
    """Wrapper to create app from arguments. Both for direct Flask app and WSGI (gunicorn)"""
    # Configure logging
    configure_logging(debug)

    # Create Flask app
    app = create_app(yaml_config_path=app_config_path, one_off_call=one_off, debug=debug)

    return app


def run_one_off_commands(app: Flask, args: argparse.Namespace) -> None:
    """
    Run one-off commands like DB migrations or admin user creation

    Args:
        app (Flask): the Flask application
        args (argparse.Namespace): parsed command-line arguments
    """
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
            print(f"Admin user '{username}' created")
        return

    # Handle DB commands if provided
    if args.db is not None:
        with app.app_context():
            if args.db == "check":
                check()
            elif args.db in ("init", "upgrade"):
                # Backup existing DB before init/upgrade
                backup_sqlite_database(config_database_uri=app.config["DATABASE_URI"])
                upgrade()
            elif args.db == "downgrade":
                backup_sqlite_database(config_database_uri=app.config["DATABASE_URI"])
                downgrade()
            else:
                logging.error("Unknown DB command: %s", args.db)
                return
            print(f"Database command '{args.db}' completed")
            return
    # Handle DB migration if requested
    if args.db_migrate:
        with app.app_context():
            backup_sqlite_database(config_database_uri=app.config["DATABASE_URI"])
            migrate(message=args.db_migrate)
            print(f"Database migration with message '{args.db_migrate}' created")
        return
    # Seed database if requested
    if args.db_seed:
        seed_database(app, seed_file=args.db_seed)
        return


def main():
    """Run the app"""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-H", "--host", type=str, help="Host of Flask app", default="127.0.0.1")
    parser.add_argument("-p", "--port", type=int, help="Port of Flask app", default=2278)
    parser.add_argument(
        "-c",
        "--app-config",
        type=str,
        help="Path to YAML configuration file",
        default=get_user_config_path(file="config.yaml"),
    )
    parser.add_argument(
        "--create-admin",
        nargs=2,
        metavar=("USERNAME", "PASSWORD"),
        help="Create an admin user and exit (usage: --create-admin admin secret)",
    )
    # DB Commands
    parser.add_argument(
        "--db",
        choices=["check", "upgrade", "downgrade", "init"],
        help="Database commands, e.g. for migrations",
    )
    parser.add_argument("--db-migrate", type=str, help="Run a DB migration with the given message")
    parser.add_argument(
        "--db-seed",
        type=str,
        metavar="SEED_FILE",
        help="Seed the database with a seed file and exit",
    )
    parser.add_argument(
        "--dry", action="store_true", help="Run in dry mode (no changes to emails or DB)"
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument(
        "--debug", action="store_true", help="Run in debug mode (may leak sensitive information)"
    )
    args = parser.parse_args()

    # Create the Flask application
    one_off = False
    if args.db or args.create_admin or args.db_seed or args.db_migrate:
        # one-off call for most CLI commands
        one_off = True
    app = create_app_wrapper(app_config_path=args.app_config, debug=args.debug, one_off=one_off)

    # Run one-off commands if any
    if one_off:
        run_one_off_commands(app, args)
        return

    # Insert modes into config
    if args.dry:
        app.config["DRY"] = True
        logging.warning("Running in DRY mode: no changes to emails or database will be made.")

    # Identify and abort if database seems to be empty
    with app.app_context():
        try:
            # get alembic version, first entry, version column
            alembic_version = db.session.query(AlembicVersion).first()
            logging.debug(
                "Database revision: %s", alembic_version.version_num if alembic_version else None
            )
        except OperationalError as e:
            logging.info("Database error: %s", e)
            logging.critical(
                "Database does not seem to be initialized. Run with --db init to initialize."
            )
            return

    # Run the Flask app
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        extra_files=[
            bundle[0] for bundle in app.config["SCSS_FILES"]
        ],  # watch SCSS files for changes
    )


if __name__ == "__main__":
    main()
