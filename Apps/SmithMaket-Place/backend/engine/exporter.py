import os
from typing import Dict, Any, List
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Intentamos importar WeasyPrint de forma segura
try:
    import weasyprint
    WEASYPRINT_AVAILABLE = True
except OSError:
    # Si estamos en Windows local y fallan las DLLs, evitamos que el programa muera
    WEASYPRINT_AVAILABLE = False
    print("\n[AVISO LOCAL] WeasyPrint no está instalado en el sistema operativo Windows.")
    print("[AVISO LOCAL] El modo visual funcionará, pero la generación de PDF real se delegará a Docker.\n")

def set_mirror_margins(section) -> None:
    """
    Enables mirror margins in a python-docx Section via XML manipulation.
    """
    sectPr = section._sectPr
    # Word sets mirror margins on the document level, which corresponds to setting
    # <w:mirrorMargins/> inside sectPr.
    mirror = OxmlElement('w:mirrorMargins')
    sectPr.append(mirror)

def set_section_margins(section, top: float, bottom: float, inner: float, outer: float) -> None:
    """
    Sets specific margins on a python-docx Section.
    Note: Under mirror margins, left_margin acts as inner, and right_margin acts as outer.
    """
    section.top_margin = Inches(top)
    section.bottom_margin = Inches(bottom)
    section.left_margin = Inches(inner)
    section.right_margin = Inches(outer)

def export_pdf(book_data: Dict[str, Any], pages: List[Dict[str, Any]], output_path: str) -> None:
    """Genera el PDF simulado o real según disponibilidad"""
    if not WEASYPRINT_AVAILABLE:
        # En modo desarrollo local, si no está WeasyPrint, creamos un archivo de texto de simulacro
        print("[MOCK] Simulando exportación de PDF vía WeasyPrint...")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("Simulación de PDF para desarrollo local. El motor real corre en Docker.")
        return True
        
    """
    Generates a professional KDP PDF using WeasyPrint with CSS Paged Media.
    """
    width_in = book_data.get("kdp_width_inches", 6.0)
    height_in = book_data.get("kdp_height_inches", 9.0)
    m_inner = book_data.get("margin_inner_inches", 0.75)
    m_outer = book_data.get("margin_outer_inches", 0.5)
    m_top = book_data.get("margin_top_inches", 0.75)
    m_bottom = book_data.get("margin_bottom_inches", 0.75)
    font_name = book_data.get("font_family", "Garamond")
    font_size = book_data.get("font_size_pt", 11.0)
    line_height = book_data.get("line_height_relative", 1.35)
    tracking = book_data.get("letter_spacing_pt", 0.0)

    # 1. Build the HTML and Paged Media CSS
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <style>
        @page {{
            size: {width_in}in {height_in}in;
            margin-top: {m_top}in;
            margin-bottom: {m_bottom}in;
            @bottom-center {{
                content: counter(page);
                font-family: '{font_name}', serif;
                font-size: 10pt;
            }}
        }}
        @page:left {{
            margin-left: {m_outer}in;
            margin-right: {m_inner}in;
        }}
        @page:right {{
            margin-left: {m_inner}in;
            margin-right: {m_outer}in;
        }}
        @page chapter_start {{
            margin-top: {m_top + 1.0}in; /* lower chapter titles by 1 inch */
            @bottom-center {{
                content: ""; /* hide page numbers on chapter start pages */
            }}
            @top-center {{
                content: "";
            }}
        }}
        
        body {{
            font-family: '{font_name}', serif;
            font-size: {font_size}pt;
            line-height: {line_height};
            letter-spacing: {tracking}pt;
            color: device-cmyk(0, 0, 0, 1); /* 100% K ink for KDP printing */
            text-align: justify;
            margin: 0;
            padding: 0;
        }}

        .page-break {{
            page-break-before: always;
        }}

        .chapter {{
            page: chapter_start;
            page-break-before: always;
        }}

        .chapter-title {{
            font-size: 1.5em;
            text-align: center;
            margin-top: 0;
            margin-bottom: 2em;
            font-weight: bold;
            page-break-after: avoid;
        }}

        p {{
            margin-top: 0;
            margin-bottom: 0;
            text-indent: 1.5em; /* standard fiction indent */
        }}

        p.first-para {{
            text-indent: 0; /* no indent for first paragraph of chapter */
        }}
    </style>
    </head>
    <body>
    """

    current_chapter_id = None
    first_para_of_chapter = False

    for page_idx, page in enumerate(pages):
        page_lines = page["lines"]
        if not page_lines:
            continue

        if page_idx > 0:
            # Check if this page starts a new chapter
            if page_lines[0]["is_chapter"]:
                html_content += '\n<div class="chapter"></div>\n'
            else:
                html_content += '\n<div class="page-break"></div>\n'

        for line in page_lines:
            if line["is_chapter"]:
                current_chapter_id = line["block_id"]
                first_para_of_chapter = True
                html_content += f'<div class="chapter-title">{line["text"]}</div>\n'
            else:
                # If first paragraph of a chapter, style without indent
                p_class = ' class="first-para"' if first_para_of_chapter else ''
                # We group line texts. For simplicity, we output lines directly inside divs/paragraphs
                # styled to look continuous, or wrap each paragraph.
                # Since we know the exact line-breaks, we can just represent each line inside a paragraph wrapper
                # with no indent, or output as a page of text lines.
                # In WeasyPrint, representing line-by-line matches exactly what we calculated.
                html_content += f'<p{p_class}>{line["text"]}</p>\n'
                first_para_of_chapter = False

    html_content += """
    </body>
    </html>
    """

    # 2. Write PDF
    weasyprint.HTML(string=html_content).write_pdf(output_path)

def export_docx(book_data: Dict[str, Any], pages: List[Dict[str, Any]], output_path: str) -> None:
    """
    Generates a symmetrical Word DOCX document that mirrors the exact pagination
    of the PDF typesetting engine by injecting hard page and section breaks.
    """
    width_in = book_data.get("kdp_width_inches", 6.0)
    height_in = book_data.get("kdp_height_inches", 9.0)
    m_inner = book_data.get("margin_inner_inches", 0.75)
    m_outer = book_data.get("margin_outer_inches", 0.5)
    m_top = book_data.get("margin_top_inches", 0.75)
    m_bottom = book_data.get("margin_bottom_inches", 0.75)
    font_name = book_data.get("font_family", "Garamond")
    font_size = book_data.get("font_size_pt", 11.0)
    line_height = book_data.get("line_height_relative", 1.35)

    doc = Document()
    
    # Configure first section
    section = doc.sections[0]
    section.page_width = Inches(width_in)
    section.page_height = Inches(height_in)
    set_section_margins(section, m_top, m_bottom, m_inner, m_outer)
    set_mirror_margins(section)

    first_page = True
    
    for page_idx, page in enumerate(pages):
        page_lines = page["lines"]
        if not page_lines:
            continue

        # Handle page breaking
        if not first_page:
            # Check if this page starts a new chapter
            if page_lines[0]["is_chapter"]:
                # Start new section for the new chapter (enables first-page header hides)
                new_section = doc.add_section(WD_SECTION.NEW_PAGE)
                new_section.page_width = Inches(width_in)
                new_section.page_height = Inches(height_in)
                set_section_margins(new_section, m_top, m_bottom, m_inner, m_outer)
                set_mirror_margins(new_section)
            else:
                # Standard hard page break
                doc.add_page_break()
        else:
            first_page = False

        # Add lines belonging to this page
        for line in page_lines:
            p = doc.add_paragraph()
            
            # Paragraph formatting
            p_format = p.paragraph_format
            p_format.space_before = Pt(0)
            p_format.space_after = Pt(0)
            p_format.line_spacing = line_height
            
            if line["is_chapter"]:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_format.space_before = Pt(72)  # Space before chapter title
                p_format.space_after = Pt(36)
                
                run = p.add_run(line["text"])
                run.font.name = font_name
                run.font.size = Pt(font_size * 1.5)
                run.bold = True
            else:
                # Body text line
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                run = p.add_run(line["text"])
                run.font.name = font_name
                run.font.size = Pt(font_size)

    doc.save(output_path)
