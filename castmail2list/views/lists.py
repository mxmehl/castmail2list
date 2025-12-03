"""Lists blueprint for CastMail2List application"""

import logging
from typing import cast

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import login_required

from ..config import AppConfig
from ..forms import MailingListForm, SubscriberAddForm
from ..models import MailingList, Subscriber, db
from ..utils import (
    check_email_account_works,
    check_recommended_list_setting,
    create_email_account,
    flash_form_errors,
    get_list_subscribers,
    is_email_a_list,
    list_to_string,
    string_to_list,
)

lists = Blueprint("lists", __name__, url_prefix="/lists")


@lists.before_request
@login_required
def before_request() -> None:
    """Require login for all routes"""


# -----------------------------------------------------------------
# Viewing mailing lists
# -----------------------------------------------------------------


@lists.route("/", methods=["GET"])
def index():
    """Show all active mailing lists"""
    active_lists: list[MailingList] = MailingList.query.filter_by(deleted=False).all()
    return render_template("lists/index.html", lists=active_lists, config=AppConfig)


@lists.route("/deactivated", methods=["GET"])
def deactivated():
    """Show all deactivated mailing lists"""
    deactivated_lists: list[MailingList] = MailingList.query.filter_by(deleted=True).all()
    return render_template("lists/deactivated.html", lists=deactivated_lists, config=AppConfig)


# -----------------------------------------------------------------
# Managing lists themselves
# -----------------------------------------------------------------


@lists.route("/add", methods=["GET", "POST"])
def add():
    """Add a new mailing list"""
    form = MailingListForm()

    if form.validate_on_submit():
        # Convert input to comma-separated for storage
        new_list = MailingList(
            mode=form.mode.data,
            name=form.name.data,
            address=form.address.data.lower(),
            from_addr=form.from_addr.data or "",
            # Mode settings
            only_subscribers_send=form.only_subscribers_send.data,
            allowed_senders=string_to_list(form.allowed_senders.data),
            sender_auth=string_to_list(form.sender_auth.data),
            # IMAP settings with defaults
            imap_host=form.imap_host.data or current_app.config["IMAP_DEFAULT_HOST"],
            imap_port=form.imap_port.data or current_app.config["IMAP_DEFAULT_PORT"],
            imap_user=form.imap_user.data or form.address.data,
            imap_pass=form.imap_pass.data or current_app.config["IMAP_DEFAULT_PASS"],
        )
        # Verify that the list address is unique
        existing_list = MailingList.query.filter_by(address=new_list.address).first()
        if existing_list:
            status = "deactivated" if existing_list.deleted else "active"
            flash(
                _(
                    'A mailing list with the address "%(address)s" (%(status)s) already exists.',
                    address=new_list.address,
                    status=status,
                ),
                "error",
            )
            logging.warning(
                'Attempt to create mailing list with address "%s" failed. It already exists in DB.',
                new_list.address,
            )
            return render_template("lists/add.html", config=AppConfig, form=form, retry=True)
        # Verify that the email account works
        if not check_email_account_works(
            new_list.imap_host, int(new_list.imap_port), new_list.imap_user, new_list.imap_pass
        ):
            if current_app.config["CREATE_LISTS_AUTOMATICALLY"]:
                # Try to create the email account automatically
                created = create_email_account(
                    host_type=current_app.config["HOST_TYPE"],
                    email=new_list.address,
                    password=new_list.imap_pass,
                )
                # Case: account created, consider it will work now
                if created:
                    logging.info("Created email account %s automatically", new_list.address)
                # Case: account not created, show error
                else:
                    logging.error(
                        "Failed to create email account %s automatically", new_list.address
                    )
                    flash(
                        _(
                            "Could not connect to the IMAP server with the provided credentials. "
                            "Creation of the email account with this data also failed. Check the "
                            "logs for details."
                        ),
                        "error",
                    )
                    return render_template(
                        "lists/add.html", config=AppConfig, form=form, retry=True
                    )
            # Case: automatic account creation disabled, show error
            else:
                flash(
                    _(
                        "Could not connect to the IMAP server with the provided credentials. "
                        "Automatic creation of email accounts is disabled. "
                        "Please check and try again."
                    ),
                    "error",
                )
                return render_template("lists/add.html", config=AppConfig, form=form, retry=True)

        # Add and commit new list
        db.session.add(new_list)
        db.session.commit()
        flash(_('Mailing list "%(name)s" created successfully!', name=new_list.name), "success")
        logging.info('Mailing list "%s" created', new_list.address)

        # Check recommended settings and flash warnings if needed
        for finding in check_recommended_list_setting(ml=new_list):
            flash(finding[0], finding[1])

        return redirect(url_for("lists.index"))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    return render_template("lists/add.html", config=AppConfig, form=form)


@lists.route("/<int:list_id>/edit", methods=["GET", "POST"])
def edit(list_id):
    """Edit a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    form = MailingListForm(obj=mailing_list)

    # Handle form submission
    if form.validate_on_submit():
        # Verify that the list address is unique
        new_address = form.address.data
        existing_list = MailingList.query.filter_by(address=new_address).first()
        if existing_list:
            status = _("deactivated") if existing_list.deleted else _("active")
            flash(
                _(
                    'A mailing list with the address "%(address)s" (%(status)s) already exists.',
                    address=new_address,
                    status=status,
                ),
                "error",
            )
            logging.warning(
                "Attempt to change list %s's address to '%s' failed. It already exists in DB.",
                mailing_list.id,
                new_address,
            )
            return render_template(
                "lists/edit.html", mailing_list=mailing_list, form=form, retry=True
            )

        # Only update imap_pass if a new value is provided
        old_pass = mailing_list.imap_pass
        form.populate_obj(mailing_list)
        if not form.imap_pass.data:
            mailing_list.imap_pass = old_pass

        # Verify that the email account works
        if not check_email_account_works(
            mailing_list.imap_host,
            int(mailing_list.imap_port),
            mailing_list.imap_user,
            mailing_list.imap_pass,
        ):
            flash(
                _(
                    "Could not connect to the IMAP server with the provided credentials. "
                    "Please check and try again."
                ),
                "error",
            )
            return render_template("lists/edit.html", mailing_list=mailing_list, form=form)

        # Convert comma-separated fields to list object for storage in DB
        mailing_list.allowed_senders = string_to_list(form.allowed_senders.data)
        mailing_list.sender_auth = string_to_list(form.sender_auth.data)

        db.session.commit()
        flash(_('List "%(name)s" updated successfully!', name=mailing_list.name), "success")
        logging.info('Mailing list "%s" updated', mailing_list.address)

        # Check recommended settings and flash warnings if needed
        for finding in check_recommended_list_setting(ml=mailing_list):
            flash(finding[0], finding[1])

        return redirect(url_for("lists.index"))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    # Flash if list is deactivated
    if mailing_list.deleted:
        flash(
            _("This mailing list is deactivated. Reactivate it to process incoming emails."),
            "warning",
        )

    # Case: GET request: populate form fields from list objects to comma-separated strings
    if not form.submit.data:
        form.allowed_senders.data = list_to_string(mailing_list.allowed_senders)
        form.sender_auth.data = list_to_string(mailing_list.sender_auth)

    return render_template("lists/edit.html", mailing_list=mailing_list, form=form)


@lists.route("/<int:list_id>/deactivate", methods=["GET"])
def deactivate(list_id):
    """Deactivate a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(
        id=list_id, deleted=False
    ).first_or_404()
    mailing_list.deactivate()  # Use the soft_delete method from the model
    db.session.commit()
    flash(_('List "%(name)s" deactivated successfully!', name=mailing_list.name), "success")
    logging.info('Mailing list "%s" deactivated', mailing_list.address)
    return redirect(url_for("lists.index"))


@lists.route("/<int:list_id>/reactivate", methods=["GET"])
def reactivate(list_id):
    """Reactivate a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id, deleted=True).first_or_404()
    mailing_list.reactivate()  # Use the reactivate method from the model
    db.session.commit()
    flash(_('List "%(name)s" reactivated successfully!', name=mailing_list.name), "success")
    logging.info('Mailing list "%s" reactivated', mailing_list.address)
    return redirect(url_for("lists.index"))


# -----------------------------------------------------------------
# Managing subscribers of lists
# -----------------------------------------------------------------


@lists.route("/<int:list_id>/subscribers", methods=["GET", "POST"])
def subscribers_manage(list_id):
    """Manage subscribers of a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    form = SubscriberAddForm()

    # Handle adding subscribers
    if form.submit.data and form.validate_on_submit():
        name = form.name.data
        email = form.email.data.strip().lower()  # normalize before lookup/insert
        comment = form.comment.data

        # Check if subscriber already exists, identified by email and list_id
        existing_subscriber = Subscriber.query.filter_by(
            list_id=mailing_list.id, email=email
        ).first()
        if existing_subscriber:
            flash(
                _('Email "%(email)s" is already subscribed to this list.', email=email),
                "warning",
            )
            logging.info(
                'Attempt to add existing subscriber "%s" to mailing list %s',
                email,
                mailing_list.address,
            )
            return redirect(url_for("lists.subscribers_manage", list_id=list_id))

        # Check if subscriber is an existing list. If so, set type and re-use name
        if existing_list := is_email_a_list(email):
            name = existing_list.name
            subscriber_type = "list"
        else:
            subscriber_type = "normal"

        # Add new subscriber
        new_subscriber = Subscriber(
            list_id=mailing_list.id,
            name=name,
            email=email,
            comment=comment,
            subscriber_type=subscriber_type,
        )
        db.session.add(new_subscriber)
        db.session.commit()
        flash(_('Successfully added "%(email)s" to the list!', email=email), "success")

        return redirect(url_for("lists.subscribers_manage", list_id=list_id))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    # Flash if list is deactivated
    if mailing_list.deleted:
        flash(
            _("This mailing list is deactivated. Reactivate it to process incoming emails."),
            "warning",
        )

    # Get recursive subscribers for display
    # all_recursive_subscribers = get_list_subscribers(mailing_list)
    subscribers_direct = cast(list[Subscriber], mailing_list.subscribers)
    subscriber_lists = [
        is_email_a_list(s.email) for s in subscribers_direct if s.subscriber_type == "list"
    ]
    subscribers_indirect = {}
    for sub_list in subscriber_lists:
        if sub_list:
            subscribers_indirect[sub_list] = get_list_subscribers(sub_list)

    return render_template(
        "lists/subscribers_manage.html",
        mailing_list=mailing_list,
        subscribers_indirect=subscribers_indirect,
        form=form,
    )


@lists.route("/<int:list_id>/subscribers/<int:subscriber_id>/delete", methods=["GET"])
def subscriber_delete(list_id, subscriber_id):
    """Delete a subscriber from a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    subscriber = Subscriber.query.get_or_404(subscriber_id)
    if subscriber.list_id == mailing_list.id:
        email = subscriber.email
        db.session.delete(subscriber)
        db.session.commit()
        flash(_('Successfully removed "%(email)s" from the list!', email=email), "success")
        logging.info('Subscriber "%s" removed from mailing list %s', email, mailing_list.address)
    return redirect(url_for("lists.subscribers_manage", list_id=list_id))


@lists.route("/<int:list_id>/subscribers/<int:subscriber_id>/edit", methods=["GET", "POST"])
def subscriber_edit(list_id, subscriber_id):
    """Edit a subscriber of a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    subscriber: Subscriber = Subscriber.query.get_or_404(subscriber_id)
    form = SubscriberAddForm(obj=subscriber)
    if form.validate_on_submit():

        # Check if subscriber with new email already exists in this list
        existing_subscriber = Subscriber.query.filter_by(
            list_id=mailing_list.id, email=form.email.data
        ).first()
        # Avoid false positive when the email is unchanged (same subscriber)
        if existing_subscriber and existing_subscriber.id != subscriber.id:
            flash(
                _(
                    'Email "%(email)s" is already subscribed to this list.',
                    email=form.email.data,
                ),
                "warning",
            )
            return redirect(
                url_for(
                    "lists.subscriber_edit",
                    mailing_list=mailing_list,
                    form=form,
                    subscriber=subscriber,
                )
            )

        # Update subscriber fields from form
        subscriber.name = form.name.data
        subscriber.email = form.email.data
        subscriber.comment = form.comment.data

        # Check if subscriber is an existing list. If so, set type and re-use name
        if existing_list := is_email_a_list(form.email.data):
            subscriber.name = existing_list.name
            subscriber.subscriber_type = "list"
        else:
            subscriber.subscriber_type = "normal"

        # Commit updates
        db.session.commit()
        flash(_("Subscriber updated successfully!"), "success")
        logging.info(
            'Subscriber "%s" updated in mailing list %s', subscriber.email, mailing_list.address
        )
        return redirect(url_for("lists.subscribers_manage", list_id=list_id))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    # Flash if list is deactivated
    if mailing_list.deleted:
        flash(
            _(
                "This mailing list is deactivated. The subscriber won't receive any emails "
                "until you reactivate it."
            ),
            "warning",
        )

    # Flash if subscriber is itself a list
    if is_email_a_list(subscriber.email):
        flash(_("Note: This subscriber is itself a mailing list."), "message")

    return render_template(
        "lists/subscriber_edit.html", mailing_list=mailing_list, form=form, subscriber=subscriber
    )
