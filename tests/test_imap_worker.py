"""Test for IMAP worker functionality in the Castmail2List application"""

import os

from imap_tools import MailMessage

from castmail2list.imap_worker import detect_bounce

BOUNCE_TEST_DIR = os.path.join(os.path.dirname(__file__), "bounces")
BOUNCE_RECIPIENTS = {
    "mailbox-full.eml": "recipient-mailbox-is-full@docomo.ne.jp",
    "exceeds-size.eml": "this-message-is-too-big-for-the-host@k.vodafone.ne.jp",
}


def test_detect_bounce_valid():
    """
    Test the detect_bounce function with real-life bounce email samples in the /tests/bounces/
    directory
    """
    for filename in os.listdir(BOUNCE_TEST_DIR):
        if filename.endswith(".eml"):
            filepath = os.path.join(BOUNCE_TEST_DIR, filename)
            with open(filepath, "rb") as f:
                email_bytes = MailMessage.from_bytes(f.read())
                bouncer = detect_bounce(email_bytes)
                assert bouncer == BOUNCE_RECIPIENTS.get(filename, ""), f"Failed for {filename}"
