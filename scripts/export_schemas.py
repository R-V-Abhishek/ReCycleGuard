"""Generate/check the CP0 boundary schemas from runtime models."""

import json
from pathlib import Path
from typing import Annotated

import typer

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
    Registration,
    ReviewedInterval,
)
from recycleguard.contracts.dossier import AssetEntry, CaseManifest, TableDisposition
from recycleguard.contracts.extraction import CoverageItem, ExtractionResult, Observation
from recycleguard.contracts.results import (
    BucketResult,
    CalculationRequest,
    CalculationResult,
    CalculationValueRef,
    FindingRecord,
    Hypothesis,
    Recommendation,
)
from recycleguard.contracts.sources import (
    ProvisionVersion,
    RightsMetadata,
    SourceLead,
    SourceVersion,
)
from recycleguard.model_port import ModelCallRequest, ModelCallResult

MODELS = [
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
    Registration,
    ReviewedInterval,
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
