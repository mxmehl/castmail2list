"""Functions and operations to collect reports about different parts of Castmail2List"""

from .models import EmailIn, MailingList
from .utils import get_all_messages, get_all_subscribers


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
    all_msg = get_all_messages()
    normal_msg_7 = get_all_messages(only="normal", days=7)
    bounce_msg_7 = get_all_messages(only="bounces", days=7)
    status: dict = {
        "lists": {
            "count": lists_count(),
        },
        "subscribers": {
            "count": len(get_all_subscribers()),
        },
        "messages": {
            "count": len(all_msg),
            "all_last_7_days": {
                "count": len(normal_msg_7) + len(bounce_msg_7),
            },
            "normal_last_7_days": {
                "count": len(normal_msg_7),
            },
            "bounces_last_7_days": {
                "count": len(bounce_msg_7),
                "ids": [msg.message_id for msg in bounce_msg_7],
            },
            "last_5_messages": {
                "ids": [msg.message_id for msg in all_msg[:5]],
            },
        },
    }
    return status
