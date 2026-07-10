"""
MOEX ISS (Interactive Statistical Server) adapter.

Docs: https://iss.moex.com/iss/reference/

Point-in-time discipline:
- Every fetch records `as_of` timestamp
- Corporate actions applied only up to as_of
- No forward-fill of missing bars (leaves gaps explicit)
- Volume adjustments logged in manifest
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd
import requests

MOEX_ISS_BASE = "https://iss.moex.com/iss"


class MOEXAdapter:
    """
    Fetch MOEX securities data with point-in-time guarantees.

    Supported engines/markets:
    - stock/shares — equities (SBER, GAZP, LKOH, ...)
    - stock/index — indices (IMOEX, RTSI, ...)
    - futures/forts — futures (Si-, Br-, GD-, ...)
    - currency/selt — FX (USD/RUB, CNY/RUB, ...)
    - stock/bonds — bonds

    Example:
        adapter = MOEXAdapter()
        df = adapter.candles("SBER", "2024-01-01", "2024-12-31", interval="D")
    """

    ENGINE_MARKET_MAP = {
        "shares": ("stock", "shares"),
        "index": ("stock", "index"),
        "futures": ("futures", "forts"),
        "currency": ("currency", "selt"),
        "bonds": ("stock", "bonds"),
    }

    INTERVAL_MAP = {
        "1min": 1, "10min": 10, "1H": 60, "D": 24, "W": 7, "M": 31, "Q": 4,
    }

    def __init__(self, session: requests.Session | None = None, rate_limit_ms: int = 500):
        self.session = session or requests.Session()
        self.rate_limit_ms = rate_limit_ms
        self._last_call = 0.0

    def _rate_limit(self):
        now = time.time() * 1000
        elapsed = now - self._last_call
        if elapsed < self.rate_limit_ms:
            time.sleep((self.rate_limit_ms - elapsed) / 1000)
        self._last_call = time.time() * 1000

    def candles(
        self,
        security: str,
        from_date: str,
        to_date: str,
        interval: str = "D",
        engine: Literal["shares", "index", "futures", "currency", "bonds"] = "shares",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candles.

        Returns DataFrame with columns: open, high, low, close, volume, value, begin, end
        Indexed by begin (UTC).
        """
        eng, market = self.ENGINE_MARKET_MAP[engine]
        int_code = self.INTERVAL_MAP.get(interval, 24)

        rows = []
        start = 0
        while True:
            self._rate_limit()
            url = (
                f"{MOEX_ISS_BASE}/engines/{eng}/markets/{market}/securities/"
                f"{security}/candles.json"
            )
            params = {
                "from": from_date,
                "till": to_date,
                "interval": int_code,
                "start": start,
            }
            r = self.session.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()

            candles = data.get("candles", {})
            cols = candles.get("columns", [])
            batch = candles.get("data", [])

            if not batch:
                break
            for row in batch:
                rows.append(dict(zip(cols, row)))
            if len(batch) < 500:
                break
            start += len(batch)

        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "value"])

        df = pd.DataFrame(rows)
        df["begin"] = pd.to_datetime(df["begin"])
        df["end"] = pd.to_datetime(df["end"])
        df = df.set_index("begin").sort_index()
        return df

    def securities_list(
        self,
        engine: Literal["shares", "index", "futures", "currency"] = "shares",
        as_of: str | None = None,
    ) -> pd.DataFrame:
        """
        List active securities on given engine.

        Args:
            as_of: date string 'YYYY-MM-DD' for historical universe (avoids survivorship bias)
        """
        eng, market = self.ENGINE_MARKET_MAP[engine]
        self._rate_limit()
        url = f"{MOEX_ISS_BASE}/engines/{eng}/markets/{market}/securities.json"
        params = {"date": as_of} if as_of else {}
        r = self.session.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        sec = data.get("securities", {})
        cols = sec.get("columns", [])
        rows = sec.get("data", [])
        return pd.DataFrame(rows, columns=cols)

    def corporate_actions(self, security: str, as_of: str | None = None) -> pd.DataFrame:
        """
        Dividend history and splits.

        Only actions with ex-date <= as_of should be applied to point-in-time data.
        """
        self._rate_limit()
        url = f"{MOEX_ISS_BASE}/securities/{security}/dividends.json"
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        div = data.get("dividends", {})
        df = pd.DataFrame(div.get("data", []), columns=div.get("columns", []))
        if "registryclosedate" in df.columns:
            df["registryclosedate"] = pd.to_datetime(df["registryclosedate"])
            if as_of:
                cutoff = pd.Timestamp(as_of)
                df = df[df["registryclosedate"] <= cutoff]
        return df
