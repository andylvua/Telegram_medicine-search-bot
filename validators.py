from typing import Optional
from polyglot.detect import Detector


def check_name(name) -> Optional[str]:
    try:
        assert not name.isdigit()
        return name
    except AssertionError:
        return None


def check_active_ingredient(active_ingredient) -> Optional[str]:
    try:
        assert not active_ingredient.isdigit()
        return active_ingredient
    except AssertionError:
        return None


def check_description(description) -> Optional[str]:
    try:
        assert Detector(description).language.name == "Ukrainian"
        return description
    except AssertionError:
        return Detector(description).language.name
