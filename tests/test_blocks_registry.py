"""Block registry tests."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_registry(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.chdir(td)
        os.makedirs("workspace/blocks/code", exist_ok=True)
        os.makedirs("workspace/blocks/tests", exist_ok=True)
        # Force fresh db path
        from aqr.db.schema import init_schema
        init_schema()
        from aqr.blocks.registry import BlockRegistry
        reg = BlockRegistry()
        yield reg


def test_register_valid_block(tmp_registry):
    code = """
import pandas as pd
import numpy as np

def sma(px: pd.Series, window: int = 10) -> pd.Series:
    return px.rolling(window).mean()
"""
    tests = """
import pandas as pd
import numpy as np
import importlib.util, sys
from pathlib import Path
code_path = Path(__file__).parent.parent / "code" / "sma.py"
spec = importlib.util.spec_from_file_location("sma", code_path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_length():
    s = pd.Series(range(100), dtype=float)
    assert len(mod.sma(s, 10)) == 100
"""
    bid = tmp_registry.register("sma", code, tests, "Simple moving average", author="test")
    assert bid is not None


def test_rejects_leakage(tmp_registry):
    code = """
import pandas as pd
def bad(px: pd.Series) -> pd.Series:
    return px.shift(-1)
"""
    bid = tmp_registry.register("bad", code, "", "leakage test", author="test")
    assert bid is None


def test_catalog_format(tmp_registry):
    assert tmp_registry.catalog_for_llm() == ""


def test_dedup_by_hash(tmp_registry):
    code = """
def foo(x):
    return x + 1
"""
    tests_body = ""
    bid1 = tmp_registry.register("foo", code, tests_body, "test", author="a")
    bid2 = tmp_registry.register("foo2", code, tests_body, "test", author="a")
    # Same code → same block id
    if bid1 is not None:
        assert bid1 == bid2 or bid2 is None
