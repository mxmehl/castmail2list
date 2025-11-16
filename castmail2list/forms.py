"""Flask-WTF forms for castmail2list application"""

from flask_babel import lazy_gettext as _  # Using lazy_gettext for form field labels
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    EmailField,
    IntegerField,
    PasswordField,
    RadioField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class MailingListForm(FlaskForm):
    """Form for creating and editing mailing lists"""

    # Basics
    name = StringField(_("List Name"), validators=[DataRequired(), Length(min=1, max=100)])
    address = EmailField(_("List Email Address"), validators=[DataRequired(), Email()])
    from_addr = EmailField(
        _("From Address"),
        validators=[Optional(), Email()],
        description=_(
            "Optional 'From' address for emails sent by the list. "
            "If left empty, the list address will be used."
        ),
    )
    # Modes
    mode = RadioField(
        _("Mode"),
        choices=[
            ("broadcast", _("Broadcast List: One-to-many communication, distribution list")),
            ("group", _("Group List: Many-to-many communication, discussion group")),
        ],
        default="broadcast",
    )
    allowed_senders = StringField(
        _("Allowed Senders"),
        validators=[Optional()],
        description=_(
            "Enter email addresses, separated by commas. Only relevant in Broadcast mode."
        ),
    )
    only_subscribers_send = BooleanField(
        _("Only allow subscribers to send messages to the list. Only relevant in Group mode."),
        default=False,
    )
    # IMAP Settings
    imap_host = StringField(_("IMAP Server"), validators=[Optional(), Length(max=200)])
    imap_port = IntegerField(_("IMAP Port"), validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField(_("IMAP Username"), validators=[Optional(), Length(max=200)])
    imap_pass = PasswordField(_("IMAP Password"), validators=[Optional()])
    submit = SubmitField(_("Save List"))


class SubscriberAddForm(FlaskForm):
    """Form for adding new subscribers"""

    name = StringField(_("Name"), validators=[Optional(), Length(max=100)])
    email = EmailField(_("Email Address"), validators=[DataRequired(), Email()])
    comment = StringField(_("Comment"), validators=[Optional(), Length(max=100)])
    submit = SubmitField(_("Save Subscriber"))
