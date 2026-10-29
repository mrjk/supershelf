"""One-pass template substitution."""

import pytest

from supershelf.errors import SupershelfError
from supershelf.template import Template


def test_render_replaces_a_name() -> None:
    assert Template({"name": "work"}).render("id-{{ name }}") == "id-work"


def test_render_allows_spaces_inside_braces() -> None:
    assert Template({"name": "work"}).render("{{ name }}") == "work"


def test_render_reads_dotted_dict_keys() -> None:
    scope = {"__config_data__": {"config": {"root_dir": "data"}}}

    assert Template(scope).render("{{ __config_data__.config.root_dir }}") == "data"


def test_render_does_not_render_substituted_text_again() -> None:
    scope = {"raw": "{{ name }}", "name": "work"}

    assert Template(scope).render("{{ raw }}") == "{{ name }}"


def test_render_unknown_name() -> None:
    with pytest.raises(SupershelfError, match="Unknown template name 'missing'"):
        Template({}).render("{{ missing }}")


def test_render_unknown_dotted_key() -> None:
    with pytest.raises(SupershelfError, match="Unknown template key"):
        Template({"data": {}}).render("{{ data.config }}")


def test_render_rejects_a_non_string() -> None:
    with pytest.raises(SupershelfError, match="must be a string"):
        Template({"count": 1}).render("{{ count }}")
