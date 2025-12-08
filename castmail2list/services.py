"""Service layer for business logic in CastMail2List application"""

import logging
from typing import cast

from flask_babel import _

from .models import MailingList, Subscriber, db
from .utils import get_list_subscribers, is_email_a_list

# -----------------------------------------------------------------
# Subscriber Services
# -----------------------------------------------------------------


def get_subscribers_with_details(list_id: int) -> tuple[MailingList, dict] | tuple[None, None]:
    """
    Get all subscribers for a mailing list with direct and indirect breakdown.

    Args:
        list_id (int): The ID of the mailing list

    Returns:
        tuple: A tuple of (mailing_list, subscribers_data) where subscribers_data contains:
            - 'direct': list of direct Subscriber objects
            - 'indirect': dict mapping MailingList to their subscribers
            Returns (None, None) if list not found.
    """
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if not mailing_list:
        return None, None

    subscribers_direct = cast(list[Subscriber], mailing_list.subscribers)
    subscriber_lists = [
        is_email_a_list(s.email) for s in subscribers_direct if s.subscriber_type == "list"
    ]
    subscribers_indirect = {}
    for sub_list in subscriber_lists:
        if sub_list:
            subscribers_indirect[sub_list] = get_list_subscribers(sub_list)

    subscribers_data = {
        "direct": subscribers_direct,
        "indirect": subscribers_indirect,
    }

    return mailing_list, subscribers_data


def add_subscriber_to_list(
    list_id: int, name: str, email: str, comment: str | None = None
) -> tuple[str | None, str]:
    """
    Add a new subscriber to a mailing list.

    Following steps are performed:
        * Verify mailing list exists
        * Normalize email to lowercase
        * Check if subscriber already exists in the list
        * Check if subscriber email is an existing mailing list
        * Create and save new subscriber

    Args:
        list_id (int): The ID of the mailing list
        name (str): Name of the subscriber
        email (str): Email address of the subscriber
        comment (str | None): Optional comment about the subscriber

    Returns:
        tuple: A tuple of (email, error_message).
            - On success: (added subscriber's email, "")
            - On failure: (None, error message string)
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if not mailing_list:
        return None, f"Mailing list with ID {list_id} not found"

    # Normalize email
    email = email.strip().lower()

    # Check if subscriber already exists
    existing_subscriber = Subscriber.query.filter_by(list_id=list_id, email=email).first()
    if existing_subscriber:
        return None, f'Email "{email}" is already subscribed to this list'

    # Check if subscriber is an existing list. If so, set type and re-use name
    if existing_list := is_email_a_list(email):
        name = existing_list.name
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
        return new_subscriber.email, ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error('Failed to add subscriber "%s" to list %s: %s', email, list_id, e)
        return None, _("Database error: ") + str(e)


def update_subscriber_in_list(
    list_id: int, subscriber_id: int, name: str, email: str, comment: str | None = None
) -> tuple[str | None, str]:
    """
    Update an existing subscriber in a mailing list.

    Args:
        list_id (int): The ID of the mailing list
        subscriber_id (int): The ID of the subscriber to update
        name (str): New name for the subscriber
        email (str): New email address for the subscriber
        comment (str | None): New comment for the subscriber

    Returns:
        tuple: A tuple of (email, error_message).
            - On success: (updated subscriber's email, "")
            - On failure: (None, error message string)
    """
    # TODO: Deal with incomplete data, don't overwrite existing fields with None
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if mailing_list is None:
        return None, f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.get(subscriber_id)
    if subscriber is None:
        return None, f"Subscriber with ID {subscriber_id} not found"
    if subscriber.list_id != list_id:
        return None, f"Subscriber {subscriber_id} does not belong to list {list_id}"

    # Normalize email
    email = email.strip().lower()

    # Check if new email conflicts with existing subscriber (but not itself)
    existing_subscriber: Subscriber | None = Subscriber.query.filter_by(
        list_id=list_id, email=email
    ).first()
    if existing_subscriber and existing_subscriber.id != subscriber_id:
        return None, f'Email "{email}" is already subscribed to this list'

    # Check if subscriber is an existing list. If so, set type and re-use name
    if existing_list := is_email_a_list(email):
        name = existing_list.name
        subscriber_type = "list"
    else:
        subscriber_type = "normal"

    # Update subscriber fields
    subscriber.name = name
    subscriber.email = email
    subscriber.comment = comment  # type: ignore[assignment]
    subscriber.subscriber_type = subscriber_type

    try:
        db.session.commit()
        logging.info('Subscriber "%s" updated in mailing list %s', email, mailing_list.address)
        return subscriber.email, ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error("Failed to update subscriber %s in list %s: %s", subscriber_id, list_id, e)
        return None, f"Database error: {str(e)}"


def delete_subscriber_from_list(list_id: int, subscriber_email: str) -> tuple[str | None, str]:
    """
    Delete a subscriber from a mailing list.

    Args:
        list_id (int): The ID of the mailing list
        subscriber_email (str): The email of the subscriber to delete

    Returns:
        tuple: A tuple of (email, error_message).
            - On success: (deleted subscriber's email, "")
            - On failure: (None, error message string)
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if mailing_list is None:
        return None, f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.filter_by(
        list_id=list_id, email=subscriber_email
    ).first()
    if not subscriber:
        return None, f"Subscriber with email {subscriber_email} not found"
    if subscriber.list_id != list_id:
        return None, f"Subscriber {subscriber_email} does not belong to list {list_id}"

    try:
        db.session.delete(subscriber)
        db.session.commit()
        logging.info(
            'Subscriber "%s" removed from mailing list %s', subscriber_email, mailing_list.address
        )
        return subscriber_email, ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        db.session.rollback()
        logging.error(
            "Failed to delete subscriber %s from list %s: %s", subscriber_email, list_id, e
        )
        return None, f"Database error: {str(e)}"


def get_subscriber_by_id(list_id: int, subscriber_id: int) -> tuple[Subscriber | None, str | None]:
    """
    Get a single subscriber by ID.

    Args:
        list_id (int): The ID of the mailing list
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


def get_subscriber_by_email(list_id: int, subscriber_email: str) -> tuple[Subscriber | None, str]:
    """
    Get a single subscriber by list ID and subscriber email.

    Args:
        list_id (int): The ID of the mailing list
        subscriber_email (str): The email of the subscriber

    Returns:
        tuple: A tuple of (subscriber, error_message).
            - On success: (Subscriber object, "")
            - On failure: (None, error message string)
    """
    # Verify list exists
    mailing_list: MailingList | None = MailingList.query.filter_by(id=list_id).first()
    if not mailing_list:
        return None, f"Mailing list with ID {list_id} not found"

    # Verify subscriber exists and belongs to this list
    subscriber: Subscriber | None = Subscriber.query.filter_by(
        list_id=list_id, email=subscriber_email
    ).first()
    if not subscriber:
        return None, f"Subscriber with email {subscriber_email} not found on list {list_id}"
    if subscriber.list_id != list_id:
        return None, f"Subscriber {subscriber_email} does not belong to list {list_id}"

    return subscriber, ""
