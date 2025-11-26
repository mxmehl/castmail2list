"""Flask routes for castmail2list application"""

from flask import Blueprint, render_template
from flask_login import login_required

from ..config import AppConfig
from ..status import status_complete

general = Blueprint("general", __name__)


@general.route("/")
@login_required
def index():
    """Show dashboard"""
    status = status_complete()
    return render_template("index.html", status=status)


@general.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Manage application settings"""

    return render_template("settings.html", config=AppConfig)
