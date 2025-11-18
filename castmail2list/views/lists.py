"""Lists blueprint for CastMail2List application"""

from datetime import datetime, timezone

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_babel import _
from flask_login import login_required

from ..config import Config
from ..forms import MailingListForm, SubscriberAddForm
from ..models import List, Subscriber, db
from ..utils import (
    flash_form_errors,
    is_email_a_list,
    json_array_to_string,
    normalize_email_list,
    string_to_json_array,
)

lists = Blueprint("lists", __name__, url_prefix="/lists")



@lists.route("/", methods=["GET"])
@login_required
def show_all():
    """Show all mailing lists"""
    active_lists = List.query.filter_by(deleted=False).all()
    return render_template("lists/index.html", lists=active_lists, config=Config)

@lists.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add a new mailing list"""
    form = MailingListForm()

    if form.validate_on_submit():
        # Convert input to comma-separated for storage
        allowed_senders_data = normalize_email_list(form.allowed_senders.data)

        new_list = List(
            mode=form.mode.data,
            name=form.name.data,
            address=form.address.data,
            from_addr=form.from_addr.data or "",
            # Mode settings
            only_subscribers_send=form.only_subscribers_send.data,
            allowed_senders=allowed_senders_data or "",
            sender_auth=string_to_json_array(form.sender_auth.data),
            # IMAP settings with defaults
            imap_host=form.imap_host.data or Config.IMAP_DEFAULT_HOST,
            imap_port=form.imap_port.data or Config.IMAP_DEFAULT_PORT,
            imap_user=form.imap_user.data or form.address.data,
            imap_pass=form.imap_pass.data or Config.IMAP_DEFAULT_PASS,
        )
        db.session.add(new_list)
        db.session.commit()
        flash(_('Mailing list "%(name)s" created successfully!', name=new_list.name), "success")
        return redirect(url_for("lists.show_all"))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    return render_template("lists/add.html", config=Config, form=form)


@lists.route("/<int:list_id>/edit", methods=["GET", "POST"])
@login_required
def edit(list_id):
    """Edit a mailing list"""
    mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
    form = MailingListForm(obj=mailing_list)

    # Handle form submission
    if form.validate_on_submit():
        # Only update imap_pass if a new value is provided
        old_pass = mailing_list.imap_pass
        form.populate_obj(mailing_list)
        if not form.imap_pass.data:
            mailing_list.imap_pass = old_pass

        # Convert input to comma-separated for storage
        mailing_list.allowed_senders = normalize_email_list(form.allowed_senders.data)

        # Convert sender_auth to JSON array
        mailing_list.sender_auth = string_to_json_array(form.sender_auth.data)

        db.session.commit()
        flash(_('List "%(name)s" updated successfully!', name=mailing_list.name), "success")
        return redirect(url_for("lists.show_all"))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    # Case: GET request, pre-fill sender_auth field
    if not form.submit.data:
        form.sender_auth.data = json_array_to_string(mailing_list.sender_auth)

    return render_template("lists/edit.html", mailing_list=mailing_list, form=form)


@lists.route("/<int:list_id>/subscribers", methods=["GET", "POST"])
@login_required
def subscribers_manage(list_id):
    """Manage subscribers for a mailing list"""
    mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
    form = SubscriberAddForm()

    # Handle adding subscribers
    if form.submit.data and form.validate_on_submit():
        name = form.name.data
        email = form.email.data.strip().lower()  # normalize before lookup/insert
        comment = form.comment.data
        subscriber_type = "list" if is_email_a_list(email) else "normal"
        # Check if subscriber already exists, identified by email and list_id
        existing_subscriber = Subscriber.query.filter_by(
            list_id=mailing_list.id, email=email
        ).first()

        if not existing_subscriber:
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
        else:
            flash(
                _('Email "%(email)s" is already subscribed to this list.', email=email),
                "warning",
            )

        return redirect(url_for("lists.subscribers_manage", list_id=list_id))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    return render_template(
        "lists/subscribers_manage.html",
        mailing_list=mailing_list,
        form=form,
    )


@lists.route("/<int:list_id>/delete", methods=["GET"])
@login_required
def delete(list_id):
    """Delete (soft-delete) a mailing list"""
    mailing_list: List = List.query.filter_by(id=list_id, deleted=False).first_or_404()
    # Soft-delete: mark the list deleted so IDs remain for messages/subscribers
    mailing_list.deleted = True
    mailing_list.deleted_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(_('List "%(name)s" marked deleted successfully!', name=mailing_list.name), "success")
    return redirect(url_for("lists.show_all"))


@lists.route("/<int:list_id>/subscribers/<int:subscriber_id>/delete", methods=["GET"])
@login_required
def subscriber_delete(list_id, subscriber_id):
    """Delete a subscriber from a mailing list"""
    mailing_list = List.query.filter_by(id=list_id).first_or_404()
    subscriber = Subscriber.query.get_or_404(subscriber_id)
    if subscriber.list_id == mailing_list.id:
        email = subscriber.email
        db.session.delete(subscriber)
        db.session.commit()
        flash(_('Successfully removed "%(email)s" from the list!', email=email), "success")
    return redirect(url_for("lists.subscribers_manage", list_id=list_id))


@lists.route("/<int:list_id>/subscribers/<int:subscriber_id>/edit", methods=["GET", "POST"])
@login_required
def subscriber_edit(list_id, subscriber_id):
    """Edit a subscriber of a mailing list"""
    mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
    subscriber: Subscriber = Subscriber.query.get_or_404(subscriber_id)
    form = SubscriberAddForm(obj=subscriber)
    if form.validate_on_submit():
        subscriber.name = form.name.data
        subscriber.email = form.email.data
        subscriber.comment = form.comment.data
        subscriber.subscriber_type = "list" if is_email_a_list(form.email.data) else "normal"

        # Check if subscriber with new email already exists
        existing_subscriber = Subscriber.query.filter_by(
            list_id=mailing_list.id, email=form.email.data
        ).first()
        if existing_subscriber and existing_subscriber.id != subscriber.id:
            flash(
                _(
                    'Email "%(email)s" is already subscribed to this list.',
                    email=form.email.data,
                ),
                "warning",
            )
            return render_template(
                "lists/subscriber_edit.html",
                mailing_list=mailing_list,
                form=form,
                subscriber=subscriber,
            )

        # Commit updates
        db.session.commit()
        flash(_("Subscriber updated successfully!"), "success")
        return redirect(url_for("lists.subscribers_manage", list_id=list_id))

    # Flash on form errors
    if form.submit.data and form.errors:
        flash_form_errors(form)

    return render_template(
        "lists/subscriber_edit.html", mailing_list=mailing_list, form=form, subscriber=subscriber
    )
