import html
import json

from bs4 import BeautifulSoup

from image_scraper.adapters.bing import _parse_candidates_from_soup
from image_scraper.adapters.google_errors import error_summary, selenium_exceptions
from image_scraper.adapters.google_parsing import is_block_page as _is_block_page


def _anchor(murl: str, turl: str = "") -> str:
    payload = html.escape(json.dumps({"murl": murl, "turl": turl}))
    return f'<a class="iusc" m="{payload}"></a>'


def test_bing_parser_dedupes_and_skips_invalid() -> None:
    html = (
        _anchor("https://example.com/a.jpg", "https://example.com/a_t.jpg")
        + _anchor("https://example.com/a.jpg")
        + '<a class="iusc"></a>'
        + '<a class="iusc" m="not-json"></a>'
    )
    candidates = _parse_candidates_from_soup(BeautifulSoup(html, "html.parser"), seen_urls=set())
    assert [c.url for c in candidates] == ["https://example.com/a.jpg"]
    assert candidates[0].fallback_url == "https://example.com/a_t.jpg"


def test_bing_parser_skips_non_string_metadata() -> None:
    soup = BeautifulSoup('<a class="iusc" m="x"></a>', "html.parser")
    tag = soup.select_one("a.iusc")
    assert tag is not None
    tag["m"] = ["not", "a", "string"]  # type: ignore[assignment]
    candidates = _parse_candidates_from_soup(soup, seen_urls=set())
    assert candidates == []


def test_block_page_detects_sorry_redirect() -> None:
    assert (
        _is_block_page(
            page_source="<html></html>",
            current_url="https://www.google.com/sorry/index?continue=https://www.google.com/search",
        )
        is True
    )


def test_block_page_detects_captcha_body() -> None:
    html = '<form id="captcha-form">Our systems have detected unusual traffic</form>'
    assert (
        _is_block_page(page_source=html, current_url="https://www.google.com/search?tbm=isch")
        is True
    )


def test_block_page_accepts_normal_results() -> None:
    html = '<div class="isv-r"><img class="n3VNCb" src="https://example.com/x.jpg"></div>'
    assert (
        _is_block_page(
            page_source=html, current_url="https://www.google.com/search?tbm=isch&q=cats"
        )
        is False
    )


def test_selenium_exceptions_shape() -> None:
    stale_errors, fatal_errors = selenium_exceptions()
    assert {t.__name__ for t in stale_errors} == {"StaleElementReferenceException"}
    # WebDriverException is the base of every Selenium error; it must never
    # be classified fatal or any per-card hiccup kills the whole engine.
    assert {t.__name__ for t in fatal_errors} == {
        "InvalidSessionIdException",
        "NoSuchWindowException",
    }


def test_error_summary_handles_empty_message() -> None:
    assert error_summary(RuntimeError("")) == "RuntimeError"
    assert error_summary(RuntimeError("boom\ntrace")) == "RuntimeError: boom"
