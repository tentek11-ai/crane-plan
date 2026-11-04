from __future__ import annotations

import re
import argparse
import json
from xml.sax.saxutils import escape
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


INTERNAL_CODES = ("PPRK-005", "PPRK-006", "PPRK-007")
ECONOMIC_TERMS = (
    "стоимость решения", "экономический фактор", "экономические факторы",
    "коммерческое предложение", "окупаемость", "себестоимость",
    "денежные затраты", "цена решения", "снижена стоимость",
)


def validate_article_claims(text: str, evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    lowered = text.lower()
    for code in INTERNAL_CODES:
        if code.lower() in lowered:
            errors.append(f"internal case code is forbidden: {code}")
    if "pass_with_conditions" in lowered:
        errors.append("raw machine status is forbidden in Russian manuscript")
    if re.search(r"однокранов\w*\s+схем\w*.{0,80}(внедрен|внедрён|принят\w*\s+для\s+реализации)", lowered):
        errors.append("implementation of the one-crane scheme is not evidenced")
    for term in ECONOMIC_TERMS:
        if term in lowered:
            errors.append(f"economic factor is outside article scope: {term}")
    for paragraph in re.split(r"\n\s*\n", lowered):
        if ("1,774" in paragraph or "1.774" in paragraph) and not (
            "160" in paragraph and re.search(r"подъ[её]м", paragraph)
        ):
            errors.append("1.774 days must be described only for the defined set of 160 lifts")
    for group in re.findall(r"\[(\d+(?:\s*[-,]\s*\d+){3,})\]", text):
        numbers = re.findall(r"\d+", group)
        if len(numbers) > 3:
            errors.append("one citation group contains more than three sources")
    return errors


def _set_run_font(run, name: str = "Times New Roman", size: float = 14.0) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    rfonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:cs"), name)


def _shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def _set_cell_margins(cell, value_twips: int = 90) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for edge in ("top", "left", "bottom", "right"):
        node = tc_mar.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value_twips))
        node.set(qn("w:type"), "dxa")


def _set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:color"), "D9D9D9")


def _add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run()
    _set_run_font(run, size=10)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for element in (begin, instr, separate, text, end):
        run._r.append(element)


def _configure_document(document: Document) -> None:
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(3.0)
    section.right_margin = Cm(1.5)
    section.header_distance = Cm(1.0)
    section.footer_distance = Cm(1.0)
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(14)
    normal.font.color.rgb = RGBColor(0, 0, 0)
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.first_line_indent = Cm(1.25)
    normal.paragraph_format.line_spacing = 1.0
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.widow_control = True
    for style_name in ("Title", "Heading 1", "Heading 2"):
        style = document.styles[style_name]
        style.font.name = "Times New Roman"
        style.font.color.rgb = RGBColor(0, 0, 0)
        style._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    title = document.styles["Title"]
    title.font.size = Pt(14)
    title.font.bold = True
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(6)
    heading = document.styles["Heading 1"]
    heading.font.size = Pt(14)
    heading.font.bold = True
    heading.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    heading.paragraph_format.keep_with_next = True
    heading.paragraph_format.space_before = Pt(10)
    heading.paragraph_format.space_after = Pt(4)
    _add_page_number(section.footer.paragraphs[0])


def _add_plain_paragraph(document: Document, text: str, *, center: bool = False, italic: bool = False, size: float = 14.0):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.JUSTIFY
    paragraph.paragraph_format.first_line_indent = None if center else Cm(1.25)
    paragraph.paragraph_format.line_spacing = 1.0
    paragraph.paragraph_format.space_after = Pt(0)
    clean = text.replace("`", "")
    run = paragraph.add_run(clean)
    _set_run_font(run, "Cambria Math" if any(token in clean for token in ("∈", "∩", "≥", "≤", "||")) else "Times New Roman", size)
    run.italic = italic
    return paragraph


def _add_markdown_table(document: Document, rows: list[list[str]]) -> None:
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    _set_table_borders(table)
    for r_idx, values in enumerate(rows):
        for c_idx, value in enumerate(values):
            cell = table.cell(r_idx, c_idx)
            cell.text = value.strip()
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            _set_cell_margins(cell)
            if r_idx == 0:
                _shade_cell(cell, "44546A")
            elif r_idx % 2 == 0:
                _shade_cell(cell, "F2F5F8")
            for paragraph in cell.paragraphs:
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx == 1 else WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.first_line_indent = None
                paragraph.paragraph_format.space_after = Pt(0)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    _set_run_font(run, size=9.5)
                    if r_idx == 0:
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
    header_tr_pr = table.rows[0]._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    header_tr_pr.append(repeat)
    document.add_paragraph().paragraph_format.space_after = Pt(2)


def markdown_to_docx(markdown_path: Path, output_path: Path, *, response: bool = False) -> Path:
    document = Document()
    _configure_document(document)
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    index = 0
    front_matter_paragraphs = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            paragraph = document.add_paragraph(line[2:].strip(), style="Title")
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            index += 1
            continue
        if line.startswith("## "):
            document.add_paragraph(line[3:].strip(), style="Heading 1")
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            rows: list[list[str]] = []
            rows.append([item.strip() for item in line.strip("|").split("|")])
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([item.strip() for item in lines[index].strip().strip("|").split("|")])
                index += 1
            _add_markdown_table(document, rows)
            continue
        if re.match(r"^\d+\.\s", line):
            paragraph = _add_plain_paragraph(document, line, size=12.0 if "Список литературы" in "\n".join(lines[max(0, index-15):index]) else 14.0)
            paragraph.paragraph_format.first_line_indent = Cm(-0.75)
            paragraph.paragraph_format.left_indent = Cm(0.75)
            index += 1
            continue
        if not response and front_matter_paragraphs < 2 and not line.startswith("##"):
            _add_plain_paragraph(document, line, center=True, italic=front_matter_paragraphs < 2, size=14.0 if front_matter_paragraphs == 0 else 12.0)
            front_matter_paragraphs += 1
        else:
            paragraph = _add_plain_paragraph(document, line)
            if line.startswith("Таблица "):
                paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                paragraph.paragraph_format.first_line_indent = None
                paragraph.paragraph_format.keep_with_next = True
        index += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.core_properties.title = lines[0].removeprefix("# ") if lines else ""
    document.core_properties.author = "В. И. Мигин; А. М. Эльшейх"
    document.core_properties.subject = "Переработанная научная статья для журнала Инженерный вестник Дона"
    document.save(output_path)
    return output_path


def build_documents(article_root: Path, output_root: Path) -> tuple[Path, Path]:
    article_root = Path(article_root)
    output_root = Path(output_root)
    manuscript = article_root / "manuscript" / "ARTICLE_RU.md"
    response = article_root / "manuscript" / "EDITOR_RESPONSE_RU.md"
    evidence = {
        "retrospective": json.loads((article_root / "results" / "external_validation_attestation.json").read_text(encoding="utf-8")),
        "novatorov": json.loads((article_root / "results" / "novatorov_v222_result.json").read_text(encoding="utf-8")),
    }
    errors = validate_article_claims(manuscript.read_text(encoding="utf-8"), evidence)
    if errors:
        raise ValueError("article claim gate failed: " + "; ".join(errors))
    article_docx = output_root / "Статья_Математическая_модель_выбора_башенных_кранов_ИВД_2026.docx"
    response_docx = output_root / "Ответ_редакции_Инженерный_вестник_Дона_2026.docx"
    markdown_to_docx(manuscript, article_docx)
    markdown_to_docx(response, response_docx, response=True)
    return article_docx, response_docx


def _register_pdf_fonts() -> None:
    fonts = {
        "TimesNewRoman": Path(r"C:\Windows\Fonts\times.ttf"),
        "TimesNewRoman-Bold": Path(r"C:\Windows\Fonts\timesbd.ttf"),
        "TimesNewRoman-Italic": Path(r"C:\Windows\Fonts\timesi.ttf"),
        "SegoeSymbol": Path(r"C:\Windows\Fonts\seguisym.ttf"),
    }
    for name, path in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "TimesNewRoman",
        normal="TimesNewRoman",
        bold="TimesNewRoman-Bold",
        italic="TimesNewRoman-Italic",
    )


def build_article_pdf(article_root: Path, output_path: Path) -> Path:
    article_root = Path(article_root)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _register_pdf_fonts()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "ArticleBody", parent=styles["BodyText"], fontName="TimesNewRoman",
        fontSize=12, leading=14, alignment=TA_JUSTIFY, firstLineIndent=1.25 * cm,
        spaceAfter=2,
    )
    title = ParagraphStyle(
        "ArticleTitle", parent=body, fontName="TimesNewRoman-Bold", fontSize=14,
        leading=17, alignment=TA_CENTER, firstLineIndent=0, spaceAfter=8,
    )
    heading = ParagraphStyle(
        "ArticleHeading", parent=body, fontName="TimesNewRoman-Bold", fontSize=13,
        leading=16, alignment=TA_CENTER, firstLineIndent=0, spaceBefore=10, spaceAfter=5,
        keepWithNext=True,
    )
    centered = ParagraphStyle(
        "ArticleCentered", parent=body, fontName="TimesNewRoman-Italic", alignment=TA_CENTER,
        firstLineIndent=0, spaceAfter=3,
    )
    equation = ParagraphStyle(
        "ArticleEquation", parent=body, fontName="SegoeSymbol", alignment=TA_CENTER,
        firstLineIndent=0, leftIndent=0.5 * cm, rightIndent=0.5 * cm, spaceBefore=4, spaceAfter=4,
    )
    reference = ParagraphStyle(
        "ArticleReference", parent=body, fontSize=10.5, leading=12, firstLineIndent=-0.6 * cm,
        leftIndent=0.6 * cm, alignment=TA_LEFT,
    )
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, rightMargin=1.5 * cm, leftMargin=3.0 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title="Математическая модель построения допустимой области размещения башенного крана",
        author="В. И. Мигин; А. М. Эльшейх",
    )
    lines = (article_root / "manuscript" / "ARTICLE_RU.md").read_text(encoding="utf-8").splitlines()
    story: list[Any] = []
    index = 0
    front_count = 0
    in_references = False
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:]), title))
            index += 1
            continue
        if line.startswith("## "):
            heading_text = line[3:]
            in_references = heading_text == "Список литературы"
            story.append(Paragraph(escape(heading_text), heading))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and set(lines[index + 1].replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            raw_rows = [[item.strip() for item in line.strip("|").split("|")]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                raw_rows.append([item.strip() for item in lines[index].strip().strip("|").split("|")])
                index += 1
            cell_style = ParagraphStyle("Cell", parent=body, fontSize=8.2, leading=9.6, firstLineIndent=0, alignment=TA_LEFT)
            header_style = ParagraphStyle("CellHead", parent=cell_style, fontName="TimesNewRoman-Bold", textColor=colors.white, alignment=TA_CENTER)
            data = []
            for row_index, row in enumerate(raw_rows):
                data.append([Paragraph(escape(value), header_style if row_index == 0 else cell_style) for value in row])
            table = Table(data, colWidths=[4.0 * cm, 3.2 * cm, 5.0 * cm, 3.3 * cm], repeatRows=1, hAlign="CENTER")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#44546A")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9D9D9")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5F8")]),
            ]))
            story.extend([Spacer(1, 5), table, Spacer(1, 7)])
            continue
        clean = escape(line.replace("`", ""))
        if front_count < 2:
            story.append(Paragraph(clean, centered))
            front_count += 1
        elif in_references and re.match(r"^\d+\.\s", line):
            story.append(Paragraph(clean, reference))
        elif line.startswith("`") and line.endswith("`"):
            story.append(Paragraph(clean, equation))
        else:
            story.append(Paragraph(clean, body))
        index += 1

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("TimesNewRoman", 9)
        canvas.drawCentredString(A4[0] / 2, 1.0 * cm, str(canvas.getPageNumber()))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--article-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--pdf-output", type=Path)
    args = parser.parse_args()
    for path in build_documents(args.article_root, args.output_root):
        print(path)
    if args.pdf_output:
        print(build_article_pdf(args.article_root, args.pdf_output))


if __name__ == "__main__":
    main()
