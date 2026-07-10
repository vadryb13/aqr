"""
Растущая библиотека стратегических блоков.

Каждый блок:
- код (Python function)
- тесты (pytest-style)
- метаданные (signature, description, tags)
- статистика использования (n_used, avg_sharpe_of_users, last_used_at)

LLM может (1) найти подходящий блок или (2) написать новый.
Новый блок проходит проверки: syntax → tests → no leakage → performance.
"""
from __future__ import annotations
import ast, hashlib, importlib.util, subprocess, sys, tempfile, uuid, json
from pathlib import Path
from typing import Optional, Callable

from ..db.schema import get_conn


BLOCKS_DIR = Path("./workspace/blocks/code")
TESTS_DIR = Path("./workspace/blocks/tests")
BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
TESTS_DIR.mkdir(parents=True, exist_ok=True)


BLOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS block_registry (
    id              VARCHAR PRIMARY KEY,
    name            VARCHAR UNIQUE,
    description     TEXT,
    signature       JSON,            -- {params: {px_a: 'pd.Series', ...}, returns: '...'}
    file_path       VARCHAR,
    test_path       VARCHAR,
    code_hash       VARCHAR,
    author          VARCHAR,         -- 'human' | 'coder_agent'
    tags            VARCHAR[],
    n_used          INTEGER DEFAULT 0,
    avg_sharpe      DOUBLE,
    max_sharpe      DOUBLE,
    last_used_at    TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active       BOOLEAN DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_blocks_name ON block_registry(name);
CREATE INDEX IF NOT EXISTS idx_blocks_active ON block_registry(is_active);
"""


class BlockRegistry:
    def __init__(self):
        conn = get_conn()
        conn.execute(BLOCK_SCHEMA)
        conn.close()

    # ── Register (from LLM Coder or human) ────────────────────────
    def register(self, name: str, code: str, tests: str,
                 description: str, author: str = "human",
                 tags: Optional[list[str]] = None) -> Optional[str]:
        """
        Полная валидация и сохранение нового блока.
        Возвращает block_id или None если провалилась проверка.
        """
        # 1. Синтакс
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return self._fail("syntax", str(e))

        # 2. Извлечь signature
        sig = self._extract_signature(tree, target_name=name)
        if not sig:
            return self._fail("no_function", f"function '{name}' not found in code")

        # 3. Data-leakage статический анализ
        leakage = self._check_leakage(code)
        if leakage:
            return self._fail("leakage", leakage)

        # 4. Deduplication по хешу
        code_hash = hashlib.sha256(code.encode()).hexdigest()[:16]
        conn = get_conn()
        try:
            dup = conn.execute("SELECT id FROM block_registry WHERE code_hash = ?", [code_hash]).fetchone()
            if dup:
                return dup[0]

            # 5. Написать файлы
            block_path = BLOCKS_DIR / f"{name}.py"
            test_path = TESTS_DIR / f"test_{name}.py"
            block_path.write_text(code)
            test_path.write_text(tests)

            # 6. Прогнать тесты (в изоляции)
            ok, err = self._run_tests(test_path)
            if not ok:
                block_path.unlink()
                test_path.unlink()
                return self._fail("tests_failed", err)

            # 7. Записать в реестр
            bid = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO block_registry (id, name, description, signature,
                                            file_path, test_path, code_hash, author, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [bid, name, description, json.dumps(sig),
                  str(block_path), str(test_path), code_hash, author, tags or []])
            return bid
        finally:
            conn.close()

    # ── Load & call ───────────────────────────────────────────────
    def get_callable(self, name: str) -> Optional[Callable]:
        conn = get_conn(read_only=True)
        try:
            row = conn.execute(
                "SELECT file_path FROM block_registry WHERE name = ? AND is_active", [name]
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return self._load_from_file(row[0], name)

    def record_use(self, name: str, sharpe: Optional[float] = None):
        conn = get_conn()
        try:
            conn.execute("""
                UPDATE block_registry
                SET n_used = n_used + 1,
                    last_used_at = CURRENT_TIMESTAMP,
                    avg_sharpe = CASE
                        WHEN avg_sharpe IS NULL THEN ?
                        ELSE (avg_sharpe * n_used + ?) / (n_used + 1)
                    END,
                    max_sharpe = GREATEST(COALESCE(max_sharpe, ?), ?)
                WHERE name = ?
            """, [sharpe, sharpe or 0, sharpe or 0, sharpe or 0, name])
        finally:
            conn.close()

    # ── Discovery ─────────────────────────────────────────────────
    def list_blocks(self, tag: Optional[str] = None, min_uses: int = 0) -> list[dict]:
        conn = get_conn(read_only=True)
        try:
            q = "SELECT name, description, signature, n_used, avg_sharpe, tags FROM block_registry WHERE is_active"
            if min_uses:
                q += f" AND n_used >= {min_uses}"
            if tag:
                q += f" AND ? = ANY(tags)"
                rows = conn.execute(q, [tag]).fetchall()
            else:
                rows = conn.execute(q).fetchall()
            return [{"name": r[0], "description": r[1], "signature": json.loads(r[2]),
                     "n_used": r[3], "avg_sharpe": r[4], "tags": r[5]} for r in rows]
        finally:
            conn.close()

    def catalog_for_llm(self) -> str:
        """Компактный листинг для инжекта в промпт LLM."""
        blocks = self.list_blocks(min_uses=1)
        blocks.sort(key=lambda b: -(b["avg_sharpe"] or 0))
        lines = []
        for b in blocks[:50]:
            sig = b["signature"]
            params = ", ".join(f"{k}: {v}" for k, v in sig.get("params", {}).items())
            lines.append(f"- {b['name']}({params}) — {b['description']} [avg Sh {b.get('avg_sharpe', 0):.2f}, used {b['n_used']}]")
        return "\n".join(lines)

    # ── Validation helpers ────────────────────────────────────────
    def _extract_signature(self, tree: ast.AST, target_name: str) -> Optional[dict]:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == target_name:
                params = {}
                for arg in node.args.args:
                    ann = ast.unparse(arg.annotation) if arg.annotation else "Any"
                    params[arg.arg] = ann
                ret = ast.unparse(node.returns) if node.returns else "Any"
                return {"params": params, "returns": ret}
        return None

    def _check_leakage(self, code: str) -> Optional[str]:
        """Простые эвристики против look-ahead bias."""
        red_flags = [
            (".shift(-", "shift with negative arg — potential future leak"),
            (".rolling(", None),  # rolling обычно ок, но проверим что не с shift(-)
            ("np.roll(", "np.roll — легко получить future data"),
        ]
        for pattern, msg in red_flags:
            if pattern in code and msg:
                return msg
        return None

    def _run_tests(self, test_path: Path) -> tuple[bool, str]:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path), "-q", "--tb=short"],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            return True, ""
        return False, proc.stdout + proc.stderr

    def _load_from_file(self, file_path: str, fn_name: str):
        spec = importlib.util.spec_from_file_location(fn_name, file_path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, fn_name, None)

    def _fail(self, reason: str, msg: str):
        # Логируем в память
        try:
            from ..memory.store import MemoryStore
            MemoryStore().log_event(
                agent="block_registry", event_type="registration_failed",
                content=f"{reason}: {msg}",
            )
        except Exception:
            pass
        return None
