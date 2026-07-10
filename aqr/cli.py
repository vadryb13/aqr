"""CLI: aqr-stream start / stats / top / pause."""
from __future__ import annotations
import asyncio, json
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="AQR Stream — continuous hypothesis engine")
console = Console()


@app.command()
def start():
    """Запустить всю фабрику: generators + workers + insight loop + API."""
    from .orchestrator import main
    asyncio.run(main())


@app.command()
def stats():
    """Показать текущую статистику."""
    from .db.schema import get_conn
    conn = get_conn(read_only=True)
    try:
        overall = conn.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(CASE WHEN status='pending' THEN 1 END) AS pending,
                   COUNT(CASE WHEN status='tested' THEN 1 END) AS tested,
                   COUNT(CASE WHEN status='duplicate' THEN 1 END) AS dup
            FROM hypotheses
        """).fetchone()
        gens = conn.execute("SELECT * FROM generator_stats").fetchall()

        console.print(f"[bold]Всего: {overall[0]}  pending: {overall[1]}  tested: {overall[2]}  duplicates: {overall[3]}[/bold]")
        table = Table("Generator", "N", "Tested", "Dup", "Avg Sh", "Max Sh", "Cost $", "gd/hyp")
        for g in gens:
            table.add_row(*[str(x)[:8] if x else "-" for x in g])
        console.print(table)
    finally:
        conn.close()


@app.command()
def top(limit: int = 20):
    """Показать топ гипотез по Sharpe."""
    from .db.schema import get_conn
    conn = get_conn(read_only=True)
    try:
        rows = conn.execute(f"""
            SELECT h.hypothesis, h.category, r.sharpe, r.pvalue, r.n, r.best_regime
            FROM hypotheses h JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE r.pvalue < 0.05 AND r.n > 200
            ORDER BY r.sharpe DESC LIMIT {int(limit)}
        """).fetchall()
        table = Table("Hyp", "Cat", "Sharpe", "p-val", "n", "Regime")
        for r in rows:
            table.add_row(str(r[0])[:60], str(r[1]), f"{r[2]:.2f}", f"{r[3]:.4f}", str(r[4]), str(r[5]))
        console.print(table)
    finally:
        conn.close()


@app.command()
def init_db():
    """Создать/обновить схему БД."""
    from .db.schema import init_schema
    init_schema()
    console.print("[green]OK[/green]")


if __name__ == "__main__":
    app()
