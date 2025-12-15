"""Utility functions for Castmail2List application"""

import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import email_validator  # dependency for WTForms email validator
from flask import Flask, flash
from flask_babel import _
from imap_tools import EmailAddress, MailBox, MailboxLoginError
from imap_tools.message import MailMessage
from platformdirs import user_config_path
from sqlalchemy import func

from . import __version__
from .models import EmailIn, EmailOut, Logs, MailingList, Subscriber, db


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


def string_to_list(input_str: str, lower: bool = False) -> list[str]:
    """
    Normalize a string of strings into a list.

    Args:
        input_str (str): Input string with comma or newline separated values
        lower (bool): Whether to convert all strings to lowercase
    Returns:
        list[str]: List of normalized strings
    """
    # Accepts either comma or newline separated, returns list of strings
    if not input_str:
        return []
    # Replace newlines with commas, then split
    strings = [
        string.strip() for string in input_str.replace("\n", ",").split(",") if string.strip()
    ]
    # Optionally convert to lowercase
    if lower:
        strings = [s.lower() for s in strings]
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


def generate_via_from_header(
    from_values: EmailAddress | None, ml_address: str, ml_display: str
) -> str:
    """Generate 'Sender Name via List Name <list@address>' format for From header.

    Args:
        from_values (EmailAddress | None): The original From header values
        ml_address (str): The mailing list email address
        ml_display (str): The display name of the mailing list

    Returns:
        str: Formatted From header string
    """
    if not from_values:
        logging.error("No valid From header, cannot generate via header")
        return ""
    return f"{from_values.name or from_values.email} " f"via {ml_display} <{ml_address}>"


def reply_to_from_email_and_name(email: str, name: str | None = None) -> str:
    """
    Generate 'Sender Name <email>' format for Reply-To header from the EmailAddress object generated
    by imap-tools.

    Args:
        email (str): The email address
        name (str | None): The display name
    Returns:
        str: Formatted Reply-To header string
    """
    if name:
        return f"{name} <{email}>"
    return email


def is_email_a_list(email: str) -> MailingList | None:
    """
    Check if the given email address is the address of one of the configured active or inactive
    mailing lists.

    To avoid case sensitivity issues, the check is done in a case-insensitive manner.

    It also removes any +suffix before checking.

    Args:
        email (str): The email address to check
    Returns:
        The MailingList object if the email is a list address, None otherwise
    """
    email = remove_plus_suffix(email)
    if ml := MailingList.query.filter(func.lower(MailingList.address) == func.lower(email)).first():
        return ml
    return None


def get_list_by_id(list_id: str) -> MailingList | None:
    """
    Get a mailing list by its ID.

    Args:
        list_id (str): The ID of the mailing list
    Returns:
        MailingList | None: The MailingList object if found, None otherwise
    """
    return MailingList.query.filter_by(id=list_id).first()


def get_list_recipients_recursive(
    list_id: str, only_direct: bool = False, only_indirect: bool = False
) -> dict[str, dict]:
    """
    Get all real recipients for a mailing list with direct and indirect breakdown. The result is a
    mapping of recipient email to their details and source lists. Direct subscribers are marked with
    source ["direct"]. Indirect recipients have source list IDs they are subscribed through.

    Notes:
    * Recipients are not the same as subscribers. A subscriber is always direct and may be a list. A
      recipient is always a real person and may also be coming from indirect subscription via nested
      lists.
    * It may happen that a recipient appears both as direct and indirect recipient.

    Args:
        list_id (str): The ID of the mailing list
        only_direct (bool): If True, return only direct recipients
        only_indirect (bool): If True, return only indirect recipients

    Returns:
        dict: Mapping of recipient email to their details and source lists. If the mailing list is
            not found, returns an empty dictionary.
    """
    visited_list_ids = set()
    recipients_dict: dict[str, dict] = {}

    ml = get_list_by_id(list_id)
    if not ml:
        logging.warning("Mailing list with ID %s not found.", list_id)
        return recipients_dict

    def _collect_recipients(list_obj: MailingList, is_direct: bool = False):
        """Recursively collect subscribers from the given mailing list and nested lists"""
        if list_obj.id in visited_list_ids:  # list already visited, avoid recursion
            return
        visited_list_ids.add(list_obj.id)  # Mark this list as visited

        # Exclude deleted lists
        if list_obj.deleted:
            return

        # Get direct subscribers
        direct_subs: list[Subscriber] = Subscriber.query.filter_by(list_id=list_obj.id).all()
        for rec in direct_subs:
            # Add subscriber if not already added
            if rec.email not in recipients_dict:
                recipients_dict[rec.email] = {
                    "id": rec.id,
                    "name": rec.name,
                    "email": rec.email,
                    "source": ["direct"] if is_direct else [list_obj.id],
                }
            else:
                # Update source list
                if is_direct:
                    if "direct" not in recipients_dict[rec.email]["source"]:
                        recipients_dict[rec.email]["source"].append("direct")
                else:
                    if list_obj.id not in recipients_dict[rec.email]["source"]:
                        recipients_dict[rec.email]["source"].append(list_obj.id)

        # Iterate over direct recipients. If any is a list, recurse into it
        for rec in direct_subs:
            if nested_list := is_email_a_list(rec.email):
                # Only recurse if the nested list hasn't been visited yet
                if nested_list.id not in visited_list_ids:
                    _collect_recipients(nested_list, is_direct=False)

    # Start collecting from the given mailing list
    _collect_recipients(ml, is_direct=True)

    # Remove any recipient whose email is a list address (do not send to lists themselves)
    for email in list(recipients_dict.keys()):
        if is_email_a_list(email):
            del recipients_dict[email]

    # Filter based on only_direct / only_indirect flags
    if only_direct and only_indirect:
        # If both are requested, return empty dict (no email can be both)
        return {}
    if only_direct:
        recipients_dict = {
            email: details
            for email, details in recipients_dict.items()
            if "direct" in details.get("source", [])
        }
    elif only_indirect:
        recipients_dict = {
            email: details
            for email, details in recipients_dict.items()
            if "direct" not in details.get("source", [])
        }

    # Sort by email
    recipients_dict = dict(sorted(recipients_dict.items(), key=lambda item: item[0]))

    logging.debug(
        "Found %d unique, non-list recipients (after optional filters) with details for the list "
        "<%s>: %s",
        len(recipients_dict),
        ml.address,
        ", ".join(recipients_dict.keys()),
    )

    return recipients_dict


def get_list_subscribers(list_id: str, exclude_lists: bool = False) -> dict[str, dict]:
    """
    Get all direct subscribers for a mailing list. The result is a mapping of subscriber email to
    their details.

    Notes:

    * A subscriber is always a direct subscription to the mailing list, and may be either a real
      person or a list. This is different from recipients, which are always real people and may be
      direct or indirect by being subscribed via nested lists.

    Args:
        list_id (str): The ID of the mailing list

        exclude_lists (bool): Whether to exclude subscribers that are mailing lists themselves
    Returns:
        dict: Mapping of subscriber email to their details. If the mailing list is not found,
            returns an empty dictionary.
    """
    subscribers_dict: dict[str, dict] = {}

    ml = get_list_by_id(list_id)
    if not ml:
        logging.warning("Mailing list with ID %s not found.", list_id)
        return subscribers_dict

    # Get direct subscribers
    direct_subs: list[Subscriber] = (
        Subscriber.query.order_by(Subscriber.email).filter_by(list_id=ml.id).all()
    )
    for sub in direct_subs:
        # Skip if subscriber is a list and include_lists is False
        if exclude_lists and is_email_a_list(sub.email):
            continue
        subscribers_dict[sub.email] = {
            "id": sub.id,
            "name": sub.name,
            "email": sub.email,
            "comment": sub.comment,
            "subscriber_type": sub.subscriber_type,
            "list_id": sub.list_id,
        }

    logging.debug(
        "Found %d direct subscribers (after optional filters) with details for the list <%s>: %s",
        len(subscribers_dict),
        ml.address,
        ", ".join(subscribers_dict.keys()),
    )

    return subscribers_dict


def get_all_subscribers() -> dict[str, dict[str, list[MailingList] | int]]:
    """
    Get all subscribers from the database, the lists they are subscribed to, and the number of
    bounces. As subscribers may be subscribed to multiple lists, the result is a mapping of email
    address, not the individual DB record.

    Returns:
        dict: A mapping of email addresses to the lists they are subscribed to and their
        bounce count
    """
    subscriber_map: dict[str, dict] = {}

    all_lists: list[MailingList] = MailingList.query.all()
    for ml in all_lists:
        subscribers: list[Subscriber] = Subscriber.query.filter_by(list_id=ml.id).all()
        for sub in subscribers:
            if sub.email not in subscriber_map:
                subscriber_map[sub.email] = {"lists": [], "bounces": 0}
            subscriber_map[sub.email]["lists"].append(ml)
            subscriber_map[sub.email]["bounces"] += sub.bounces

    # sort subscriber_map by email
    subscriber_map = dict(sorted(subscriber_map.items(), key=lambda item: item[0]))

    return subscriber_map


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


def get_all_incoming_messages(only: str = "", days: int = 0) -> list[EmailIn]:
    """
    Get all incoming messages from the database. With options to filter for bounce messages and by
    date.

    Args:
        only (str): Filter the messages
            * If "ok", return only successful
            * If "bounces", return only bounce messages
            * If "failures", return only failure messages (except bounces)
            * If empty, return all messages
        days (int): Only return messages from the last given number of days. If 0, return all

    Returns:
        list[Message]: A list of all requested messages, descending by received date
    """
    if only not in ("", "bounces", "failures", "ok"):
        logging.critical("Invalid 'only' parameter for get_all_messages: %s", only)
        raise ValueError(f"Invalid 'only' parameter: {only}")
    all_messages: list[EmailIn] = EmailIn.query.order_by(EmailIn.received_at.desc()).all()
    if only == "bounces":
        all_messages = [msg for msg in all_messages if msg.status == "bounce-msg"]
    if only == "failures":
        all_messages = [msg for msg in all_messages if msg.status not in ("ok", "bounce-msg")]
    if only == "ok":
        all_messages = [msg for msg in all_messages if msg.status == "ok"]
    if days > 0:
        cutoff_date = datetime.now() - timedelta(days=days)
        all_messages = [msg for msg in all_messages if msg.received_at >= cutoff_date]
    return all_messages


def get_all_outgoing_messages(days: int = 0) -> list[EmailOut]:
    """
    Get all outgoing messages from the database. With option to filter by date.

    Args:
        days (int): Only return messages from the last given number of days. If 0, return all
    Returns:
        list[EmailOut]: A list of all requested outgoing messages, descending by sent date
    """
    all_messages: list[EmailOut] = EmailOut.query.order_by(EmailOut.sent_at.desc()).all()
    if days > 0:
        cutoff_date = datetime.now() - timedelta(days=days)
        all_messages = [msg for msg in all_messages if msg.sent_at >= cutoff_date]
    return all_messages


def get_all_messages_id_from_raw_email(raw_email: str) -> list[str]:
    """
    Extract the (Original-)Message-IDs from a raw email string.

    Args:
        raw_email (str): The raw email content as a string
    Returns:
        list[str]: A list of Message-ID/Original-Message-ID found in the email
    """
    message_ids = []
    for line in raw_email.splitlines():
        if line.lower().startswith("message-id:") or line.lower().startswith(
            "original-message-id:"
        ):
            _, msg_id = line.split(":", 1)
            message_ids.append(msg_id.strip().strip("<>"))
    return message_ids


def get_message_id_in_db(message_ids: list[str], only: str = "") -> EmailIn | EmailOut | None:
    """
    Check if any of the given Message-IDs exist in the database as either incoming or outgoing
    messages. Can be filtered to only check incoming or outgoing messages.

    Args:
        message_ids (list[str]): A list of Message-IDs to check
        only (str): "in" to check only incoming messages, "out" for outgoing, "" for both.
            Searches in "in" first.
    Returns:
        EmailIn | EmailOut | None: The first matching message found, or None if none found
    """
    if only not in ("", "in", "out"):
        logging.critical("Invalid 'filter' parameter for get_message_id_in_db: %s", only)
        raise ValueError(f"Invalid 'filter' parameter: {only}")

    if only in ("", "in"):
        for msg_id in message_ids:
            msg_in: EmailIn | None = EmailIn.query.filter_by(message_id=msg_id).first()
            if msg_in:
                return msg_in

    if only in ("", "out"):
        for msg_id in message_ids:
            msg_out: EmailOut | None = EmailOut.query.filter_by(message_id=msg_id).first()
            if msg_out:
                return msg_out

    return None


def get_message_id_from_incoming(msg: MailMessage) -> str:
    """
    Extract the Message-ID from an incoming MailMessage object.

    Args:
        msg (MailMessage): The incoming email message
    Returns:
        str: The Message-ID of the email, without < > brackets; if not present, a new UUID is
        generated
    """
    return next(iter(msg.headers.get("message-id", ())), str(uuid.uuid4())).strip("<>")


def create_log_entry(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    level: str,
    event: str,
    message: str,
    details: dict | None = None,
    list_id: str | None = None,
) -> Logs:
    """
    Create and persist a log entry in the database.

    Args:
        level (str): Log level (e.g., 'info', 'warning', 'error')
        event (str): Event type (e.g., 'email_sent', 'bounce_received')
        message (str): Log message text
        details (dict | None): Optional JSON-serializable details dictionary
        list_id (str | None): Optional mailing list ID this log relates to

    Returns:
        Logs: The created and persisted log entry
    """

    log_entry = Logs(
        level=level.lower(),
        event=event.lower(),
        message=message,
        details=details or {},
        list_id=list_id,
        timestamp=datetime.now(timezone.utc),
    )

    db.session.add(log_entry)
    db.session.commit()

    return log_entry


def get_log_entries(exact: bool = False, days: int = 0, **kwargs) -> list[Logs]:
    """
    Retrieve log entries from the database based on provided filters.

    Args:
        exact (bool): If True, use exact matching; if False, use partial matching
        days (int): Only return log entries from the last given number of days. If 0, return all
        **kwargs: Filter criteria for querying logs (e.g., level='error', list_id=1)
    Returns:
        list[Logs]: A list of log entries matching the filter criteria
    """
    query = Logs.query

    for key, value in kwargs.items():
        column = getattr(Logs, key, None)
        if column is not None:
            if exact:
                query = query.filter(column == value)
            else:
                query = query.filter(column.ilike(f"%{value}%"))
        else:
            logging.warning("Invalid filter key for get_log_entries: %s", key)

    log_entries: list[Logs] = query.order_by(Logs.timestamp.desc()).all()
    if days > 0:
        cutoff_date = datetime.now() - timedelta(days=days)
        log_entries = [log for log in log_entries if log.timestamp >= cutoff_date]
    return log_entries


def validate_email(email: str, allow_smtputf8: bool = True) -> bool:
    """
    Validate the format of an email address.

    Args:
        email (str): The email address to validate
        allow_smtputf8 (bool): Whether to allow SMTPUTF8 addresses
    Returns:
        bool: True if the email format is valid, False otherwise
    """
    try:
        email_validator.validate_email(email, allow_smtputf8=allow_smtputf8)
        return True
    except email_validator.EmailNotValidError as e:
        logging.debug("Email validation failed for %s: %s", email, e)
        return False
