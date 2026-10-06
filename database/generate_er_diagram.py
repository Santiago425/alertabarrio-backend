"""
Genera el diagrama entidad-relacion (er_diagram.png / .svg / .dot) a partir de
los modelos SQLAlchemy del backend, asi el diagrama nunca queda desactualizado.

Requisitos: graphviz instalado (comando `dot`).
Uso (desde esta carpeta):
    python generate_er_diagram.py ../alertabarrio-backend
"""

import subprocess
import sys
from pathlib import Path

backend = Path(sys.argv[1] if len(sys.argv) > 1 else "../alertabarrio-backend").resolve()
sys.path.insert(0, str(backend))

from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401

HEADER = "#b91c1c"


def column_row(col) -> str:
    keys = []
    if col.primary_key:
        keys.append("PK")
    if col.foreign_keys:
        keys.append("FK")
    key = ",".join(keys) or " "
    ctype = str(col.type).lower().replace("varchar", "varchar").replace("timestamp with time zone", "timestamptz")
    nullable = "" if col.nullable or col.primary_key else " NN"
    name = f"<b>{col.name}</b>" if col.primary_key else col.name
    return (
        f'<tr><td align="left" width="28"><font color="#b45309">{key}</font></td>'
        f'<td align="left">{name}</td><td align="left"><font color="#64748b">{ctype}{nullable}</font></td></tr>'
    )


lines = [
    "digraph ER {",
    '  graph [rankdir=LR, splines=true, nodesep=0.5, ranksep=1.1, bgcolor="white", fontname="Helvetica",'
    ' label="AlertaBarrio - Diagrama Entidad-Relacion", labelloc=t, fontsize=22];',
    '  node [shape=plaintext, fontname="Helvetica", fontsize=11];',
    '  edge [fontname="Helvetica", fontsize=9, color="#475569", arrowhead=crow, arrowtail=tee, dir=both];',
]
for table in Base.metadata.sorted_tables:
    rows = "".join(column_row(c) for c in table.columns)
    lines.append(
        f'  {table.name} [label=<<table border="0" cellborder="1" cellspacing="0" cellpadding="4">'
        f'<tr><td colspan="3" bgcolor="{HEADER}"><font color="white"><b>{table.name}</b></font></td></tr>{rows}</table>>];'
    )
for table in Base.metadata.sorted_tables:
    for fk in table.foreign_keys:
        parent = fk.column.table.name
        lines.append(f'  {parent} -> {table.name} [label="{fk.parent.name}"];')
lines.append("}")

out = Path(__file__).parent
(out / "er_diagram.dot").write_text("\n".join(lines), encoding="utf-8")
for fmt in ("png", "svg"):
    subprocess.run(["dot", f"-T{fmt}", "-Gdpi=110", "er_diagram.dot", "-o", f"er_diagram.{fmt}"], cwd=out, check=True)
print("Diagrama generado: er_diagram.png, er_diagram.svg")
