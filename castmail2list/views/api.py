"""API blueprint for CastMail2List application"""

from functools import wraps

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user

from ..models import User
from ..services import (
    add_subscriber_to_list,
    delete_subscriber_from_list,
    get_lists,
    get_subscriber_by_email,
    update_subscriber_in_list,
)
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


def api_require_list(f):
    """Decorator to verify mailing list exists before proceeding.

    Checks if the mailing list with the given list_id exists and returns 404 if not.
    This is a lightweight check for API routes that don't need the full object.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if list_id := kwargs.get("list_id"):
            ml = get_list_by_id(list_id)
            if not ml:
                abort(404, description=f"Mailing list with ID '{list_id}' not found")
        return f(*args, **kwargs)

    return decorated_function


def api_require_list_and_subscriber(f):
    """Decorator to verify both mailing list and subscriber exist before proceeding.

    Checks if both the mailing list and the subscriber exist and returns 404 if either is missing.
    This is a lightweight check for API routes that don't need the full objects.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        list_id = kwargs.get("list_id")
        email = kwargs.get("email")

        if list_id:
            ml = get_list_by_id(list_id)
            if not ml:
                abort(404, description=f"Mailing list with ID '{list_id}' not found")

            if email:
                subscriber = get_subscriber_by_email(list_id=list_id, subscriber_email=email)
                if not subscriber:
                    abort(404, description=f"Subscriber '{email}' not found on list '{list_id}'")

        return f(*args, **kwargs)

    return decorated_function


@api1.route("/status", methods=["GET"])
@api_auth_required
def status_get():
    """Provide overall status information as JSON"""
    stats = status_complete()
    return jsonify(stats)


@api1.route("/lists", methods=["GET"])
@api_auth_required
def lists_get():
    """Provide a list of all mailing lists as JSON"""
    # Get query parameters
    show_deactivated = request.args.get("show_deactivated", "false").lower() == "true"

    lists = get_lists(show_deactivated=show_deactivated)
    return jsonify(lists)


@api1.route("/lists/<list_id>/subscribers", methods=["GET"])
@api_auth_required
@api_require_list
def list_subscribers_get(list_id: str):
    """Provide a list of direct subscribers for a specific mailing list as JSON"""
    # Get query parameters
    exclude_lists = request.args.get("exclude_lists", "false").lower() == "true"

    subscribers = get_list_subscribers(list_id=list_id, exclude_lists=exclude_lists)

    return jsonify(subscribers)


@api1.route("/lists/<list_id>/subscribers", methods=["POST"])
@api_auth_required
@api_require_list
def list_subscribers_post(list_id: str):
    """Add a new subscriber to a specific mailing list via API"""
    # Parse query parameters
    data: dict = request.get_json()
    if not data or "email" not in data:
        abort(400, description="Missing 'email' in request body")

    email = data.get("email", "")
    name = data.get("name", "")
    comment = data.get("comment", "")

    # Add subscriber using service layer
    error_message = add_subscriber_to_list(list_id=list_id, email=email, name=name, comment=comment)

    # Return errors or success message
    if error_message:
        abort(400, description=error_message)
    return jsonify({"message": f"Subscriber {email} added successfully to list {list_id}"}), 201


@api1.route("/lists/<list_id>/subscribers/<email>", methods=["DELETE", "PATCH"])
@api_auth_required
@api_require_list_and_subscriber
def list_subscribers_delete_patch(list_id: str, email: str):
    """Delete or update an existing subscriber of a specific mailing list via API"""
    if request.method == "DELETE":
        # Delete subscriber using service layer
        error_message = delete_subscriber_from_list(list_id=list_id, subscriber_email=email)

        # Return errors or success message
        if error_message:
            abort(400, description=error_message)
        return (
            jsonify({"message": f"Subscriber {email} deleted successfully from list {list_id}"}),
            200,
        )

    if request.method == "PATCH":
        # Get subscriber object (we need the ID for update)
        subscriber = get_subscriber_by_email(list_id=list_id, subscriber_email=email)
        if not subscriber:
            abort(404, description=f"Subscriber {email} not found on list '{list_id}'")

        # Parse query parameters
        data: dict = request.get_json()
        email_new = data.get("email", "")
        name_new = data.get("name", "")
        comment_new = data.get("comment", "")

        # Update subscriber using service layer
        error_message = update_subscriber_in_list(
            list_id=list_id,
            subscriber_id=subscriber.id,
            email=email_new,
            name=name_new,
            comment=comment_new,
        )

        # Return errors or success message
        if error_message:
            abort(400, description=error_message)
        return (
            jsonify({"message": f"Subscriber {email} updated successfully on list {list_id}"}),
            200,
        )

    return abort(405)


@api1.route("/lists/<list_id>/recipients", methods=["GET"])
@api_auth_required
@api_require_list
def list_recipients_get(list_id):
    """Provide a list of recipients for a specific mailing list as JSON"""
    # Get query parameters
    only_direct = request.args.get("only_direct", "false").lower() == "true"
    only_indirect = request.args.get("only_indirect", "false").lower() == "true"

    if only_direct and only_indirect:
        abort(400, description="Cannot set both only_direct and only_indirect to true")
    if only_direct:
        recipients = get_list_recipients_recursive(list_id=list_id, only_direct=True)
    elif only_indirect:
        recipients = get_list_recipients_recursive(list_id=list_id, only_indirect=True)
    else:
        recipients = get_list_recipients_recursive(list_id=list_id)

    return jsonify(recipients)
