"""Flask routes for castmail2list application"""

from flask import Flask, flash, redirect, render_template, request, url_for

from .config import Config
from .forms import MailingListForm, SubscriberAddForm, SubscriberDeleteForm
from .models import List, Message, Subscriber, db


def init_routes(app: Flask):
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
            new_list = List(
                name=form.name.data,
                address=form.address.data,
                imap_host=form.imap_host.data or Config.IMAP_DEFAULT_HOST,
                imap_port=form.imap_port.data or Config.IMAP_DEFAULT_PORT,
                imap_user=form.imap_user.data or "",
                imap_pass=form.imap_pass.data or Config.IMAP_DEFAULT_PASS,
                from_addr=form.from_addr.data or "",
            )
            db.session.add(new_list)
            db.session.commit()
            flash(f'Mailing list "{new_list.name}" created successfully!', "success")
            return redirect(url_for("lists"))

        return render_template("add_list.html", config=Config, form=form)

    @app.route("/lists/<int:list_id>/edit", methods=["GET", "POST"])
    def edit_list(list_id):
        mailing_list = List.query.get_or_404(list_id)
        form = MailingListForm(obj=mailing_list)

        if form.validate_on_submit():
            form.populate_obj(mailing_list)
            db.session.commit()
            flash(f'List "{mailing_list.name}" updated successfully!', "success")
            return redirect(url_for("lists"))

        return render_template("edit_list.html", mailing_list=mailing_list, form=form)

    @app.route("/lists/<int:list_id>/subscribers", methods=["GET", "POST"])
    def manage_subs(list_id):
        mailing_list = List.query.get_or_404(list_id)
        add_form = SubscriberAddForm()
        delete_form = SubscriberDeleteForm()

        # Handle adding subscribers
        if add_form.validate_on_submit():
            email = add_form.email.data
            existing_subscriber = Subscriber.query.filter_by(
                list_id=mailing_list.id, email=email
            ).first()

            if not existing_subscriber:
                new_subscriber = Subscriber(list_id=mailing_list.id, email=email)
                db.session.add(new_subscriber)
                db.session.commit()
                flash(f'Successfully added "{email}" to the list!', "success")
            else:
                flash(f'Email "{email}" is already subscribed to this list.', "warning")

            return redirect(url_for("manage_subs", list_id=list_id))

        # Handle removing subscribers
        if delete_form.validate_on_submit():
            sub_id = int(delete_form.subscriber_id.data)
            subscriber = Subscriber.query.get_or_404(sub_id)

            if subscriber.list_id == mailing_list.id:
                email = subscriber.email
                db.session.delete(subscriber)
                db.session.commit()
                flash(f'Successfully removed "{email}" from the list!', "success")

            return redirect(url_for("manage_subs", list_id=list_id))

        return render_template(
            "subscribers.html",
            mailing_list=mailing_list,
            add_form=add_form,
            delete_form=delete_form,
        )

    @app.route("/lists/<int:list_id>/delete", methods=["GET"])
    def delete_list(list_id):
        mailing_list = List.query.get_or_404(list_id)
        db.session.delete(mailing_list)
        db.session.commit()
        flash(f'List "{mailing_list.name}" deleted successfully!', "success")
        return redirect(url_for("lists"))
