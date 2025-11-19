"""Tests for route responses in the Castmail2List application"""

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
    response = client.get("/subscriber/user@example.com")
    assert response.status_code == 200


def test_template_lists_unauthed(client_unauthed):
    """Ensure that the lists template redirects unauthenticated users to login"""
    response = client_unauthed.get("/lists/")
    assert response.status_code == 302  # Redirect to login
    assert response.location.endswith("/login?next=%2Flists%2F")
