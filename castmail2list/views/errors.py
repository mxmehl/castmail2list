"""Error handlers for CastMail2List"""

from flask import Flask, jsonify, render_template, request


def _generic_error_response(status: int, exception):
    """Generate a generic error response in JSON format"""
    message = str(exception.description)
    if request.path.startswith("/api/"):
        return jsonify({"status": status, "message": message}), status
    return render_template("error.html", status=status, message=message), status


def register_error_handlers(app: Flask):
    """Register application-level error handlers"""

    @app.errorhandler(400)
    def handle_400(e):
        """Handle 400 errors - JSON for API, HTML for web"""
        status = 400
        return _generic_error_response(status, e)

    @app.errorhandler(401)
    def handle_401(e):
        """Handle 401 errors - JSON for API, HTML for web"""
        status = 401
        return _generic_error_response(status, e)

    @app.errorhandler(404)
    def handle_404(e):
        """Handle 404 errors - JSON for API, HTML for web"""
        status = 404
        return _generic_error_response(status, e)
