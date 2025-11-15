"""Flask-WTF forms for castmail2list application"""

from flask_wtf import FlaskForm
from wtforms import (
    EmailField,
    HiddenField,
    IntegerField,
    PasswordField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class MailingListForm(FlaskForm):
    """Form for creating and editing mailing lists"""
    name = StringField('List Name', validators=[DataRequired(), Length(min=1, max=100)])
    address = EmailField('List Email Address', validators=[DataRequired(), Email()])
    imap_host = StringField('IMAP Server', validators=[Optional(), Length(max=200)])
    imap_port = IntegerField('IMAP Port', validators=[Optional(), NumberRange(min=1, max=65535)])
    imap_user = StringField('IMAP Username', validators=[Optional(), Length(max=200)])
    imap_pass = PasswordField('IMAP Password', validators=[Optional()])
    from_addr = EmailField('From Address', validators=[Optional(), Email()])
    submit = SubmitField('Save List')


class SubscriberAddForm(FlaskForm):
    """Form for adding new subscribers"""
    name = StringField('Name', validators=[Optional(), Length(max=100)])
    email = EmailField('Email Address', validators=[DataRequired(), Email()])
    comment = StringField('Comment', validators=[Optional(), Length(max=100)])
    add_subscriber = SubmitField('Add Subscriber')


class SubscriberDeleteForm(FlaskForm):
    """Form for removing subscribers"""
    subscriber_id = HiddenField('Subscriber ID', validators=[DataRequired()])
    delete_subscriber = SubmitField('Remove from list')
