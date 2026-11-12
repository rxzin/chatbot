"""Cleaning the model's follow-up questions."""

from services.graph.nodes.suggest import parse_suggestions


def test_keeps_three_distinct_plain_questions():
    text = (
        "1. First question?\n"
        "- first question?\n"
        "See http://x.y for more?\n"
        "Second question?\n"
        "Third question?\n"
        "Fourth question?"
    )

    assert parse_suggestions(text) == [
        "First question?",
        "Second question?",
        "Third question?",
    ]


def test_drops_lines_that_are_too_short_or_too_long():
    text = f"A?\n{'long ' * 40}?\nJust right?"

    assert parse_suggestions(text) == ["Just right?"]


def test_empty_text_gives_no_suggestions():
    assert parse_suggestions("") == []
