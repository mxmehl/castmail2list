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
    all_msgs_in = get_all_incoming_messages()
    msgs_in_normal_7 = get_all_incoming_messages(only="normal", days=7)
    msgs_in_bounce_7 = get_all_incoming_messages(only="bounces", days=7)
    all_msgs_out = get_all_outgoing_messages()
    msgs_out_7 = get_all_outgoing_messages(days=7)
    errors_last_7_days = get_log_entries(exact=True, days=7, level="error")
    error_last_5 = get_log_entries(exact=True, level="error")[:5]

    status: dict = {
        "lists": {
            "count": lists_count(),
        },
        "subscribers": {
            "count": len(get_all_subscribers()),
        },
        "messages_in": {
            "count": len(all_msgs_in),
            "all_last_7_days": {
                "count": len(msgs_in_normal_7) + len(msgs_in_bounce_7),
            },
            "normal_last_7_days": {
                "count": len(msgs_in_normal_7),
            },
            "bounces_last_7_days": {
                "count": len(msgs_in_bounce_7),
                "ids": [msg.message_id for msg in msgs_in_bounce_7],
            },
            "last_5_messages": {
                "ids": [msg.message_id for msg in all_msgs_in[:5]],
            },
        },
        "messages_out": {
            "count": len(all_msgs_out),
            "last_7_days": {
                "count": len(msgs_out_7),
            },
            "last_5_messages": {
                "ids": [msg.message_id for msg in all_msgs_out[:5]],
            },
        },
        "errors": {
            "last_7_days": {
                "count": len(errors_last_7_days),
            },
            "last_5": {
                "entries": [
                    {
                        "id": log.id,
                        "timestamp": log.timestamp.isoformat(),
                        "event": log.event,
                        "message": log.message,
                    }
                    for log in error_last_5
                ],
            },
        },
    }
    return status
