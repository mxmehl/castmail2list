<!--
  SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
  SPDX-License-Identifier: CC-BY-4.0
-->

# Security Practices

This document captures security rules derived from CastMail2List's security audit. Follow
these when adding features or modifying the codebase. They exist because the same class of
mistake was previously made or nearly made; don't repeat them.

## 1. Never Use GET for State-Changing Operations

Any route that modifies data (delete, deactivate, reactivate, etc.) **must** use POST, not
GET. GET requests are logged, bookmarked, prefetched, and embeddable in `<img>` tags — all
of which can trigger state changes without user intent (CSRF).

**Pattern:** Redirect a GET to a confirmation page; only perform the action on POST.
Use the shared `confirm_action.html` template for this. See [Issue #3 in SECURITY_REPORT.md].

```python
# Wrong
@bp.route("/<list_id>/subscribers/<email>/delete")
def subscriber_delete(list_id, email):
    delete_subscriber(...)  # performs the action on GET

# Correct
@bp.route("/<list_id>/subscribers/<email>/delete", methods=["GET", "POST"])
def subscriber_delete(list_id, email):
    if request.method == "POST":
        delete_subscriber(...)
    return render_template("confirm_action.html", ...)
```

## 2. Never Pass User Input to Flash Messages Without Escaping

Jinja2's `| safe` filter disables autoescaping for **all** flash messages globally.
Do not add or re-introduce `| safe` in `flash.html`. If a specific message needs to embed
HTML (e.g., a link), wrap only that string in `Markup()` at the call site before passing
it to `flash()`.

```python
# Wrong — user-controlled email ends up unescaped in the browser
flash(f"Subscriber {subscriber_email} not found", "error")  # with | safe in template

# Correct — let Jinja2 autoescape the interpolated value
flash(f"Subscriber {subscriber_email} not found", "error")  # template must NOT use | safe

# Correct — intentional HTML: wrap only this specific message
from markupsafe import Markup
flash(Markup('See <a href="/help">help</a> for details'), "info")
```

## 3. Validate All Redirect Targets

Never redirect to a URL taken directly from user input (`request.args`, `request.form`,
etc.) without validation. An attacker can supply an absolute URL pointing to a phishing
site.

```python
from werkzeug.utils import url_has_allowed_host_and_scheme

# Wrong
return redirect(request.args.get("next"))

# Correct
next_url = request.args.get("next")
if next_url and url_has_allowed_host_and_scheme(next_url, host=request.host):
    return redirect(next_url)
return redirect(url_for("general.index"))
```

## 4. Redact Sensitive Values in Logs

Never log secrets, passwords, or credentials verbatim — even in debug mode. This includes:

- `SECRET_KEY`, `SMTP_PASS`, `IMAP_DEFAULT_PASS`, and any config key containing
  `SECRET`, `PASS`, or `KEY`
- Sender authentication passwords (`plus_suffix` in IMAP worker)

Use the shared `redact()` helper in `utils.py`, which exposes ~50% of the value and masks
the rest.

```python
# Wrong
logging.debug("App configuration:\n%s", app.config)
logging.debug("Auth password: %s", plus_suffix)

# Correct
logging.debug("Auth password: %s", redact(plus_suffix))
# For config, filter sensitive keys first — see app.py for the pattern
```

## 5. Do Not Mix Session Auth Into CSRF-Exempt Endpoints

The API blueprint is marked CSRF-exempt because it uses Bearer token authentication, which
is the correct choice. Do not add session-cookie-based authentication to this same
blueprint. A CSRF-exempt endpoint that also accepts session cookies is vulnerable to
cross-origin requests using the user's browser session.

```python
# Wrong — session auth on a CSRF-exempt blueprint
def api_auth_required(f):
    if current_user.is_authenticated:   # accepts session cookies
        return f(*args, **kwargs)
    token = request.headers.get("Authorization")
    ...

# Correct — Bearer token only, no session fallback
def api_auth_required(f):
    token = request.headers.get("Authorization")
    ...
```

## 6. Whitelist ORM Query Parameters Derived from User Input

Do not pass user-controlled values directly as `**kwargs` key names to ORM query helpers.
Even if SQLAlchemy parameterizes the values, an attacker can probe arbitrary columns.
Validate the field name against an explicit allowlist before using it.

```python
# Wrong
column = request.args.get("search_field")
results = get_log_entries(**{column: search_text})

# Correct
ALLOWED_SEARCH_FIELDS = {"sender", "subject", "list_id"}
column = request.args.get("search_field")
if column not in ALLOWED_SEARCH_FIELDS:
    abort(400)
results = get_log_entries(**{column: search_text})
```

## 7. Protect Subprocess Calls Against Flag Injection

When calling external programs using list-based `subprocess.run()`, always separate
options from positional arguments with `--`. A user-supplied value starting with `-` would
otherwise be interpreted as a flag by the external command.

```python
# Wrong
cmd = ["uberspace", "mail", "user", "add", "-p", password, username]

# Correct
cmd = ["uberspace", "mail", "user", "add", "-p", password, "--", username]
```

## 8. Validate SECRET_KEY at Startup

An empty or missing `SECRET_KEY` makes Flask sessions and CSRF tokens trivially forgeable.
Always check for this in `create_app()` and raise a `ValueError` immediately — fail fast
rather than silently accepting an insecure default.

```python
# Wrong — empty string as default
SECRET_KEY: str = ""

# Correct — validate at startup
if not app.config.get("SECRET_KEY"):
    raise ValueError("SECRET_KEY must be set and non-empty in the configuration.")
```

## 9. Configure Remember-Me Cookie Security Explicitly

Flask-Login's remember-me cookie is separate from the session cookie. Its `SameSite`
attribute is not inherited from `SESSION_COOKIE_SAMESITE`. Always set the following in
your Flask config to prevent it from being sent on cross-origin requests:

```python
REMEMBER_COOKIE_SECURE = True
REMEMBER_COOKIE_HTTPONLY = True
REMEMBER_COOKIE_SAMESITE = "Lax"
```

## 10. Set HTTP Security Headers

Add an `@app.after_request` handler that sets at minimum:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Strict-Transport-Security` (when served over HTTPS)
- `Content-Security-Policy` (at least restrict `default-src`)

Alternatively, use `flask-talisman` to manage these declaratively.

## 11. Understand the Email Notification Spam-Relay Risk

Sending rejection notifications to **any** From address in incoming mail (i.e.,
`NOTIFY_REJECTED_SENDERS=True` with `NOTIFY_REJECTED_KNOWN_ONLY=False`) turns the SMTP
server into a relay for unsolicited email: an attacker sends a message to a list with a
forged From header, and the app dutifully notifies that address.

The default configuration (`NOTIFY_REJECTED_KNOWN_ONLY=True`) is safe. Never change both
settings simultaneously without explicitly acknowledging the spam-relay risk.

## 12. Encrypt Credentials Stored in the Database

Passwords and credentials stored in database columns should be encrypted at rest, not
stored as plaintext strings. Use `cryptography.fernet.Fernet` keyed from `SECRET_KEY` to
encrypt on write and decrypt on read. Pair this with:

- Ensuring the `instance/` directory is never served by the web server.
- Treating `.db` backup files as sensitive — encrypt or restrict access.

Any schema change for encryption requires an Alembic migration that re-encrypts existing
rows.
