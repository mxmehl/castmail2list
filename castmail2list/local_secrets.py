"""Secret seed data for local development and testing purposes"""

# TODO: gitignore this file and provide a template instead if productive

SEED = {
    "list": {
        "name": "Test List",
        "address": "test-list@***REMOVED***",
        "imap_pass": "testtest123",
        "mode": "broadcast",
        "imap_host": "***REMOVED***",
        "imap_port": 993,
        "imap_user": "test-list@***REMOVED***",
        "from_addr": "no-reply@***REMOVED***",
        "allowed_senders": "user@***REMOVED***",
        "only_subscribers_send": False,
    },
    "subscribers": [
        {"name": "Max", "email": "tech@mehl.mx"},
        {"name": "Bouncetest", "email": "bouncetest@tribulant.com"},
    ],
}
