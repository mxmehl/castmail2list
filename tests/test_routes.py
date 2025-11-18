"""Tests for route responses in the Castmail2List application"""


def test_main_route_status_code(client):
    """Test that the main route returns a 200 status code."""
    response = client.get("/")
    assert response.status_code == 200


def test_subscriber_route_status_code(client):
    """Test that the subscriber route returns a 200 status code."""
    response = client.get("/subscriber/test@example.com")
    assert response.status_code == 200


def test_template_lists_unauthed(client_unauthed):
    """Ensure that the lists template redirects unauthenticated users to login"""
    response = client_unauthed.get("/lists/")
    assert response.status_code == 302  # Redirect to login
    assert response.location.endswith("/login?next=%2Flists%2F")
