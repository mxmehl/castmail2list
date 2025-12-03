"""Flask routes for castmail2list application"""

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from ..config import AppConfig
from ..status import status_complete

general = Blueprint("general", __name__)


@general.before_request
@login_required
def before_request() -> None:
    """Require login for all routes"""


@general.route("/")
def index():
    """Show dashboard"""
    stats = status_complete()
    return render_template("index.html", stats=stats)

@general.route("/status")
def status():
    """Provide overall status information as JSON"""
    stats = status_complete()
    return jsonify(stats)


@general.route("/settings", methods=["GET", "POST"])
def settings():
    """Manage application settings"""

    return render_template("settings.html", config=AppConfig)
