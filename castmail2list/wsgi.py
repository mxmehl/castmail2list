"""WSGI entry point for production servers like gunicorn"""

import logging
import os

from flask import Flask

from .app import create_app_wrapper


def main() -> Flask | None:
    """Entrypoint for WSGI servers. Loading relevant configuration from environment variables.
    Returns the Flask app instance"""
    # Get debug flag from environment variable
    debug = os.environ.get("DEBUG", "false").lower() == "true"

    # Get config path from environment variable
    config_path = os.environ.get("CONFIG_FILE", None)
    if config_path is None:
        logging.critical("CONFIG_FILE environment variable is not set")
        return None
    # Test if config file exists
    if not os.path.exists(config_path):
        logging.critical("Configuration file %s does not exist", config_path)
        return None
    # Get absolute path for logging
    config_path = os.path.abspath(config_path)
    logging.info("Using configuration file: %s", config_path)

    app = create_app_wrapper(app_config_path=config_path, debug=debug, one_off=False)

    return app
