"""Tests for the utils module"""

from castmail2list.utils import create_bounce_address, parse_bounce_address


def test_create_bounce_address_normal() -> None:
    """Test the create_bounce_address function: normal case"""
    original_email = "jane.doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=gmail.com@list.example.com"


def test_create_bounce_address_plus() -> None:
    """Test the create_bounce_address function: handling plus sign in email"""
    original_email = "jane.doe+test@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"

def test_create_bounce_address_hyphen() -> None:
    """Test the create_bounce_address function: handling hyphen sign in email"""
    original_email = "jane-doe@gmail.com"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane-doe=gmail.com@list.example.com"

def test_create_bounce_address_special_chars() -> None:
    """Test the create_bounce_address function: handling special characters in email"""
    original_email = "jane.doe@wäb.de"
    list_address = "list1@list.example.com"

    bounce_address = create_bounce_address(list_address, original_email)
    assert bounce_address == "list1+bounces--jane.doe=wäb.de@list.example.com"


def test_parse_bounce_address_normal() -> None:
    """Test the parse_bounce_address function: normal case"""
    bounce_address = "list1+bounces--jane.doe=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe@gmail.com"

def test_parse_bounce_address_plus() -> None:
    """Test the parse_bounce_address function: handling plus sign in email"""
    bounce_address = "list1+bounces--jane.doe---plus---test=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane.doe+test@gmail.com"

def test_parse_bounce_address_hyphen() -> None:
    """Test the parse_bounce_address function: handling hyphen sign in email"""
    bounce_address = "list1+bounces--jane-test=gmail.com@list.example.com"
    original_email = parse_bounce_address(bounce_address)

    assert original_email == "jane-test@gmail.com"
