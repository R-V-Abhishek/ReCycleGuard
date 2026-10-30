"""Single-process local demonstration API over trusted application services."""

import asyncio
import io
import json
import secrets
import shutil
import stat
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import Field, SecretStr

from recycleguard.application import command_context, local_application, local_review_application
from recycleguard.config import Settings
from recycleguard.contracts.baseline import RecordSupportAssertion, RecordSupportReview
from recycleguard.contracts.core import BlobRef, BoundaryModel, Nonempty
from recycleguard.contracts.dossier import CaseManifest
from recycleguard.contracts.foundation import (
    FoundationApproval,
    FoundationRequest,
    FoundationResult,
)
from recycleguard.contracts.review import ReviewDecision
from recycleguard.contracts.workflow import BudgetLimits, PlanProposal
from recycleguard.foundation import FoundationService
from recycleguard.foundation_review import FoundationReviewer
from recycleguard.investigation import (
    InvestigationConfiguration,
    InvestigationRequest,
    InvestigationService,
    ScriptedExchange,
)
from recycleguard.local_model import LocalModelConfig
from recycleguard.local_session import initialize_reviewer
from recycleguard.storage import canonical_json_bytes
from recycleguard.support_review import SupportReviewer

from .store import ApiStore
from .trace import trace_events

_STOPPED = {
    "AWAITING_REVIEW",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "BLOCKED_INPUT",
    "BLOCKED_OUTPUT",
}
_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ApiOptions:
    settings: Settings
    token: str
    fixture_root: Path = _ROOT / "tests/fixtures/visible"
    r02_path: Path = _ROOT / "tests/fixtures/visible/h04/acquired_originals/e-waste_rules_2022.pdf"
    r08_path: Path = _ROOT / "tests/fixtures/visible/h01/acquired_originals/cpcb_faq_20240123.pdf"
    model_config_path: Path | None = None
    test_exchanges: tuple[ScriptedExchange, ...] = ()
    cors_origins: tuple[str, ...] = ()


class Selection(BoundaryModel):
    fixture_id: Nonempty


class Enrollment(BoundaryModel):
    actor_id: Nonempty
    password: SecretStr


class FoundationReviewRequest(BoundaryModel):
    password: SecretStr
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    accepted_qualifications: Nonempty


class SupportReviewRequest(BoundaryModel):
    password: SecretStr
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    assertions: list[RecordSupportAssertion] = Field(min_length=1)
    reason: Nonempty


class RunRequest(BoundaryModel):
    dossier_id: Nonempty
    mode: Literal["MODEL_BACKED", "SCRIPTED_TEST"] = "MODEL_BACKED"
    budgets: BudgetLimits | None = None


class DecisionRequest(BoundaryModel):
    password: SecretStr
    packet_id: Nonempty
    expected_dependency_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES", "ESCALATE"]
    reason: Nonempty


def create_app(options: ApiOptions):
    if len(options.token) < 24:
        raise ValueError("API bearer token must contain at least 24 characters")
    settings = options.settings
    home = settings.data_root / "api"
    store = ApiStore(home / "catalog.sqlite")
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="investigation")
    mutation_lock, scheduling_lock = threading.Lock(), threading.Lock()
    active = {}

    @asynccontextmanager
    async def lifespan(_app):
        yield
        # Never kill a model operation at shutdown; worker checks cancellation between turns.
        for run_id in tuple(active):
            store.request_cancel(run_id)
        await asyncio.to_thread(executor.shutdown, wait=True)

    async def authorize(authorization: Annotated[str | None, Header()] = None):
        expected = "Bearer " + options.token
        if authorization is None or not secrets.compare_digest(
            authorization.encode(), expected.encode()
        ):
            raise HTTPException(
                401, detail={"code": "UNAUTHORIZED", "message": "Bearer token required"}
            )

    app = FastAPI(
        title="ReCycleGuard local API",
        version="0.1.0",
        lifespan=lifespan,
        dependencies=[Depends(authorize)],
    )
    app.state.options, app.state.store = options, store
    if options.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(options.cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, exc):
        # Validation diagnostics must not echo reviewer passwords from request bodies.
        return JSONResponse(
            status_code=422,
            content={
                "code": "INVALID_SCHEMA",
                "errors": [
                    {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ],
            },
        )

    @app.exception_handler(ValueError)
    async def invalid_value(_request, exc):
        return JSONResponse(
            status_code=409, content={"code": "PRECONDITION_FAILED", "message": str(exc)}
        )

    @app.exception_handler(KeyError)
    async def missing(_request, exc):
        return JSONResponse(status_code=404, content={"code": "NOT_FOUND", "message": str(exc)})

    @contextmanager
    def mutation():
        if not mutation_lock.acquire(blocking=False):
            raise HTTPException(
                409, detail={"code": "BUSY", "message": "Another operation is active"}
            )
        try:
            yield
        finally:
            mutation_lock.release()

    def foundation_value(row, approved=False):
        raw = row["approved" if approved else "candidate"]
        if raw is None:
            raise ValueError(
                "dossier must have an approved foundation" if approved else "prepare dossier first"
            )
        ref = BlobRef.model_validate_json(raw)
        with local_application(settings) as (cases, _, _):
            value = FoundationResult.model_validate_json(cases.kernel.blob_store.get(ref))
        return ref, value

    def dossier_view(row):
        view = {
            "dossier_id": row["dossier_id"],
            "name": row["name"],
            "status": "APPROVED"
            if row["approved"]
            else "DRAFT"
            if row["candidate"]
            else "UPLOADED",
        }
        if row["candidate"]:
            ref, value = foundation_value(row, approved=bool(row["approved"]))
            view.update(
                candidate_digest=BlobRef.model_validate_json(row["candidate"]).sha256,
                foundation=value.model_dump(mode="json"),
                foundation_blob=ref.model_dump(mode="json"),
            )
        return view

    def register(path, name, dossier_id):
        manifest = CaseManifest.model_validate_json((path / "case_manifest.json").read_bytes())
        # Manifest validation grants no approval. Intake verifies declared digests and all files.
        store.register(dossier_id, path, name)
        return {
            "dossier_id": dossier_id,
            "name": name,
            "status": "UPLOADED",
            "synthetic": manifest.synthetic,
            "case_id": manifest.case_id,
        }

    def run_view(run_id):
        job = store.job(run_id)
        with local_application(settings) as (cases, _, cap):
            service = InvestigationService(cases, settings, capability=cap)
            state = service.store.load(run_id)
        return {"state": state.model_dump(mode="json"), "job": job}

    def drive(run_id, resume):
        store.job_status(run_id, "RUNNING")
        runner = None
        try:
            with local_application(settings) as (cases, context, cap):
                service = InvestigationService(cases, settings, capability=cap)
                spec = service.store.spec(run_id)
                runner = service.runner(spec)
                with mutation_lock:
                    state = service.recover_reviews(context, run_id)
                    if resume and state.status not in _STOPPED:
                        state = runner.resume(context, run_id, capability=cap)
                for _ in range(128):
                    if store.job(run_id)["cancel_requested"]:
                        if state.status not in {
                            "COMPLETED",
                            "FAILED",
                            "CANCELLED",
                            "BLOCKED_INPUT",
                            "BLOCKED_OUTPUT",
                        }:
                            with mutation_lock:
                                state = runner.cancel(
                                    command_context(context.actor),
                                    run_id,
                                    state.version,
                                    "Cancellation requested through API",
                                    capability=cap,
                                )
                        break
                    if state.status in _STOPPED:
                        break
                    with mutation_lock:
                        state = runner.advance(
                            command_context(context.actor), run_id, state.version, capability=cap
                        )
                store.job_status(run_id, "STOPPED", state.status)
        except Exception as exc:
            # This boundary records worker failure, rather than losing it in a detached future.
            store.job_status(run_id, "FAILED", f"{type(exc).__name__}: {exc}")
        finally:
            if runner is not None:
                runner.close()

    def schedule(run_id, *, resume=False):
        with scheduling_lock:
            if any(not future.done() for future in active.values()):
                raise HTTPException(
                    409,
                    detail={
                        "code": "BUSY",
                        "message": "Only one active investigation is supported",
                    },
                )
            store.clear_cancel(run_id)
            store.job_status(run_id, "QUEUED")
            active[run_id] = executor.submit(drive, run_id, resume)

    @app.get("/api/v1/health")
    def health():
        return {
            "status": "OK",
            "model_configured": options.model_config_path is not None,
            "model_probed": False,
            "concurrency": 1,
            "ui_implemented": False,
        }

    @app.get("/api/v1/agent")
    def agent():
        from recycleguard.contracts.workflow import AssessmentProposal, PlanProposal
        from recycleguard.local_model import _PHASE_RULES, _SYSTEM

        config = (
            None
            if options.model_config_path is None
            else LocalModelConfig.model_validate_json(options.model_config_path.read_bytes())
        )
        return {
            "configured": config is not None,
            "model_id": None if config is None else config.model_id,
            "prompt_pin": None if config is None else config.prompt_pin().model_dump(mode="json"),
            "system_template": _SYSTEM,
            "phase_rules": _PHASE_RULES,
            "response_schemas": {
                "PLAN": PlanProposal.model_json_schema(),
                "ASSESS": AssessmentProposal.model_json_schema(),
            },
            "note": (
                "Templates are configuration. Per-call exact sent prompts appear "
                "in provider_trace after completion."
            ),
        }

    @app.post("/api/v1/reviewer", status_code=201)
    def enroll(body: Enrollment):
        with mutation():
            initialize_reviewer(settings.data_root, body.actor_id, body.password.get_secret_value())
        return {"status": "ENROLLED"}

    @app.get("/api/v1/dossiers")
    def dossiers():
        fixtures = []
        if options.fixture_root.exists():
            for path in sorted(options.fixture_root.glob("case_*")):
                if (path / "case_manifest.json").is_file() and not path.is_symlink():
                    manifest = CaseManifest.model_validate_json(
                        (path / "case_manifest.json").read_bytes()
                    )
                    fixtures.append(
                        {
                            "fixture_id": path.name,
                            "case_id": manifest.case_id,
                            "fiscal_year": manifest.fiscal_year,
                            "synthetic": True,
                        }
                    )
        return {"fixtures": fixtures, "dossiers": [dossier_view(row) for row in store.dossiers()]}

    @app.post("/api/v1/dossiers/select", status_code=201)
    def select(body: Selection):
        # IDs are directory names from an explicit DEV catalogue, never caller-supplied paths.
        allowed = {item["fixture_id"] for item in dossiers()["fixtures"]}
        if body.fixture_id not in allowed:
            raise KeyError("fixture is not in the development catalogue")
        dossier_id = "dossier:" + uuid4().hex
        target = home / "uploads" / dossier_id.split(":")[1]
        shutil.copytree(options.fixture_root / body.fixture_id, target, symlinks=False)
        return register(target, body.fixture_id, dossier_id)

    @app.post("/api/v1/dossiers", status_code=201)
    async def upload(request: Request):
        if request.headers.get("content-type", "").split(";")[0] != "application/zip":
            raise HTTPException(415, detail="Upload a manifest-based dossier as application/zip")
        body = bytearray()
        async for block in request.stream():
            body.extend(block)
            if len(body) > 25 * 1024 * 1024:
                raise HTTPException(413, detail="ZIP exceeds 25 MiB upload limit")
        dossier_id = "dossier:" + uuid4().hex
        target = home / "uploads" / dossier_id.split(":")[1]
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as archive:
                entries = archive.infolist()
                if (
                    len(entries) > 500
                    or sum(item.file_size for item in entries) > 100 * 1024 * 1024
                ):
                    raise ValueError("ZIP exceeds 500 entries or 100 MiB expanded limit")
                names = set()
                for item in entries:
                    path = PurePosixPath(item.filename)
                    if (
                        not path.parts
                        or path.is_absolute()
                        or ".." in path.parts
                        or "\\" in item.filename
                        or ":" in item.filename
                        or stat.S_ISLNK(item.external_attr >> 16)
                        or item.filename.casefold() in names
                    ):
                        raise ValueError("ZIP contains unsafe or duplicate paths")
                    names.add(item.filename.casefold())
                for item in entries:
                    destination = target.joinpath(*PurePosixPath(item.filename).parts)
                    if item.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(item) as source, destination.open("xb") as output:
                            shutil.copyfileobj(source, output)
            manifests = list(target.rglob("case_manifest.json"))
            if len(manifests) != 1:
                raise ValueError("ZIP must contain exactly one case_manifest.json")
            return register(manifests[0].parent, "Uploaded synthetic dossier", dossier_id)
        except (zipfile.BadZipFile, ValueError, OSError) as exc:
            # Remove only this newly generated staging directory after rejecting its upload.
            if target.exists():
                shutil.rmtree(target)
            raise HTTPException(422, detail=str(exc)) from exc

    @app.get("/api/v1/dossiers/{dossier_id}")
    def get_dossier(dossier_id: str):
        return dossier_view(store.dossier(dossier_id))

    @app.post("/api/v1/dossiers/{dossier_id}/prepare")
    def prepare(dossier_id: str):
        with mutation():
            row = store.dossier(dossier_id)
            if row["candidate"]:
                return dossier_view(row)
            manifest = CaseManifest.model_validate_json(
                (Path(row["path"]) / "case_manifest.json").read_bytes()
            )
            suffix = uuid4().hex
            with local_application(settings) as (cases, context, cap):
                case_head = cases.snapshots.head(manifest.case_id)
                corpus_head = cases.snapshots.head("corpus:initial")
                result = FoundationService(cases).build(
                    context,
                    FoundationRequest(
                        case_root=row["path"],
                        r02_path=str(options.r02_path),
                        r08_path=str(options.r08_path),
                        case_snapshot_id=f"snapshot:api_case_{suffix}",
                        corpus_snapshot_id=f"snapshot:api_corpus_{suffix}",
                        profile_version=f"api-draft-{suffix}",
                        expected_case_head=None if case_head is None else case_head.snapshot_id,
                        expected_corpus_head=None
                        if corpus_head is None
                        else corpus_head.snapshot_id,
                        expected_profile_head=cases.profiles.head(manifest.calculation_profile_id),
                    ),
                    capability=cap,
                )
                if result.output is None:
                    raise ValueError(f"foundation rejected: {result.issues}")
                store.foundation(dossier_id, result.output_blob)
            return dossier_view(store.dossier(dossier_id))

    @app.post("/api/v1/dossiers/{dossier_id}/review-foundation")
    def approve_foundation(dossier_id: str, body: FoundationReviewRequest):
        with mutation():
            row = store.dossier(dossier_id)
            if row["approved"]:
                raise ValueError("foundation already approved")
            ref, _ = foundation_value(row)
            if ref.sha256 != body.candidate_digest:
                raise ValueError("STALE_REVIEW: candidate digest changed")
            suffix = uuid4().hex
            with local_review_application(settings, body.password.get_secret_value()) as args:
                cases, context, human_cap, actor, service_cap = args
                proof = cases.kernel.blob_store.put(
                    body.accepted_qualifications.encode(), "text/plain"
                )
                result = FoundationReviewer(
                    cases, service_actor=actor, service_capability=service_cap
                ).approve(
                    context,
                    FoundationApproval(
                        candidate_blob=ref,
                        approval_evidence_blob=proof,
                        approval_reference=f"approval:api_{suffix}",
                        accepted_qualifications=body.accepted_qualifications,
                        reviewed_profile_version=f"api-reviewed-{suffix}",
                        approved_profile_version=f"api-approved-{suffix}",
                        reviewed_case_snapshot_id=f"snapshot:api_case_reviewed_{suffix}",
                        approved_case_snapshot_id=f"snapshot:api_case_approved_{suffix}",
                        reviewed_corpus_snapshot_id=f"snapshot:api_corpus_reviewed_{suffix}",
                        approved_corpus_snapshot_id=f"snapshot:api_corpus_approved_{suffix}",
                    ),
                    capability=human_cap,
                )
                if result.output is None:
                    raise ValueError(f"foundation review failed: {result.issues}")
                store.foundation(dossier_id, result.output_blob, approved=True)
            return dossier_view(store.dossier(dossier_id))

    @app.get("/api/v1/dossiers/{dossier_id}/evidence")
    def evidence(dossier_id: str):
        row = store.dossier(dossier_id)
        _, foundation = foundation_value(row, approved=bool(row["approved"]))
        with local_application(settings) as (cases, _, _):
            blobs = cases.kernel.blob_store
            membership = json.loads(blobs.get(foundation.case_snapshot.membership_blob))
            observations = [
                json.loads(line)
                for item in membership["extractions"]
                for line in blobs.get(
                    BlobRef.model_validate(item["observations_blob"])
                ).splitlines()
            ]
        return {
            "snapshot": {
                "snapshot_id": foundation.case_snapshot.snapshot_id,
                "membership_digest": foundation.case_snapshot.membership_digest,
            },
            "records": membership["normalization"]["records"],
            "observations": observations,
            "originals": membership["originals"],
        }

    @app.get("/api/v1/dossiers/{dossier_id}/artifacts/{artifact_revision_id}")
    def artifact(dossier_id: str, artifact_revision_id: str):
        row = store.dossier(dossier_id)
        _, foundation = foundation_value(row, approved=bool(row["approved"]))
        with local_application(settings) as (cases, _, _):
            blobs = cases.kernel.blob_store
            membership = json.loads(blobs.get(foundation.case_snapshot.membership_blob))
            originals = [
                item
                for item in membership["originals"]
                if item["artifact_revision_id"] == artifact_revision_id
            ]
            if len(originals) != 1:
                raise KeyError("artifact is not an original in this dossier")
            original = originals[0]
            content = blobs.get(BlobRef.model_validate(original["blob"]))
            reference = BlobRef.model_validate(original["blob"])
            return Response(
                content,
                media_type=reference.media_type,
                headers={
                    "Content-Disposition": "inline",
                    "X-Content-Type-Options": "nosniff",
                    "Content-Security-Policy": "sandbox",
                },
            )

    @app.post("/api/v1/dossiers/{dossier_id}/support-review")
    def support_review(dossier_id: str, body: SupportReviewRequest):
        with mutation():
            _, foundation = foundation_value(store.dossier(dossier_id), approved=True)
            if body.snapshot_digest != foundation.case_snapshot.membership_digest:
                raise ValueError("STALE_REVIEW: support snapshot changed")
            suffix = uuid4().hex
            from recycleguard.contracts.artifacts import SnapshotRef

            with local_review_application(settings, body.password.get_secret_value()) as args:
                cases, context, human_cap, actor, service_cap = args
                snapshot = SupportReviewer(
                    cases, service_actor=actor, service_capability=service_cap
                ).approve(
                    context,
                    RecordSupportReview(
                        target=SnapshotRef(
                            snapshot_id=foundation.case_snapshot.snapshot_id,
                            membership_digest=foundation.case_snapshot.membership_digest,
                        ),
                        reviewed_snapshot_id=f"snapshot:api_support_reviewed_{suffix}",
                        approved_snapshot_id=f"snapshot:api_support_approved_{suffix}",
                        assertions=body.assertions,
                        reason=body.reason,
                    ),
                    capability=human_cap,
                )
                updated = foundation.model_copy(update={"case_snapshot": snapshot})
                blob = cases.kernel.blob_store.put(
                    canonical_json_bytes(updated.model_dump(mode="json")), "application/json"
                )
                store.foundation(dossier_id, blob, approved=True)
            return dossier_view(store.dossier(dossier_id))

    @app.post("/api/v1/runs", status_code=202)
    def start_run(body: RunRequest):
        with scheduling_lock:
            if any(not future.done() for future in active.values()):
                raise HTTPException(409, detail="Another investigation is active")
            with mutation():
                _, foundation = foundation_value(store.dossier(body.dossier_id), approved=True)
                from recycleguard.contracts.artifacts import SnapshotRef

                config = None
                steps = []
                if body.mode == "MODEL_BACKED":
                    if options.model_config_path is None:
                        raise ValueError("local model is not configured")
                    config = LocalModelConfig.model_validate_json(
                        options.model_config_path.read_bytes()
                    )
                else:
                    if (
                        settings.mode != "test"
                        or not settings.enable_test_adapters
                        or not options.test_exchanges
                    ):
                        raise ValueError(
                            "scripted mode requires explicitly configured test adapters"
                        )
                    steps = list(options.test_exchanges)
                budgets = body.budgets
                if budgets is None:
                    budgets = (
                        BudgetLimits()
                        if config is None
                        else BudgetLimits(
                            tokens_per_model_call=config.max_total_tokens,
                            max_total_tokens=config.max_total_tokens * 12,
                            max_model_calls=12,
                            max_wall_seconds=600,
                        )
                    )
                run_id = "run:" + uuid4().hex
                finding_ids = [f"finding:{run_id.split(':')[1]}"]
                if config is None:
                    scripted_ids = []
                    for step in steps:
                        if step.phase == "PLAN":
                            plan = PlanProposal.model_validate_json(
                                canonical_json_bytes(step.response)
                            )
                            if plan.action is not None:
                                scripted_ids.append(plan.action.finding_id)
                    finding_ids = list(dict.fromkeys(scripted_ids)) or finding_ids
                with local_application(settings) as (cases, context, cap):
                    service = InvestigationService(cases, settings, capability=cap)
                    spec = service.prepare(
                        context,
                        InvestigationRequest(
                            run_id=run_id,
                            case_snapshot=SnapshotRef(
                                snapshot_id=foundation.case_snapshot.snapshot_id,
                                membership_digest=foundation.case_snapshot.membership_digest,
                            ),
                            corpus_snapshot=SnapshotRef(
                                snapshot_id=foundation.corpus_snapshot.snapshot_id,
                                membership_digest=foundation.corpus_snapshot.membership_digest,
                            ),
                            finding_ids=finding_ids,
                            scripted_exchanges=steps,
                            local_model_config=config,
                            budgets=budgets,
                        ),
                    )
                    runner = service.runner(spec)
                    try:
                        runner.start_run(context, spec, capability=cap)
                    finally:
                        runner.close()
                store.add_job(run_id, body.dossier_id)
                active[run_id] = executor.submit(drive, run_id, False)
        return {"run_id": run_id, "status": "QUEUED", "mode": body.mode}

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str):
        return run_view(run_id)

    @app.post("/api/v1/runs/{run_id}/resume", status_code=202)
    def resume_run(run_id: str):
        state = run_view(run_id)["state"]
        if state["status"] in _STOPPED:
            raise ValueError("paused or terminal run cannot resume; use review or a new run")
        schedule(run_id, resume=True)
        return {"run_id": run_id, "status": "QUEUED"}

    @app.post("/api/v1/runs/{run_id}/cancel", status_code=202)
    def cancel(run_id: str):
        state = run_view(run_id)["state"]
        if state["status"] in {
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "BLOCKED_INPUT",
            "BLOCKED_OUTPUT",
        }:
            raise ValueError("terminal run cannot be cancelled")
        store.request_cancel(run_id)
        if run_id not in active or active[run_id].done():
            with mutation(), local_application(settings) as (cases, context, cap):
                service = InvestigationService(cases, settings, capability=cap)
                runner = service.runner(service.store.spec(run_id))
                try:
                    runner.cancel(
                        context, run_id, state["version"], "API cancellation", capability=cap
                    )
                finally:
                    runner.close()
        return {
            "run_id": run_id,
            "cancellation_requested": True,
            "note": (
                "Takes effect between graph turns; in-flight inference is not repeated or killed."
            ),
        }

    @app.get("/api/v1/runs/{run_id}/trace")
    def trace(run_id: str, after: Annotated[int, Field(ge=0)] = 0):
        store.job(run_id)
        with local_application(settings) as (cases, _, cap):
            service = InvestigationService(cases, settings, capability=cap)
            rows = trace_events(service, run_id, after=after)
        return {
            "run_id": run_id,
            "events": rows,
            "last_sequence": after if not rows else rows[-1]["sequence"],
        }

    @app.get("/api/v1/runs/{run_id}/events")
    async def events(
        run_id: str,
        request: Request,
        after: Annotated[int, Field(ge=0)] = 0,
        last_event_id: Annotated[str | None, Header()] = None,
    ):
        store.job(run_id)
        cursor = after
        if last_event_id is not None:
            try:
                cursor = max(cursor, int(last_event_id))
            except ValueError as exc:
                raise HTTPException(422, detail="Last-Event-ID must be a sequence integer") from exc

        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                page = await asyncio.to_thread(trace, run_id, cursor)
                for item in page["events"]:
                    cursor = item["sequence"]
                    yield f"id: {cursor}\nevent: trace\ndata: {json.dumps(item)}\n\n"
                job = store.job(run_id)
                if job["status"] not in {"RUNNING", "QUEUED"}:
                    yield f"event: stopped\ndata: {json.dumps(job)}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/runs/{run_id}/audit")
    def audit(run_id: str):
        from recycleguard.knowledge.corpus_audit import audit_frozen_corpus_profile

        store.job(run_id)
        with local_application(settings) as (cases, _, cap):
            service = InvestigationService(cases, settings, capability=cap)
            spec = service.store.spec(run_id)
            configuration = InvestigationConfiguration.model_validate_json(
                service.blobs.get(spec.runtime_configuration)
            )
            manifest = configuration.index_manifest
            return audit_frozen_corpus_profile(
                corpus_snapshot=cases.snapshots.get(spec.corpus_snapshot),
                profile=cases.profiles.get(spec.profile, require_approved=True),
                index_manifest=manifest,
                blobs=service.blobs,
                index_path=settings.data_root
                / "indexes"
                / manifest.index_id.replace(":", "_")
                / "index.sqlite",
                expected_corpus=spec.corpus_snapshot,
                expected_profile=spec.profile,
                expected_index=spec.index,
                kernel=cases.kernel,
                runtime_metadata={
                    "execution_kind": spec.execution_kind,
                    "model_configuration_id": spec.model.configuration_id,
                },
            )

    @app.get("/api/v1/runs/{run_id}/report")
    def report(run_id: str):
        store.job(run_id)
        with local_application(settings) as (cases, _, cap):
            return InvestigationService(cases, settings, capability=cap).latest_report(run_id)

    @app.post("/api/v1/runs/{run_id}/packet")
    def packet(run_id: str):
        store.job(run_id)
        with mutation(), local_application(settings) as (cases, context, cap):
            service = InvestigationService(cases, settings, capability=cap)
            service.recover_reviews(context, run_id)
            return service.packet(context, service.store.spec(run_id))

    @app.post("/api/v1/runs/{run_id}/review")
    def review(run_id: str, body: DecisionRequest):
        store.job(run_id)
        with (
            mutation(),
            local_review_application(settings, body.password.get_secret_value()) as args,
        ):
            cases, human, human_cap, actor, cap = args
            service = InvestigationService(cases, settings, capability=cap)
            service.recover_reviews(command_context(actor), run_id)
            reviewer = service.review_service()
            packet = reviewer.get_packet(body.packet_id)
            if packet.run_id != run_id:
                raise ValueError("packet belongs to a different run")
            spec = service.store.spec(run_id)
            result = reviewer.submit_review(
                service.bound(human, spec),
                packet.packet_id,
                body.expected_dependency_digest,
                ReviewDecision(
                    decision=body.decision,
                    authenticated_reviewer_ref=human.actor,
                    reason=body.reason,
                    recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                ),
                capability=human_cap,
            )
            if result.status != "SUCCESS":
                raise ValueError(f"review rejected: {result.issues}")
            state = service.project_review(command_context(actor), packet.packet_id)
            if state.status == "DRAFTING":
                schedule(run_id)
            return state

    return app
