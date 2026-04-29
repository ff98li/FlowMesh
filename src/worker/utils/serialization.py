import io
from typing import Any

import pandas as pd


def serialize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    return {"df": df.to_json()}


def try_deserialize_dataframe(data: dict[str, Any]) -> pd.DataFrame | dict[str, Any]:
    if "df" in data:
        try:
            return pd.read_json(io.StringIO(data["df"]))
        except Exception:
            pass
    return data
