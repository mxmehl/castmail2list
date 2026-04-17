# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Error handlers for CastMail2List."""

import contextlib

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response


def _generic_error_handler(e: Exception) -> tuple[str | Response, int]:
    """Handle HTTP errors - JSON for API routes, HTML for web routes."""
    if isinstance(e, HTTPException):
        status = e.code or 500
        message = str(e.description)
    else:
        status = 500
        message = str(e)

    if request.path.startswith("/api/"):
        return jsonify({"status": status, "message": message}), status
    return render_template("error.html", status=status, message=message), status


def register_error_handlers(app: Flask) -> None:
    """Register application-level error handlers for common HTTP errors."""
    # Register the same handler for multiple error codes
    error_codes = range(400, 505)

    for code in error_codes:
        with contextlib.suppress(ValueError):
            app.register_error_handler(code, _generic_error_handler)
