"""Secret seed data for local development and testing purposes"""

# TODO: gitignore this file and provide a template instead if productive

SEED = {
    "lists": [
        {
            "name": "Alle Eltern",
            "address": "list-eltern@***REMOVED***",
            "mode": "broadcast",
            "from_addr": "test-info@***REMOVED***",
            "allowed_senders": "test-info@***REMOVED***",
            "only_subscribers_send": False,
            "imap_pass": "testtest123",
            "imap_host": "***REMOVED***",
            "imap_port": 993,
            "imap_user": "list-eltern@***REMOVED***",
            "subscribers": [
                {
                    "name": "Eltern Mondgruppe",
                    "email": "list-eltern-mondgruppe@***REMOVED***",
                },
                {
                    "name": "Eltern Sonnengruppe",
                    "email": "list-eltern-sonnengruppe@***REMOVED***",
                },
                {
                    "name": "Elternbeirat",
                    "email": "list-elternbeirat@***REMOVED***",
                },
            ],
        },
        {
            "name": "Eltern Sonnengruppe",
            "address": "list-eltern-sonnengruppe@***REMOVED***",
            "mode": "broadcast",
            "from_addr": "test-info@***REMOVED***",
            "allowed_senders": "test-info@***REMOVED***",
            "only_subscribers_send": False,
            "imap_pass": "testtest123",
            "imap_host": "***REMOVED***",
            "imap_port": 993,
            "imap_user": "list-eltern-sonnengruppe@***REMOVED***",
            "subscribers": [
                {
                    "name": "Elternteil Sonne 1",
                    "email": "test-user+sonne1@***REMOVED***",
                },
                {
                    "name": "Elternteil Sonne 2",
                    "email": "test-user+sonne2@***REMOVED***",
                },
            ],
        },
        {
            "name": "Eltern Mondgruppe",
            "address": "list-eltern-mondgruppe@***REMOVED***",
            "mode": "broadcast",
            "from_addr": "test-info@***REMOVED***",
            "allowed_senders": "test-info@***REMOVED***",
            "only_subscribers_send": False,
            "imap_pass": "testtest123",
            "imap_host": "***REMOVED***",
            "imap_port": 993,
            "imap_user": "list-eltern-mondgruppe@***REMOVED***",
            "subscribers": [
                {
                    "name": "Elternteil Mond 1",
                    "email": "test-user+mond1@***REMOVED***",
                },
                {
                    "name": "Elternteil Mond 2",
                    "email": "test-user+mond2@***REMOVED***",
                },
            ],
        },
        {
            "name": "Elternbeirat",
            "address": "list-elternbeirat@***REMOVED***",
            "mode": "group",
            "from_addr": "",
            "allowed_senders": "",
            "only_subscribers_send": False,
            "imap_pass": "testtest123",
            "imap_host": "***REMOVED***",
            "imap_port": 993,
            "imap_user": "list-elternbeirat@***REMOVED***",
            "subscribers": [
                {
                    "name": "Elternteil Mond 1",
                    "email": "test-user+mond1@***REMOVED***",
                },
                {
                    "name": "Elternteil Sonne 2",
                    "email": "test-user+sonne2@***REMOVED***",
                },
            ],
        },
        {
            "name": "Vorstand",
            "address": "list-vorstand@***REMOVED***",
            "mode": "group",
            "from_addr": "",
            "allowed_senders": "",
            "only_subscribers_send": False,
            "imap_pass": "testtest123",
            "imap_host": "***REMOVED***",
            "imap_port": 993,
            "imap_user": "list-vorstand@***REMOVED***",
            "subscribers": [
                {
                    "name": "Vorstand 1",
                    "email": "test-user+vorstand@***REMOVED***",
                },
            ],
        },
    ],
}
