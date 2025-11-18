"""
Gunicorn wrapper for CastMail2List for productive use.

For administrative use, run castmail2list-cli
"""

import argparse
import os
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "-c", "--app-config", type=str, required=True, help="Path to YAML configuration file"
)
parser.add_argument("-g", "--gunicorn-config", type=str, help="Path to Gunicorn configuration file")
parser.add_argument("--debug", action="store_true", help="Run in debug mode (development only)")


def main():
    """Run Gunicorn server with the specified configuration"""
    args = parser.parse_args()

    if args.gunicorn_config:
        gunicorn_config_path = args.gunicorn_config
    else:
        # Get path of this file to define location of the default gunicorn config
        gunicorn_config_path = os.path.join(os.path.dirname(__file__), "gunicorn.conf.py")

    subprocess.run(
        [
            "gunicorn",
            "-c",
            gunicorn_config_path,
            "castmail2list.wsgi:app",
            "-e",
            f"CONFIG_FILE={args.app_config}",
            "-e",
            f"DEBUG={args.debug}",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
