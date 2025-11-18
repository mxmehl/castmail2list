"""WSGI entry point for production servers like gunicorn"""

import logging
import os

from .app import configure_logging, create_app

# Configure logging for production
configure_logging(debug=False)

# Get config path from environment variable or use default
config_path = os.environ.get("CONFIG_FILE", "config.yaml")
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
