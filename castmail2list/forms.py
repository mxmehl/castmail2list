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

    mode = RadioField(
        _("Mode"),
        choices=[("broadcast", _("Broadcast List")), ("group", _("Group List"))],
        default="broadcast",
    )
    name = StringField(_("List Name"), validators=[DataRequired(), Length(min=1, max=100)])
    address = EmailField(_("List Email Address"), validators=[DataRequired(), Email()])
    imap_host = StringField(_("IMAP Server"), validators=[Optional(), Length(max=200)])
    imap_port = IntegerField(_("IMAP Port"), validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField(_("IMAP Username"), validators=[Optional(), Length(max=200)])
    imap_pass = PasswordField(_("IMAP Password"), validators=[Optional()])
    from_addr = EmailField(_("From Address"), validators=[Optional(), Email()])
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
    submit = SubmitField(_("Save List"))


class BounceListForm(FlaskForm):
    """Form for creating and editing the bounce handling list"""

    name = StringField(
        _("List Name"),
        validators=[DataRequired(), Length(min=1, max=100)],
        default="Bounce Handler",
        description=_("Internal name for the bounce handler"),
    )
    address = EmailField(
        _("Bounce Email Address"),
        validators=[DataRequired(), Email()],
        description=_(
            "Email address that will receive bounce notification. It will be the Envelope-Sender for all outgoing mails."
        ),
    )
    imap_host = StringField(_("IMAP Server"), validators=[Optional(), Length(max=200)])
    imap_port = IntegerField(_("IMAP Port"), validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField(_("IMAP Username"), validators=[DataRequired(), Length(max=200)])
    imap_pass = PasswordField(_("IMAP Password"), validators=[Optional()])
    submit = SubmitField(_("Save Bounce Settings"))


class SubscriberAddForm(FlaskForm):
    """Form for adding new subscribers"""

    name = StringField(_("Name"), validators=[Optional(), Length(max=100)])
    email = EmailField(_("Email Address"), validators=[DataRequired(), Email()])
    comment = StringField(_("Comment"), validators=[Optional(), Length(max=100)])
    submit = SubmitField(_("Save Subscriber"))
