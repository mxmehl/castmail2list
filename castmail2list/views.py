"""Flask routes for castmail2list application"""

from flask import Flask, redirect, render_template_string, request, url_for

from .config import Config
from .models import List, Message, Subscriber, db


def init_routes(app: Flask):
    """Initialize Flask routes"""
    @app.route("/")
    def index():
        lists = List.query.all()
        return "<h2>Lists</h2>" + "<br>".join(
            [f"{l.name} ({len(l.subscribers)} subs)" for l in lists]
        )

    @app.route("/messages")
    def messages() -> str:
        msgs: list[Message] = Message.query.order_by(Message.received_at.desc()).limit(20).all()
        return "<br>".join([f"{m.received_at} - {m.subject}" for m in msgs])

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
                from_addr=request.form.get("from_addr", Config.IMAP_LIST_FROM),
            )
            db.session.add(l)
            db.session.commit()
            return redirect(url_for("settings"))
        lists = List.query.all()
        return render_template_string("""
        <h2>Mailing Lists</h2>
        <ul>
        {% for l in lists %}
          <li>
            {{ l.name }} ({{ l.address }})
            <a href="{{ url_for('edit_list', list_id=l.id) }}">Edit</a>
            <a href="{{ url_for('manage_subs', list_id=l.id) }}">Subscribers</a>
          </li>
        {% endfor %}
        </ul>
        <h3>Add List</h3>
        <form method="post">
          Name: <input name="name"><br>
          Address: <input name="address"><br>
          IMAP Host: <input name="imap_host" value="{{ config.IMAP_DEFAULT_HOST }}"><br>
          IMAP Port: <input name="imap_port" value="{{ config.IMAP_DEFAULT_PORT }}"><br>
          IMAP User: <input name="imap_user"><br>
          IMAP Pass: <input name="imap_pass" value="{{ config.IMAP_DEFAULT_PASS }}"><br>
          From Address: <input name="from_addr" value="{{ config.IMAP_LIST_FROM }}"><br>
          <input type="submit" value="Add List">
        </form>
        """, lists=lists, config=Config)

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
        return render_template_string("""
        <h3>Edit List</h3>
        <form method="post">
          Name: <input name="name" value="{{ l.name }}"><br>
          Address: <input name="address" value="{{ l.address }}"><br>
          IMAP Host: <input name="imap_host" value="{{ l.imap_host }}"><br>
          IMAP Port: <input name="imap_port" value="{{ l.imap_port }}"><br>
          IMAP User: <input name="imap_user" value="{{ l.imap_user }}"><br>
          IMAP Pass: <input name="imap_pass" value="{{ l.imap_pass }}"><br>
          From Address: <input name="from_addr" value="{{ l.from_addr }}"><br>
          <input type="submit" value="Save">
        </form>
        """, l=l)

    @app.route("/settings/<int:list_id>/subscribers", methods=["GET", "POST"])
    def manage_subs(list_id):
        l = List.query.get_or_404(list_id)
        if request.method == "POST":
            # Add subscriber
            email = request.form["email"]
            if not any(s.email == email for s in l.subscribers):
                db.session.add(Subscriber(list_id=l.id, email=email))
                db.session.commit()
            return redirect(url_for("manage_subs", list_id=list_id))
        return render_template_string("""
        <h3>Subscribers for {{ l.name }}</h3>
        <ul>
        {% for s in l.subscribers %}
          <li>{{ s.email }}</li>
        {% endfor %}
        </ul>
        <form method="post">
          Add subscriber: <input name="email">
          <input type="submit" value="Add">
        </form>
        <a href="{{ url_for('settings') }}">Back to settings</a>
        """, l=l)
