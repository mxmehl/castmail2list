"""Flask routes for castmail2list application"""

from datetime import datetime, timezone

from flask import Flask, flash, redirect, render_template, url_for
from flask_babel import _

from .config import Config
from .forms import MailingListForm, SubscriberAddForm
from .models import List, Message, Subscriber, db
from .utils import flash_form_errors, normalize_email_list


def init_routes(app: Flask):  # pylint: disable=too-many-statements
    """Initialize Flask routes"""

    @app.route("/")
    def index():
        lists = List.query.filter_by(deleted=False).all()
        return render_template("index.html", lists=lists)

    @app.route("/messages")
    def messages() -> str:
        msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return render_template("messages.html", messages=msgs)

    @app.route("/lists", methods=["GET"])
    def lists():
        lists = List.query.filter_by(deleted=False).all()
        return render_template("lists.html", lists=lists, config=Config)

    @app.route("/lists/add", methods=["GET", "POST"])
    def list_add():
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
                # IMAP settings with defaults
                imap_host=form.imap_host.data or Config.IMAP_DEFAULT_HOST,
                imap_port=form.imap_port.data or Config.IMAP_DEFAULT_PORT,
                imap_user=form.imap_user.data or form.address.data,
                imap_pass=form.imap_pass.data or Config.IMAP_DEFAULT_PASS,
            )
            db.session.add(new_list)
            db.session.commit()
            flash(_('Mailing list "%(name)s" created successfully!', name=new_list.name), "success")
            return redirect(url_for("lists"))

        # Flash on form errors
        if form.submit.data and form.errors:
            flash_form_errors(form)

        return render_template("list_add.html", config=Config, form=form)

    @app.route("/lists/<int:list_id>/edit", methods=["GET", "POST"])
    def list_edit(list_id):
        mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
        form = MailingListForm(obj=mailing_list)

        if form.validate_on_submit():
            # Only update imap_pass if a new value is provided
            old_pass = mailing_list.imap_pass
            form.populate_obj(mailing_list)
            if not form.imap_pass.data:
                mailing_list.imap_pass = old_pass

            # Convert input to comma-separated for storage
            mailing_list.allowed_senders = normalize_email_list(form.allowed_senders.data)

            db.session.commit()
            flash(_('List "%(name)s" updated successfully!', name=mailing_list.name), "success")
            return redirect(url_for("lists"))

        # Flash on form errors
        if form.submit.data and form.errors:
            flash_form_errors(form)

        return render_template("list_edit.html", mailing_list=mailing_list, form=form)

    @app.route("/lists/<int:list_id>/subscribers", methods=["GET", "POST"])
    def list_subscribers(list_id):
        mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
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

            if not existing_subscriber:
                new_subscriber = Subscriber(
                    list_id=mailing_list.id, name=name, email=email, comment=comment
                )
                db.session.add(new_subscriber)
                db.session.commit()
                flash(_('Successfully added "%(email)s" to the list!', email=email), "success")
            else:
                flash(
                    _('Email "%(email)s" is already subscribed to this list.', email=email),
                    "warning",
                )

            return redirect(url_for("list_subscribers", list_id=list_id))

        # Flash on form errors
        if form.submit.data and form.errors:
            flash_form_errors(form)

        return render_template(
            "list_subscribers.html",
            mailing_list=mailing_list,
            add_form=form,
        )

    @app.route("/lists/<int:list_id>/delete", methods=["GET"])
    def list_delete(list_id):
        mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
        # Soft-delete: mark the list deleted so IDs remain for messages/subscribers
        mailing_list.deleted = True
        mailing_list.deleted_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(_('List "%(name)s" marked deleted successfully!', name=mailing_list.name), "success")
        return redirect(url_for("lists"))

    @app.route("/lists/<int:list_id>/subscribers/<int:subscriber_id>/delete", methods=["GET"])
    def list_subscriber_delete(list_id, subscriber_id):
        mailing_list = List.query.filter_by(id=list_id).first_or_404()
        subscriber = Subscriber.query.get_or_404(subscriber_id)
        if subscriber.list_id == mailing_list.id:
            email = subscriber.email
            db.session.delete(subscriber)
            db.session.commit()
            flash(_('Successfully removed "%(email)s" from the list!', email=email), "success")
        return redirect(url_for("list_subscribers", list_id=list_id))

    @app.route("/lists/<int:list_id>/subscribers/<int:subscriber_id>/edit", methods=["GET", "POST"])
    def list_subscriber_edit(list_id, subscriber_id):
        mailing_list = List.query.filter_by(id=list_id, deleted=False).first_or_404()
        subscriber = Subscriber.query.get_or_404(subscriber_id)
        form = SubscriberAddForm(obj=subscriber)
        if form.validate_on_submit():
            subscriber.name = form.name.data
            subscriber.email = form.email.data
            subscriber.comment = form.comment.data
            db.session.commit()
            flash(_("Subscriber updated successfully!"), "success")
            return redirect(url_for("list_subscribers", list_id=list_id))

        # Flash on form errors
        if form.submit.data and form.errors:
            flash_form_errors(form)

        return render_template(
            "list_subscriber_edit.html", mailing_list=mailing_list, form=form, subscriber=subscriber
        )

    @app.route("/subscriber/<email>")
    def subscriber(email):
        """Show which lists a subscriber is part of"""
        # Find all subscriptions for this email address
        email_norm = email.strip().lower()
        subscriptions = Subscriber.query.filter_by(email=email_norm).all()

        if not subscriptions:
            flash(_('No subscriptions found for "%(email)s"', email=email), "warning")
            return render_template("subscriber.html", email=email)

        # Get list information for each subscription
        subscriber_lists = []
        for sub in subscriptions:
            mailing_list = List.query.get(sub.list_id)
            if mailing_list:
                subscriber_lists.append({"list": mailing_list, "subscriber": sub})

        return render_template("subscriber.html", email=email, subscriber_lists=subscriber_lists)

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Manage application settings"""

        return render_template("settings.html", config=Config)
