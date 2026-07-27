"""Domain-level errors for the evidence module."""


class EvidenceDomainError(Exception):
    """Base class for evidence-module domain errors."""


class EvidenceNotFoundError(EvidenceDomainError):
    def __init__(self, evidence_id: str) -> None:
        super().__init__(f"no evidence with evidence_id={evidence_id!r}")
        self.evidence_id = evidence_id


class EvidenceCreationFailedError(EvidenceDomainError):
    """Raised when persisting an evidence record fails.

    Per brief section 19's explicit rule: a candidate that would otherwise
    be accepted must not become a fact if its evidence could not be
    created. `EvidenceGateway.create_evidence` (in `modules/extraction`)
    surfaces this to the application service, which then skips accepting
    that candidate rather than accepting it without evidence.
    """

    def __init__(self, *, reason: str) -> None:
        super().__init__(f"evidence creation failed: {reason}")
        self.reason = reason
