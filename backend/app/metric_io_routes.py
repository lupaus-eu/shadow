"""Import and export: metric values as CSV or Excel, and an analysis as an Excel workbook.

Import takes the file as the request body (``?filename=`` names it) and applies it to the input
metrics of one version; derived metrics, unknown metrics and unreadable cells are reported and
skipped. Everything else is written in one transaction, with an audit entry.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis_routes import _build, _simulation
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.metric_engine import series_of_version
from app.metric_io import MAX_BYTES, ImportError_, csv_bytes, parse_table, series_table, workbook_bytes
from app.model_routes import _audit, _editor_session, _member_session, _model, version_of
from app.models import MetricValue, Recommendation
from app.simulation_routes import result_of

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ImportReport(BaseModel):
    metrics: int
    values: int
    unknown_metrics: list[str]
    derived_metrics: list[str]
    invalid_cells: int


def _filename(name: str) -> str:
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in name)[:80] or "export"


def create_metric_io_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Import and export"])
    base = "/{organization_id}/models/{model_id}"

    @router.post(base + "/versions/{version_id}/metrics/import", response_model=ImportReport)
    async def import_values(organization_id: UUID, model_id: UUID, version_id: UUID, request: Request, filename: str = "values.csv", user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> ImportReport:
        if int(request.headers.get("content-length") or 0) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="the file is too large")
        data = await request.body()

        def apply() -> ImportReport:
            try:
                parsed = parse_table(data, filename)
            except ImportError_ as error:
                raise HTTPException(status_code=422, detail=str(error)) from None
            with _editor_session(session_factory, organization_id, user) as session:
                _model(session, organization_id, model_id)
                version = version_of(session, organization_id, model_id, version_id)
                metrics, _ = series_of_version(session, version.id)
                by_label = {**{metric.name.lower(): metric for metric in metrics.values()}, **{key: metric for key, metric in metrics.items()}}
                unknown, derived, written, touched = [], [], 0, 0
                for label, series in parsed.values.items():
                    metric = by_label.get(label.lower())
                    if metric is None:
                        unknown.append(label)
                        continue
                    if metric.formula:
                        derived.append(metric.key)
                        continue
                    existing = {value.period: value for value in session.scalars(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.period.in_(list(series)))).all()}
                    for period, number in series.items():
                        if period in existing:
                            existing[period].value = number
                        else:
                            session.add(MetricValue(metric_id=metric.id, period=period, organization_id=organization_id, version_id=version.id, value=number))
                    touched += 1
                    written += len(series)
                session.flush()
                _audit(session, request, "metric.values_imported", "model_version", version.id, {"metrics": touched, "values": written, "skipped_metrics": len(unknown) + len(derived)})
                return ImportReport(metrics=touched, values=written, unknown_metrics=sorted(unknown), derived_metrics=sorted(derived), invalid_cells=parsed.invalid_cells)

        return await run_in_threadpool(apply)

    @router.get(base + "/versions/{version_id}/metrics/export")
    def export_values(organization_id: UUID, model_id: UUID, version_id: UUID, format: Literal["csv", "xlsx"] = "csv", user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            model = _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model_id, version_id)
            metrics, series = series_of_version(session, version.id)
            rows = series_table([(key, series[key]) for key in metrics])
            name = _filename(f"{model.name}-{version.name}-metrics")
        if format == "csv":
            return Response(csv_bytes(rows), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
        return Response(workbook_bytes({"Metrics": rows}), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})

    @router.get(base + "/simulations/{simulation_id}/analysis/export")
    def export_analysis(organization_id: UUID, model_id: UUID, simulation_id: UUID, compare_to: UUID | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            model = _model(session, organization_id, model_id)
            simulation = _simulation(session, model_id, simulation_id)
            other = _simulation(session, model_id, compare_to) if compare_to else None
            analysis = _build(session, simulation, other)
            result = result_of(session, simulation)
            order = {"high": 0, "medium": 1, "low": 2}
            stored = sorted(session.scalars(select(Recommendation).where(Recommendation.simulation_id == simulation.id)).all(), key=lambda row: (order[row.severity], row.metric_key, row.kind))
            summary = [
                ["Model", model.name],
                ["Simulation", simulation.name],
                ["Method", simulation.method],
                ["Horizon (months)", simulation.horizon_months],
                ["What-if adjustments", "; ".join(f"{item['metric_key']} {item['change_pct']:+g} %" for item in simulation.adjustments) or ""],
                ["Compared against", other.name if other else ""],
                ["Summary", simulation.analysis_summary or ""],
                ["Summary written by", simulation.analysis_summary_author or ""],
                ["Summary written at", simulation.analysis_summary_at.strftime("%Y-%m-%d %H:%M") if simulation.analysis_summary_at else ""],
            ]
            findings = [["Metric", "Key", "Unit", "Start", "End", "Change", "Trend", "Turns negative", "Band / value", "Versus other run"]] + [
                [item.name, item.key, item.unit, item.start, item.end, item.change_pct, item.trend, item.turns_negative.strftime("%Y-%m") if item.turns_negative else None, item.band_ratio, item.versus] for item in analysis.findings
            ]
            proposals = [["Severity", "Metric", "Source", "Status", "Title", "Rationale"]] + [[row.severity, row.metric_key, "agent" if row.kind == "agent" else "rule", row.status, row.title, row.rationale] for row in stored]
            keys = [metric.key for metric in result.metrics]
            header: list[object] = ["Period"]
            for key in keys:
                header += [key, f"{key} lower", f"{key} upper"]
            lookup = {metric.key: {point.period: point for point in metric.forecast} for metric in result.metrics}
            periods = sorted({period for points in lookup.values() for period in points})
            forecast = [header] + [[period.strftime("%Y-%m"), *[value for key in keys for value in ((lookup[key][period].value, lookup[key][period].lower, lookup[key][period].upper) if period in lookup[key] else (None, None, None))]] for period in periods]
            name = _filename(f"{model.name}-{simulation.name}-analysis")
        data = workbook_bytes({"Summary": summary, "Findings": findings, "Proposals": proposals, "Forecast": forecast})
        return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})

    return router
