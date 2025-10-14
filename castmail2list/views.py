"""Flask routes for castmail2list application"""

from flask import Flask, flash, redirect, render_template, url_for

from .config import Config
from .forms import MailingListForm, SubscriberAddForm
from .models import List, Message, Subscriber, db


def init_routes(app: Flask):  # pylint: disable=too-many-statements
    """Initialize Flask routes"""

    @app.route("/")
    def index():
        lists = List.query.all()
        return render_template("index.html", lists=lists)

    @app.route("/messages")
    def messages() -> str:
        msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return render_template("messages.html", messages=msgs)

    @app.route("/lists", methods=["GET"])
    def lists():
        lists = List.query.all()
        return render_template("lists.html", lists=lists, config=Config)

    @app.route("/lists/add", methods=["GET", "POST"])
    def add_list():
        form = MailingListForm()

        if form.validate_on_submit():
            # Convert line-separated input to comma-separated for storage
            allowed_senders_data = ""
            if form.allowed_senders.data:
                emails = [
                    email.strip()
                    for email in form.allowed_senders.data.strip().split("\n")
                    if email.strip()
                ]
                allowed_senders_data = ", ".join(emails)

            new_list = List(
                mode=form.mode.data,
                name=form.name.data,
                address=form.address.data,
                imap_host=form.imap_host.data or Config.IMAP_DEFAULT_HOST,
                imap_port=form.imap_port.data or Config.IMAP_DEFAULT_PORT,
                imap_user=form.imap_user.data or "",
                imap_pass=form.imap_pass.data or Config.IMAP_DEFAULT_PASS,
                from_addr=form.from_addr.data or "",
                allowed_senders=allowed_senders_data or "",
            )
            db.session.add(new_list)
            db.session.commit()
            flash(f'Mailing list "{new_list.name}" created successfully!', "success")
            return redirect(url_for("lists"))

        # Flash on form errors
        if form.submit.data and form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}: {error}", "error")

        return render_template("add_list.html", config=Config, form=form)

    @app.route("/lists/<int:list_id>/edit", methods=["GET", "POST"])
    def edit_list(list_id):
        mailing_list = List.query.get_or_404(list_id)
        form = MailingListForm(obj=mailing_list)

        if form.validate_on_submit():
            # Only update imap_pass if a new value is provided
            old_pass = mailing_list.imap_pass
            form.populate_obj(mailing_list)
            if not form.imap_pass.data:
                mailing_list.imap_pass = old_pass

            # Convert line-separated input to comma-separated for storage
            if form.allowed_senders.data:
                emails = [
                    email.strip()
                    for email in form.allowed_senders.data.strip().split(",")
                    if email.strip()
                ]
                mailing_list.allowed_senders = ", ".join(emails)
            else:
                mailing_list.allowed_senders = ""

            db.session.commit()
            flash(f'List "{mailing_list.name}" updated successfully!', "success")
            return redirect(url_for("lists"))

        # Flash on form errors
        if form.submit.data and form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}: {error}", "error")

        return render_template("edit_list.html", mailing_list=mailing_list, form=form)

    @app.route("/lists/<int:list_id>/subscribers", methods=["GET", "POST"])
    def manage_subs(list_id):
        mailing_list = List.query.get_or_404(list_id)
        form = SubscriberAddForm()

        # Handle adding subscribers
        if form.submit.data and form.validate_on_submit():
            name = form.name.data
            email = form.email.data
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
                flash(f'Successfully added "{email}" to the list!', "success")
            else:
                flash(f'Email "{email}" is already subscribed to this list.', "warning")

            return redirect(url_for("manage_subs", list_id=list_id))

        # Flash on form errors
        if form.submit.data and form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}: {error}", "error")

        return render_template(
            "subscribers.html",
            mailing_list=mailing_list,
            add_form=form,
        )

    @app.route("/lists/<int:list_id>/delete", methods=["GET"])
    def delete_list(list_id):
        mailing_list = List.query.get_or_404(list_id)
        db.session.delete(mailing_list)
        db.session.commit()
        flash(f'List "{mailing_list.name}" deleted successfully!', "success")
        return redirect(url_for("lists"))

    @app.route("/lists/<int:list_id>/subscribers/<int:subscriber_id>/delete", methods=["GET"])
    def delete_subscriber(list_id, subscriber_id):
        mailing_list = List.query.get_or_404(list_id)
        subscriber = Subscriber.query.get_or_404(subscriber_id)
        if subscriber.list_id == mailing_list.id:
            email = subscriber.email
            db.session.delete(subscriber)
            db.session.commit()
            flash(f'Successfully removed "{email}" from the list!', "success")
        return redirect(url_for("manage_subs", list_id=list_id))

    @app.route("/lists/<int:list_id>/subscribers/<int:subscriber_id>/edit", methods=["GET", "POST"])
    def edit_subscriber(list_id, subscriber_id):
        mailing_list = List.query.get_or_404(list_id)
        subscriber = Subscriber.query.get_or_404(subscriber_id)
        form = SubscriberAddForm(obj=subscriber)
        if form.validate_on_submit():
            subscriber.name = form.name.data
            subscriber.email = form.email.data
            subscriber.comment = form.comment.data
            db.session.commit()
            flash("Subscriber updated successfully!", "success")
            return redirect(url_for("manage_subs", list_id=list_id))

        # Flash on form errors
        if form.submit.data and form.errors:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"Error in {getattr(form, field).label.text}: {error}", "error")

        return render_template(
            "edit_subscriber.html", mailing_list=mailing_list, form=form, subscriber=subscriber
        )
