"""Regenerate sample_business_motoshop_catalog.pdf.

Run from the repo root:
    python chatroom_ai/tests/fixtures/generate_catalog_pdf.py

Requires reportlab (pip install reportlab). Only used to refresh the fixture;
not loaded at runtime.
"""
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PRODUCTS = [
    ("Motos 0km", [
        ("Honda Wave 110 0km", "$1.350.000"),
        ("Yamaha YBR 125 0km", "$1.890.000"),
        ("Honda CB 190R 0km", "$3.250.000"),
        ("Bajaj Rouser 220F 0km", "$2.480.000"),
        ("Yamaha FZ-S Fi V3 0km", "$3.580.000"),
        ("Honda Tornado XR250 0km", "$5.120.000"),
    ]),
    ("Cascos y protección", [
        ("Casco Hawk RS5 negro talle M", "$85.000"),
        ("Casco Hawk integral RS9 talle L", "$145.000"),
        ("Casco LS2 modular FF902 talle L", "$320.000"),
        ("Guantes Alpinestars SP-1", "$55.000"),
        ("Campera Alpinestars Vento Air", "$185.000"),
        ("Botas Alpinestars Toucan GTX", "$420.000"),
    ]),
    ("Repuestos", [
        ("Cubierta Pirelli 110/80-17", "$42.000"),
        ("Cubierta Pirelli 130/70-17", "$58.000"),
        ("Kit transmisión Honda Wave (corona + piñón + cadena)", "$38.000"),
        ("Kit transmisión Yamaha YBR (corona + piñón + cadena)", "$45.000"),
        ("Batería YTX9-BS Yuasa", "$48.000"),
        ("Pastillas de freno delanteras Honda CB190", "$18.500"),
        ("Filtro de aceite Honda Wave (x1)", "$3.800"),
    ]),
    ("Aceites y lubricantes", [
        ("Aceite Motul 5100 4T 10W40 1L", "$14.500"),
        ("Aceite Motul 7100 4T 10W40 1L", "$22.000"),
        ("Aceite Castrol Power1 4T 20W50 1L", "$11.800"),
        ("Líquido de frenos Motul DOT4 500ml", "$8.200"),
    ]),
    ("Servicios de taller", [
        ("Service básico Honda Wave (mano de obra)", "$25.000"),
        ("Service básico Honda CB190R (mano de obra)", "$38.000"),
        ("Cambio de cubierta delantera (m.o.)", "$12.000"),
        ("Cambio de cubierta trasera (m.o.)", "$15.000"),
        ("Alineación y balanceo de ruedas", "$18.000"),
    ]),
]


def build():
    out_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "sample_business_motoshop_catalog.pdf",
    )

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title="Catálogo MotoSur",
        author="MotoSur",
    )

    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    normal = styles["Normal"]
    small = ParagraphStyle(
        "small", parent=normal, fontSize=9, textColor=colors.HexColor("#555555")
    )

    story = []
    story.append(Paragraph("Catálogo MotoSur", h1))
    story.append(Paragraph(
        "Av. Colón 2300, Córdoba Capital — Tel: +54 351 555-1234 — motosur.com.ar",
        small,
    ))
    story.append(Paragraph(
        "Horarios: Lun-Vie 9-13 / 16-20 · Sáb 9-13", small,
    ))
    story.append(Spacer(1, 0.6 * cm))

    intro = (
        "Precios vigentes en pesos argentinos (ARS), final consumidor. "
        "Las motos 0km incluyen garantía oficial del fabricante "
        "(12 meses o 12.000 km). Patentamiento incluido en motos 0km financiadas. "
        "Despachos a todo el país por Andreani (costo a cargo del cliente)."
    )
    story.append(Paragraph(intro, normal))
    story.append(Spacer(1, 0.5 * cm))

    for section_title, rows in PRODUCTS:
        story.append(Paragraph(section_title, h2))
        data = [["Producto", "Precio"]]
        data.extend(rows)
        table = Table(data, colWidths=[12.5 * cm, 4 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#222222")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F4F4F4")]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CCCCCC")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.5 * cm))

    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Financiación", h2))
    story.append(Paragraph(
        "Plan Mi Moto (gobierno) hasta 48 cuotas en motos 0km seleccionadas. "
        "Visa / Mastercard hasta 12 cuotas sin interés con bancos seleccionados. "
        "Permutamos motos usadas (con turno previo).",
        normal,
    ))

    doc.build(story)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    build()
