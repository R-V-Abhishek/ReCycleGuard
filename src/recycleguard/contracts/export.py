"""C14 export and replay boundary models."""

from typing import Literal

from pydantic import Field

from .core import ID, BlobRef, BoundaryModel, Digest, Nonempty

BundleKind = Literal["COMPLETE_LOCAL", "PUBLICATION"]
ReplayKind = Literal["ARTIFACT", "RECOMPUTE", "MODEL_RERUN"]


class BundleRequest(BoundaryModel):
    bundle_id: ID
    run_id: ID
    kind: BundleKind
    allow_restricted: bool = False


class BundleObject(BoundaryModel):
    reference: BlobRef
    role: Nonempty
    derivative_of: BlobRef | None = None


class BundleExclusion(BoundaryModel):
    reference: BlobRef | None
    role: Nonempty
    reason: Nonempty


class BundleManifest(BoundaryModel):
    bundle_id: ID
    run_id: ID
    kind: BundleKind
    spec: BlobRef
    state: BlobRef
    objects: list[BundleObject] = Field(default_factory=list)
    exclusions: list[BundleExclusion] = Field(default_factory=list)
    dependency_head: Digest
    manifest_digest: Digest


class ReplayRequest(BoundaryModel):
    bundle: BundleManifest
    kind: ReplayKind = "ARTIFACT"


class IntegrityResult(BoundaryModel):
    valid: bool
    bundle_id: ID
    checked_objects: int = 0
    issue_codes: list[Nonempty] = Field(default_factory=list)


class ReplayResult(BoundaryModel):
    valid: bool
    run_id: ID
    kind: ReplayKind
    state: BlobRef | None
    issue_codes: list[Nonempty] = Field(default_factory=list)
