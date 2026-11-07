"""Simulations may use the Prophet forecasting method.

Revision ID: 0056
Revises: 0055
"""

from alembic import op


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_simulations_method", "simulations", type_="check")
    op.create_check_constraint("ck_simulations_method", "simulations", "method IN ('linear', 'seasonal', 'holt', 'prophet')")
