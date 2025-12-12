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
    """Get application status
    Retrieve overall status information including counts of lists, subscribers, and messages.
    ---
    tags:
      - System
    security:
      - Bearer: []
    responses:
      200:
        description: Status information retrieved successfully
        schema:
          type: object
          properties:
            lists:
              type: object
              properties:
                active:
                  type: integer
                  example: 5
                total:
                  type: integer
                  example: 7
            subscribers:
              type: integer
              example: 150
            messages:
              type: object
              properties:
                incoming:
                  type: integer
                  example: 234
                outgoing:
                  type: integer
                  example: 1170
      401:
        description: Unauthorized - invalid or missing API key
    """
    stats = status_complete()
    return jsonify(stats)


@api1.route("/lists", methods=["GET"])
@api_auth_required
def lists_get():
    """Get all mailing lists
    Retrieve a list of all mailing lists. By default, only active lists are returned.
    ---
    tags:
      - Lists
    parameters:
      - name: show_deactivated
        in: query
        type: boolean
        default: false
        description: Include deactivated/deleted lists in the response
        example: false
    security:
      - Bearer: []
    responses:
      200:
        description: Lists retrieved successfully
        schema:
          type: object
          additionalProperties:
            type: object
            properties:
              id:
                type: string
                example: "announcements"
              address:
                type: string
                example: "announcements@example.com"
              display:
                type: string
                example: "Company Announcements"
              mode:
                type: string
                enum: [broadcast, group]
                example: "broadcast"
              deleted:
                type: boolean
                example: false
      401:
        description: Unauthorized - invalid or missing API key
    """
    # Get query parameters
    show_deactivated = request.args.get("show_deactivated", "false").lower() == "true"

    lists = get_lists(show_deactivated=show_deactivated)
    return jsonify(lists)


@api1.route("/lists/<list_id>/subscribers", methods=["GET"])
@api_auth_required
@api_require_list
def list_subscribers_get(list_id: str):
    """Get all subscribers of a mailing list
    Retrieve all direct subscribers for a specific mailing list. Note that subscribers can be
    either regular email addresses or other mailing lists.
    ---
    tags:
      - Subscribers
    parameters:
      - name: list_id
        in: path
        type: string
        required: true
        description: The ID of the mailing list
        example: "announcements"
      - name: exclude_lists
        in: query
        type: boolean
        default: false
        description: Exclude subscribers that are themselves mailing lists
        example: false
    security:
      - Bearer: []
    responses:
      200:
        description: Subscribers retrieved successfully
        schema:
          type: object
          additionalProperties:
            type: object
            properties:
              email:
                type: string
                example: "user@example.com"
              name:
                type: string
                example: "John Doe"
              comment:
                type: string
                example: "Subscribed at conference"
              subscriber_type:
                type: string
                enum: [normal, list]
                example: "normal"
      401:
        description: Unauthorized - invalid or missing API key
      404:
        description: Mailing list not found
    """
    # Get query parameters
    exclude_lists = request.args.get("exclude_lists", "false").lower() == "true"

    subscribers = get_list_subscribers(list_id=list_id, exclude_lists=exclude_lists)

    return jsonify(subscribers)


@api1.route("/lists/<list_id>/subscribers", methods=["PUT"])
@api_auth_required
@api_require_list
def list_subscribers_put(list_id: str):
    """Add a new subscriber to a mailing list
    Add a new subscriber to a specific mailing list. The subscriber can be a regular email address
    or another mailing list.
    ---
    tags:
      - Subscribers
    parameters:
      - name: list_id
        in: path
        type: string
        required: true
        description: The ID of the mailing list
        example: "announcements"
      - name: body
        in: body
        required: true
        description: Subscriber details
        schema:
          type: object
          required:
            - email
          properties:
            email:
              type: string
              format: email
              description: Email address of the subscriber
              example: "user@example.com"
            name:
              type: string
              description: Display name of the subscriber (optional)
              example: "John Doe"
            comment:
              type: string
              description: Optional comment about the subscriber
              example: "Subscribed at conference 2025"
    security:
      - Bearer: []
    responses:
      201:
        description: Subscriber added successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Subscriber user@example.com added successfully to list announcements"
      400:
        description: Bad request - missing email or subscriber already exists
        schema:
          type: object
          properties:
            status:
              type: integer
              example: 400
            message:
              type: string
              example: "Missing 'email' in request body"
      401:
        description: Unauthorized - invalid or missing API key
        schema:
          type: object
          properties:
            status:
              type: integer
              example: 401
            message:
              type: string
              example: "Authentication required"
      404:
        description: Mailing list not found
        schema:
          type: object
          properties:
            status:
              type: integer
              example: 404
            message:
              type: string
              example: "Mailing list with ID 'announcements' not found"
    """
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
    """Delete or update a subscriber
    Delete a subscriber from a mailing list or update their details (email, name, comment).
    ---
    tags:
      - Subscribers
    parameters:
      - name: list_id
        in: path
        type: string
        required: true
        description: The ID of the mailing list
        example: "announcements"
      - name: email
        in: path
        type: string
        required: true
        description: Email address of the subscriber
        example: "user@example.com"
      - name: body
        in: body
        required: false
        description: Updated subscriber details (only for PATCH)
        schema:
          type: object
          properties:
            email:
              type: string
              format: email
              description: New email address (optional)
              example: "newemail@example.com"
            name:
              type: string
              description: New display name (optional)
              example: "Jane Doe"
            comment:
              type: string
              description: New comment (optional)
              example: "Updated role"
    security:
      - Bearer: []
    responses:
      200:
        description: Subscriber deleted or updated successfully
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Subscriber user@example.com deleted successfully from list announcements"
      400:
        description: Bad request - validation error or email conflict
        schema:
          type: object
          properties:
            status:
              type: integer
              example: 400
            message:
              type: string
              example: 'Email "newemail@example.com" is already subscribed to this list'
      401:
        description: Unauthorized - invalid or missing API key
      404:
        description: Mailing list or subscriber not found
      405:
        description: Method not allowed
    """
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
    """Get all recipients of a mailing list
    Retrieve all real recipients (no lists) for a mailing list, including indirect recipients
    from nested lists. Recipients are actual email addresses that will receive messages.
    ---
    tags:
      - Recipients
    parameters:
      - name: list_id
        in: path
        type: string
        required: true
        description: The ID of the mailing list
        example: "announcements"
      - name: only_direct
        in: query
        type: boolean
        default: false
        description: Return only direct recipients (exclude those from nested lists)
        example: false
      - name: only_indirect
        in: query
        type: boolean
        default: false
        description: Return only indirect recipients (from nested lists)
        example: false
    security:
      - Bearer: []
    responses:
      200:
        description: Recipients retrieved successfully
        schema:
          type: object
          additionalProperties:
            type: object
            properties:
              email:
                type: string
                example: "recipient@example.com"
              name:
                type: string
                example: "Recipient Name"
              source:
                type: array
                items:
                  type: string
                description: List IDs or "direct" if directly subscribed
                example: ["direct", "staff-list"]
      400:
        description: Bad request - conflicting query parameters
        schema:
          type: object
          properties:
            status:
              type: integer
              example: 400
            message:
              type: string
              example: "Cannot set both only_direct and only_indirect to true"
      401:
        description: Unauthorized - invalid or missing API key
      404:
        description: Mailing list not found
    """
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
