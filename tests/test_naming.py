from image_scraper.domain.naming import sanitize_filename, slugify


def test_sanitize_filename_replaces_invalid_characters() -> None:
    assert sanitize_filename("cat:dog?.png") == "cat_dog_.png"


def test_sanitize_filename_defaults_when_empty() -> None:
    assert sanitize_filename("   ") == "image"


def test_slugify_normalizes_to_dash_separated_lowercase() -> None:
    assert slugify("  Red Panda Photos!!!  ") == "red-panda-photos"


def test_slugify_defaults_when_empty_after_cleanup() -> None:
    assert slugify("@@@") == "query"
