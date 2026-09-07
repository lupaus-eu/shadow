from datetime import date as dt_date
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base

BigIntPrimaryKey = BigInteger().with_variant(Integer, "sqlite")


class PredictionVersion(Base):
    __tablename__ = "prediction_versions"

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
