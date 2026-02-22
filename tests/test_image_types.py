from image_scraper.domain.image_types import best_extension


def test_best_extension_prefers_filename_extension() -> None:
    assert best_extension(original_name="photo.webp") == ".webp"


def test_best_extension_falls_back_to_url_extension() -> None:
    assert best_extension(fallback_url="https://example.com/path/image.png?x=1") == ".png"


def test_best_extension_uses_content_type() -> None:
    assert best_extension(content_type="image/gif") == ".gif"


def test_best_extension_defaults_to_jpg_for_unknown_inputs() -> None:
    assert best_extension(original_name="file.unknown") == ".jpg"
