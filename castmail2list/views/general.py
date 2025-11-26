"""Flask routes for castmail2list application"""

from flask import Blueprint, render_template
from flask_login import login_required

from ..config import AppConfig
from ..models import MailingList

general = Blueprint("general", __name__)


@general.route("/")
@login_required
def index():
    """Show dashboard"""
    active_lists: list[MailingList] = MailingList.query.filter_by(deleted=False).all()
    return render_template("index.html", lists=active_lists)


@general.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Manage application settings"""

    return render_template("settings.html", config=AppConfig)
