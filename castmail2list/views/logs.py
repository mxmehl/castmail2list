"""Logs blueprint for CastMail2List application"""

from flask import Blueprint, flash, render_template, request
from flask_babel import _
from flask_login import login_required

from ..models import Logs, MailingList
from ..utils import get_log_entries

logs = Blueprint("logs", __name__, url_prefix="/logs")


@logs.before_request
@login_required
def before_request() -> None:
    """Require login for all routes"""


@logs.route("/")
def index() -> str:
    """Show all logs entries with optional search filters"""
    # Get search parameters from query string
    search_field = request.args.get("fields", "").strip()
    search_text = request.args.get("text", "").strip()

    # Apply search filter if both field and text are provided
    if search_field and search_text:
        column = search_field.lower()
        # Dynamic column name requires type: ignore for kwargs
        log_entries = get_log_entries(exact=False, days=0, **{column: search_text})
    else:
        # No search query, get all entries
        log_entries = get_log_entries()

    lists: dict[int, MailingList] = {ml.id: ml for ml in MailingList.query.all()}

    return render_template(
        "logs/index.html",
        logs=log_entries,
        lists=lists,
        search_field=search_field,
        search_text=search_text,
    )


@logs.route("/<int:log_id>")
def detail(log_id: int) -> str:
    """Show detail for a specific log entry"""
    log_entry: Logs | None = Logs.query.get(log_id)
    lists: dict[int, MailingList] = {ml.id: ml for ml in MailingList.query.all()}
    if log_entry is None:
        flash(_("Log entry not found."), "error")
    return render_template("logs/detail.html", log=log_entry, lists=lists)
