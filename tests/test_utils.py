# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for the utils module."""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import pytest
from flask import Flask

from castmail2list import utils
from castmail2list.app import create_app
from castmail2list.models import EmailIn, EmailOut, MailingList, Subscriber, db
from castmail2list.utils import create_bounce_address, parse_bounce_address, parse_older_than

if TYPE_CHECKING:
    from pytest import MonkeyPatch


def test_create_bounce_address_normal() -> None:
    """Test the create_bounce_address function: normal case."""
    original_email = "jane.doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=gmail.com@list.example.com"


def test_create_bounce_address_plus() -> None:
    """Test the create_bounce_address function: handling plus sign in email."""
    original_email = "jane.doe+test@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"


def test_create_bounce_address_hyphen() -> None:
    """Test the create_bounce_address function: handling hyphen sign in email."""
    original_email = "jane-doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane-doe=gmail.com@list.example.com"


def test_create_bounce_address_special_chars() -> None:
    """Test the create_bounce_address function: handling special characters in email."""
    original_email = "jane.doe@wäb.de"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=wäb.de@list.example.com"


@pytest.mark.parametrize(
    ("value", "expected_seconds"),
    [
        ("1hour", 3600),
        ("24hours", 86400),
        ("1day", 86400),
        ("7days", 7 * 86400),
        ("1month", 30 * 86400),
        ("3months", 90 * 86400),
        # case-insensitive
        ("1HOUR", 3600),
        ("3Days", 3 * 86400),
        ("2MONTHS", 60 * 86400),
        # leading/trailing whitespace
        ("  7days  ", 7 * 86400),
    ],
)
def test_parse_older_than_valid(value: str, expected_seconds: int) -> None:
    """parse_older_than should return correct timedelta for valid inputs."""
    result = parse_older_than(value)
    assert isinstance(result, timedelta)
    assert result.total_seconds() == pytest.approx(expected_seconds)


@pytest.mark.parametrize(
    "value",
    [
        "7d",  # short form no longer accepted
        "24h",  # short form no longer accepted
        "3w",  # weeks not supported
        "1week",  # weeks not supported
        "0days",  # zero is technically valid — ensure it parses (timedelta(0))
        "foobar",
        "",
        "3",
        "days3",
    ],
)
def test_parse_older_than_invalid(value: str) -> None:
    """parse_older_than should raise ValueError for unrecognised formats."""
    if value == "0days":
        # Zero should parse without error, just yields a zero timedelta
        assert parse_older_than(value).total_seconds() == 0
    else:
        with pytest.raises(ValueError, match="Invalid --older-than"):
            parse_older_than(value)


def test_parse_bounce_address_normal() -> None:
    """Test the parse_bounce_address function: normal case."""
    bounce_address = "list1+bounces--jane.doe=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe@gmail.com"


def test_parse_bounce_address_plus() -> None:
    """Test the parse_bounce_address function: handling plus sign in email."""
    bounce_address = "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe+test@gmail.com"


def test_parse_bounce_address_hyphen() -> None:
    """Test the parse_bounce_address function: handling hyphen sign in email."""
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

    def fake_run(cmd, check=True) -> None:
        calls["cmd"] = cmd
        # subprocess.run has no meaningful return value in our tests

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok = utils.create_email_account("uberspace7", "user@example.com", "pw")
    assert ok is True
    assert "uberspace" in calls["cmd"][0]

    # Unsupported host type
    assert utils.create_email_account("unknown", "user@example.com", "pw") is False

    # Simulate CalledProcessError
    def fake_run_fail(cmd, check=True) -> NoReturn:
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

        def __init__(self, host, port) -> None:
            """Initialize with host and port."""
            # no-op: constructor present to match MailBox signature

        def login(self, user, password) -> NoReturn:
            """Simulate login failure by raising the patched MailboxLoginError."""
            msg = "authentication failed"
            raise CustomLoginError(msg)

    monkeypatch.setattr(utils, "MailBox", DummyMailbox)
    assert utils.check_email_account_works("h", 993, "u", "p") is False


def test_is_email_a_list_and_get_list_subscribers(client):
    """is_email_a_list and get_list_recipients_recursive() work with DB-backed
    lists/subscribers.
    """
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

    subs = utils.get_list_recipients_recursive(ml.id)
    assert any(sub == "alice@example.com" for sub in subs)


def test_get_list_recipients_recursive_no_subs(client):
    """get_list_recipients_recursive() returns empty list when no subscribers exist."""
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

    subs = utils.get_list_recipients_recursive(ml.id)
    assert not subs


def test_get_list_recipients_recursive_deduplicates(client):
    """get_list_recipients_recursive() deduplicates subscribers with same email and with list as
    subscriber.
    """
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
    subs = utils.get_list_recipients_recursive(ml1.id)
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

    subs = utils.get_list_recipients_recursive(ml1.id)
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


def test_get_list_recipients_recursive_circular_reference(client):
    """get_list_recipients_recursive() handles circular list subscriptions without infinite loop."""
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

    # Add normal subscribers
    s11 = Subscriber(list_id=ml1.id, email="alice@example.com", name="Alice")
    s21 = Subscriber(list_id=ml2.id, email="bob@example.com")
    db.session.add_all([s11, s21])
    db.session.commit()

    # Add circular list subscriptions
    s12 = Subscriber(list_id=ml1.id, email="l2@example.com", subscriber_type="list")
    s22 = Subscriber(list_id=ml2.id, email="l1@example.com", subscriber_type="list")
    db.session.add_all([s12, s22])
    db.session.commit()

    subs = utils.get_list_recipients_recursive(ml1.id)
    assert len(subs) == 2  # alice and bob
    assert list(subs.keys()) == ["alice@example.com", "bob@example.com"]


def test_get_list_recipients_recursive_deep(client):
    """get_list_recipients_recursive() handles lists subscribing to lists multiple levels deep."""
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
    ml3: MailingList = MailingList(
        id="l3",
        address="l3@example.com",
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    db.session.add_all([ml1, ml2, ml3])
    db.session.commit()

    # Add normal subscribers
    s11 = Subscriber(list_id=ml1.id, email="alice@example.com", name="Alice")
    s21 = Subscriber(list_id=ml2.id, email="bob@example.com")
    s31 = Subscriber(list_id=ml3.id, email="carol@example.com")
    db.session.add_all([s11, s21, s31])
    db.session.commit()

    # Add list subscriptions: ml1 -> ml2 -> ml3
    s12 = Subscriber(list_id=ml1.id, email="l2@example.com", subscriber_type="list")
    s22 = Subscriber(list_id=ml2.id, email="l3@example.com", subscriber_type="list")
    db.session.add_all([s12, s22])
    db.session.commit()

    subs = utils.get_list_recipients_recursive(ml1.id)
    assert len(subs) == 3  # alice, bob, carol
    assert list(subs.keys()) == ["alice@example.com", "bob@example.com", "carol@example.com"]
    assert subs["bob@example.com"]["source"] == ["l2"]  # from l2
    assert subs["carol@example.com"]["source"] == ["l3"]  # from l3

    # State doesn't change if m3 is added as subscriber to m1 directly
    s13 = Subscriber(list_id=ml1.id, email="l3@example.com", subscriber_type="list")
    db.session.add(s13)
    db.session.commit()

    subs = utils.get_list_recipients_recursive(ml1.id)
    assert len(subs) == 3  # still alice, bob, carol
    assert list(subs.keys()) == ["alice@example.com", "bob@example.com", "carol@example.com"]
    assert subs["bob@example.com"]["source"] == ["l2"]  # from l2
    assert subs["carol@example.com"]["source"] == ["l3"]  # from l3


def test_get_list_recipients_recursive_direct_indirect(client):
    """get_list_recipients_recursive() handles only_direct and only_indirect flags correctly."""
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

    # Add normal subscribers
    s11 = Subscriber(list_id=ml1.id, email="alice@example.com", name="Alice")
    s21 = Subscriber(list_id=ml2.id, email="bob@example.com")
    db.session.add_all([s11, s21])
    db.session.commit()

    # Add ml2 as subscriber for ml1
    s12 = Subscriber(list_id=ml1.id, email="l2@example.com", subscriber_type="list")
    db.session.add_all([s12])
    db.session.commit()

    subs_all = utils.get_list_recipients_recursive(ml1.id)
    subs_direct = utils.get_list_recipients_recursive(ml1.id, only_direct=True)
    subs_indirect = utils.get_list_recipients_recursive(ml1.id, only_indirect=True)

    assert len(subs_all) == 2  # alice and bob
    assert len(subs_direct) == 1  # only alice
    assert len(subs_indirect) == 1  # only bob
    assert list(subs_all.keys()) == ["alice@example.com", "bob@example.com"]
    assert list(subs_direct.keys()) == ["alice@example.com"]
    assert list(subs_indirect.keys()) == ["bob@example.com"]


def test_list_subscribers(client) -> None:
    """list_subscribers returns direct subscribers of a mailing list, optionally excluding lists."""
    del client  # ensure app and DB fixtures are active

    ml1 = MailingList(
        id="l1",
        address="l1@example.com",
        mode="broadcast",
        imap_host="imap.example",
        imap_port=993,
        imap_user="u",
        imap_pass="p",
    )
    ml2 = MailingList(
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

    # Add subscribers: one normal, one list
    s1 = Subscriber(list_id=ml1.id, email="alice@example.com")
    s2 = Subscriber(list_id=ml1.id, email="l2@example.com")
    db.session.add_all([s1, s2])
    db.session.commit()

    # Get subscribers including lists
    subs_including_lists = utils.get_list_subscribers(ml1.id, exclude_lists=False)
    subs_excluding_lists = utils.get_list_subscribers(ml1.id, exclude_lists=True)
    assert len(subs_including_lists) == 2
    assert list(subs_including_lists.keys()) == ["alice@example.com", "l2@example.com"]
    assert len(subs_excluding_lists) == 1
    assert list(subs_excluding_lists.keys()) == ["alice@example.com"]


def test_check_recommended_list_setting() -> None:
    """check_recommended_list_setting returns warnings for broadcast lists missing security
    settings.
    """
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
    assert findings
    assert findings[0][1] == "warning"

    ml.allowed_senders = ["foo@example.com"]
    assert not utils.check_recommended_list_setting(ml)

    ml.allowed_senders = []
    ml.sender_auth = ["pass1", "pass2"]
    assert not utils.check_recommended_list_setting(ml)


def test_get_all_incoming_messages(client) -> None:
    """Check that get_all_incoming_messages retrieves messages with filters correctly."""
    del client  # ensure app and DB fixtures are active

    def _days_ago(days: int) -> datetime:
        return datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=days)

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
    recent_normals = utils.get_all_incoming_messages(only="ok", days=7)
    assert len(recent_normals) == 1
    assert any(msg.message_id == "normal-1" for msg in recent_normals)

    # Retrieve all messages from the last 7 days
    recent_all = utils.get_all_incoming_messages(days=7)
    assert len(recent_all) == 2
    assert recent_all[0].message_id == "bounce-1"
    assert recent_all[1].message_id == "normal-1"


def test_get_all_outgoing_messages(client) -> None:
    """Check that get_all_outgoing_messages retrieves outgoing messages correctly."""
    del client  # ensure app and DB fixtures are active

    def _days_ago(days: int) -> datetime:
        return datetime.now(tz=timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    sent1: EmailOut = EmailOut(
        message_id="sent-1",
        subject="Sent 1",
        email_in_mid="in-1",
        list_id="list1",
        sent_at=_days_ago(1),
    )
    sent2: EmailOut = EmailOut(
        message_id="sent-2",
        subject="Sent 2",
        email_in_mid="in-2",
        list_id="list1",
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


def test_redact_helper() -> None:
    """redact() exposes ~50% of the value and masks the rest."""
    assert utils.redact("secret") == "sec***"  # 6 chars: 3 visible, 3 masked
    assert utils.redact("ab") == "a*"  # 2 chars: 1 visible, 1 masked
    assert utils.redact("x") == "x"  # 1 char: 1 visible, 0 masked
    assert utils.redact("") == "***"  # empty: fully masked


def test_create_app_raises_on_missing_secret_key() -> None:
    """create_app() raises ValueError when SECRET_KEY is absent outside of TESTING mode."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app(
            config_overrides={
                "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            },
            one_off_call=True,
        )


# ---------------------- SCSS Compilation Tests ----------------------


def test_compile_scss_uses_system_sass_when_available(monkeypatch: MonkeyPatch) -> None:
    """If a system sass binary is found on PATH, it should be used via subprocess."""
    monkeypatch.setattr(utils.shutil, "which", lambda _name: "/usr/bin/sass")

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool) -> None:
        calls.append(cmd)

    monkeypatch.setattr(utils.subprocess, "run", fake_run)

    utils._compile_scss(scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert calls == [["/usr/bin/sass", "/tmp/in.scss", "/tmp/out.css"]]


def test_compile_scss_falls_back_to_embedded_when_no_system_sass(
    monkeypatch: MonkeyPatch,
) -> None:
    """If no system sass binary is found on PATH, fall back to sass-embedded."""
    monkeypatch.setattr(utils.shutil, "which", lambda _name: None)

    embedded_calls: list[tuple[str, str]] = []

    def fake_compile_scss_embedded(scss_input: str, css_output: str) -> None:
        embedded_calls.append((scss_input, css_output))

    monkeypatch.setattr(utils, "_compile_scss_embedded", fake_compile_scss_embedded)

    utils._compile_scss(scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert embedded_calls == [("/tmp/in.scss", "/tmp/out.css")]


def test_compile_scss_embedded_installs_and_compiles(monkeypatch: MonkeyPatch) -> None:
    """compile_scss_embedded should install Dart Sass (idempotent), then compile via
    sass_embedded.
    """
    install_calls = []
    compile_calls = []

    fake_sass_embedded = type(
        "FakeModule",
        (),
        {"compile_file": staticmethod(lambda source, dest: compile_calls.append((source, dest)))},
    )()
    fake_installer = type(
        "FakeInstaller", (), {"install": staticmethod(lambda: install_calls.append(True))}
    )()

    monkeypatch.setitem(__import__("sys").modules, "sass_embedded", fake_sass_embedded)
    monkeypatch.setitem(
        __import__("sys").modules, "sass_embedded.dart_sass.installer", fake_installer
    )

    utils._compile_scss_embedded(scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert install_calls == [True]
    assert compile_calls == [(Path("/tmp/in.scss"), Path("/tmp/out.css"))]


def test_compile_scss_system_exits_on_missing_compiler(monkeypatch: MonkeyPatch) -> None:
    """compile_scss_system should log critical and exit if the compiler binary is not found."""

    def fake_run(cmd: list[str], check: bool) -> NoReturn:
        raise FileNotFoundError

    monkeypatch.setattr(utils.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        utils._compile_scss_system("sass", scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert exc_info.value.code == 1


def test_compile_scss_system_exits_on_compile_error(monkeypatch: MonkeyPatch) -> None:
    """compile_scss_system should log critical and exit if compilation fails."""

    def fake_run(cmd: list[str], check: bool) -> NoReturn:
        raise subprocess.CalledProcessError(returncode=1, cmd=cmd)

    monkeypatch.setattr(utils.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        utils._compile_scss_system("sass", scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert exc_info.value.code == 1


def test_compile_scss_embedded_exits_on_compile_error(monkeypatch: MonkeyPatch) -> None:
    """compile_scss_embedded should log critical and exit if sass-embedded compilation fails."""

    def fake_compile_file(source: Path, dest: Path) -> NoReturn:
        msg = "boom"
        raise RuntimeError(msg)

    fake_sass_embedded = type("FakeModule", (), {"compile_file": staticmethod(fake_compile_file)})()
    fake_installer = type("FakeInstaller", (), {"install": staticmethod(lambda: None)})()

    monkeypatch.setitem(__import__("sys").modules, "sass_embedded", fake_sass_embedded)
    monkeypatch.setitem(
        __import__("sys").modules, "sass_embedded.dart_sass.installer", fake_installer
    )

    with pytest.raises(SystemExit) as exc_info:
        utils._compile_scss_embedded(scss_input="/tmp/in.scss", css_output="/tmp/out.css")

    assert exc_info.value.code == 1


def test_compile_scss_on_startup_resolves_paths_and_compiles(monkeypatch: MonkeyPatch) -> None:
    """compile_scss_on_startup should resolve absolute paths and delegate to compile_scss."""
    calls: list[tuple[str, str]] = []

    def fake_compile_scss(scss_input: str, css_output: str) -> None:
        calls.append((scss_input, css_output))

    monkeypatch.setattr(utils, "_compile_scss", fake_compile_scss)

    result = utils.compile_scss_on_startup([("static/scss/main.scss", "static/css/main.css")])

    curpath = Path(utils.__file__).parent.resolve()
    expected_input = str(curpath / "static/scss/main.scss")
    expected_output = str(curpath / "static/css/main.css")

    assert calls == [(expected_input, expected_output)]
    assert result == [(expected_input, expected_output)]
