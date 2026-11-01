"""MG1 smoke driver (scratchpad, not part of the repo): real local model, dev cases only."""
import json, secrets, sys, time
from pathlib import Path
from fastapi.testclient import TestClient
from recycleguard.api import ApiOptions, create_app
from recycleguard.config import Settings
from recycleguard.contracts.core import EvidenceRef

BASE = "/api/v1"
data_root, out, cfg = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CASES = [("F01_CLEAN_BASELINE", "case_10f56abef2"), ("F07_PAID_NO_TRANSFER", "case_06a6c66e74"),
         ("F16_PROMPT_INJECTION", "case_e850a98a6c")]
KILL = ("F04_UNIT_DIMENSION_MIX", "case_8659baf637")
out.mkdir(parents=True)
password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
app = create_app(ApiOptions(settings=Settings(data_root=data_root), token=token, model_config_path=cfg))
results = []
with TestClient(app) as c:
    c.headers["Authorization"] = "Bearer " + token
    def req(m, p, b=None, code=200):
        r = c.request(m, BASE + p, json=b)
        if r.status_code != code:
            raise RuntimeError(f"{m} {p}: {r.status_code} {r.text[:300]}")
        return r.json()
    req("POST", "/reviewer", {"actor_id": "human:mg1_smoke_fixture", "password": password}, 201)
    def prepare(fixture):
        d = req("POST", "/dossiers/select", {"fixture_id": fixture}, 201)["dossier_id"]
        p = req("POST", f"/dossiers/{d}/prepare")
        req("POST", f"/dossiers/{d}/review-foundation", {"password": password,
            "candidate_digest": p["candidate_digest"],
            "accepted_qualifications": "MG1 smoke fixture review; synthetic data; applicability unknown."})
        ev = req("GET", f"/dossiers/{d}/evidence")
        obs = {o["observation_id"]: o for o in ev["observations"]}
        asr = []
        for rec in ev["records"]:
            if rec["record_type"] not in {"Certificate", "CertificateEvent", "Allocation"}:
                continue
            def ok(o, rt=rec["record_type"]):
                f = o["parsed_fields"]
                if f.get("record_type") != rt: return False
                if rt == "Allocation" and f.get("state") != "SUPPORTED": return False
                if rt == "CertificateEvent" and (f.get("assertion_state") != "SUPPORTED" or f.get("transfer_stage") != "COMPLETED"): return False
                return True
            cand = [obs[k] for k in rec["observation_refs"] if ok(obs[k])]
            if not cand:
                continue
            o = cand[0]
            ref = EvidenceRef(ref_kind="OBSERVATION", ref_id=o["observation_id"],
                              artifact_revision_id=o["artifact_revision_id"], locator=o["locator"])
            asr.append({"target_record_revision_id": rec["record_revision_id"],
                        "evidence_refs": [ref.model_dump(mode="json")],
                        "reason": "MG1 smoke: exact structured support reviewed (synthetic fixture)."})
        req("POST", f"/dossiers/{d}/support-review", {"password": password,
            "snapshot_digest": ev["snapshot"]["membership_digest"], "assertions": asr,
            "reason": "MG1 smoke fixture support review."})
        return d, len(asr)
    for family, fx in CASES:
        row = {"family": family, "fixture": fx}
        try:
            d, n = prepare(fx); row["support_assertions"] = n
            t = time.monotonic()
            rid = req("POST", "/runs", {"dossier_id": d, "mode": "MODEL_BACKED"}, 202)["run_id"]
            while time.monotonic() - t < 900:
                r = req("GET", f"/runs/{rid}")
                if r["job"]["status"] in {"STOPPED", "FAILED"}:
                    break
                time.sleep(1)
            row.update(run_id=rid, seconds=round(time.monotonic() - t, 1), job=r["job"]["status"],
                       status=r["state"]["status"], stop_reason=r["state"].get("stop_reason"),
                       budget=r["state"]["budget"])
            tr = req("GET", f"/runs/{rid}/trace")
            ev = tr["events"]
            row["trace_events"] = len(ev)
            row["wire_exchanges"] = sum(1 for e in ev if e.get("provider_trace") is not None)
            row["tools"] = [e.get("tool") or e.get("operation") for e in ev if e["kind"] == "TOOL_PROPOSED"]
            if row["status"] == "AWAITING_REVIEW":
                rep = req("GET", f"/runs/{rid}/report")
                row["verdict"] = rep["verification"]["verdict"]
                row["balances"] = rep["report"]["calculations"][0]["bucket_results"]
                row["audit"] = req("GET", f"/runs/{rid}/audit")["verification_status"]
        except Exception as e:
            row["error"] = str(e)[:500]
        results.append(row); print(json.dumps({k: row.get(k) for k in ("family", "status", "seconds", "error")}), flush=True)
    # kill-switch: cancel mid-run
    krow = {"family": KILL[0], "fixture": KILL[1], "test": "cancel_mid_run"}
    try:
        d, _ = prepare(KILL[1])
        rid = req("POST", "/runs", {"dossier_id": d, "mode": "MODEL_BACKED"}, 202)["run_id"]
        time.sleep(6)
        pre = req("GET", f"/runs/{rid}")
        krow["status_before_cancel"] = pre["state"]["status"]
        krow["cancel_response"] = req("POST", f"/runs/{rid}/cancel", {"reason": "MG1 kill-switch test"} , 202)
        t = time.monotonic()
        while time.monotonic() - t < 300:
            r = req("GET", f"/runs/{rid}")
            if r["job"]["status"] in {"STOPPED", "FAILED"}:
                break
            time.sleep(1)
        krow.update(final_status=r["state"]["status"], job=r["job"]["status"], seconds_to_stop=round(time.monotonic() - t, 1),
                    budget=r["state"]["budget"], audit=req("GET", f"/runs/{rid}/audit")["verification_status"])
    except Exception as e:
        krow["error"] = str(e)[:500]
    results.append(krow); print(json.dumps(krow, default=str)[:600], flush=True)
(out / "results.json").write_text(json.dumps(results, indent=2, default=str))
(data_root / "reviewer.json").unlink(missing_ok=True)
