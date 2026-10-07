"""Genera docs/schema_postgresql.sql y docs/modelo_datos.md a partir de los modelos SQLAlchemy.

Uso:  python scripts/export_schema.py
"""
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app import create_app
from app.config import TestConfig
from app.extensions import db

DOCS = Path(__file__).resolve().parent.parent / "docs"


def ddl() -> str:
    dialecto = postgresql.dialect()
    partes = ["-- Arequipa House ML · esquema PostgreSQL (generado desde los modelos SQLAlchemy)\n"]
    for tabla in db.metadata.sorted_tables:
        partes.append(str(CreateTable(tabla).compile(dialect=dialecto)).strip() + ";\n")
        for idx in sorted(tabla.indexes, key=lambda i: i.name or ""):
            partes.append(str(CreateIndex(idx).compile(dialect=dialecto)).strip() + ";")
        partes.append("")
    return "\n".join(partes)


def er_mermaid() -> str:
    lineas = ["```mermaid", "erDiagram"]
    for tabla in db.metadata.sorted_tables:
        for col in tabla.columns:
            for fk in col.foreign_keys:
                lineas.append(f"    {fk.column.table.name} ||--o{{ {tabla.name} : \"{col.name}\"")
    for tabla in db.metadata.sorted_tables:
        lineas.append(f"    {tabla.name} {{")
        for col in tabla.columns:
            tipo = str(col.type).split("(")[0].replace(" ", "_")
            marca = " PK" if col.primary_key else (" FK" if col.foreign_keys else "")
            lineas.append(f"        {tipo} {col.name}{marca}")
        lineas.append("    }")
    lineas.append("```")
    return "\n".join(lineas)


def diccionario() -> str:
    filas = ["| Tabla | Campo | Tipo | Nulo | Clave |", "|---|---|---|---|---|"]
    for tabla in db.metadata.sorted_tables:
        for col in tabla.columns:
            clave = "PK" if col.primary_key else ("FK → " + next(iter(col.foreign_keys)).target_fullname if col.foreign_keys else "")
            filas.append(f"| {tabla.name} | {col.name} | {col.type} | {'sí' if col.nullable else 'no'} | {clave} |")
    return "\n".join(filas)


if __name__ == "__main__":
    app = create_app(TestConfig)
    with app.app_context():
        (DOCS / "schema_postgresql.sql").write_text(ddl(), encoding="utf-8")
        (DOCS / "modelo_datos.md").write_text(
            "# Modelo de datos\n\n## Diagrama entidad-relación\n\n" + er_mermaid() + "\n\n## Diccionario de datos\n\n" + diccionario() + "\n",
            encoding="utf-8",
        )
    print("Generado en", DOCS)
