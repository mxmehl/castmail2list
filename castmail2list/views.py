"""Flask routes for castmail2list application"""

from flask import Flask, redirect, render_template, request, url_for

from .config import Config
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

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            # Add new list
            l = List(
                name=request.form["name"],
                address=request.form["address"],
                imap_host=request.form.get("imap_host", Config.IMAP_DEFAULT_HOST),
                imap_port=request.form.get("imap_port", Config.IMAP_DEFAULT_PORT),
                imap_user=request.form.get("imap_user", ""),
                imap_pass=request.form.get("imap_pass", Config.IMAP_DEFAULT_PASS),
                from_addr=request.form.get("from_addr", ""),
            )
            db.session.add(l)
            db.session.commit()
            return redirect(url_for("settings"))
        lists = List.query.all()
        return render_template("settings.html", lists=lists, config=Config)

    @app.route("/settings/<int:list_id>/edit", methods=["GET", "POST"])
    def edit_list(list_id):
        l = List.query.get_or_404(list_id)
        if request.method == "POST":
            l.name = request.form["name"]
            l.address = request.form["address"]
            l.imap_host = request.form["imap_host"]
            l.imap_port = request.form["imap_port"]
            l.imap_user = request.form["imap_user"]
            l.imap_pass = request.form["imap_pass"]
            l.from_addr = request.form["from_addr"]
            db.session.commit()
            return redirect(url_for("settings"))
        return render_template("edit_list.html", l=l)

    @app.route("/settings/<int:list_id>/subscribers", methods=["GET", "POST"])
    def manage_subs(list_id):
        l = List.query.get_or_404(list_id)
        if request.method == "POST":
            if "delete" in request.form:
                # Delete subscriber
                sub_id = int(request.form["delete"])
                sub = Subscriber.query.get_or_404(sub_id)
                if sub.list_id == l.id:
                    db.session.delete(sub)
                    db.session.commit()
            else:
                # Add subscriber
                email = request.form["email"]
                if not any(s.email == email for s in l.subscribers):
                    db.session.add(Subscriber(list_id=l.id, email=email))
                    db.session.commit()
            return redirect(url_for("manage_subs", list_id=list_id))
        return render_template("subscribers.html", l=l)
