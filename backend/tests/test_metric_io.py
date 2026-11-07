"""Import and export of metric values and analyses (feature 11)."""
import io
from contextlib import ExitStack
from datetime import date

import pytest
from openpyxl import Workbook, load_workbook

from app.metric_io import ImportError_, parse_table
from test_metrics import _setup, _values


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_tables_are_read_in_wide_and_long_layouts() -> None:
    wide = parse_table("Month;revenue;Cost price\n2025-01;1 000,5;10\n1.2.2025;1200;abc\n3/2025;;12\nnope;1;2\n".encode(), "x.csv")
    assert wide.values["revenue"] == {date(2025, 1, 1): 1000.5, date(2025, 2, 1): 1200.0}
    assert wide.values["Cost price"] == {date(2025, 1, 1): 10.0, date(2025, 3, 1): 12.0}
    assert wide.invalid_cells == 3  # "abc" and the two cells of the row with an unreadable month
    long = parse_table(b"metric,period,value\nrevenue,2025-01-15,5\nrevenue,2025-02,6\n,2025-03,7\n", "x.csv")
    assert long.values == {"revenue": {date(2025, 1, 1): 5.0, date(2025, 2, 1): 6.0}}
    workbook = Workbook()
    workbook.active.append(["period", "revenue"])
    workbook.active.append([date(2025, 4, 20), 9])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert parse_table(buffer.getvalue(), "x.xlsx").values == {"revenue": {date(2025, 4, 1): 9.0}}
    for bad in (b"only a header\n", b"a\n1\n"):
        with pytest.raises(ImportError_):
            parse_table(bad, "x.csv")
    with pytest.raises(ImportError_):
        parse_table(b"PK not a workbook", "x.xlsx")


def test_values_import_and_export_round_trip(database_url: str, stack: ExitStack) -> None:
    owner, path, url = _setup(stack, database_url, "io-values")
    owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"})
    owner.post(url, json={"key": "cost", "name": "Cost"})
    owner.post(url, json={"key": "profit", "name": "Profit", "formula": "revenue - cost"})
    csv = "period;revenue;Cost;profit;ghost\n2025-01;100;40;1;1\n2025-02;110;45;2;2\n"
    report = owner.post(f"{url}/import", params={"filename": "v.csv"}, content=csv.encode(), headers={"Content-Type": "text/csv"})
    assert report.status_code == 200
    assert report.json() == {"metrics": 2, "values": 4, "unknown_metrics": ["ghost"], "derived_metrics": ["profit"], "invalid_cells": 0}
    exported = owner.get(f"{url}/export")
    assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
    lines = exported.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "period,cost,profit,revenue" and lines[1] == "2025-01,40.0,60.0,100.0"
    sheet = load_workbook(io.BytesIO(owner.get(f"{url}/export", params={"format": "xlsx"}).content)).active
    assert [cell.value for cell in sheet[3]] == ["2025-02", 45, 65, 110]
    assert owner.post(f"{url}/import", params={"filename": "v.csv"}, content=b"nothing").status_code == 422


def test_an_analysis_exports_as_a_workbook(database_url: str, stack: ExitStack) -> None:
    owner, path, url = _setup(stack, database_url, "io-analysis")
    revenue = owner.post(url, json={"key": "revenue", "name": "Revenue", "unit": "EUR"}).json()
    _values(owner, url, revenue["id"], [(f"2025-{m:02d}-01", 200 - 3 * m) for m in range(1, 13)])
    run = owner.post(f"{url.replace('/metrics', '')}/simulations", json={"name": "Trend", "horizon_months": 6}).json()["simulation"]["id"]
    api = f"{path}/simulations/{run}"
    owner.post(f"{api}/analysis")
    response = owner.get(f"{api}/analysis/export")
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook.sheetnames == ["Summary", "Findings", "Proposals", "Forecast"]
    assert [cell.value for cell in workbook["Findings"][2]][:2] == ["Revenue", "revenue"]
    assert workbook["Proposals"].max_row >= 2 and workbook["Forecast"].max_row == 7
