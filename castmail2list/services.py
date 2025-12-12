"""Service layer for shared logic for both the API and web interface"""

import logging

from flask_babel import _

from .models import MailingList, Subscriber, db
from .utils import is_email_a_list, validate_email

# -----------------------------------------------------------------
# Lists Services
# -----------------------------------------------------------------


def get_lists(show_deactivated: bool = False) -> dict[str, dict]:
    """
    Retrieve all mailing lists.

    Returns:

    """
    lists: list[MailingList] = MailingList.query.order_by(MailingList.id).all()
    if not show_deactivated:
        lists = [ml for ml in lists if not ml.deleted]
    return {
        ml.id: {
            "id": ml.id,
            "address": ml.address,
            "display": ml.display,
            "mode": ml.mode,
            "deleted": ml.deleted,
        }
        for ml in lists
    }


# -----------------------------------------------------------------
# Subscriber Services
# -----------------------------------------------------------------


def add_subscriber_to_list(list_id: str, email: str, name: str = "", comment: str = "") -> str:
    """
    Add a new subscriber to a mailing list.

    Following steps are performed:
        * Verify mailing list exists
        * Normalize email to lowercase
        * Check if subscriber already exists in the list
        * Check if subscriber email is an existing mailing list
        * Create and save new subscriber

    Args:
        list_id (str): The ID of the mailing list
        email (str): Email address of the subscriber
        name (str): Name of the subscriber (optional)
        comment (str): Optional comment about the subscriber (optional)

    Returns:
        str: An error message if any issues occur, otherwise empty string on success
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if not mailing_list:
        return f"Mailing list with ID {list_id} not found"

    # Normalize email
    email = email.strip().lower()

    # Validate email
    if not validate_email(email):
        return f"Invalid email address: {email}"

    # Check if subscriber already exists
    existing_subscriber = Subscriber.query.filter_by(list_id=list_id, email=email).first()
    if existing_subscriber:
        return f"Email {email} is already subscribed to list {list_id}"

    # Check if subscriber is an existing list. If so, set type and re-use name
    if existing_list := is_email_a_list(email):
        name = existing_list.display
        subscriber_type = "list"
    else:
        subscriber_type = "normal"

    # Create new subscriber
    new_subscriber = Subscriber(
        list_id=list_id,
        name=name,
        email=email,
        comment=comment,
        subscriber_type=subscriber_type,
    )

    try:
        db.session.add(new_subscriber)
        db.session.commit()
        logging.info('Subscriber "%s" added to mailing list %s', email, mailing_list.address)
        return ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error('Failed to add subscriber "%s" to list %s: %s', email, list_id, e)
        return _("Database error: ") + str(e)


def update_subscriber_in_list(list_id: str, subscriber_id: int, **kwargs: str) -> str:
    # pylint: disable=too-many-return-statements
    """
    Update an existing subscriber in a mailing list.

    Args:
        list_id (str): The ID of the mailing list
        subscriber_id (int): The ID of the subscriber to update
        **kwargs: Fields to update (name, email, comment). If not provided, existing values are kept

    Returns:
        str: An error message if any issues occur, otherwise empty string on success
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if mailing_list is None:
        return f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.get(subscriber_id)
    if subscriber is None:
        return f"Subscriber with ID {subscriber_id} not found"
    if subscriber.list_id != list_id:
        return f"Subscriber {subscriber_id} does not belong to list {list_id}"

    # Get updated fields or keep existing
    name_new = kwargs.get("name")
    email_new = kwargs.get("email")
    comment_new = kwargs.get("comment")
    subscriber_type_new = None  # use existing type unless email changes

    # Special case: update of email, check for conflicts
    if email_new and email_new != subscriber.email:
        email_new = email_new.strip().lower()
        # Validate new email
        if not validate_email(email_new):
            return f"Invalid email address: {email_new}"

        # Check if new email conflicts with existing subscriber on the same list (but not itself)
        existing_subscriber: Subscriber | None = Subscriber.query.filter_by(
            list_id=list_id, email=email_new
        ).first()
        if existing_subscriber and existing_subscriber.id != subscriber_id:
            return f'Email "{email_new}" is already subscribed to this list'

        # Check if subscriber's new email is an existing list. If so, set type and re-use name
        if existing_list := is_email_a_list(email_new):
            name_new = existing_list.display
            subscriber_type_new = "list"
        else:
            subscriber_type_new = "normal"

    # Update subscriber fields
    for field, value in {
        "name": name_new,
        "email": email_new,
        "comment": comment_new,
        "subscriber_type": subscriber_type_new,
    }.items():
        if field == "email" and not value:
            # Skip empty email updates
            continue
        if value is not None:
            logging.debug("Updating field %s of subscriber %s to '%s'", field, subscriber_id, value)
            setattr(subscriber, field, value)

    try:
        db.session.commit()
        logging.info(
            'Subscriber "%s" updated in mailing list %s', subscriber.email, mailing_list.address
        )
        return ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error("Failed to update subscriber %s in list %s: %s", subscriber_id, list_id, e)
        return _("Database error: ") + str(e)


def delete_subscriber_from_list(list_id: str, subscriber_email: str) -> str:
    """
    Delete a subscriber from a mailing list.

    Args:
        list_id (str): The ID of the mailing list
        subscriber_email (str): The email of the subscriber to delete

    Returns:
        str: An error message if any issues occur, otherwise empty string on success
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if mailing_list is None:
        return f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.filter_by(
        list_id=list_id, email=subscriber_email
    ).first()
    if not subscriber:
        return f"Subscriber with email {subscriber_email} not found on list {list_id}"
    if subscriber.list_id != list_id:
        return f"Subscriber {subscriber_email} does not belong to list {list_id}"

    try:
        db.session.delete(subscriber)
        db.session.commit()
        logging.info(
            'Subscriber "%s" removed from mailing list %s', subscriber_email, mailing_list.address
        )
        return ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error(
            "Failed to delete subscriber %s from list %s: %s", subscriber_email, list_id, e
        )
        return _("Database error: ") + str(e)


def get_subscriber_by_id(list_id: str, subscriber_id: int) -> tuple[Subscriber | None, str | None]:
    """
    Get a single subscriber by ID.

    Args:
        list_id (str): The ID of the mailing list
        subscriber_id (int): The ID of the subscriber

    Returns:
        tuple[Subscriber | None, str | None]: A tuple of (subscriber, error_message).
            - On success: (Subscriber object, None)
            - On failure: (None, error message string)
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if not mailing_list:
        return None, f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.get(subscriber_id)
    if not subscriber:
        return None, f"Subscriber with ID {subscriber_id} not found"
    if subscriber.list_id != list_id:
        return None, f"Subscriber {subscriber_id} does not belong to list {list_id}"

    return subscriber, None


def get_subscriber_by_email(list_id: str, subscriber_email: str) -> Subscriber | None:
    """
    Get a single subscriber by list ID and subscriber email.

    Args:
        list_id (str): The ID of the mailing list
        subscriber_email (str): The email of the subscriber

    Returns:
        Subscriber | None: Subscriber object if found, otherwise None
    """
    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.filter_by(
        list_id=list_id, email=subscriber_email
    ).first()
    if not subscriber:
        return None
    if subscriber.list_id != list_id:
        return None

    return subscriber
