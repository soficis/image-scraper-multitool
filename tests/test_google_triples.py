"""Unit tests for Google triple extraction and tightened block detection."""

from image_scraper.adapters.google_parsing import (
    extract_triple_candidates,
    is_block_page,
)


def _triple(url: str, height: int = 1365, width: int = 2048) -> str:
    return f'["{url}",{height},{width}]'


def test_triples_extract_strict_with_dimensions() -> None:
    source = _triple("https://example.com/full-123.jpg") + _triple(
        "https://example.com/second.png", 480, 640
    )
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == [
        "https://example.com/full-123.jpg",
        "https://example.com/second.png",
    ]


def test_triples_skip_denylisted_hosts() -> None:
    source = _triple("https://encrypted-tbn0.gstatic.com/thumb.jpg") + _triple(
        "https://example.com/real.jpg"
    )
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == [
        "https://example.com/real.jpg"
    ]


def test_triples_skip_seen_sources() -> None:
    source = _triple("https://example.com/seen.jpg") + _triple("https://example.com/fresh.jpg")
    assert extract_triple_candidates(
        page_source=source, seen_sources={"https://example.com/seen.jpg"}, limit=10
    ) == ["https://example.com/fresh.jpg"]


def test_triples_include_ou_field_supplement() -> None:
    source = '{"ou":"https://example.com/ou-full.jpg","ow":640}'
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == [
        "https://example.com/ou-full.jpg"
    ]


def test_triples_respect_limit() -> None:
    source = "".join(f'["https://example.com/{index}.jpg",10,10]' for index in range(5))
    assert len(extract_triple_candidates(page_source=source, seen_sources=set(), limit=3)) == 3


def test_triples_empty_on_junk() -> None:
    assert (
        extract_triple_candidates(
            page_source="<html><body>no images here</body></html>",
            seen_sources=set(),
            limit=10,
        )
        == []
    )


def test_block_page_good_body_with_sorry_reference_and_cards_is_clean() -> None:
    html = (
        '<div class="VifEQd">results</div><script>var x="/sorry/index?continue=/search";</script>'
    )
    assert (
        is_block_page(
            page_source=html,
            current_url="https://www.google.com/search?tbm=isch&q=owls",
            card_count=248,
        )
        is False
    )


def test_block_page_challenge_with_cards_is_not_blocked() -> None:
    html = '<form id="captcha-form">solve</form><div class="VifEQd">results</div>'
    assert (
        is_block_page(
            page_source=html,
            current_url="https://www.google.com/search?tbm=isch&q=owls",
            card_count=12,
        )
        is False
    )


def test_block_page_challenge_with_zero_cards_is_blocked() -> None:
    html = "<body>unusual traffic from your computer network</body>"
    assert (
        is_block_page(
            page_source=html,
            current_url="https://www.google.com/search?tbm=isch&q=owls",
            card_count=0,
        )
        is True
    )


def test_triples_decode_json_escapes() -> None:
    source = _triple("https://example.com/a.jpg?w\\u003d800\\u0026h\\u003d600")
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == [
        "https://example.com/a.jpg?w=800&h=600"
    ]


def test_triples_drop_undecodable_escape() -> None:
    source = _triple("https://example.com/bad\\uZZZZ.jpg")
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == []


def test_triples_apply_resolution_bounds() -> None:
    source = (
        _triple("https://example.com/small.jpg", height=200, width=300)
        + _triple("https://example.com/big.jpg", height=1200, width=1600)
        + _triple("https://example.com/huge.jpg", height=6000, width=8000)
    )
    assert extract_triple_candidates(
        page_source=source,
        seen_sources=set(),
        limit=10,
        min_resolution=(800, 600),
        max_resolution=(4000, 4000),
    ) == ["https://example.com/big.jpg"]


def test_triples_denylist_matches_host_not_query() -> None:
    source = _triple("https://img.site/p.jpg?ref=google.com") + _triple(
        "https://lh3.googleusercontent.com/x.jpg"
    )
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=10) == [
        "https://img.site/p.jpg?ref=google.com"
    ]


def test_triples_non_positive_limit_is_empty() -> None:
    source = _triple("https://example.com/a.jpg")
    assert extract_triple_candidates(page_source=source, seen_sources=set(), limit=0) == []
