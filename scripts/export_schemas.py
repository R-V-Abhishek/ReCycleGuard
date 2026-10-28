"""Generate/check the CP0 boundary schemas from runtime models."""

import json
from pathlib import Path
from typing import Annotated

import typer

from recycleguard.baseline import BaselineOutput, VerifiedReport
from recycleguard.contracts import (
    ActorRef,
    BlobRef,
    CommandContext,
    EvidenceRef,
    Issue,
    Locator,
    Quantity,
    ServiceResult,
    TemporalValue,
)
from recycleguard.contracts.artifacts import (
    ArtifactRevision,
    AssetReceipt,
    FrozenSnapshot,
    ProfileRef,
    SnapshotRef,
)
from recycleguard.contracts.audit import AuditEvent, OperationIntent, OperationResult
from recycleguard.contracts.baseline import (
    BaselineRequest,
    RecordSupportAssertion,
    RecordSupportReview,
)
from recycleguard.contracts.checks import CheckRequest, CheckTarget, StructuredCheckResult
from recycleguard.contracts.domain import (
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    CreditLot,
    DatedAlias,
    Entity,
    Identifier,
    ObligationBucket,
    ProductMapping,
    Registration,
    ReviewedInterval,
    SalesRecord,
)
from recycleguard.contracts.dossier import AssetEntry, CaseManifest, TableDisposition
from recycleguard.contracts.extraction import CoverageItem, ExtractionResult, Observation
from recycleguard.contracts.foundation import (
    ApplicabilityProposal,
    ExtractedBatch,
    FoundationApproval,
    FoundationRequest,
    FoundationResult,
    SourceBatch,
)
from recycleguard.contracts.profiles import (
    AllocationPolicy,
    CalculationProfile,
    EligibilityRule,
    EventEquivalencePolicy,
    NumericPolicy,
    ProfileDefinition,
    ProfilePublication,
    ProfileReview,
    PurchaseCeilingPolicy,
    SourceDependency,
)
from recycleguard.contracts.results import (
    BucketResult,
    CalculationRequest,
    CalculationResult,
    CalculationValueRef,
    FindingRecord,
    Hypothesis,
    Recommendation,
)
from recycleguard.contracts.snapshots import CaseReopen, SnapshotPublication, SnapshotReview
from recycleguard.contracts.sources import (
    ProvisionVersion,
    RightsMetadata,
    SourceLead,
    SourceVersion,
)
from recycleguard.domain.models import (
    AllocationCheck,
    BucketDerivation,
    Derivation,
    EligibilityOutcome,
    LotCheck,
    PortalComparison,
    PriorityCheck,
    QuantityDisposition,
)
from recycleguard.intake.acquisition import AcquisitionOutcome
from recycleguard.intake.batch import IntakeBatchResult
from recycleguard.model_port import ModelCallRequest, ModelCallResult
from recycleguard.normalization.models import (
    EventEquivalence,
    NormalizationBatch,
    ObservationDisposition,
)
from recycleguard.reporting.baseline import (
    BaselineReport,
    ReportClaim,
    ReportRevision,
    ReportSection,
    VerificationResult,
)

MODELS = [
    BaselineOutput,
    VerifiedReport,
    BaselineRequest,
    RecordSupportReview,
    RecordSupportAssertion,
    BaselineReport,
    ReportClaim,
    ReportSection,
    ReportRevision,
    VerificationResult,
    QuantityDisposition,
    Derivation,
    AllocationCheck,
    BucketDerivation,
    EligibilityOutcome,
    LotCheck,
    PortalComparison,
    PriorityCheck,
    FoundationApproval,
    ApplicabilityProposal,
    ExtractedBatch,
    FoundationRequest,
    FoundationResult,
    SourceBatch,
    EventEquivalence,
    NormalizationBatch,
    ObservationDisposition,
    IntakeBatchResult,
    AcquisitionOutcome,
    ServiceResult[FoundationResult],
    CaseReopen,
    CalculationProfile,
    ProfileDefinition,
    ProfilePublication,
    ProfileReview,
    AllocationPolicy,
    EligibilityRule,
    EventEquivalencePolicy,
    NumericPolicy,
    PurchaseCeilingPolicy,
    SourceDependency,
    ServiceResult[CalculationProfile],
    ServiceResult[FrozenSnapshot],
    SnapshotPublication,
    SnapshotReview,
    ActorRef,
    BlobRef,
    CommandContext,
    EvidenceRef,
    Issue,
    Locator,
    Quantity,
    TemporalValue,
    ModelCallRequest,
    ModelCallResult,
    ServiceResult[Quantity],
    ArtifactRevision,
    AssetReceipt,
    FrozenSnapshot,
    ProfileRef,
    SnapshotRef,
    AuditEvent,
    OperationIntent,
    OperationResult,
    AccountBalanceObservation,
    Allocation,
    Certificate,
    CertificateEvent,
    CommercialRecord,
    CreditLot,
    DatedAlias,
    Entity,
    Identifier,
    ObligationBucket,
    ProductMapping,
    Registration,
    ReviewedInterval,
    SalesRecord,
    CheckRequest,
    CheckTarget,
    StructuredCheckResult,
    AssetEntry,
    CaseManifest,
    TableDisposition,
    CoverageItem,
    ExtractionResult,
    Observation,
    BucketResult,
    CalculationRequest,
    CalculationResult,
    CalculationValueRef,
    FindingRecord,
    Hypothesis,
    Recommendation,
    ProvisionVersion,
    RightsMetadata,
    SourceLead,
    SourceVersion,
    ServiceResult[CalculationResult],
    ServiceResult[ExtractionResult],
]
app = typer.Typer()


@app.command()
def export(check: Annotated[bool, typer.Option("--check")] = False):
    root = Path(__file__).resolve().parents[1] / "schemas/v1"
    root.mkdir(parents=True, exist_ok=True)
    for model in MODELS:
        name = model.__name__.replace("[", "_").replace("]", "")
        path = root / f"{name}.json"
        expected = json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                raise typer.BadParameter(f"schema drift: {path.name}; regenerate schemas")
        else:
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(expected)
    typer.echo(f"{'Checked' if check else 'Generated'} {len(MODELS)} boundary schemas")


if __name__ == "__main__":
    app()
