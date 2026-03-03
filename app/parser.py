from __future__ import annotations

import re
from dataclasses import dataclass

WHITESPACE_RE = re.compile(r"\s+")
PKM_RE = re.compile(r"\b([pk]\d{3}|m\d{6})\b", re.IGNORECASE)
CUSTOM_RE = re.compile(r"^\s*§\s*([^\s]+)\s*(.*)$", re.IGNORECASE)
ENCLOSED_CUSTOM_RE = re.compile(r"§([^§]+)§")


@dataclass
class ParsedTodo:
    category_key: str
    category_type: str
    text: str


def _collapse_space(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.strip())


def _capitalize_first(value: str) -> str:
    if not value:
        return "Untitled task"
    return value[0].upper() + value[1:]


def _normalize_custom_category(raw: str, category_max_length: int) -> str:
    category = _collapse_space(raw)[:category_max_length]
    if not category:
        return "General"
    return category[:1].upper() + category[1:]


def parse_line(line: str, category_max_length: int = 64) -> ParsedTodo | None:
    cleaned = _collapse_space(line)
    if not cleaned:
        return None

    enclosed_match = ENCLOSED_CUSTOM_RE.search(cleaned)
    if enclosed_match:
        category = _normalize_custom_category(enclosed_match.group(1), category_max_length)
        raw_text = _collapse_space(ENCLOSED_CUSTOM_RE.sub("", cleaned, count=1))
        return ParsedTodo(category_key=category, category_type="CUSTOM", text=_capitalize_first(raw_text))

    custom_match = CUSTOM_RE.match(cleaned)
    if custom_match:
        category = _normalize_custom_category(custom_match.group(1), category_max_length)
        raw_text = _collapse_space(custom_match.group(2))
        return ParsedTodo(category_key=category, category_type="CUSTOM", text=_capitalize_first(raw_text))

    token_match = PKM_RE.search(cleaned)
    if token_match:
        token = token_match.group(1).upper()
        text_without_token = _collapse_space(PKM_RE.sub("", cleaned, count=1))
        return ParsedTodo(category_key=token, category_type="PKM", text=_capitalize_first(text_without_token))

    return ParsedTodo(category_key="GENERAL", category_type="GENERAL", text=_capitalize_first(cleaned))


def parse_multiline(input_text: str, category_max_length: int = 64) -> list[ParsedTodo]:
    parsed: list[ParsedTodo] = []
    for line in input_text.splitlines():
        item = parse_line(line, category_max_length=category_max_length)
        if item:
            parsed.append(item)
    return parsed
