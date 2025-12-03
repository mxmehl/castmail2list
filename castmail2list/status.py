"""Functions and operations to collect reports about different parts of Castmail2List"""

from .models import MailingList
from .utils import (
    get_all_incoming_messages,
    get_all_outgoing_messages,
    get_all_subscribers,
    get_log_entries,
)


def lists_count() -> dict:
    """Counts mailing lists by their status.

    Returns:
        dict: A dictionary containing status information about mailing lists.
    """
    list_stats: dict[str, int] = {
        "total": 0,
        "active": 0,
        "deactivated": 0,
    }
    all_lists: list[MailingList] = MailingList.query.all()
    list_stats["total"] = len(all_lists)
    for mailing_list in all_lists:
        if getattr(mailing_list, "deleted", True):
            list_stats["deactivated"] += 1
        else:
            list_stats["active"] += 1

    return list_stats


def status_complete() -> dict:
    """Collects overall status information about Castmail2List.

    Returns:
        dict: A dictionary containing overall status information.
    """
    email_in_all = get_all_incoming_messages(only="normal")
    email_in_days_7 = get_all_incoming_messages(only="normal", days=7)
    bounce_days_7 = get_all_incoming_messages(only="bounces", days=7)
    bounce_last_5 = get_all_incoming_messages(only="bounces")[:5]
    email_out_all = get_all_outgoing_messages()
    email_out_days_7 = get_all_outgoing_messages(days=7)
    errors_days_7 = get_log_entries(exact=True, days=7, level="error")
    errors_last_5 = get_log_entries(exact=True, level="error")[:5]
    warnings_days_7 = get_log_entries(exact=True, days=7, level="warning")
    warnings_last_5 = get_log_entries(exact=True, level="warning")[:5]

    status: dict = {
        "lists": {
            "count": lists_count(),
        },
        "subscribers": {
            "count": len(get_all_subscribers()),
        },
        "email_in": {
            "count": len(email_in_all),
            "days_7": [{"mid": msg.message_id, "subject": msg.subject} for msg in email_in_days_7],
            "last_5": [{"mid": msg.message_id, "subject": msg.subject} for msg in email_in_all[:5]],
        },
        "bounces": {
            "days_7": [{"mid": msg.message_id, "subject": msg.subject} for msg in bounce_days_7],
            "last_5": [{"mid": msg.message_id, "subject": msg.subject} for msg in bounce_last_5],
        },
        "email_out": {
            "count": len(email_out_all),
            "days_7": [{"mid": msg.message_id, "subject": msg.subject} for msg in email_out_days_7],
            "last_5": [
                {"mid": msg.message_id, "subject": msg.subject} for msg in email_out_all[:5]
            ],
        },
        "errors": {
            "days_7": [log.id for log in errors_days_7],
            "last_5": [
                {
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "event": log.event,
                    "message": log.message,
                }
                for log in errors_last_5
            ],
        },
        "warnings": {
            "days_7": [log.id for log in warnings_days_7],
            "last_5": [
                {
                    "id": log.id,
                    "timestamp": log.timestamp,
                    "event": log.event,
                    "message": log.message,
                }
                for log in warnings_last_5
            ],
        },
    }
    return status
