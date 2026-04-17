# SPDX-FileCopyrightText: 2025 Max Mehl <https://mehl.mx>
#
# SPDX-License-Identifier: Apache-2.0

"""Tests for route responses in the Castmail2List application."""

from .conftest import add_subscriber


def test_main_route_status_code(client):
    """Test that the main route returns a 200 status code."""
    response = client.get("/")
    assert response.status_code == 200


def test_subscriber_does_not_exist(client):
    """Test that the subscriber route returns a 404 status code if subscriber does not exist."""
    response = client.get("/subscriber/noexist@example.com")
    assert response.status_code == 404


def test_subscriber_exists(client):
    """Test that the subscriber route returns a 200 status code if subscriber exists."""
    add_subscriber(email="user@example.com", list_id=1)
    response = client.get("/subscribers/user@example.com")
    assert response.status_code == 200


def test_template_lists_unauthed(client_unauthed):
    """Ensure that the lists template redirects unauthenticated users to login."""
    response = client_unauthed.get("/lists/")
    assert response.status_code == 302  # Redirect to login
    assert response.location.endswith("/login?next=%2Flists%2F")


# ---------- Error handler tests ----------


def test_404_html_response(client):
    """A request to a non-existent web route should return HTML with 404 status."""
    response = client.get("/nonexistent-page")
    assert response.status_code == 404
    assert response.content_type.startswith("text/html")
    assert b"404" in response.data


def test_404_api_json_response(client):
    """A request to a non-existent API route should return JSON with 404 status."""
    response = client.get("/api/v1/nonexistent-endpoint")
    assert response.status_code == 404
    assert response.content_type == "application/json"
    data = response.get_json()
    assert data["status"] == 404
    assert "message" in data


def test_405_html_response(client):
    """A method-not-allowed request to a web route should return HTML with 405 status."""
    response = client.delete("/")
    assert response.status_code == 405
    assert response.content_type.startswith("text/html")


def test_405_api_json_response(client):
    """A method-not-allowed request to an API route should return JSON with 405 status."""
    response = client.delete("/api/v1/status")
    assert response.status_code == 405
    assert response.content_type == "application/json"
    data = response.get_json()
    assert data["status"] == 405
