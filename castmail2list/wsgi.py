# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""WSGI entry point for production servers like gunicorn."""

# pylint: disable=duplicate-code

import argparse
import logging
import os
import subprocess
from pathlib import Path

from flask import Flask

from . import __version__
from .app import create_app_wrapper
from .utils import get_app_bin_dir, get_user_config_path


def main() -> Flask | None:
    """Entrypoint for WSGI servers. Loading relevant configuration from environment variables.
    Returns the Flask app instance.
    """
    # Get debug and dry flags from environment variable
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    dry = os.environ.get("DRY", "false").lower() == "true"

    # Get config path from environment variable
    config_path = os.environ.get("CONFIG_FILE", None)
    if config_path is None:
        logging.critical("CONFIG_FILE environment variable is not set")
        return None
    # Test if config file exists
    if not Path(config_path).exists():
        logging.critical("Configuration file %s does not exist", config_path)
        return None
    # Get absolute path for logging
    config_path = str(Path(config_path).resolve())
    logging.info("Using configuration file: %s", config_path)

    return create_app_wrapper(app_config_path=config_path, debug=debug, dry=dry, one_off=False)


def gunicorn() -> None:
    """Run Gunicorn server with the specified configuration."""
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
    parser.add_argument(
        "--dry", action="store_true", help="Run in dry mode (no changes to emails or DB)"
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args()

    gunicorn_config_path = args.gunicorn_config or str(Path(__file__).parent / "gunicorn.conf.py")

    gunicorn_exec = args.gunicorn_exec or str(get_app_bin_dir() / "gunicorn")

    subprocess.run(  # noqa: S603
        [
            gunicorn_exec,
            "-c",
            gunicorn_config_path,
            "castmail2list.wsgi:main()",
            "-e",
            f"CONFIG_FILE={args.app_config}",
            "-e",
            f"DEBUG={args.debug}",
            "-e",
            f"DRY={args.dry}",
        ],
        check=True,
    )
