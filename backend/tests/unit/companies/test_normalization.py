import pytest

from app.modules.companies.domain.normalization import normalize_domain


class TestNormalizeDomain:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Example.com", "example.com"),
            ("https://example.com", "example.com"),
            ("http://www.example.com/path?query=1", "example.com"),
            ("  example.com  ", "example.com"),
            ("example.com:8080", "example.com"),
            ("example.com.", "example.com"),
            ("https://www.example.com#section", "example.com"),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert normalize_domain(raw) == expected

    def test_rejects_empty_after_normalization(self) -> None:
        with pytest.raises(ValueError, match="normalized_domain"):
            normalize_domain("   ")

    def test_rejects_scheme_only(self) -> None:
        with pytest.raises(ValueError, match="normalized_domain"):
            normalize_domain("https://")
