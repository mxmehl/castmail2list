"""Authentication blueprint for CastMail2List application"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from ..forms import LoginForm
from ..models import User
from ..utils import create_log_entry

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
def login():
    """Handle user login requests"""
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data

        user = User.query.filter_by(username=username).first()

        if not user or not check_password_hash(user.password, password):
            flash("Please check your login details and try again.", "warning")
            logging.warning(
                "Failed login attempt for user %s from IP %s", username, request.remote_addr
            )
            create_log_entry(
                level="warning",
                event="user",
                message=f"Failed login attempt for {username}",
                details={"ip": request.remote_addr},
            )
            return redirect(url_for("auth.login"))

        login_user(user, remember=True)
        logging.info("User %s logged in successfully from IP %s", username, request.remote_addr)
        create_log_entry(
            level="info",
            event="user",
            message=f"Successful login by {username}",
            details={"ip": request.remote_addr},
        )
        return redirect(request.args.get("next") or url_for("general.index"))

    return render_template("login.html", form=form)


@auth.route("/logout")
@login_required
def logout():
    """Handle user logout requests"""
    logout_user()
    return redirect(url_for("general.index"))
