"""Utility functions for Castmail2List application"""

import logging

from flask import flash


def flash_form_errors(form):
    """Flash all errors from a Flask-WTF form"""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"Error in {getattr(form, field).label.text}: {error}", "error")


def normalize_email_list(input_str: str) -> str:
    """Normalize a string of emails into a comma-separated list"""
    # Accepts either comma or newline separated, returns comma-separated
    if not input_str:
        return ""
    # Replace newlines with commas, then split
    emails = [email.strip() for email in input_str.replace("\n", ",").split(",") if email.strip()]
    return ", ".join(emails)


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
    sanitized_recipient = recipient.replace("@", "=").replace("+", "-")
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
        recipient = sanitized_recipient.replace("=", "@").replace("-", "+")
        return recipient
    except ValueError:
        logging.warning("Failed to parse bounce address: %s", bounce_address)
        return None
