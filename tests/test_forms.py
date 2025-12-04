"""Tests for form input handling and validation"""

from flask import current_app

from castmail2list.forms import (
    LoginForm,
    MailingListForm,
    SubscriberAddForm,
    UserDetailsForm,
)

# pylint: disable=unused-argument


def test_login_form_strips_whitespace(client):
    """Test that LoginForm strips leading/trailing whitespace from username"""
    with current_app.test_request_context():
        form = LoginForm(data={"username": "  testuser  ", "password": "password123"})
        assert form.username.data == "testuser"
        assert form.password.data == "password123"


def test_mailing_list_form_strips_whitespace(client):
    """Test that MailingListForm strips whitespace from string fields"""
    with current_app.test_request_context():
        form = MailingListForm(
            data={
                "name": "  My List  ",
                "address": "  list@example.com  ",
                "mode": "broadcast",
                "from_addr": "  sender@example.com  ",
                "allowed_senders": "  user1@test.com, user2@test.com  ",
                "imap_host": "  imap.example.com  ",
                "imap_user": "  listuser  ",
            }
        )
        assert form.name.data == "My List"
        assert form.address.data == "list@example.com"
        assert form.from_addr.data == "sender@example.com"
        assert form.allowed_senders.data == "user1@test.com, user2@test.com"
        assert form.imap_host.data == "imap.example.com"
        assert form.imap_user.data == "listuser"


def test_subscriber_add_form_strips_whitespace(client):
    """Test that SubscriberAddForm strips whitespace from fields"""
    with current_app.test_request_context():
        form = SubscriberAddForm(
            data={
                "name": "  John Doe  ",
                "email": "  john@example.com  ",
                "comment": "  Test subscriber  ",
            }
        )
        assert form.name.data == "John Doe"
        assert form.email.data == "john@example.com"
        assert form.comment.data == "Test subscriber"


def test_user_details_form_strips_whitespace(client):
    """Test that UserDetailsForm strips whitespace from password fields"""
    with current_app.test_request_context():
        form = UserDetailsForm(
            data={
                "password": "  newpassword123  ",
                "password_retype": "  newpassword123  ",
            }
        )
        assert form.password.data == "newpassword123"
        assert form.password_retype.data == "newpassword123"


def test_form_preserves_integer_fields(client):
    """Test that integer fields are not affected by stripping filter"""
    with current_app.test_request_context():
        form = MailingListForm(
            data={
                "name": "Test List",
                "address": "list@example.com",
                "mode": "broadcast",
                "imap_port": 993,
            }
        )
        assert form.imap_port.data == 993
        assert isinstance(form.imap_port.data, int)
