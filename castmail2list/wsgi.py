"""WSGI entry point for production servers like gunicorn"""

import logging
import os
import sys

from .app import configure_logging, create_app

# Configure logging for production
debug = os.environ.get("DEBUG", "false").lower() == "true"
configure_logging(debug=debug)

# Get config path from environment variable
config_path = os.environ.get("CONFIG_FILE", None)
if config_path is None:
    logging.critical("CONFIG_FILE environment variable is not set")
    sys.exit(1)
# Test if config file exists
if not os.path.exists(config_path):
    logging.critical("Configuration file %s does not exist", config_path)
else:
    # Get absolute path for logging
    config_path = os.path.abspath(config_path)
logging.info("Using configuration file: %s", config_path)

# Create the Flask application
app = create_app(yaml_config_path=config_path)

if __name__ == "__main__":
    app.run()
