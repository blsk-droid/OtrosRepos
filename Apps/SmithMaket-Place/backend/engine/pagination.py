import os
import math
from typing import Dict, Any, List
from PIL import ImageFont

# Path helper for Windows system fonts
def get_font_path(font_name: str) -> str:
    """
    Attempts to find the requested font on the system, falling back to standard alternatives.
    """
    system_root = os.environ.get("SystemRoot", "C:\\Windows")
    fonts_dir = os.path.join(system_root, "Fonts")

    # Common fiction serifs mapping to Windows font filenames
    font_mapping = {
        "garamond": ["gara.ttf", "garabd.ttf", "garait.ttf"],
        "georgia": ["georgia.ttf", "georgiab.ttf", "georgiai.ttf"],
        "times new roman": ["times.ttf", "timesbd.ttf", "timesi.ttf"],
        "baskerville": ["baskvill.ttf"],
        "book antiqua": ["bkant.ttf"],
        "palatino": ["pala.ttf"],
    }

    normalized_name = font_name.lower()
    filenames = font_mapping.get(normalized_name, ["times.ttf"]) # Fallback to Times New Roman

    for filename in filenames:
        path = os.path.join(fonts_dir, filename)
        if os.path.exists(path):
            return path

    # absolute fallback
    fallback_path = os.path.join(fonts_dir, "times.ttf")
    if os.path.exists(fallback_path):
        return fallback_path
    
    # If no font found (e.g. non-windows container), return empty and let Pillow raise or use default
    return ""

def measure_text_width(text: str, font: ImageFont.FreeTypeFont, letter_spacing_pt: float) -> float:
    """
    Measures the exact width of the text in points.
    1 point = 1 pixel at 72 DPI (Pillow's default).
    """
    if not text:
        return 0.0
    try:
        width = font.getlength(text)
    except AttributeError:
        # Fallback for older Pillow versions
        width = font.getbbox(text)[2]
    
    # Inject letter spacing (tracking)
    if letter_spacing_pt != 0.0 and len(text) > 1:
        width += (len(text) - 1) * letter_spacing_pt
    return width

def wrap_text_greedy(text: str, font: ImageFont.FreeTypeFont, max_width_pt: float, letter_spacing_pt: float) -> List[str]:
    """
    Wraps text into multiple lines using a greedy word-wrapping algorithm.
    Preserves whitespace and wraps cleanly at word boundaries.
    """
    if not text.strip():
        return [""]

    words = text.split(" ")
    lines = []
    current_line = []

    for word in words:
        # Test line width with this word added
        test_line = " ".join(current_line + [word]) if current_line else word
        test_w = measure_text_width(test_line, font, letter_spacing_pt)
        
        if test_w <= max_width_pt:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                # If a single word is wider than max_width, force wrap it (rare in fiction)
                lines.append(word)
                current_line = []
                
    if current_line:
        lines.append(" ".join(current_line))
        
    return lines

def paginate_book(book_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Simulates typesetting and paginates the document.
    Returns a list of Page dicts.
    """
    # 1. Load book dimensions & parameters
    width_in = book_data.get("kdp_width_inches", 6.0)
    height_in = book_data.get("kdp_height_inches", 9.0)
    
    m_inner = book_data.get("margin_inner_inches", 0.75)
    m_outer = book_data.get("margin_outer_inches", 0.5)
    m_top = book_data.get("margin_top_inches", 0.75)
    m_bottom = book_data.get("margin_bottom_inches", 0.75)
    
    font_name = book_data.get("font_family", "Garamond")
    font_size = book_data.get("font_size_pt", 11.0)
    line_height_mult = book_data.get("line_height_relative", 1.35)
    tracking = book_data.get("letter_spacing_pt", 0.0)
    widow_orphan = book_data.get("widow_orphan_control", True)
    
    blocks = book_data.get("content_blocks", [])
    style_mappings = book_data.get("style_mappings", {})
    chapter_defs = book_data.get("chapter_definitions", {})
    chapter_block_ids = set(chapter_defs.get("chapter_block_ids", []))

    # 2. Compute grid and layout constraints in points (1 in = 72 pt)
    page_w_pt = width_in * 72
    page_h_pt = height_in * 72
    
    # Symmetrical margins map to Left/Right vs Inner/Outer based on page side
    # For computation, we assume a constant body text width
    printable_w_pt = page_w_pt - (m_inner + m_outer) * 72
    printable_h_pt = page_h_pt - (m_top + m_bottom) * 72
    
    # Base fonts
    font_path = get_font_path(font_name)
    
    # Load fonts (Regular, Bold, Italic)
    try:
        font_body = ImageFont.truetype(font_path, int(font_size))
        font_chapter = ImageFont.truetype(font_path, int(font_size * 1.5))  # Chapters are 1.5x larger
    except Exception:
        # Final fallback in case of loading issues
        font_body = ImageFont.load_default()
        font_chapter = ImageFont.load_default()

    # 3. Process and wrap all paragraph blocks
    processed_paragraphs = []
    for block in blocks:
        b_id = block["id"]
        text = block["text"]
        style = block["style"]
        
        # Resolve semantic type
        semantic_type = style_mappings.get(style, "body_text")
        if b_id in chapter_block_ids:
            semantic_type = "chapter_title"
            
        # Determine styling properties
        if semantic_type == "chapter_title":
            f_size = font_size * 1.5
            l_height = f_size * 1.4
            p_font = font_chapter
            space_before = 72.0  # 1 inch space before chapter title
            space_after = 36.0   # 0.5 inch space after chapter title
            is_chapter = True
        else:
            f_size = font_size
            l_height = f_size * line_height_mult
            p_font = font_body
            space_before = 0.0
            space_after = 8.0    # 8pt space after paragraphs
            is_chapter = False

        # Wrap text into lines
        lines = wrap_text_greedy(text, p_font, printable_w_pt, tracking)
        
        processed_paragraphs.append({
            "block_id": b_id,
            "style": style,
            "semantic_type": semantic_type,
            "is_chapter": is_chapter,
            "lines": lines,
            "line_height": l_height,
            "space_before": space_before,
            "space_after": space_after
        })

    # 4. Paginate lines
    pages = []
    current_page_lines = []
    current_y = 0.0
    page_number = 1

    def push_page():
        nonlocal page_number, current_page_lines, current_y
        is_left = (page_number % 2 == 0)
        pages.append({
            "page_number": page_number,
            "is_left": is_left,
            "lines": current_page_lines
        })
        page_number += 1
        current_page_lines = []
        current_y = 0.0

    for p_idx, p in enumerate(processed_paragraphs):
        # Chapter title forces page break
        if p["is_chapter"]:
            if current_page_lines:
                push_page()
            # Apply chapter spacing
            current_y += p["space_before"]
            
        lines = p["lines"]
        line_height = p["line_height"]
        num_lines = len(lines)
        
        if num_lines == 0:
            continue
            
        # Distribute paragraph lines to pages enforcing widow & orphan controls
        line_idx = 0
        while line_idx < num_lines:
            lines_left_to_place = num_lines - line_idx
            
            # How many lines fit on the current page?
            space_remaining = printable_h_pt - current_y
            lines_that_fit = math.floor(space_remaining / line_height)
            
            if lines_that_fit <= 0:
                push_page()
                continue
                
            # If all remaining lines fit, we place them
            if lines_left_to_place <= lines_that_fit:
                for idx in range(line_idx, num_lines):
                    current_page_lines.append({
                        "block_id": p["block_id"],
                        "text": lines[idx],
                        "is_chapter": p["is_chapter"],
                        "semantic_type": p["semantic_type"]
                    })
                current_y += (lines_left_to_place * line_height) + p["space_after"]
                break
                
            # Paragraph needs to be split
            if not widow_orphan:
                # Without controls, fit as many as possible
                for idx in range(line_idx, line_idx + lines_that_fit):
                    current_page_lines.append({
                        "block_id": p["block_id"],
                        "text": lines[idx],
                        "is_chapter": p["is_chapter"],
                        "semantic_type": p["semantic_type"]
                    })
                line_idx += lines_that_fit
                push_page()
            else:
                # With widow/orphan controls
                # 1. Orphan rule: Cannot leave a single line at the bottom of a page
                if lines_that_fit < 2:
                    # Move everything remaining to the next page
                    push_page()
                    continue
                    
                # 2. Widow rule: Cannot leave a single line at the top of the next page
                # If splitting would leave exactly 1 line on the next page, we must reduce the lines placed on this page by 1
                lines_on_next_page = lines_left_to_place - lines_that_fit
                if lines_on_next_page == 1:
                    lines_to_place_now = lines_that_fit - 1
                else:
                    lines_to_place_now = lines_that_fit
                    
                # Place lines
                for idx in range(line_idx, line_idx + lines_to_place_now):
                    current_page_lines.append({
                        "block_id": p["block_id"],
                        "text": lines[idx],
                        "is_chapter": p["is_chapter"],
                        "semantic_type": p["semantic_type"]
                    })
                line_idx += lines_to_place_now
                push_page()

    # Flush last page if it contains content
    if current_page_lines:
        push_page()
        
    return pages
