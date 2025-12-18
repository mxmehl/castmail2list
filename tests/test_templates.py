# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for template rendering and content verification"""

from bs4 import BeautifulSoup


def test_template_root(client):
    """Ensure that the base template renders correctly with navigation and footer"""
    response = client.get("/")
    soup = BeautifulSoup(response.data, "html.parser")

    nav = soup.find("nav")
    assert nav is not None
    assert "CastMail2List" in nav.text
    assert nav.find("a", {"href": "/messages/"})
    assert nav.find("a", {"href": "/account"})

    footer = soup.find("footer")
    assert footer is not None
    assert "CastMail2List" in footer.text

    h2 = soup.find(name="h2")
    assert h2 is not None
    assert h2.string == "Overview"


def test_template_root_unauthed(client_unauthed):
    """Ensure that the base template renders correctly for unauthenticated users"""
    response = client_unauthed.get("/")

    assert response.status_code == 302  # Redirect to login
    assert response.location.endswith("/login?next=%2F")

    response = client_unauthed.get("/", follow_redirects=True)  # Follow redirect to login
    soup = BeautifulSoup(response.data, "html.parser")

    nav = soup.find("nav")
    assert nav is not None
    assert "CastMail2List" in nav.text
    assert not nav.find("a", {"href": "/messages/"})

    form = soup.find("form", {"method": "post"})
    assert form is not None
    assert form.find("input", {"name": "csrf_token"})
    assert form.find("input", {"name": "username"})
    assert form.find("input", {"name": "password"})
