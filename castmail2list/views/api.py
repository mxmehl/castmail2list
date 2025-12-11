"""API blueprint for CastMail2List application"""

from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

from ..models import User
from ..services import get_lists
from ..status import status_complete
from ..utils import get_list_by_id, get_list_recipients_recursive, get_list_subscribers

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


@api1.route("/status", methods=["GET"])
@api_auth_required
def status():
    """Provide overall status information as JSON"""
    stats = status_complete()
    return jsonify(stats)


@api1.route("/lists", methods=["GET"])
@api_auth_required
def lists_all():
    """Provide a list of all mailing lists as JSON"""
    # Get query parameters
    show_deactivated = request.args.get("show_deactivated", "false").lower() == "true"

    lists = get_lists(show_deactivated=show_deactivated)
    return jsonify(lists)


@api1.route("/lists/<list_id>/subscribers", methods=["GET"])
@api_auth_required
def list_subscribers(list_id):
    """Provide a list of direct subscribers for a specific mailing list as JSON"""
    # Get query parameters
    exclude_lists = request.args.get("exclude_lists", "false").lower() == "true"

    # Sanity check
    ml = get_list_by_id(list_id)
    if not ml:
        abort(404, description=f"Mailing list with ID '{list_id}' not found")

    subscribers = get_list_subscribers(list_id=list_id, exclude_lists=exclude_lists)

    return jsonify(subscribers)


@api1.route("/lists/<list_id>/recipients", methods=["GET"])
@api_auth_required
def list_recipients(list_id):
    """Provide a list of recipients for a specific mailing list as JSON"""
    # Get query parameters
    only_direct = request.args.get("only_direct", "false").lower() == "true"
    only_indirect = request.args.get("only_indirect", "false").lower() == "true"

    # Sanity check
    ml = get_list_by_id(list_id)
    if not ml:
        abort(404, description=f"Mailing list with ID '{list_id}' not found")

    if only_direct and only_indirect:
        abort(400, description="Cannot set both only_direct and only_indirect to true")
    if only_direct:
        recipients = get_list_recipients_recursive(list_id=list_id, only_direct=True)
    elif only_indirect:
        recipients = get_list_recipients_recursive(list_id=list_id, only_indirect=True)
    else:
        recipients = get_list_recipients_recursive(list_id=list_id)

    return jsonify(recipients)
