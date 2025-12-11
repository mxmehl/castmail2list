"""Error handlers for CastMail2List"""

from flask import Flask, jsonify, render_template, request


def _generic_error_handler(e):
    """Handle HTTP errors - JSON for API routes, HTML for web routes"""
    status = e.code if hasattr(e, "code") else 500
    message = str(e.description) if hasattr(e, "description") else str(e)

    if request.path.startswith("/api/"):
        return jsonify({"status": status, "message": message}), status
    return render_template("error.html", status=status, message=message), status


def register_error_handlers(app: Flask):
    """Register application-level error handlers for common HTTP errors"""
    # Register the same handler for multiple error codes
    error_codes = range(400, 505)

    for code in error_codes:
        try:
            app.register_error_handler(code, _generic_error_handler)
        except ValueError:
            # Some codes may not be valid HTTP exceptions; skip those
            pass
