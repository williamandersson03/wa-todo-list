from app.parser import parse_line, parse_multiline


def test_case_insensitive_pkm():
    parsed = parse_line("p842 test of io")
    assert parsed.category_key == "P842"
    assert parsed.category_type == "PKM"
    assert parsed.text == "Test of io"


def test_case_insensitive_custom_category_precedence():
    parsed = parse_line("§office p842 check inventory")
    assert parsed.category_key == "Office"
    assert parsed.category_type == "CUSTOM"
    assert parsed.text == "P842 check inventory"


def test_enclosed_custom_category_anywhere_takes_precedence():
    parsed = parse_line("Call vendor §P842 Em117§ tomorrow")
    assert parsed.category_key == "P842 Em117"
    assert parsed.category_type == "CUSTOM"
    assert parsed.text == "Call vendor tomorrow"


def test_multiple_spaces_trimmed():
    parsed = parse_line("   K186    prepare    report   ")
    assert parsed.category_key == "K186"
    assert parsed.text == "Prepare report"


def test_multiline_paste_skips_empty_lines():
    rows = parse_multiline("\nP842 first\n\nsecond task\n")
    assert len(rows) == 2
    assert rows[0].category_key == "P842"
    assert rows[1].category_key == "GENERAL"


def test_missing_text_after_category_token_graceful():
    parsed = parse_line("M100400")
    assert parsed.category_key == "M100400"
    assert parsed.text == "Untitled task"


def test_missing_text_after_custom_category_graceful():
    parsed = parse_line("§office")
    assert parsed.category_key == "Office"
    assert parsed.text == "Untitled task"
