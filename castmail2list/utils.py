"""Utility functions for Castmail2List application"""

import logging
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, flash
from flask_babel import _
from imap_tools import MailBox, MailboxLoginError
from platformdirs import user_config_path

from . import __version__
from .models import MailingList, Subscriber


def compile_scss(compiler: str, scss_input: str, css_output: str) -> None:
    """Compile SCSS files to CSS using an external compiler"""
    try:
        logging.info("Compiling %s to %s", scss_input, css_output)
        subprocess.run([compiler, scss_input, css_output], check=True)
    except subprocess.CalledProcessError as e:
        logging.critical("Error compiling %s: %s", scss_input, e)
        sys.exit(1)
    except FileNotFoundError as e:
        logging.critical(
            "Sass compiler not found. Please ensure '%s' is installed: %s", compiler, e
        )
        sys.exit(1)


def compile_scss_on_startup(scss_files: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Compile SCSS to CSS on application startup.

    Args:
        scss_files (list[tuple[str, str]]): List of tuples with relative paths
    Return:
        list: List of compiled (input, output) absolute file paths
    """
    curpath = Path(__file__).parent.resolve()
    compiled_files: list[tuple[str, str]] = []
    for scss_input, css_output in scss_files:
        scss_input_abs = str(curpath / Path(scss_input))
        css_output_abs = str(curpath / Path(css_output))
        compile_scss("sass", scss_input=scss_input_abs, css_output=css_output_abs)
        compiled_files.append((scss_input_abs, css_output_abs))
    return compiled_files


def flash_form_errors(form):
    """Flash all errors from a Flask-WTF form"""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error in {getattr(form, field).label.text}: {error}", "error")


def get_version_info(debug: bool = False) -> str:
    """
    Get the current version information of the application. If in debug mode, include git commit
    hash.

    Example: "1.2.3 (a1b2c3d)" in debug mode, "1.2.3" otherwise.

    Args:
        debug (bool): Whether to include git commit hash information
    Returns:
        str: The version information string
    """
    if not debug:
        return __version__
    # Get short git commit hash if available
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except Exception:  # pylint: disable=broad-exception-caught
        logging.debug("Failed to get git commit hash.", exc_info=True)
        commit = "unknown commit"

    return f"{__version__} ({commit})"


def normalize_email_list(input_str: str) -> str:
    """Normalize a string of emails into a comma-separated list"""
    # Accepts either comma or newline separated, returns comma-separated
    if not input_str:
        return ""
    # Replace newlines with commas, then split
    emails = [email.strip() for email in input_str.replace("\n", ",").split(",") if email.strip()]
    return ", ".join(emails)


def list_to_string(listobj: list[str]) -> str:
    """Convert a list to a comma-separated string"""
    if isinstance(listobj, list):
        return ", ".join(listobj)
    logging.warning("Input is not a list: %s", listobj)
    return ""


def string_to_list(input_str: str) -> list[str]:
    """Normalize a string of strings into a list"""
    # Accepts either comma or newline separated, returns list of strings
    if not input_str:
        return []
    # Replace newlines with commas, then split
    strings = [
        string.strip() for string in input_str.replace("\n", ",").split(",") if string.strip()
    ]
    return strings


def create_bounce_address(ml_address: str, recipient: str) -> str:
    """
    Construct the individualized Envelope From address for bounce handling.

    For the list address `list1@list.example.com` and the recipient `jane.doe@gmail.com`,
    the return will be `list1+bounces--jane.doe=gmail.com@list.example.com`

    Args:
        recipient (str): The recipient email address
    Returns:
        str: The constructed Envelope From address
    """
    local_part, domain_part = ml_address.split("@", 1)
    sanitized_recipient = recipient.replace("@", "=").replace("+", "---plus---")
    return f"{local_part}+bounces--{sanitized_recipient}@{domain_part}"


def parse_bounce_address(bounce_address: str) -> str | None:
    """
    Parse the recipient email from a bounce address.

    For the bounce address `list1+bounces--jane.doe=gmail.com@list.example.com`, the return will be
    `jane.doe@gmail.com`

    Args:
        bounce_address (str): The bounce email address

    Returns:
        (str | None): The parsed recipient email address, or None if parsing fails
    """
    try:
        local_part, _ = bounce_address.split("@", 1)
        if "+bounces--" not in local_part:
            logging.debug("No bounce marker in address: %s", bounce_address)
            return None
        _, sanitized_recipient = local_part.split("+bounces--", 1)
        recipient = sanitized_recipient.replace("=", "@").replace("---plus---", "+")
        return recipient
    except ValueError:
        logging.warning("Failed to parse bounce address: %s", bounce_address)
        return None


def is_email_a_list(email: str) -> bool:
    """
    Check if the given email address is the address of one of the configured mailing lists.

    Args:
        email (str): The email address to check
    Returns:
        bool: True if the email is a mailing list address, False otherwise
    """
    list_addresses: set[str] = {
        lst.address.lower() for lst in MailingList.query.filter_by(deleted=False).all()
    }
    return email.lower() in list_addresses


def get_list_subscribers(ml: MailingList) -> list[Subscriber]:
    """
    Get all (deduplicated) subscribers of a mailing list, including those from overlapping
    lists, recursively.
    """
    visited_list_ids = set()
    subscribers_dict = {}

    def _collect_subscribers(list_obj: MailingList):
        logging.debug(
            "Collecting subscribers for list: %s <%s> (id=%s)",
            list_obj.name,
            list_obj.address,
            list_obj.id,
        )
        if list_obj.id in visited_list_ids:
            logging.debug(
                "List id %s already visited, skipping to avoid recursion loop.", list_obj.id
            )
            return
        visited_list_ids.add(list_obj.id)

        # Exclude deleted lists
        if list_obj.deleted:
            logging.warning("List id %s is marked deleted, skipping.", list_obj.id)
            return

        # Get direct subscribers
        direct_subs = Subscriber.query.filter_by(list_id=list_obj.id).all()
        logging.debug(
            "Found %d direct subscribers for list <%s>: %s",
            len(direct_subs),
            list_obj.address,
            ", ".join([sub.email for sub in direct_subs]),
        )
        for sub in direct_subs:
            if sub.email not in subscribers_dict:
                subscribers_dict[sub.email] = sub
                logging.debug("Added subscriber: %s", sub.email)
            else:
                logging.debug("Subscriber %s already added, skipping.", sub.email)

        # Find subscribers whose email matches another list address (nested lists)
        all_lists: list[MailingList] = MailingList.query.all()
        ml_addresses = {l.address: l for l in all_lists}
        for sub in direct_subs:
            nested_list = ml_addresses.get(sub.email)
            if nested_list:
                logging.debug(
                    "Subscriber %s is also a list address (%s), recursing into list id %s.",
                    sub.email,
                    nested_list.address,
                    nested_list.id,
                )
                if nested_list.id not in visited_list_ids:
                    _collect_subscribers(nested_list)
                else:
                    logging.debug("Nested list id %s already visited, skipping.", nested_list.id)

    _collect_subscribers(ml)

    # Remove any subscribers whose email is a list address (do not send to lists themselves)
    all_lists: list[MailingList] = MailingList.query.all()
    ml_addresses = {l.address for l in all_lists}
    result = [sub for email, sub in subscribers_dict.items() if email not in ml_addresses]

    logging.debug(
        "Found %d unique, non-list subscribers for the list <%s>: %s",
        len(result),
        ml.address,
        ", ".join([sub.email for sub in result]),
    )
    return result


def get_plus_suffix(email: str) -> str | None:
    """
    Extract the +suffix from an email address, if present.

    Args:
        email (str): The email address to extract the suffix from
    Returns:
        str | None: The suffix (without the +), or None if no suffix is present
    """
    local_part, _ = email.split("@", 1)
    if "+" in local_part:
        suffix = local_part.split("+", 1)[1]
        return suffix
    return None


def remove_plus_suffix(email: str) -> str:
    """
    Remove the +suffix from an email address, if present.

    Args:
        email (str): The email address to remove the suffix from
    Returns:
        str: The email address without the +suffix
    """
    local_part, domain_part = email.split("@", 1)
    if "+" in local_part:
        local_part = local_part.split("+", 1)[0]
    return f"{local_part}@{domain_part}"


def is_expanded_address_the_mailing_list(to_address: str, list_address: str) -> bool:
    """
    Check if the given (expanded) To address corresponds to the mailing list address,
    considering possible +suffixes and casing.

    Args:
        to_address (str): The (expanded) To email address
        list_address (str): The mailing list address to compare against
    Returns:
        bool: True if the address matches the mailing list address, False otherwise
    """
    to_local_part, to_domain_part = to_address.split("@", 1)
    list_local_part, list_domain_part = list_address.split("@", 1)

    # Check domain parts (case-insensitive)
    if to_domain_part.lower() != list_domain_part.lower():
        return False

    # Check local parts (case-insensitive, ignoring +suffix)
    to_local_part_no_suffix = to_local_part.split("+", 1)[0].lower()

    return to_local_part_no_suffix == list_local_part.lower()


def run_only_once(app: Flask):
    """Ensure that something is only run once if Flask is run in Debug mode. Check if Flask is run
    in Debug mode and what the value of env variable WERKZEUG_RUN_MAIN is"""
    logging.debug("FLASK_DEBUG=%s, WERKZEUG_RUN_MAIN=%s", app.debug, os.getenv("WERKZEUG_RUN_MAIN"))

    if not app.debug:
        return True
    if app.debug and os.getenv("WERKZEUG_RUN_MAIN") == "true":
        return True
    return False


def check_email_account_works(
    imap_host: str, imap_port: int, imap_user: str, imap_password: str
) -> bool:
    """
    Check if an email account exists on the IMAP server.

    Args:
        app (Flask): The Flask application instance for accessing configuration
        email (str): The email address to check
    Returns:
        bool: True if the email account exists, False otherwise
    """
    try:
        with MailBox(imap_host, imap_port).login(imap_user, imap_password):
            logging.debug("Successfully logged in to IMAP server %s as %s", imap_host, imap_user)
            return True
    except MailboxLoginError:
        logging.warning("Failed to log in to IMAP server %s as %s", imap_host, imap_user)
        return False
    except Exception as e:  # pylint: disable=broad-exception-caught
        logging.error(
            "Error while checking email account on IMAP server %s as %s: %s",
            imap_host,
            imap_user,
            e,
        )
        return False


def split_email_address(email: str) -> tuple[str, str]:
    """
    Split an email address into local part and domain part.

    Args:
        email (str): The email address to split
    Returns:
        tuple[str, str]: A tuple containing the local part and domain part
    """
    local_part, domain_part = email.split("@", 1)
    return local_part, domain_part


def create_email_account(host_type: str, email: str, password: str) -> bool:
    """
    Create an email account on the server.

    Args:
        host_type (str): The type of hosting environment (e.g., 'uberspace7', 'uberspace8')
        email (str): The email address to create
        password (str): The password for the new email account
    Returns:
        bool: True if the email account was created successfully, False otherwise
    """
    logging.info("Creating email account %s on host type %s", email, host_type)
    try:
        if host_type == "uberspace7":
            cmd = [
                "uberspace",
                "mail",
                "user",
                "add",
                "-p",
                password,
                split_email_address(email)[0],
            ]
        elif host_type == "uberspace8":
            cmd = ["uberspace", "mail", "address", "add", "--password", password, email]
        else:
            logging.error("Unsupported host type for email account creation: %s", host_type)
            return False

        subprocess.run(cmd, check=True)
        logging.info("Successfully created email account: %s", email)
        return True
    except subprocess.CalledProcessError as e:
        logging.error("Failed to create email account %s: %s", email, e)
        return False
    except FileNotFoundError as e:
        logging.error(
            "Uberspace command not found. Ensure application actually runs on Uberspace host: %s",
            e,
        )
        return False


def check_recommended_list_setting(ml: MailingList) -> list[tuple[str, str]]:
    """
    Check if the mailing list has recommended security settings.

    Args:
        ml (MailingList): The mailing list to check
    Returns:
        list[tuple[str, str]]: A list of warnings about missing recommended settings
    """
    findings = []

    if ml.mode == "broadcast":
        if not ml.allowed_senders and not ml.sender_auth:
            findings.append(
                (
                    _(
                        "In Broadcast mode, it is recommended to set Allowed Senders and/or "
                        "Sender Authentication Passwords!"
                    ),
                    "warning",
                )
            )

    return findings


def get_app_bin_dir() -> Path:
    """
    Get the directory where this app's executable resides in the current Python environment.
    """
    return Path(sys.executable).parent


def get_user_config_path(name: str = "castmail2list", file: str = "") -> str:
    """
    Get the user configuration directory for the application.

    Args:
        app_name (str): The name of the application
        file (str): Optional filename to append to the config directory
    Returns:
        str: The path to the user configuration directory
    """
    config_path = Path(user_config_path(appname=name, ensure_exists=True))
    if file:
        config_path = config_path / file
    return str(config_path)
