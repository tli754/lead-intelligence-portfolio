"""Domain-level errors for the companies module."""


class CompanyDomainError(Exception):
    """Base class for companies-module domain errors."""


class CompanyNotFoundError(CompanyDomainError):
    def __init__(self, company_id: str) -> None:
        super().__init__(f"no company with company_id={company_id!r}")
        self.company_id = company_id


class DuplicateCompanyError(CompanyDomainError):
    def __init__(self, normalized_domain: str) -> None:
        super().__init__(
            f"a company with normalized_domain={normalized_domain!r} already exists"
        )
        self.normalized_domain = normalized_domain


class InvalidStatusTransitionError(CompanyDomainError):
    """Raised when a processing/workflow status change isn't a valid transition."""

    def __init__(self, field: str, current: str, attempted: str) -> None:
        super().__init__(f"cannot transition {field} from {current!r} to {attempted!r}")
        self.field = field
        self.current = current
        self.attempted = attempted
