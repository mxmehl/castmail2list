# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Configuration for CastMail2List."""

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import yaml
from jsonschema import FormatChecker, validate
from jsonschema.exceptions import ValidationError


def _load_config_schema() -> dict:
    """Load the configuration schema from JSON file.

    Returns:
        Dictionary with the configuration schema
    """
    schema_path = Path(__file__).parent / "config_schema.json"
    with schema_path.open(encoding="utf-8") as f:
        return json.load(f)


CONFIG_SCHEMA = _load_config_schema()


class AppConfig:  # pylint: disable=too-few-public-methods
    """Flask configuration from YAML file with some defaults."""

    # App settings
    DATABASE_URI: str = ""  # Empty here; app setup falls back to SQLite in XDG config dir.
    SECRET_KEY: str = ""  # Empty here; production startup requires a non-empty value.

    # General settings
    LANGUAGE: str = "en"  # Supported languages: "en", "de"
    DOMAIN: str = ""  # Email domain used for list addresses and related headers.
    SYSTEM_EMAIL: str = ""
    HOST_TYPE: str = ""  # Used for auto list creation. Can be: empty, uberspace7, uberspace8.
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
    SMTP_STARTTLS: bool = True

    # Sender notification settings
    NOTIFY_REJECTED_SENDERS: bool = False
    NOTIFY_REJECTED_KNOWN_ONLY: bool = True
    NOTIFY_REJECTED_TRUSTED_DOMAINS: ClassVar[list[str]] = []
    NOTIFY_REJECTED_HOURLY_LIMIT: int = 20

    @classmethod
    def validate_config_schema(cls, cfg: dict, schema: dict) -> None:
        """Validate the config against a JSON schema."""
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
            with Path(yaml_path).open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                cls.validate_config_schema(data, CONFIG_SCHEMA)
                return data
        except FileNotFoundError:
            logging.critical("Configuration file not found: %s", yaml_path)
            raise
        except yaml.YAMLError as e:
            logging.critical("Error parsing YAML configuration file: %s", e)
            raise

    @classmethod
    def from_yaml_and_env(cls, yaml_path: str | Path) -> "AppConfig":
        """Create Config instance from YAML file, overriding class defaults.

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
