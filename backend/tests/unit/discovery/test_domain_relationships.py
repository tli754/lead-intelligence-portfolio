from app.modules.discovery.domain.domain_relationships import (
    is_same_domain,
    is_same_registrable_domain,
    registrable_domain,
)


class TestIsSameDomain:
    def test_exact_match(self) -> None:
        assert is_same_domain("example.com", "example.com") is True

    def test_case_insensitive(self) -> None:
        assert is_same_domain("Example.com", "example.com") is True

    def test_different_hosts(self) -> None:
        assert is_same_domain("example.com", "other.com") is False

    def test_subdomain_is_not_same_domain(self) -> None:
        assert is_same_domain("shop.example.com", "example.com") is False

    def test_none_inputs(self) -> None:
        assert is_same_domain(None, "example.com") is False
        assert is_same_domain("example.com", None) is False


class TestRegistrableDomain:
    def test_simple_domain(self) -> None:
        assert registrable_domain("example.com") == "example.com"

    def test_subdomain(self) -> None:
        assert registrable_domain("shop.example.com") == "example.com"

    def test_compound_tld(self) -> None:
        assert registrable_domain("example.co.nz") == "example.co.nz"
        assert registrable_domain("shop.example.co.nz") == "example.co.nz"

    def test_none_input(self) -> None:
        assert registrable_domain(None) is None


class TestIsSameRegistrableDomain:
    def test_same_registrable_domain_across_subdomains(self) -> None:
        assert is_same_registrable_domain("www.example.com", "example.com") is True
        assert is_same_registrable_domain("shop.example.com", "www.example.com") is True

    def test_compound_tld_subdomains(self) -> None:
        assert is_same_registrable_domain("shop.example.co.nz", "example.co.nz") is True

    def test_different_registrable_domains(self) -> None:
        assert is_same_registrable_domain("example.com", "other.com") is False

    def test_none_inputs(self) -> None:
        assert is_same_registrable_domain(None, "example.com") is False
