"""WSGI entry point for production servers like gunicorn"""

# pylint: disable=duplicate-code

import argparse
import logging
import os
import subprocess

from flask import Flask

from . import __version__
from .app import create_app_wrapper
from .utils import get_app_bin_dir, get_user_config_path


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


def gunicorn():
    """Run Gunicorn server with the specified configuration"""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-c",
        "--app-config",
        type=str,
        help="Path to YAML configuration file",
        default=get_user_config_path(file="config.yaml"),
    )
    parser.add_argument(
        "-gc",
        "--gunicorn-config",
        type=str,
        help=(
            "Path to Gunicorn configuration file. Defaults to gunicorn.conf.py "
            "in the castmail2list package directory."
        ),
    )
    parser.add_argument(
        "-ge",
        "--gunicorn-exec",
        type=str,
        help=(
            "Path to Gunicorn executable. Defaults to using Gunicorn from the current Python "
            "environment."
        ),
    )
    parser.add_argument(
        "--debug", action="store_true", help="Run in debug mode (may leak sensitive information)"
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args()

    if args.gunicorn_config:
        gunicorn_config_path = args.gunicorn_config
    else:
        # Get path of this file to define location of the default gunicorn config
        gunicorn_config_path = os.path.join(os.path.dirname(__file__), "gunicorn.conf.py")

    if args.gunicorn_exec:
        gunicorn_exec = args.gunicorn_exec
    else:
        gunicorn_exec = str(get_app_bin_dir() / "gunicorn")

    subprocess.run(
        [
            gunicorn_exec,
            "-c",
            gunicorn_config_path,
            "castmail2list.wsgi:main()",
            "-e",
            f"CONFIG_FILE={args.app_config}",
            "-e",
            f"DEBUG={args.debug}",
        ],
        check=True,
    )
