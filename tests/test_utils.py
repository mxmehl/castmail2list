"""Tests for the utils module"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask
from pytest import MonkeyPatch

from castmail2list import utils
from castmail2list.models import EmailIn, EmailOut, MailingList, Subscriber, db
from castmail2list.utils import create_bounce_address, parse_bounce_address

# pylint: disable=protected-access,too-few-public-methods


def test_create_bounce_address_normal() -> None:
    """Test the create_bounce_address function: normal case"""
    original_email = "jane.doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=gmail.com@list.example.com"


def test_create_bounce_address_plus() -> None:
    """Test the create_bounce_address function: handling plus sign in email"""
    original_email = "jane.doe+test@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"


def test_create_bounce_address_hyphen() -> None:
    """Test the create_bounce_address function: handling hyphen sign in email"""
    original_email = "jane-doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane-doe=gmail.com@list.example.com"


def test_create_bounce_address_special_chars() -> None:
    """Test the create_bounce_address function: handling special characters in email"""
    original_email = "jane.doe@wäb.de"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=wäb.de@list.example.com"


def test_parse_bounce_address_normal() -> None:
    """Test the parse_bounce_address function: normal case"""
    bounce_address = "list1+bounces--jane.doe=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe@gmail.com"


def test_parse_bounce_address_plus() -> None:
    """Test the parse_bounce_address function: handling plus sign in email"""
    bounce_address = "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe+test@gmail.com"


def test_parse_bounce_address_hyphen() -> None:
    """Test the parse_bounce_address function: handling hyphen sign in email"""
    bounce_address = "list1+bounces--jane-test=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane-test@gmail.com"


def test_normalize_and_string_list_helpers() -> None:
    """Normalize and list/string helper functions behave as expected."""
    assert utils.normalize_email_list("a@x.com, b@y.com\nc@z.com") == "a@x.com, b@y.com, c@z.com"
    assert utils.normalize_email_list("") == ""

    assert utils.list_to_string(["one", "two"]) == "one, two"

    assert utils.string_to_list("a, b\nc") == ["a", "b", "c"]
    assert utils.string_to_list("") == []


def test_get_version_info_debug_and_non_debug(monkeypatch: MonkeyPatch) -> None:
    """get_version_info returns version and includes commit when debug."""
    assert utils.get_version_info(debug=False) == utils.__version__

    monkeypatch.setattr(subprocess, "check_output", lambda *_: b"deadbeef\n")
    assert "(" in utils.get_version_info(debug=True)


def test_run_only_once_behavior(monkeypatch: MonkeyPatch) -> None:
    """run_only_once respects DEBUG and WERKZEUG_RUN_MAIN env var."""
    app = Flask(__name__)
    app.debug = False
    assert utils.run_only_once(app) is True

    app.debug = True
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    assert utils.run_only_once(app) is True

    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "false")
    assert utils.run_only_once(app) is False


def test_split_and_plus_suffix_helpers() -> None:
    """split_email_address and plus-suffix helpers."""
    local, domain = utils.split_email_address("foo+bar@example.org")
    assert local == "foo+bar"
    assert domain == "example.org"

    assert utils.get_plus_suffix("foo+bar=example.org@example.org") == "bar=example.org"
    assert utils.get_plus_suffix("no-suffix@example.org") is None
    assert utils.remove_plus_suffix("foo+bar=whatever.tld@example.org") == "foo@example.org"


def test_is_expanded_address_the_mailing_list() -> None:
    """is_expanded_address_the_mailing_list matches addresses ignoring +suffix and case."""
    assert utils.is_expanded_address_the_mailing_list("LiSt@EXAMPLE.com", "list@example.com")
    assert utils.is_expanded_address_the_mailing_list("list+tag@EXAMPLE.com", "list@example.com")
    assert not utils.is_expanded_address_the_mailing_list(
        "other+test@example.com", "list+test@example.com"
    )


def test_get_app_bin_dir_and_user_config_path() -> None:
    """get_app_bin_dir returns a Path and get_user_config_path appends a file name."""
    bin_dir = utils.get_app_bin_dir()
    assert isinstance(bin_dir, Path)

    p = utils.get_user_config_path(name="castmail2list", file="conf.yaml")
    assert isinstance(p, str)
    assert p.endswith("conf.yaml")


def test_create_email_account_subprocess(monkeypatch) -> None:
    """create_email_account calls subprocess.run and handles failures."""
    # Simulate subprocess.run success
    calls = {}

    def fake_run(cmd, check=True):  # pylint: disable=unused-argument
        calls["cmd"] = cmd
        # subprocess.run has no meaningful return value in our tests

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok = utils.create_email_account("uberspace7", "user@example.com", "pw")
    assert ok is True
    assert "uberspace" in calls["cmd"][0]

    # Unsupported host type
    assert utils.create_email_account("unknown", "user@example.com", "pw") is False

    # Simulate CalledProcessError
    def fake_run_fail(cmd, check=True):
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(subprocess, "run", fake_run_fail)
    assert utils.create_email_account("uberspace8", "user@example.com", "pw") is False


def test_check_email_account_works_login_error(monkeypatch) -> None:
    """check_email_account_works returns False on MailboxLoginError."""

    class CustomLoginError(Exception):
        """Local stand-in for imap_tools.MailboxLoginError in tests."""

    # Ensure utils.MailboxLoginError refers to our test-specific class so we can
    # raise it without depending on imap_tools constructor details.
    monkeypatch.setattr(utils, "MailboxLoginError", CustomLoginError)

    class DummyMailbox:
        """Stub MailBox that raises on login."""

        def __init__(self, host, port):
            """Initialize with host and port."""
            # no-op: constructor present to match MailBox signature

        def login(self, user, password):
            """Simulate login failure by raising the patched MailboxLoginError."""
            raise CustomLoginError("authentication failed")

    monkeypatch.setattr(utils, "MailBox", DummyMailbox)
    assert utils.check_email_account_works("h", 993, "u", "p") is False


def test_is_email_a_list_and_get_list_subscribers(client):
    """is_email_a_list and get_list_subscribers_with_details() work with DB-backed
    lists/subscribers."""
    del client  # ensure app and DB fixtures are active

    ml = MailingList(
        id="T",
        address="t@example.COM",
        deleted=False,
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    db.session.add(ml)
    db.session.commit()

    # is_email_a_list finds the list regardless of case
    assert utils.is_email_a_list("t@example.COM") == ml
    assert utils.is_email_a_list("t@example.com") == ml
    assert utils.is_email_a_list("T@ExAmPle.com") == ml

    # is_email_a_list returns None for non-list address
    assert utils.is_email_a_list("whatever@example.net") is None

    s = Subscriber(list_id=ml.id, email="alice@example.com")
    db.session.add(s)
    db.session.commit()

    subs = utils.get_list_subscribers_with_details(ml.id)
    assert any(sub == "alice@example.com" for sub in subs)


def test_get_list_subscribers_no_subs(client):
    """get_list_subscribers_with_details() returns empty list when no subscribers exist."""
    del client  # ensure app and DB fixtures are active

    ml = MailingList(
        id="t2",
        address="t2@example.com",
        deleted=False,
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    db.session.add(ml)
    db.session.commit()

    subs = utils.get_list_subscribers_with_details(ml.id)
    assert not subs


def test_get_list_subscribers_deduplicates(client):
    """get_list_subscribers_with_details() deduplicates subscribers with same email and with list as
    subscriber"""
    del client  # ensure app and DB fixtures are active

    ml1: MailingList = MailingList(
        id="l1",
        address="l1@example.com",
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    ml2: MailingList = MailingList(
        id="l2",
        address="l2@example.com",
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    db.session.add_all([ml1, ml2])
    db.session.commit()

    # Add subscribers with duplicate emails across lists
    s11 = Subscriber(list_id=ml1.id, email="alice@example.com", name="Alice")
    s12 = Subscriber(list_id=ml1.id, email="ALICE@example.com", name="Alice Dup")
    s13 = Subscriber(list_id=ml1.id, email="bob@example.com")
    s21 = Subscriber(list_id=ml2.id, email="alice@example.com", name="Alice 2")  # duplicate email
    s22 = Subscriber(list_id=ml2.id, email="carol@example.com")
    s23 = Subscriber(list_id=ml2.id, email="DAVE@example.com")  # to test case insensitivity
    db.session.add_all([s11, s12, s13, s21, s22, s23])
    db.session.commit()

    # Get subscribers for ml1; should deduplicate
    subs = utils.get_list_subscribers_with_details(ml1.id)
    assert len(subs) == 2  # alice and bob
    assert list(subs.keys()) == ["alice@example.com", "bob@example.com"]
    assert "ALICE@example.com" not in subs  # deduplicated

    # Add ml2 as subscriber for ml1
    s14 = Subscriber(
        list_id=ml1.id,
        email="l2@example.com",
        subscriber_type="list" if utils.is_email_a_list("l2@example.com") else "normal",
    )
    db.session.add(s14)
    db.session.commit()

    subs = utils.get_list_subscribers_with_details(ml1.id)
    assert s14.subscriber_type == "list"
    assert len(subs) == 4  # alice, bob (from list1) + carol and dave (from list2)
    assert "l2@example.com" not in subs  # list email not included
    assert list(subs.keys()) == [
        "alice@example.com",
        "bob@example.com",
        "carol@example.com",
        "dave@example.com",
    ]

    # Check that metadata is correct
    assert subs["alice@example.com"]["name"] == "Alice"  # from first subscriber
    assert subs["alice@example.com"]["source"] == ["direct", "l2"]  # direct and from l2
    assert subs["dave@example.com"]["source"] == ["l2"]  # only from l2
    assert subs["dave@example.com"]["email"] == "dave@example.com"  # correct email


def test_check_recommended_list_setting() -> None:
    """check_recommended_list_setting returns warnings for broadcast lists missing security
    settings."""

    ml = MailingList(
        id="rec",
        address="rec@example.com",
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    ml.allowed_senders = []
    ml.sender_auth = []

    findings = utils.check_recommended_list_setting(ml)
    assert findings and findings[0][1] == "warning"

    ml.allowed_senders = ["foo@example.com"]
    assert not utils.check_recommended_list_setting(ml)

    ml.allowed_senders = []
    ml.sender_auth = ["pass1", "pass2"]
    assert not utils.check_recommended_list_setting(ml)


def test_get_all_incoming_messages(client) -> None:
    """Check that get_all_incoming_messages retrieves messages with filters correctly"""
    del client  # ensure app and DB fixtures are active

    def _days_ago(days: int) -> datetime:
        return datetime.now() - timedelta(days=days)

    bounce1: EmailIn = EmailIn(
        message_id="bounce-1",
        subject="Bounce 1",
        status="bounce-msg",
        headers="{'foo': 'bar'}",
        received_at=_days_ago(1),
        list_id="list1",
    )
    normal1: EmailIn = EmailIn(
        message_id="normal-1",
        subject="Normal 1",
        status="ok",
        headers="{'foo': 'bar'}",
        received_at=_days_ago(2),
        list_id="list1",
    )
    bounce2: EmailIn = EmailIn(
        message_id="bounce-2",
        subject="Bounce 2",
        status="bounce-msg",
        headers="{'foo': 'bar'}",
        received_at=_days_ago(8),
        list_id="list1",
    )
    normal2: EmailIn = EmailIn(
        message_id="normal-2",
        subject="Bounce 2",
        status="ok",
        headers="{'foo': 'bar'}",
        received_at=_days_ago(10),
        list_id="list1",
    )

    # Add bounce messages to the database
    db.session.add_all([bounce1, bounce2, normal1, normal2])
    db.session.commit()

    # Retrieve all messages without filtering
    all_messages = utils.get_all_incoming_messages()
    assert len(all_messages) == 4
    assert any(msg.message_id == "bounce-1" for msg in all_messages)
    assert any(msg.message_id == "bounce-2" for msg in all_messages)
    assert any(msg.message_id == "normal-1" for msg in all_messages)
    assert any(msg.message_id == "normal-2" for msg in all_messages)

    # Check descending order by received_at
    assert (
        all_messages[0].received_at
        >= all_messages[1].received_at
        >= all_messages[2].received_at
        >= all_messages[3].received_at
    )

    # Retrieve bounce messages from the last 7 days
    recent_bounces = utils.get_all_incoming_messages(only="bounces", days=7)
    assert len(recent_bounces) == 1
    assert any(msg.message_id == "bounce-1" for msg in recent_bounces)

    # Retrieve normal messages from the last 7 days
    recent_normals = utils.get_all_incoming_messages(only="normal", days=7)
    assert len(recent_normals) == 1
    assert any(msg.message_id == "normal-1" for msg in recent_normals)

    # Retrieve all messages from the last 7 days
    recent_all = utils.get_all_incoming_messages(days=7)
    assert len(recent_all) == 2
    assert recent_all[0].message_id == "bounce-1"
    assert recent_all[1].message_id == "normal-1"


def test_get_all_outgoing_messages(client) -> None:
    """Check that get_all_outgoing_messages retrieves outgoing messages correctly"""
    del client  # ensure app and DB fixtures are active

    def _days_ago(days: int) -> datetime:
        return datetime.now() - timedelta(days=days)

    sent1: EmailOut = EmailOut(
        message_id="sent-1",
        subject="Sent 1",
        email_in_mid="in-1",
        sent_at=_days_ago(1),
    )
    sent2: EmailOut = EmailOut(
        message_id="sent-2",
        subject="Sent 2",
        email_in_mid="in-2",
        sent_at=_days_ago(10),
    )

    # Add sent messages to the database
    db.session.add_all([sent1, sent2])
    db.session.commit()

    # Retrieve all outgoing messages
    outgoing_messages = utils.get_all_outgoing_messages()
    assert len(outgoing_messages) == 2
    assert any(msg.message_id == "sent-1" for msg in outgoing_messages)
    assert any(msg.message_id == "sent-2" for msg in outgoing_messages)

    # Check descending order by sent_at
    assert outgoing_messages[0].sent_at >= outgoing_messages[1].sent_at

    # Retrieve outgoing messages from the last 7 days
    recent_outgoings = utils.get_all_outgoing_messages(days=7)
    assert len(recent_outgoings) == 1
    assert recent_outgoings[0].message_id == "sent-1"
