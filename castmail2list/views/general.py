"""Flask routes for castmail2list application"""

from secrets import token_urlsafe

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import current_user, login_required
from werkzeug.security import generate_password_hash

from ..config import AppConfig
from ..forms import UserDetailsForm
from ..models import db
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


@general.route("/account", methods=["GET", "POST"])
def account():
    """Show account settings page"""
    if current_user is None:
        flash(_("You must be logged in to access account settings."), "error")
        return redirect(url_for("general.index"))

    form = UserDetailsForm(obj=current_user)

    if form.validate_on_submit():
        # Regenerate API key if requested
        if form.api_key_generate.data:
            new_api_key = token_urlsafe(32)
            current_user.api_key = new_api_key
            db.session.commit()
            db.session.refresh(current_user)
            flash(_("A new API key has been generated."), "success")
            return redirect(url_for("general.account"))

        # Update password if provided
        if form.password.data:
            if form.password.data != form.password_retype.data:
                flash(_("The passwords do not match."), "error")
                return render_template("account.html", form=form, current_user=current_user)
            current_user.password = generate_password_hash(form.password.data)
            flash(_("Your password has been updated."), "success")

        db.session.commit()
        return render_template("account.html", form=form, current_user=current_user, success=True)

    return render_template("account.html", form=form, current_user=current_user)


@general.route("/settings", methods=["GET", "POST"])
def settings():
    """Manage application settings"""

    return render_template("settings.html", config=AppConfig)
