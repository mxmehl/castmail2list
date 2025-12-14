"""Lists blueprint for CastMail2List application"""

import logging

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import login_required

from ..config import AppConfig
from ..forms import MailingListForm, SubscriberAddForm
from ..models import EmailIn, EmailOut, Logs, MailingList, Subscriber, db
from ..services import (
    add_subscriber_to_list,
    delete_subscriber_from_list,
    update_subscriber_in_list,
)
from ..utils import (
    check_email_account_works,
    check_recommended_list_setting,
    create_email_account,
    flash_form_errors,
    get_list_recipients_recursive,
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
    active_lists: list[MailingList] = (
        MailingList.query.order_by(MailingList.id).filter_by(deleted=False).all()
    )
    return render_template("lists/index.html", lists=active_lists, config=AppConfig)


@lists.route("/deactivated", methods=["GET"])
def deactivated():
    """Show all deactivated mailing lists"""
    deactivated_lists: list[MailingList] = (
        MailingList.query.order_by(MailingList.id).filter_by(deleted=True).all()
    )
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
        address = f"{form.id.data.strip().lower()}@{current_app.config['DOMAIN']}"
        new_list = MailingList(
            id=form.id.data.strip().lower(),
            address=address,
            display=form.display.data,
            mode=form.mode.data,
            from_addr=form.from_addr.data or "",
            # Mode settings
            only_subscribers_send=form.only_subscribers_send.data,
            allowed_senders=string_to_list(form.allowed_senders.data, lower=True),
            sender_auth=string_to_list(form.sender_auth.data),
            # IMAP settings with defaults
            imap_host=form.imap_host.data or current_app.config["IMAP_DEFAULT_HOST"],
            imap_port=form.imap_port.data or current_app.config["IMAP_DEFAULT_PORT"],
            imap_user=form.imap_user.data or address,
            imap_pass=form.imap_pass.data or current_app.config["IMAP_DEFAULT_PASS"],
        )
        # Verify that the list address is unique by checking the DB for the ID
        existing_list = MailingList.query.filter_by(id=new_list.id).first()
        if existing_list:
            status = "deactivated" if existing_list.deleted else "active"
            flash(
                _(
                    'A mailing list with the name "%(name)s" (%(status)s) already exists.',
                    name=new_list.id,
                    status=status,
                ),
                "error",
            )
            logging.warning(
                'Attempt to create mailing list with name "%s" failed. It already exists in DB.',
                new_list.id,
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
        flash(_('Mailing list "%(name)s" created successfully!', name=new_list.address), "success")
        logging.info('Mailing list "%s" created', new_list.address)

        # Check recommended settings and flash warnings if needed
        for finding in check_recommended_list_setting(ml=new_list):
            flash(finding[0], finding[1])

        return redirect(url_for("lists.index"))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    return render_template("lists/add.html", config=AppConfig, form=form)


@lists.route("/<list_id>/edit", methods=["GET", "POST"])
def edit(list_id: str):
    """Edit a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    form = MailingListForm(obj=mailing_list)

    # Handle form submission
    if form.validate_on_submit():
        # Verify that the list address is unique
        new_id = form.id.data.strip().lower()
        existing_list: MailingList | None = MailingList.query.filter_by(id=new_id).first()
        if existing_list is not None and existing_list.id != mailing_list.id:
            status = _("deactivated") if existing_list.deleted else _("active")
            flash(
                _(
                    'A mailing list with the name "%(name)s" (%(status)s) already exists.',
                    name=new_id,
                    status=status,
                ),
                "error",
            )
            logging.warning(
                "Attempt to change list %s's name to '%s' failed. It already exists in DB.",
                mailing_list.id,
                new_id,
            )
            return render_template(
                "lists/edit.html", mailing_list=mailing_list, form=form, retry=True
            )

        # Detect change of ID
        old_id = mailing_list.id
        if new_id != old_id:
            flash(
                _(
                    "You changed the name of the mailing list. However, this did not change the "
                    "IMAP data automatically, so it still fetches from the same mail box."
                ),
                "warning",
            )

        # Only update imap_pass if a new value is provided
        old_pass = mailing_list.imap_pass
        form.populate_obj(mailing_list)
        if not form.imap_pass.data:
            mailing_list.imap_pass = old_pass

        # Address needs to be updated if ID changed
        mailing_list.address = f"{new_id}@{current_app.config['DOMAIN']}"

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
        mailing_list.allowed_senders = string_to_list(form.allowed_senders.data, lower=True)
        mailing_list.sender_auth = string_to_list(form.sender_auth.data)

        # Handle ID change by updating related records first
        if new_id != old_id:
            # Update all related records to point to the new ID
            Subscriber.query.filter_by(list_id=old_id).update({"list_id": new_id})
            EmailIn.query.filter_by(list_id=old_id).update({"list_id": new_id})
            EmailOut.query.filter_by(list_id=old_id).update({"list_id": new_id})
            Logs.query.filter_by(list_id=old_id).update({"list_id": new_id})

            # Now update the primary key
            mailing_list.id = new_id

        db.session.commit()
        flash(_('List "%(name)s" updated successfully!', name=mailing_list.display), "success")
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


@lists.route("/<list_id>/deactivate", methods=["GET"])
def deactivate(list_id: str):
    """Deactivate a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(
        id=list_id, deleted=False
    ).first_or_404()
    mailing_list.deactivate()  # Use the soft_delete method from the model
    db.session.commit()
    flash(_('List "%(name)s" deactivated successfully!', name=mailing_list.display), "success")
    logging.info('Mailing list "%s" deactivated', mailing_list.address)
    return redirect(url_for("lists.index"))


@lists.route("/<list_id>/reactivate", methods=["GET"])
def reactivate(list_id: str):
    """Reactivate a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id, deleted=True).first_or_404()
    mailing_list.reactivate()  # Use the reactivate method from the model
    db.session.commit()
    flash(_('List "%(name)s" reactivated successfully!', name=mailing_list.display), "success")
    logging.info('Mailing list "%s" reactivated', mailing_list.address)
    return redirect(url_for("lists.index"))


# -----------------------------------------------------------------
# Managing subscribers of lists
# -----------------------------------------------------------------


@lists.route("/<list_id>/subscribers", methods=["GET", "POST"])
def subscribers_manage(list_id):
    """Manage subscribers of a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    form = SubscriberAddForm()

    # Handle adding subscribers
    if form.submit.data and form.validate_on_submit():
        name = form.name.data
        email = form.email.data
        comment = form.comment.data

        # Use service layer to add subscriber
        error = add_subscriber_to_list(list_id, email=email, name=name, comment=comment)
        if error:
            flash(error, "error")
        else:
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

    # Get recipients that are exclusively indirect
    recipients_indirect = get_list_recipients_recursive(list_id=list_id, only_indirect=True)

    return render_template(
        "lists/subscribers_manage.html",
        mailing_list=mailing_list,
        subscribers_direct=get_list_subscribers(list_id=list_id),
        recipients_indirect=recipients_indirect,
        form=form,
    )


@lists.route("/<list_id>/subscribers/<subscriber_email>/delete", methods=["GET"])
def subscriber_delete(list_id: str, subscriber_email: str):
    """Delete a subscriber from a mailing list"""
    # Use service layer to delete subscriber
    error = delete_subscriber_from_list(list_id, subscriber_email)
    if error:
        flash(_(error), "error")
    else:
        flash(
            _('Successfully removed "%(email)s" from the list!', email=subscriber_email), "success"
        )
    return redirect(url_for("lists.subscribers_manage", list_id=list_id))


@lists.route("/<list_id>/subscribers/<subscriber_email>/edit", methods=["GET", "POST"])
def subscriber_edit(list_id: str, subscriber_email: str):
    """Edit a subscriber of a mailing list"""
    mailing_list: MailingList = MailingList.query.filter_by(id=list_id).first_or_404()
    subscriber: Subscriber = Subscriber.query.filter_by(
        list_id=list_id, email=subscriber_email
    ).first_or_404()
    form = SubscriberAddForm(obj=subscriber)

    if form.validate_on_submit():
        # Use service layer to update subscriber
        error = update_subscriber_in_list(
            list_id=list_id,
            subscriber_id=subscriber.id,
            name=form.name.data,
            email=form.email.data,
            comment=form.comment.data,
        )
        if error:
            flash(_(error), "warning")
            return render_template(
                "lists/subscriber_edit.html",
                mailing_list=mailing_list,
                form=form,
                subscriber=subscriber,
            )
        flash(
            _('Subscriber "%(email)s" updated successfully!', email=subscriber.email),
            "success",
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
