"""Flask-WTF forms for castmail2list application"""

from flask_wtf import FlaskForm
from wtforms import (
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
        "Mode",
        choices=[("broadcast", "Broadcast List"), ("group", "Group List")],
        default="broadcast",
    )
    name = StringField("List Name", validators=[DataRequired(), Length(min=1, max=100)])
    address = EmailField("List Email Address", validators=[DataRequired(), Email()])
    imap_host = StringField("IMAP Server", validators=[Optional(), Length(max=200)])
    imap_port = IntegerField("IMAP Port", validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField("IMAP Username", validators=[Optional(), Length(max=200)])
    imap_pass = PasswordField("IMAP Password", validators=[Optional()])
    from_addr = EmailField("From Address", validators=[Optional(), Email()])
    allowed_senders = StringField(
        "Allowed Senders",
        validators=[Optional()],
        description="Enter email addresses, separated by commas. Only relevant in Broadcast mode.",
    )
    submit = SubmitField("Save List")


class SubscriberAddForm(FlaskForm):
    """Form for adding new subscribers"""

    name = StringField("Name", validators=[Optional(), Length(max=100)])
    email = EmailField("Email Address", validators=[DataRequired(), Email()])
    comment = StringField("Comment", validators=[Optional(), Length(max=100)])
    submit = SubmitField("Save Subscriber")
