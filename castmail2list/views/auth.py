# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Authentication blueprint for CastMail2List application."""

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from werkzeug.security import check_password_hash
from werkzeug.wrappers import Response

from castmail2list.extensions import limiter
from castmail2list.forms import LoginForm
from castmail2list.models import User
from castmail2list.utils import create_log_entry

auth = Blueprint("auth", __name__)


@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("2 per 10 seconds, 50 per hour", methods=["POST"])
def login() -> str | Response:
    """Handle user login requests."""
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
        next_url = request.args.get("next")
        # Only allow relative redirects to prevent open redirect attacks.
        # Reject anything that starts with "//" (protocol-relative) or contains "://".
        if next_url and next_url.startswith("/") and not next_url.startswith("//"):
            return redirect(next_url)
        return redirect(url_for("general.index"))

    return render_template("login.html", form=form)


@auth.route("/logout")
@login_required
def logout() -> Response:
    """Handle user logout requests."""
    logout_user()
    return redirect(url_for("general.index"))
