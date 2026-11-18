"""Generate sample datasets for DataPilot.

The datasets are deterministic (fixed seed) so tests can assert exact expected
values. Each file exercises a different code path:
  * sales_data.csv     — realistic business data with missing values, duplicates
                         and outliers; the main acceptance-test dataset.
  * iris.csv           — classic 3-group dataset for ANOVA / t-tests.
  * employees.json     — JSON array of objects with nested fields.
  * inventory.xlsx     — Excel workbook with two sheets.
  * tiny_known.csv     — hand-computable values for exact regression tests.

Run:  python sample_data/generate_samples.py
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RNG = np.random.default_rng(42)


def make_sales() -> pd.DataFrame:
    """Monthly sales across regions/products with deliberate data-quality issues."""
    months = pd.date_range("2023-01-01", periods=24, freq="MS")
    regions = ["North", "South", "East", "West"]
    products = ["Laptop", "Phone", "Tablet", "Monitor", "Keyboard", "Mouse"]

    rows = []
    base_price = {
        "Laptop": 1200.0, "Phone": 800.0, "Tablet": 450.0,
        "Monitor": 320.0, "Keyboard": 90.0, "Mouse": 35.0,
    }
    region_multiplier = {"North": 1.15, "South": 0.95, "East": 1.05, "West": 0.88}

    for month_index, month in enumerate(months):
        # A mild upward trend plus seasonality, so a time-trend chart is meaningful.
        trend = 1.0 + 0.015 * month_index
        season = 1.0 + 0.18 * np.sin(2 * np.pi * (month.month - 1) / 12)

        for region in regions:
            for product in products:
                quantity = int(
                    max(
                        1,
                        RNG.normal(
                            loc=40 * region_multiplier[region] * trend * season,
                            scale=9,
                        ),
                    )
                )
                unit_price = round(
                    base_price[product] * RNG.normal(1.0, 0.04), 2
                )
                rows.append({
                    "order_date": month.strftime("%Y-%m-%d"),
                    "region": region,
                    "product": product,
                    "units_sold": quantity,
                    "unit_price": unit_price,
                    "revenue": round(quantity * unit_price, 2),
                    "customer_segment": RNG.choice(
                        ["Enterprise", "SMB", "Consumer"], p=[0.25, 0.35, 0.40]
                    ),
                    "satisfaction_score": round(
                        float(np.clip(RNG.normal(4.1, 0.6), 1, 5)), 1
                    ),
                })

    frame = pd.DataFrame(rows)

    # --- Deliberate data-quality issues (realistic imports) --------------
    # 1. Missing values in two columns.
    missing_idx = RNG.choice(frame.index, size=45, replace=False)
    frame.loc[missing_idx[:25], "satisfaction_score"] = np.nan
    frame.loc[missing_idx[25:], "customer_segment"] = np.nan

    # 2. Duplicate rows.
    duplicates = frame.sample(n=12, random_state=7)
    frame = pd.concat([frame, duplicates], ignore_index=True)

    # 3. Extreme outliers in revenue (data-entry errors).
    outlier_idx = RNG.choice(frame.index, size=6, replace=False)
    frame.loc[outlier_idx, "revenue"] = frame.loc[outlier_idx, "revenue"] * 45

    # 4. A numeric column stored as text with a currency symbol, plus blanks.
    frame["unit_price_text"] = frame["unit_price"].map(lambda v: f"${v:,.2f}")
    text_blank_idx = RNG.choice(frame.index, size=18, replace=False)
    frame.loc[text_blank_idx, "unit_price_text"] = ""

    return frame.sample(frac=1.0, random_state=11).reset_index(drop=True)


def make_iris() -> pd.DataFrame:
    """Iris dataset — 150 rows, 3 balanced species, well-known statistics."""
    # Canonical iris measurements (public domain, Fisher 1936).
    data = {
        "sepal_length": [
            5.1, 4.9, 4.7, 4.6, 5.0, 5.4, 4.6, 5.0, 4.4, 4.9, 5.4, 4.8, 4.8,
            4.3, 5.8, 5.7, 5.4, 5.1, 5.7, 5.1, 5.4, 5.1, 4.6, 5.1, 4.8, 5.0,
            5.0, 5.2, 5.2, 4.7, 4.8, 5.4, 5.2, 5.5, 4.9, 5.0, 5.5, 4.9, 4.4,
            5.1, 5.0, 4.5, 4.4, 5.0, 5.1, 4.8, 5.1, 4.6, 5.3, 5.0,
            7.0, 6.4, 6.9, 5.5, 6.5, 5.7, 6.3, 4.9, 6.6, 5.2, 5.0, 5.9, 6.0,
            6.1, 5.6, 6.7, 5.6, 5.8, 6.2, 5.6, 5.9, 6.1, 6.3, 6.1, 6.4, 6.6,
            6.8, 6.7, 6.0, 5.7, 5.5, 5.5, 5.8, 6.0, 5.4, 6.0, 6.7, 6.3, 5.6,
            5.5, 5.5, 6.1, 5.8, 5.0, 5.6, 5.7, 5.7, 6.2, 5.1, 5.7,
            6.3, 5.8, 7.1, 6.3, 6.5, 7.6, 4.9, 7.3, 6.7, 7.2, 6.5, 6.4, 6.8,
            5.7, 5.8, 6.4, 6.5, 7.7, 7.7, 6.0, 6.9, 5.6, 7.7, 6.3, 6.7, 7.2,
            6.2, 6.1, 6.4, 7.2, 7.4, 7.9, 6.4, 6.3, 6.1, 7.7, 6.3, 6.4, 6.0,
            6.9, 6.7, 6.9, 5.8, 6.8, 6.7, 6.7, 6.3, 6.5, 6.2, 5.9,
        ],
        "sepal_width": [
            3.5, 3.0, 3.2, 3.1, 3.6, 3.9, 3.4, 3.4, 2.9, 3.1, 3.7, 3.4, 3.0,
            3.0, 4.0, 4.4, 3.9, 3.5, 3.8, 3.8, 3.4, 3.7, 3.6, 3.3, 3.4, 3.0,
            3.4, 3.5, 3.4, 3.2, 3.1, 3.4, 4.1, 4.2, 3.1, 3.2, 3.5, 3.6, 3.0,
            3.4, 3.5, 2.3, 3.2, 3.5, 3.8, 3.0, 3.8, 3.2, 3.7, 3.3,
            3.2, 3.2, 3.1, 2.3, 2.8, 2.8, 3.3, 2.4, 2.9, 2.7, 2.0, 3.0, 2.2,
            2.9, 2.9, 3.1, 3.0, 2.7, 2.2, 2.5, 3.2, 2.8, 2.5, 2.8, 2.9, 3.0,
            2.8, 3.0, 2.9, 2.6, 2.4, 2.4, 2.7, 2.7, 3.0, 3.4, 3.1, 2.3, 3.0,
            2.5, 2.6, 3.0, 2.6, 2.3, 2.7, 3.0, 2.9, 2.9, 2.5, 2.8,
            3.3, 2.7, 3.0, 2.9, 3.0, 3.0, 2.5, 2.9, 2.5, 3.6, 3.2, 2.7, 3.0,
            2.5, 2.8, 3.2, 3.0, 3.8, 2.6, 2.2, 3.2, 2.8, 2.8, 2.7, 3.3, 3.2,
            2.8, 3.0, 2.8, 3.0, 2.8, 3.8, 2.8, 2.8, 2.6, 3.0, 3.4, 3.1, 3.0,
            3.1, 3.1, 3.1, 2.7, 3.2, 3.3, 3.0, 2.5, 3.0, 3.4, 3.0,
        ],
    }
    frame = pd.DataFrame(data)
    frame["species"] = (
        ["setosa"] * 50 + ["versicolor"] * 50 + ["virginica"] * 50
    )
    return frame


def make_employees() -> list[dict]:
    """JSON-style records with nested objects and mixed types."""
    departments = ["Engineering", "Sales", "Marketing", "Support", "Finance"]
    titles = {
        "Engineering": ["Junior Engineer", "Engineer", "Senior Engineer", "Staff Engineer"],
        "Sales": ["Sales Rep", "Account Executive", "Sales Manager"],
        "Marketing": ["Coordinator", "Specialist", "Marketing Manager"],
        "Support": ["Support Agent", "Support Lead"],
        "Finance": ["Analyst", "Senior Analyst", "Controller"],
    }
    rows: list[dict] = []
    for index in range(120):
        department = str(RNG.choice(departments))
        title = str(RNG.choice(titles[department]))
        salary_base = {
            "Engineering": 95000, "Sales": 72000, "Marketing": 68000,
            "Support": 52000, "Finance": 78000,
        }[department]
        salary = int(round(RNG.normal(salary_base, salary_base * 0.14), -2))
        years = int(RNG.integers(0, 22))
        rows.append({
            "employee_id": f"E{1000 + index}",
            "name": f"Employee {index + 1}",
            "department": department,
            "job_title": title,
            "salary": salary,
            "years_experience": years,
            "performance_rating": round(float(np.clip(RNG.normal(3.6, 0.7), 1, 5)), 1),
            "remote": bool(RNG.random() < 0.42),
            "hire_date": (
                pd.Timestamp("2024-01-01")
                - pd.Timedelta(days=int(RNG.integers(30, 3600)))
            ).strftime("%Y-%m-%d"),
            "contact": {
                "email": f"employee{index + 1}@example.com",
                "city": str(RNG.choice(["Bengaluru", "Mumbai", "Delhi", "Pune", "Hyderabad"])),
            },
        })
    return rows


def make_inventory() -> dict[str, pd.DataFrame]:
    """Two-sheet Excel workbook: main inventory plus a suppliers sheet."""
    categories = ["Electronics", "Furniture", "Stationery", "Cleaning", "Hardware"]
    rows = []
    for index in range(90):
        category = str(RNG.choice(categories))
        stock = int(RNG.integers(0, 500))
        reorder = int(RNG.integers(20, 120))
        cost = round(float(RNG.uniform(5, 480)), 2)
        rows.append({
            "sku": f"SKU-{2000 + index}",
            "category": category,
            "stock_quantity": stock,
            "reorder_level": reorder,
            "unit_cost": cost,
            "inventory_value": round(stock * cost, 2),
            "needs_reorder": bool(stock < reorder),
        })
    inventory = pd.DataFrame(rows)

    suppliers = pd.DataFrame({
        "supplier_id": [f"S{100 + i}" for i in range(10)],
        "supplier_name": [f"Supplier {chr(65 + i)}" for i in range(10)],
        "country": RNG.choice(["India", "China", "Germany", "USA"], size=10).tolist(),
        "lead_time_days": RNG.integers(2, 30, size=10).tolist(),
        "rating": np.round(RNG.uniform(2.5, 5.0, size=10), 1).tolist(),
    })
    return {"Inventory": inventory, "Suppliers": suppliers}


def make_tiny_known() -> pd.DataFrame:
    """Hand-computable dataset for exact statistical regression tests.

    Values chosen so the expected mean/median/std/quartiles are exact decimals:
      x = 1..10   -> mean 5.5, median 5.5, sample std = sqrt(9.1666...) = 3.0276503541
      y = 2x      -> perfect positive correlation r = 1.0
      z = 21 - x  -> perfect negative correlation with x, r = -1.0
    """
    x = list(range(1, 11))
    return pd.DataFrame({
        "x": x,
        "y": [2 * v for v in x],
        "z": [21 - v for v in x],
        "group": ["A"] * 5 + ["B"] * 5,
        "category": ["alpha", "beta"] * 5,
    })


def main() -> None:
    HERE.mkdir(parents=True, exist_ok=True)

    sales = make_sales()
    sales.to_csv(HERE / "sales_data.csv", index=False)
    print(f"sales_data.csv          {sales.shape[0]:>5} rows × {sales.shape[1]} cols")

    iris = make_iris()
    iris.to_csv(HERE / "iris.csv", index=False)
    print(f"iris.csv                {iris.shape[0]:>5} rows × {iris.shape[1]} cols")

    employees = make_employees()
    import json

    (HERE / "employees.json").write_text(
        json.dumps(employees, indent=2), encoding="utf-8"
    )
    print(f"employees.json          {len(employees):>5} records")

    sheets = make_inventory()
    with pd.ExcelWriter(HERE / "inventory.xlsx", engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"inventory.xlsx          2 sheets (Inventory, Suppliers)")

    tiny = make_tiny_known()
    tiny.to_csv(HERE / "tiny_known.csv", index=False)
    print(f"tiny_known.csv          {tiny.shape[0]:>5} rows × {tiny.shape[1]} cols")

    print("\nSample data written to:", HERE)


if __name__ == "__main__":
    main()
