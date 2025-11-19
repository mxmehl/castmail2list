"""Configuration for CastMail2List"""

import logging
from pathlib import Path
from typing import Any

import yaml
from jsonschema import FormatChecker, validate
from jsonschema.exceptions import ValidationError

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "DATABASE_URI": {"type": "string"},
        "SECRET_KEY": {"type": "string"},
        "LANGUAGE": {"type": "string"},
        "DOMAIN": {"type": "string"},
        "HOST_TYPE": {"type": "string"},
        "CREATE_LISTS_AUTOMATICALLY": {"type": "boolean"},
        "POLL_INTERVAL_SECONDS": {"type": "integer"},
        "IMAP_DEFAULT_HOST": {"type": "string"},
        "IMAP_DEFAULT_PORT": {"type": "integer"},
        "IMAP_DEFAULT_USER_DOMAIN": {"type": "string"},
        "IMAP_DEFAULT_PASS": {"type": "string"},
        "IMAP_FOLDER_INBOX": {"type": "string"},
        "IMAP_FOLDER_PROCESSED": {"type": "string"},
        "IMAP_FOLDER_SENT": {"type": "string"},
        "IMAP_FOLDER_BOUNCES": {"type": "string"},
        "IMAP_FOLDER_DENIED": {"type": "string"},
        "IMAP_FOLDER_DUPLICATE": {"type": "string"},
        "SMTP_HOST": {"type": "string"},
        "SMTP_PORT": {"type": "integer"},
        "SMTP_USER": {"type": "string"},
        "SMTP_PASS": {"type": "string"},
        "SMTP_STARTTLS": {"type": "boolean"},
    },
    "required": ["SECRET_KEY", "DOMAIN", "HOST_TYPE", "SMTP_HOST"],
    "additionalProperties": False,
}


class AppConfig:  # pylint: disable=too-few-public-methods
    """Flask configuration from YAML file with some defaults"""

    # App settings
    DATABASE_URI: str = ""
    SECRET_KEY: str = ""

    # General settings
    LANGUAGE: str = "en"  # Supported languages: "en", "de"
    DOMAIN: str = ""
    HOST_TYPE = ""  # used for auto list creation. Can be: empty, uberspace7, uberspace8
    CREATE_LISTS_AUTOMATICALLY: bool = False
    POLL_INTERVAL_SECONDS: int = 60

    # IMAP settings and defaults (used as defaults for new lists)
    IMAP_DEFAULT_HOST: str = ""
    IMAP_DEFAULT_PORT: int = 993
    IMAP_DEFAULT_USER_DOMAIN: str = ""
    IMAP_DEFAULT_PASS: str = ""

    # IMAP folder names
    IMAP_FOLDER_INBOX: str = "INBOX"
    IMAP_FOLDER_PROCESSED: str = "Processed"
    IMAP_FOLDER_SENT: str = "Sent"
    IMAP_FOLDER_BOUNCES: str = "Bounces"
    IMAP_FOLDER_DENIED: str = "Denied"
    IMAP_FOLDER_DUPLICATE: str = "Duplicate"

    # SMTP settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_STARTTLS = True

    @classmethod
    def validate_config_schema(cls, cfg: dict, schema: dict) -> None:
        """Validate the config against a JSON schema"""
        try:
            validate(instance=cfg, schema=schema, format_checker=FormatChecker())
        except ValidationError as e:
            logging.critical("Config validation failed: %s", e.message)
            raise ValueError(e) from None
        logging.debug("Config validated successfully against schema.")

    @classmethod
    def load_from_yaml(cls, yaml_path: str | Path) -> dict[str, Any]:
        """Load configuration from YAML file.

        Args:
            yaml_path: Path to YAML configuration file

        Returns:
            Dictionary with configuration values
        """
        logging.debug("Loading configuration from YAML file: %s", yaml_path)
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                cls.validate_config_schema(data, CONFIG_SCHEMA)
                return data
        except FileNotFoundError as e:
            logging.critical("Configuration file not found: %s", yaml_path)
            raise e
        except yaml.YAMLError as e:
            logging.critical("Error parsing YAML configuration file: %s", e)
            raise e

    @classmethod
    def from_yaml_and_env(cls, yaml_path: str | Path) -> "AppConfig":
        """Create Config instance from YAML file, overriding class defaults

        Args:
            yaml_path (str | Path): Path to YAML configuration file

        Returns:
            Config instance with merged configuration
        """
        config = cls()

        # Load from YAML if provided
        if yaml_path:
            yaml_config = cls.load_from_yaml(yaml_path)
            for key, value in yaml_config.items():
                if hasattr(config, key.upper()):
                    setattr(config, key.upper(), value)

        # Environment variables override YAML (re-apply from env)
        return config
