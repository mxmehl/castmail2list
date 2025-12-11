"""API blueprint for CastMail2List application"""

from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

from ..models import User
from ..status import status_complete

api1 = Blueprint("api1", __name__, url_prefix="/api/v1")


def api_auth_required(f):
    """Decorator to require either Flask-Login session or API key authentication"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is already authenticated via Flask-Login session
        if current_user.is_authenticated:
            return f(*args, **kwargs)

        # Check for API key in Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header[7:]  # Remove "Bearer " prefix
            if api_key:  # Ensure api_key is not empty/None
                user = User.query.filter_by(api_key=api_key).first()
                if user:  # API key is valid, proceed with request
                    return f(*args, **kwargs)

        # No valid authentication found
        abort(401, description="Authentication required")

    return decorated_function


@api1.route("/status")
@api_auth_required
def status():
    """Provide overall status information as JSON"""
    stats = status_complete()
    return jsonify(stats)
