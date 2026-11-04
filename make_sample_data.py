from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
months = pd.date_range("2025-11-01", periods=12, freq="MS")
df = pd.DataFrame({
    "Month": months,
    "Revenue": rng.normal(100_000, 3_000, 12).round(0),
    "Orders": rng.normal(1_200, 40, 12).round(0),
    "Returns": rng.normal(60, 5, 12).round(0),
    "Ad_Spend": rng.normal(15_000, 500, 12).round(0),
    "Website_Visits": rng.normal(50_000, 1_500, 12).round(0),
})
df.loc[11, "Revenue"] = 145_000
df.loc[11, "Returns"] = 25
Path("data").mkdir(exist_ok=True)
df.to_excel("data/sample_sales.xlsx", index=False)
print("Created data/sample_sales.xlsx")
print(df.tail(3))
