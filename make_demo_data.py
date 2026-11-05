"""Creates data/demo_4_years.xlsx: 48 months with a yearly sales pattern and planted anomalies."""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(2024)
months = pd.date_range("2022-11-01", periods=48, freq="MS")
t = np.arange(48)

season = 1 + 0.25 * np.sin(2 * np.pi * (t - 2) / 12)  # peaks every year around the festive season
revenue = (100_000 + 600 * t) * season + rng.normal(0, 2_500, 48)
orders = revenue / 85 + rng.normal(0, 25, 48)
returns = 55 + 0.1 * t + rng.normal(0, 3, 48)
ad_spend = rng.normal(15_000, 600, 48)

df = pd.DataFrame(
    {
        "Month": months,
        "Revenue": revenue.round(),
        "Orders": orders.round(),
        "Returns": returns.round(),
        "Ad_Spend": ad_spend.round(),
    }
)

df.loc[20, "Revenue"] *= 0.70      # Jul 2024: sales fall far below the usual level
df.loc[33, "Returns"] = 110        # Aug 2025: refund spike
df.loc[44, "Ad_Spend"] *= 2.2      # Jul 2026: marketing cost jumps
df.loc[47, "Revenue"] *= 1.35      # Oct 2026: the newest month jumps

Path("data").mkdir(exist_ok=True)
df.to_excel("data/demo_4_years.xlsx", index=False)
print("Created data/demo_4_years.xlsx")
print(df.iloc[[20, 33, 44, 47]])
