"""Flask-WTF forms for castmail2list application"""

from email.utils import parseaddr

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
    ValidationError,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class CM2LBaseForm(FlaskForm):
    """Base form class for CastMail2List forms"""

    class Meta:  # pylint: disable=too-few-public-methods
        """Customize form field binding to add stripping filter"""

        def bind_field(self, form, unbound_field, options):
            """Add custom filter to strip whitespace from string fields"""
            filters = unbound_field.kwargs.get("filters", [])
            filters.append(my_strip_filter)
            return unbound_field.bind(form=form, filters=filters, **options)


def my_strip_filter(value: str | int):
    """Custom filter to strip leading/trailing whitespace from string fields"""
    if value is not None and hasattr(value, "strip"):
        return value.strip()
    return value


class LoginForm(CM2LBaseForm):
    """
    LoginForm is a form class used for user authentication.

    Attributes:
        username (StringField): A field for entering the username. It is required.
        password (PasswordField): A field for entering the password. It is required.
    """

    username = StringField(label="Username", validators=[DataRequired()])
    password = PasswordField(label="Password", validators=[DataRequired()])
    submit = SubmitField(_("Login"))


def email_with_opt_display_name(form, field):
    """Custom validator for multiple ways of providing email addresses:

    foo@bar.com
    John Doe <foo@bar.com>
    "John P. Doe" <foo@bar.com>
    """
    _, addr = parseaddr(field.data or "")
    if not addr:
        raise ValidationError("Invalid email format")

    # Temporarily replace field.data with the bare address
    original = field.data
    field.data = addr

    try:
        Email()(form, field)
    finally:
        field.data = original


class MailingListForm(CM2LBaseForm):
    """Form for creating and editing mailing lists"""

    # Basics
    id = StringField(_("List Name"), validators=[DataRequired(), Length(min=1, max=50)])
    domain = StringField(_("Domain"), validators=[])
    display = StringField(_("Display Name"), validators=[DataRequired(), Length(min=1, max=100)])

    # Modes
    mode = RadioField(
        _("Mode of the Mailing List"),
        choices=[
            ("broadcast", _("Broadcast List: One-to-many communication, distribution list")),
            ("group", _("Group List: Many-to-many communication, discussion group")),
        ],
        default="broadcast",
    )
    from_addr = StringField(
        _("From Address"),
        validators=[Optional(), email_with_opt_display_name],
        description=_(
            "Optional 'From' address for emails sent by the list. If left empty, the list address "
            "will be used. Only relevant in Broadcast mode."
        ),
    )

    # Sender Restrictions
    only_subscribers_send = BooleanField(
        _("Only allow subscribers to send messages to this group list"),
        description=_(
            "This may be overridden by sender authentication and allowed senders. "
            "Only relevant in Group mode."
        ),
        default=False,
    )
    allowed_senders = StringField(
        _("Allowed Senders"),
        validators=[Optional()],
        description=_(
            "Email addresses that are always allowed to send emails to the list. In Broadcast "
            "mode, only they are allowed to send to the list. In Group mode, they can also send to "
            "the list if 'Only allow subscribers to send' is enabled. "
            "Separated by commas."
        ),
    )
    sender_auth = StringField(
        _("Sender Authentication Passwords"),
        validators=[Optional()],
        description=_(
            "Comma-separated list of passwords that senders can provide to send emails to this "
            "list. When this is set in Broadcast mode, one of these passwords must be provided to "
            "send to the list. In Group mode, these passwords allow to send to the list even if "
            "'Only allow subscribers to send' is enabled. This can be passed via "
            "'listaddress+password1@example.com'. Leave empty to disable sender authentication."
        ),
    )

    # Additional Settings
    avoid_duplicates = BooleanField(
        _("Avoid duplicate copies of messages for subscribers"),
        description=_(
            "If enabled, subscribers will not receive a copy of a message they sent themselves."
        ),
        default=True,
    )

    # IMAP Settings
    imap_host = StringField(_("IMAP Server"), validators=[Optional(), Length(max=200)])
    imap_port = IntegerField(_("IMAP Port"), validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField(_("IMAP Username"), validators=[Optional(), Length(max=200)])
    imap_pass = PasswordField(_("IMAP Password"), validators=[Optional()])
    submit = SubmitField(_("Save List"))


class SubscriberAddForm(CM2LBaseForm):
    """Form for adding new subscribers"""

    name = StringField(_("Name"), validators=[Optional(), Length(max=100)])
    email = EmailField(_("Email Address"), validators=[DataRequired(), Email()])
    comment = StringField(_("Comment"), validators=[Optional(), Length(max=100)])
    submit = SubmitField(_("Save Subscriber"))


class UserDetailsForm(CM2LBaseForm):
    """Form for changing user password"""

    password = PasswordField(
        _("New Password"),
        validators=[Optional(), Length(min=8)],
        description=_("Enter a new password with at least 6 characters."),
    )
    password_retype = PasswordField(
        _("Retype Password"),
        validators=[Optional(), Length(min=8)],
        description=_("Retype the new password for confirmation."),
    )
    api_key = StringField(_("API Key"), render_kw={"readonly": True})
    api_key_generate = SubmitField(_("Regenerate API Key"), name="api_key_generate")
    submit = SubmitField(_("Update Your Account"), name="submit")
