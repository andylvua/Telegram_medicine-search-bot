from typing import Optional
from langdetect import detect

SPECIAL_CHARACTERS = "!@#$%^&*+?_=<>/"


def check_name(name) -> Optional[str]:
    """
    The check_name function checks that the name is not a digit.
    It returns the name if it's not a digit, otherwise None.

    :param name: Check if the name is a digit
    :return: The name if it is not a digit, otherwise none
    """
    try:
        assert not name.isdigit()
        assert not any(char in SPECIAL_CHARACTERS for char in name)
        return name
    except AssertionError:
        return None


def check_active_ingredient(active_ingredient) -> Optional[str]:
    """
    The check_active_ingredient function checks if the active ingredient is a string.
    If it is not, then it returns None.

    :param active_ingredient: Check if the active ingredient is a string
    :return: None if the active ingredient is a digit
    """
    try:
        assert not active_ingredient.isdigit()
        assert not any(char in SPECIAL_CHARACTERS for char in active_ingredient)
        return active_ingredient
    except AssertionError:
        return None


def check_description(description: str) -> str:
    """
    The check_description function checks if the description of a given
    product is in Ukrainian. If it is, then the function returns that
    description. Otherwise, it returns language of the description.

    :param description: Check if the description is in ukrainian
    :return: The description if it is ukrainian, and language otherwise
    """
    if len(description.split()) < 5:
        return "Too few words"
    if detect(description) != "uk":
        return "Wrong language"

    return description
