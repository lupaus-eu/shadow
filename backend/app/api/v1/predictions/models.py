from datetime import date as dt_date
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


class PredictionRequest(Base):
    __tablename__ = "prediction_requests"
    __table_args__ = (
        UniqueConstraint(
            "prediction_request_key", name="uq_prediction_requests_key"
        ),
        UniqueConstraint(
            "completed_prediction_version_id",
            name="uq_prediction_requests_completed_version",
        ),
        ForeignKeyConstraint(
            ["completed_prediction_version_id", "organisation_id"],
            [
                "prediction_versions.prediction_version_id",
                "prediction_versions.organisation_id",
            ],
            name="fk_prediction_requests_completed_version_organisation",
        ),
        CheckConstraint(
            "state IN ('queued', 'running', 'cancelling', 'completed', "
            "'cancelled', 'failed')",
            name="ck_prediction_requests_state",
        ),
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_prediction_requests_name_non_blank"
        ),
        CheckConstraint(
            "(cancellation_time IS NULL) = (cancelled_by IS NULL)",
            name="ck_prediction_requests_cancellation_audit",
        ),
        CheckConstraint(
            "(state IN ('cancelling', 'cancelled')) = "
            "(cancellation_time IS NOT NULL)",
            name="ck_prediction_requests_cancellation_state",
        ),
        CheckConstraint(
            "(state = 'queued' AND start_time IS NULL) OR "
            "(state IN ('running', 'cancelling', 'completed', 'failed') AND "
            "start_time IS NOT NULL) OR state = 'cancelled'",
            name="ck_prediction_requests_start_state",
        ),
        CheckConstraint(
            "(state IN ('completed', 'cancelled', 'failed')) = "
            "(finish_time IS NOT NULL)",
            name="ck_prediction_requests_finish_state",
        ),
        CheckConstraint(
            "(state IN ('running', 'cancelling')) = (worker_id IS NOT NULL)",
            name="ck_prediction_requests_worker_state",
        ),
        CheckConstraint(
            "(state = 'completed') = "
            "(completed_prediction_version_id IS NOT NULL)",
            name="ck_prediction_requests_completed_link",
        ),
        CheckConstraint(
            "(state = 'failed') = "
            "(failure_code IS NOT NULL AND failure_reason IS NOT NULL)",
            name="ck_prediction_requests_failure_state",
        ),
        Index(
            "ux_prediction_requests_active_organisation_name",
            "organisation_id",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("state IN ('queued', 'running', 'cancelling')"),
            sqlite_where=text("state IN ('queued', 'running', 'cancelling')"),
        ),
        Index(
            "idx_prediction_requests_queue",
            "submitted_time",
            "prediction_request_id",
            postgresql_where=text("state = 'queued'"),
            sqlite_where=text("state = 'queued'"),
        ),
        Index(
            "idx_prediction_requests_organisation_active",
            "organisation_id",
            "submitted_time",
            "prediction_request_id",
            postgresql_where=text(
                "state IN ('queued', 'running', 'cancelling')"
            ),
            sqlite_where=text("state IN ('queued', 'running', 'cancelling')"),
        ),
        Index(
            "idx_prediction_requests_organisation_finished",
            "organisation_id",
            text("finish_time DESC"),
            text("prediction_request_id DESC"),
        ),
    )

    prediction_request_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey, primary_key=True
    )
    prediction_request_key: Mapped[str] = mapped_column(Text)
    organisation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organisations.organisation_id")
    )
    name: Mapped[str] = mapped_column(Text)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(Text, default="queued")
    submitted_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finish_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    submitted_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    cancelled_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=True
    )
    cancellation_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_prediction_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )


class PredictionVersion(Base):
    __tablename__ = "prediction_versions"
    __table_args__ = (
        UniqueConstraint(
            "prediction_version_id",
            "organisation_id",
            name="uq_prediction_versions_id_organisation",
        ),
    )

    prediction_version_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey, primary_key=True
    )
    organisation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("organisations.organisation_id")
    )
    prediction_key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    cutoff_mode: Mapped[str] = mapped_column(Text)
    confidence_level: Mapped[int] = mapped_column(Integer, default=80)
    start_date: Mapped[dt_date] = mapped_column(Date)
    end_date: Mapped[dt_date] = mapped_column(Date)
    model_configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=True
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PredictionTarget(Base):
    __tablename__ = "prediction_targets"

    prediction_target_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey, primary_key=True
    )
    prediction_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("prediction_versions.prediction_version_id", ondelete="CASCADE"),
    )
    target_scenario_id: Mapped[int] = mapped_column(BigInteger)
    target_scenario_key: Mapped[str] = mapped_column(Text)
    metric_key: Mapped[str] = mapped_column(Text)
    metric_name: Mapped[str] = mapped_column(Text)
    time_unit: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_status: Mapped[str] = mapped_column(Text)
    eligibility_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    seasonal_period: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seasonal_period_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    input_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=True
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PredictionModelResult(Base):
    __tablename__ = "prediction_model_results"

    prediction_model_result_id: Mapped[int] = mapped_column(
        BigIntPrimaryKey, primary_key=True
    )
    prediction_target_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("prediction_targets.prediction_target_id", ondelete="CASCADE"),
    )
    result_kind: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    prediction_interval_status: Mapped[str] = mapped_column(Text)
    prediction_interval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cross_validation_status: Mapped[str] = mapped_column(Text)
    cross_validation_mae: Mapped[float | None] = mapped_column(Float, nullable=True)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=True
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PredictionPoint(Base):
    __tablename__ = "prediction_points"

    prediction_point_id: Mapped[int] = mapped_column(BigIntPrimaryKey, primary_key=True)
    prediction_model_result_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "prediction_model_results.prediction_model_result_id", ondelete="CASCADE"
        ),
    )
    date: Mapped[dt_date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    lower_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_bound: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id"), nullable=True
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
