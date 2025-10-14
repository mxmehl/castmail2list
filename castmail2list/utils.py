"""Utility functions for Castmail2List application"""

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
    emails = [
        email.strip()
        for email in input_str.replace("\n", ",").split(",")
        if email.strip()
    ]
    return ", ".join(emails)
