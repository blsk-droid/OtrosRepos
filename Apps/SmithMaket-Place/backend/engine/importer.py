import re
import uuid
from typing import Dict, Any, List, Tuple
from docx import Document

def parse_docx(file_path: str) -> Dict[str, Any]:
    """
    Parses a DOCX file, extracting paragraphs, styles, and inline run formatting.
    Returns a dict with:
      - title: Suggested title (from filename)
      - blocks: List of structured paragraph blocks
      - styles_detected: List of all paragraph style names found
      - chapter_detection: Heuristic chapter detection results
    """
    doc = Document(file_path)
    blocks: List[Dict[str, Any]] = []
    styles_detected = set()

    for p_idx, paragraph in enumerate(doc.paragraphs):
        text = paragraph.text
        style_name = paragraph.style.name if paragraph.style else "Normal"
        styles_detected.add(style_name)

        runs_data = []
        for run in paragraph.runs:
            if not run.text:
                continue
            runs_data.append({
                "text": run.text,
                "bold": bool(run.bold),
                "italic": bool(run.italic),
                "underline": bool(run.underline),
            })

        # Avoid adding empty spacer paragraphs at the end, but keep them if they are meaningful breaks
        # We assign a unique ID to each block for precise tracking
        blocks.append({
            "id": str(uuid.uuid4()),
            "index": p_idx,
            "text": text,
            "style": style_name,
            "runs": runs_data
        })

    # Heuristic Chapter Detection
    detected_chapters, confidence_score = detect_chapters_heuristic(blocks)

    return {
        "blocks": blocks,
        "styles_detected": list(styles_detected),
        "chapter_detection": {
            "detected_chapter_block_ids": detected_chapters,
            "confidence_score": confidence_score,  # 0.0 to 1.0
            "suggested_mappings": suggest_style_mappings(blocks, detected_chapters)
        }
    }

def detect_chapters_heuristic(blocks: List[Dict[str, Any]]) -> Tuple[List[str], float]:
    """
    Analyzes document blocks to find paragraph IDs that likely represent chapter headings.
    Returns list of block IDs and a confidence score between 0.0 (ambiguous) and 1.0 (certain).
    """
    chapter_block_ids = []
    
    # 1. Look for common chapter keywords in paragraph text
    # e.g., "Chapter 1", "Capítulo I", "Prologue", "Epilogue", "I. The Beginning"
    chapter_regex = re.compile(
        r'^\s*(chapter|capítulo|capitulo|prologue|prólogo|epilogue|epílogo|act|acto|scene|escena)\b\s*(\d+|[ivxldcm]+)?.*$',
        re.IGNORECASE
    )
    
    # Track statistics of styles containing matches
    style_match_counts = {}
    total_blocks_by_style = {}
    
    for block in blocks:
        style = block["style"]
        text = block["text"].strip()
        
        total_blocks_by_style[style] = total_blocks_by_style.get(style, 0) + 1
        
        if not text:
            continue
            
        # Match keywords or standalone Roman numerals/numbers with short text
        is_keyword_match = bool(chapter_regex.match(text))
        is_numeric_match = len(text) < 15 and re.match(r'^\s*(\d+|[ivxldcm]+)\s*$', text, re.IGNORECASE)
        
        if is_keyword_match or is_numeric_match:
            style_match_counts[style] = style_match_counts.get(style, 0) + 1
            chapter_block_ids.append(block["id"])

    # Determine confidence score based on consistency of matching blocks
    if not chapter_block_ids:
        # No chapters detected. High ambiguity.
        return [], 0.0

    # Let's see if the detected chapters belong mostly to a single style (e.g. Heading 1)
    # If a single style covers 90%+ of detected chapters and that style is rarely used for regular body text,
    # then we have high confidence.
    style_purity = []
    for style, match_count in style_match_counts.items():
        total_in_style = total_blocks_by_style[style]
        # Purity is high if this style is mostly used for chapter titles
        purity = match_count / total_in_style
        style_purity.append((style, purity, match_count))

    # Sort styles by match count
    style_purity.sort(key=lambda x: x[2], reverse=True)
    primary_chapter_style, purity, matches = style_purity[0]

    # If the primary style is only used for chapter titles, and we matched them all, confidence is high
    if purity > 0.8 and matches >= len(chapter_block_ids) * 0.8:
        # If the primary style is "Heading 1" or contains "Heading" or "Title", confidence goes up
        base_confidence = 0.85 if any(k in primary_chapter_style.lower() for k in ["heading", "title", "chapter"]) else 0.70
        confidence = min(base_confidence + (purity * 0.15), 1.0)
    else:
        # Style is mixed with body text, or chapters are split among random styles. Low confidence.
        confidence = 0.40

    # Filter detected list to only include blocks of the primary chapter style if confidence is high,
    # otherwise keep all matches and let user verify.
    if confidence > 0.7:
        final_chapter_ids = [b["id"] for b in blocks if b["style"] == primary_chapter_style and b["text"].strip()]
        return final_chapter_ids, confidence
    
    return chapter_block_ids, confidence

def suggest_style_mappings(blocks: List[Dict[str, Any]], detected_chapter_ids: List[str]) -> Dict[str, str]:
    """
    Suggests style mappings (e.g. "Heading 1" -> "chapter_title", "Normal" -> "body_text")
    based on detection results.
    """
    mappings = {}
    chapter_styles = set()
    body_styles = set()
    
    for block in blocks:
        if block["id"] in detected_chapter_ids:
            chapter_styles.add(block["style"])
        else:
            if block["text"].strip():
                body_styles.add(block["style"])
                
    for s in chapter_styles:
        mappings[s] = "chapter_title"
    for s in body_styles - chapter_styles:
        # Default mapping for body text
        if "normal" in s.lower() or "body" in s.lower() or s == "Default":
            mappings[s] = "body_text"
        else:
            mappings[s] = "other"
            
    return mappings
