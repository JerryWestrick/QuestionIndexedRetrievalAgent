#!/usr/bin/env python3
"""Build a QIRA corpus from EU AI Act (Regulation (EU) 2024/1689) Formex 4 XML.

Steps 1-4: Parse Formex XML → Section tree, organize, rewrite cross-references.
Steps 5-7: Generate questions (LLM), pre-format, vectorize, store.

Usage:
    python build_corpus.py --source /path/to/extracted/formex/files \
                           --output /path/to/output/eu-ai-act

The --source directory must contain the Formex files extracted from
http://publications.europa.eu/resource/cellar/dc8116a1-3fe6-11ef-865a-01aa75ed71a1.0006.02/DOC_1
i.e. L_202401689EN.doc.fmx.xml plus L_202401689EN.000101.fmx.xml plus the 13 annex files.
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


# ---------------------------------------------------------------------------
# Crash log — survives hard resets because every write is fsynced to disk
# ---------------------------------------------------------------------------
_crash_log_fh = None

def crash_log_open(path: Path):
    """Open (append) the crash log. Call once at startup."""
    global _crash_log_fh
    _crash_log_fh = open(path, "a", encoding="utf-8")
    crash_log("=== build_corpus.py started ===")

def crash_log(msg: str):
    """Write one timestamped line and fsync to disk immediately."""
    if _crash_log_fh is None:
        return
    line = f"[{time.strftime('%H:%M:%S')}] {msg}\n"
    _crash_log_fh.write(line)
    _crash_log_fh.flush()
    os.fsync(_crash_log_fh.fileno())


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORPUS = "eu-ai-act"

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX",
         "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Section:
    """A section extracted from the EU AI Act XML."""
    id: str = ""                      # e.g. eu-ai-act:4.2.1
    title: str = ""                   # e.g. "Article 9 — Risk management system"
    breadcrumb: str = ""              # e.g. "EU AI Act > Chapter III > ... > Article 9"
    content_md: str = ""              # markdown content (body, no heading)
    children: list = field(default_factory=list)
    level: int = 0                    # depth in hierarchy
    kind: str = ""                    # recitals_root|recital|chapter|section|article|definition|annex
    src_id: str = ""                  # Formex IDENTIFIER attribute (e.g. "001" or "001.002")


# ---------------------------------------------------------------------------
# Stage 1a: Inline rendering — Formex inline elements → markdown
# ---------------------------------------------------------------------------

def render_inline(elem) -> str:
    """Render an element's mixed content as inline markdown.

    Walks an element's text + children + tails, applying inline formatting:
      <HT TYPE="ITALIC">x</HT>          → *x*
      <HT TYPE="BOLD">x</HT>            → **x**
      <HT TYPE="UC">x</HT>              → X (uppercased)
      <DATE ISO="...">13 June 2024</DATE> → 13 June 2024
      <QUOT.START CODE="2018"/>         → ‘  (Unicode codepoint from CODE attr)
      <QUOT.END   CODE="2019"/>         → ’
      <NOTE>...</NOTE>                  → (dropped — footnotes always cite external OJ acts)
      <REF.DOC.OJ>OJ L 218, ...</REF.DOC.OJ> → text content (external OJ citation)
      Unknown element                   → text content as fallback

    Block-level elements (P, ALINEA, LIST, ITEM, NP, TXT) are passed through to
    text content here; the block renderer handles their structural meaning.
    """
    parts = []
    if elem.text:
        parts.append(elem.text)
    for child in elem:
        tag = child.tag
        if tag == "HT":
            inner = render_inline(child)
            t = child.get("TYPE", "")
            if t == "ITALIC":
                parts.append(f"*{inner}*")
            elif t == "BOLD":
                parts.append(f"**{inner}**")
            elif t == "UC":
                parts.append(inner.upper())
            else:
                parts.append(inner)
        elif tag == "DATE":
            parts.append(render_inline(child))
        elif tag == "QUOT.START":
            code = child.get("CODE", "2018")
            parts.append(chr(int(code, 16)))
        elif tag == "QUOT.END":
            code = child.get("CODE", "2019")
            parts.append(chr(int(code, 16)))
        elif tag == "NOTE":
            pass  # drop footnote bodies
        elif tag == "REF.DOC.OJ":
            parts.append(render_inline(child))
        else:
            parts.append(render_inline(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def squash(text: str) -> str:
    """Collapse whitespace runs and trim."""
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Stage 1b: Block rendering — Formex block elements → markdown
# ---------------------------------------------------------------------------

def render_alinea(alinea) -> str:
    """Render one <ALINEA>.

    ALINEA is the basic prose unit. It comes in two shapes:
      (a) plain text (with inline elements only) — one paragraph
      (b) contains <P> + <LIST> blocks — render each block, join with blank lines
    """
    children = list(alinea)
    has_blocks = any(c.tag in ("P", "LIST", "ALINEA") for c in children)
    if not has_blocks:
        return squash(render_inline(alinea))

    # Mixed block content. Render each child as its own block.
    out = []
    # Some ALINEAs have leading text before the first block child — preserve it
    if alinea.text and alinea.text.strip():
        out.append(squash(alinea.text))
    for child in children:
        if child.tag == "P":
            out.append(render_p(child, indent=0))
        elif child.tag == "LIST":
            out.append(render_list(child, indent=0))
        elif child.tag == "ALINEA":
            out.append(render_alinea(child))
        else:
            t = squash(render_inline(child))
            if t:
                out.append(t)
        if child.tail and child.tail.strip():
            out.append(squash(child.tail))
    return "\n\n".join(b for b in out if b)


def render_p(p, indent: int = 0) -> str:
    """Render one <P>.

    A <P> may either be a plain inline paragraph or wrap a single nested <LIST>.
    The wrapping form occurs in NPs that introduce nested lettered lists.
    """
    children = list(p)
    if len(children) == 1 and children[0].tag == "LIST" and not (p.text or "").strip():
        return render_list(children[0], indent)
    return squash(render_inline(p))


def render_list(lst, indent: int = 0) -> str:
    """Render one <LIST>.

    Children are <ITEM> elements, each containing an <NP> with <NO.P> + <TXT>
    plus optional nested <P>/<LIST> for sub-content.
    """
    lines = []
    for item in lst.findall("ITEM"):
        lines.append(render_item(item, indent))
    return "\n".join(l for l in lines if l)


def render_item(item, indent: int = 0) -> str:
    """Render one <ITEM> (containing an <NP> with <NO.P> + <TXT> + optional nested blocks)."""
    pad = "  " * indent
    np = item.find("NP")
    if np is None:
        # Some annexes have <ITEM> with direct text content — fall back
        text = squash(render_inline(item))
        return f"{pad}- {text}" if text else ""

    no_p_elem = np.find("NO.P")
    txt_elem = np.find("TXT")
    marker = squash(render_inline(no_p_elem)) if no_p_elem is not None else ""
    body = squash(render_inline(txt_elem)) if txt_elem is not None else ""

    line_parts = [f"{pad}-"]
    if marker:
        line_parts.append(marker)
    if body:
        line_parts.append(body)
    line = " ".join(line_parts)

    # Look for nested block content inside the NP
    nested = []
    for child in np:
        if child.tag in ("NO.P", "TXT"):
            continue
        if child.tag == "P":
            grandchildren = list(child)
            if len(grandchildren) == 1 and grandchildren[0].tag == "LIST" and not (child.text or "").strip():
                nested.append(render_list(grandchildren[0], indent + 1))
            else:
                p_text = squash(render_inline(child))
                if p_text:
                    nested.append(f"{pad}  {p_text}")
        elif child.tag == "LIST":
            nested.append(render_list(child, indent + 1))
        else:
            extra = squash(render_inline(child))
            if extra:
                nested.append(f"{pad}  {extra}")

    if nested:
        return line + "\n" + "\n".join(n for n in nested if n)
    return line


def render_parag(parag) -> str:
    """Render one <PARAG IDENTIFIER="NNN.MMM"> from inside an article.

    Format:  **N.** {alinea text}
             {further alinea blocks}
    """
    no_parag = parag.find("NO.PARAG")
    marker = squash(render_inline(no_parag)) if no_parag is not None else ""

    alineas = parag.findall("ALINEA")
    if not alineas:
        return f"**{marker}**" if marker else ""

    parts = []
    first = render_alinea(alineas[0])
    if marker:
        # Embed the marker at the start of the first paragraph block.
        # If the alinea is a single paragraph, prepend; if it starts with a list,
        # put the marker on its own line.
        if first.startswith("-") or first.startswith("\n"):
            parts.append(f"**{marker}**")
            parts.append(first)
        else:
            parts.append(f"**{marker}** {first}")
    else:
        parts.append(first)

    for alinea in alineas[1:]:
        parts.append(render_alinea(alinea))

    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Stage 1c: Structural walk — manifest → top-level Section list
# ---------------------------------------------------------------------------

def parse_manifest(doc_path: Path) -> tuple:
    """Read the Formex doc manifest and return (main_act_path, [annex_paths_in_order])."""
    tree = ET.parse(str(doc_path))
    root = tree.getroot()
    fmx = root.find("FMX")
    if fmx is None:
        raise ValueError(f"{doc_path}: no <FMX> element in manifest")

    main_ref = fmx.find("DOC.MAIN.PUB/REF.PHYS")
    if main_ref is None:
        raise ValueError(f"{doc_path}: no <DOC.MAIN.PUB><REF.PHYS> in manifest")
    main_file = main_ref.get("FILE")

    annex_files = []
    for sub in fmx.findall("DOC.SUB.PUB"):
        if sub.get("TYPE") != "ANNEX":
            continue
        ref = sub.find("REF.PHYS")
        if ref is not None and ref.get("FILE"):
            annex_files.append(ref.get("FILE"))

    return main_file, annex_files


def parse_main_act(main_path: Path) -> tuple:
    """Parse the main act file (000101.fmx.xml).

    Returns (recitals_root_section, [chapter_sections]).
    """
    tree = ET.parse(str(main_path))
    act = tree.getroot()  # <ACT>

    # ----- Preamble: recitals -----
    recitals_root = Section(
        title="Recitals",
        kind="recitals_root",
        level=0,
    )
    preamble = act.find("PREAMBLE")
    if preamble is not None:
        gr_consid = preamble.find("GR.CONSID")
        if gr_consid is not None:
            for consid in gr_consid.findall("CONSID"):
                recital = parse_recital(consid)
                if recital is not None:
                    recitals_root.children.append(recital)

    # ----- Enacting terms: chapters → (sections →)? articles -----
    chapters = []
    enacting = act.find("ENACTING.TERMS")
    if enacting is not None:
        for div in enacting.findall("DIVISION"):
            chapter = parse_division(div, depth=0)
            if chapter is not None:
                chapters.append(chapter)

    return recitals_root, chapters


def parse_recital(consid) -> Section:
    """Parse one <CONSID> recital element."""
    np = consid.find("NP")
    if np is None:
        return None
    no_p = np.find("NO.P")
    txt = np.find("TXT")
    marker = squash(render_inline(no_p)) if no_p is not None else ""  # e.g. "(1)"
    body = squash(render_inline(txt)) if txt is not None else ""

    # Strip outer parens from "(27)" → "27" for the title
    num_match = re.match(r"\((\d+)\)", marker)
    num_str = num_match.group(1) if num_match else marker

    return Section(
        title=f"Recital {num_str}",
        content_md=f"**{marker}** {body}".strip() if body else marker,
        kind="recital",
        src_id=num_str,
    )


def _strip_md_emphasis(s: str) -> str:
    """Remove markdown emphasis markers (** or *) from a short title-like string.

    Section titles in the OJ source frequently wrap subtitles in <HT TYPE="BOLD">,
    which render_inline turns into ``**...**``. We don't want those markers leaking
    into section titles or breadcrumbs.
    """
    # Strip surrounding bold/italic
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]*)\*", r"\1", s)
    return s.strip()


def title_with_optional_subtitle(title_elem) -> tuple:
    """Extract (heading, subtitle) from a Formex <TITLE> element.

    Two shapes occur in this regulation:
      Shape A:  <TITLE><TI><P>HEADING</P></TI><STI><P>subtitle</P></STI></TITLE>
      Shape B:  <TITLE><TI><P>HEADING</P><P>subtitle</P></TI></TITLE>

    Shape A uses an explicit <STI> sibling. Shape B puts both heading and
    subtitle as sibling <P>s inside <TI>. STI is preferred when present;
    otherwise the second-and-later <P> children of TI are joined as the
    subtitle. Markdown emphasis (from <HT TYPE="BOLD">) is stripped from
    both — section titles are plain text.
    """
    ti = title_elem.find("TI")
    sti = title_elem.find("STI")

    heading = ""
    subtitle = ""

    if sti is not None:
        subtitle = squash(render_inline(sti))

    if ti is not None:
        ti_ps = ti.findall("P")
        if len(ti_ps) >= 2 and not subtitle:
            heading = squash(render_inline(ti_ps[0]))
            extra = " ".join(squash(render_inline(p)) for p in ti_ps[1:])
            subtitle = squash(extra)
        else:
            heading = squash(render_inline(ti))

    return (_strip_md_emphasis(heading), _strip_md_emphasis(subtitle))


def division_titles(div) -> tuple:
    """Extract (heading, subtitle) from a <DIVISION>'s <TITLE>.

    Heading is the <TI>/<P> text (e.g. "CHAPTER I").
    Subtitle is the <STI>/<P> text if present (e.g. "GENERAL PROVISIONS").
    """
    title_elem = div.find("TITLE")
    if title_elem is None:
        return ("", "")
    return title_with_optional_subtitle(title_elem)


def parse_division(div, depth: int = 0) -> Section:
    """Parse one <DIVISION> recursively.

    A DIVISION is a Chapter / Section / Subsection container. It has a <TITLE>
    (with <TI> heading and optional <STI> subtitle), then either nested
    <DIVISION> children or <ARTICLE> children.
    """
    heading, subtitle = division_titles(div)

    # Build a human title. Examples:
    #   "CHAPTER I"  + "GENERAL PROVISIONS"      → "Chapter I — General Provisions"
    #   "SECTION 2"  + "Requirements for high-risk AI systems"
    #                                            → "Section 2 — Requirements for high-risk AI systems"
    label = title_case(heading)
    if subtitle:
        # Title-case all-caps subtitles, leave normal-case ones alone.
        sub = title_case(subtitle) if subtitle.isupper() else subtitle
        title = f"{label} — {sub}"
    else:
        title = label

    # Determine kind for downstream consumers
    kind = "chapter" if heading.upper().startswith("CHAPTER") else (
           "section" if heading.upper().startswith("SECTION") else
           "subsection" if heading.upper().startswith("SUBSECTION") else
           "division")

    section = Section(
        title=title,
        kind=kind,
        level=depth,
    )

    for child in div:
        if child.tag == "DIVISION":
            sub = parse_division(child, depth + 1)
            if sub is not None:
                section.children.append(sub)
        elif child.tag == "ARTICLE":
            article = parse_article(child)
            if article is not None:
                section.children.append(article)
        # TITLE already consumed via division_titles; skip

    return section


_KEEP_UPPER = {"AI", "EU", "TEU", "TFEU", "EEA", "CE", "OJ", "ID", "GPAI",
               "ML", "NLP", "GDPR", "SME", "SMES"}


def title_case(s: str) -> str:
    """Title-case an all-caps heading, leaving Roman numerals and known acronyms upper.

    Examples:
      'CHAPTER I'              → 'Chapter I'
      'GENERAL PROVISIONS'     → 'General Provisions'
      'PROHIBITED AI PRACTICES'→ 'Prohibited AI Practices'
      'CHAPTER VIII'           → 'Chapter VIII'

    Punctuation attached to a word (e.g. 'HIGH-RISK', 'AI,') is preserved by
    splitting on the alpha core, casing it, and rejoining.
    """
    if not s:
        return s
    out_words = []
    for w in s.split():
        if re.fullmatch(r"[IVXLCDM]+", w):
            out_words.append(w)  # Roman numeral
        elif w.upper() in _KEEP_UPPER:
            out_words.append(w.upper())
        elif "-" in w:
            # Hyphenated word: title-case each segment independently (HIGH-RISK → High-Risk)
            parts = w.split("-")
            cased = []
            for p in parts:
                if p.upper() in _KEEP_UPPER:
                    cased.append(p.upper())
                elif p.isupper():
                    cased.append(p.capitalize())
                else:
                    cased.append(p)
            out_words.append("-".join(cased))
        elif w.isupper():
            out_words.append(w.capitalize())
        else:
            out_words.append(w)
    return " ".join(out_words)


def parse_article(article) -> Section:
    """Parse one <ARTICLE>.

    Special case: Article 3 (Definitions) gets each definition as a child
    section so individual term lookups land precisely.
    """
    src_id = article.get("IDENTIFIER", "")  # e.g. "003"

    ti_art = article.find("TI.ART")
    sti_art = article.find("STI.ART")
    art_label = squash(render_inline(ti_art)) if ti_art is not None else f"Article {src_id.lstrip('0') or '?'}"
    subtitle = squash(render_inline(sti_art)) if sti_art is not None else ""
    # Strip stray backtick artifacts seen in source (e.g. "Subject matter`")
    subtitle = subtitle.rstrip("`")

    title = f"{art_label} — {subtitle}" if subtitle else art_label

    section = Section(
        title=title,
        kind="article",
        src_id=src_id,
    )

    is_definitions = (src_id == "003")

    if is_definitions:
        # Article 3: definitions. Render the lead-in as the article body and
        # carve each <ITEM> in the definitions <LIST> into a child section.
        body_blocks = []
        defs_list = None
        for child in article:
            if child.tag in ("TI.ART", "STI.ART"):
                continue
            if child.tag == "ALINEA":
                # The definitions ALINEA contains a <P> lead-in and a <LIST>
                for sub in child:
                    if sub.tag == "P":
                        body_blocks.append(squash(render_inline(sub)))
                    elif sub.tag == "LIST":
                        defs_list = sub
        section.content_md = "\n\n".join(b for b in body_blocks if b)

        if defs_list is not None:
            for item in defs_list.findall("ITEM"):
                child = parse_definition(item)
                if child is not None:
                    section.children.append(child)
    else:
        # Normal article: render PARAGs (or bare ALINEAs if there are no PARAGs).
        # Each rendered PARAG already begins with **N.** so the LLM can cite
        # paragraphs precisely without needing a redundant trailing marker.
        parag_blocks = []
        bare_alineas = []
        for child in article:
            if child.tag == "PARAG":
                rendered = render_parag(child)
                if rendered:
                    parag_blocks.append(rendered)
            elif child.tag == "ALINEA":
                bare_alineas.append(render_alinea(child))

        if parag_blocks:
            section.content_md = "\n\n".join(parag_blocks)
        elif bare_alineas:
            section.content_md = "\n\n".join(b for b in bare_alineas if b)

    return section


def parse_definition(item) -> Section:
    """Parse one definition <ITEM> from inside Article 3."""
    np = item.find("NP")
    if np is None:
        return None
    no_p = np.find("NO.P")
    txt = np.find("TXT")
    marker = squash(render_inline(no_p)) if no_p is not None else ""  # e.g. "(1)"
    body = squash(render_inline(txt)) if txt is not None else ""

    # Pull the defined term out of the leading 'term' single-quotes.
    # Body looks like:  ‘AI system’ means a machine-based system that...
    # A few definitions interpose a qualifier between the closing quote and
    # the word "means" (e.g. def 58: 'subject', for the purpose of real-world
    # testing, means ...). We just take whatever's in the leading single-quotes.
    term = ""
    m = re.match(r"\s*[\u2018'](.+?)[\u2019']", body)
    if m:
        term = m.group(1)

    num_match = re.match(r"\((\d+)\)", marker)
    num_str = num_match.group(1) if num_match else marker

    if term:
        title = f"({num_str}) '{term}'"
    else:
        title = f"Definition ({num_str})"

    return Section(
        title=title,
        content_md=f"**{marker}** {body}".strip() if body else marker,
        kind="definition",
        src_id=num_str,
    )


# ---------------------------------------------------------------------------
# Stage 1d: Annex parser
# ---------------------------------------------------------------------------

def parse_annex(annex_path: Path, annex_idx: int) -> Section:
    """Parse one annex file (e.g. L_202401689EN.012701.fmx.xml).

    Annexes have <ANNEX>/<TITLE> + <CONTENTS>. The contents may contain
    <P>, <LIST>, and/or <GR.SEQ> sub-grouping with its own titles.

    Two TITLE shapes occur in this regulation:
      Shape A (e.g. Annex I):  <TITLE><TI><P>ANNEX I</P></TI><STI><P>...</P></STI></TITLE>
      Shape B (e.g. Annex X):  <TITLE><TI><P>ANNEX X</P><P>...descriptive subtitle...</P></TI></TITLE>
    The parser handles both: STI is preferred when present, otherwise the
    second-and-later <P> children of TI are treated as the subtitle.
    """
    tree = ET.parse(str(annex_path))
    annex = tree.getroot()  # <ANNEX>

    title_elem = annex.find("TITLE")
    heading = ""
    subtitle = ""
    if title_elem is not None:
        heading, subtitle = title_with_optional_subtitle(title_elem)

    # heading is e.g. "ANNEX I"; subtitle is the descriptive name
    label = title_case(heading) if heading else f"Annex {ROMAN[annex_idx]}"
    if subtitle:
        title = f"{label} — {subtitle}"
    else:
        title = label

    contents = annex.find("CONTENTS")
    body = render_contents(contents) if contents is not None else ""

    return Section(
        title=title,
        content_md=body,
        kind="annex",
        src_id=ROMAN[annex_idx],
    )


def render_contents(contents) -> str:
    """Render an annex <CONTENTS> element as markdown.

    May contain <P>, <LIST>, and <GR.SEQ> blocks.
    """
    blocks = []
    for child in contents:
        tag = child.tag
        if tag == "P":
            blocks.append(render_p(child))
        elif tag == "LIST":
            blocks.append(render_list(child))
        elif tag == "GR.SEQ":
            blocks.append(render_gr_seq(child))
        elif tag == "ALINEA":
            blocks.append(render_alinea(child))
        else:
            t = squash(render_inline(child))
            if t:
                blocks.append(t)
    return "\n\n".join(b for b in blocks if b)


def render_gr_seq(gr_seq) -> str:
    """Render a <GR.SEQ> sub-grouping inside an annex.

    GR.SEQ has a <TITLE>/<TI>/<P> heading and then NP/LIST children.
    """
    blocks = []
    title_elem = gr_seq.find("TITLE")
    if title_elem is not None:
        ti = title_elem.find("TI")
        if ti is not None:
            heading = squash(render_inline(ti))
            if heading:
                blocks.append(f"### {heading}")

    for child in gr_seq:
        tag = child.tag
        if tag == "TITLE":
            continue
        if tag == "P":
            blocks.append(render_p(child))
        elif tag == "LIST":
            blocks.append(render_list(child))
        elif tag == "NP":
            # Bare NP: render as a bullet
            no_p = child.find("NO.P")
            txt = child.find("TXT")
            marker = squash(render_inline(no_p)) if no_p is not None else ""
            body = squash(render_inline(txt)) if txt is not None else ""
            blocks.append(f"- {marker} {body}".rstrip())
        elif tag == "ALINEA":
            blocks.append(render_alinea(child))
        else:
            t = squash(render_inline(child))
            if t:
                blocks.append(t)
    return "\n\n".join(b for b in blocks if b)


# ---------------------------------------------------------------------------
# Stage 2: Organize — assign IDs and breadcrumbs
# ---------------------------------------------------------------------------

ROOT_LABEL = "EU AI Act"


def organize(top_sections: list) -> list:
    """Assign hierarchical IDs and breadcrumbs to all sections."""
    all_sections = []

    for idx, top in enumerate(top_sections, 1):
        top.id = f"{CORPUS}:{idx}"
        top.breadcrumb = f"{ROOT_LABEL} > {top.title}"
        all_sections.append(top)
        _assign_ids(top, all_sections)

    return all_sections


def _assign_ids(parent: Section, all_sections: list):
    """Recursively assign IDs and breadcrumbs to children."""
    parent_num = parent.id.split(":", 1)[1]
    for idx, child in enumerate(parent.children, 1):
        child.id = f"{CORPUS}:{parent_num}.{idx}"
        child.breadcrumb = f"{parent.breadcrumb} > {child.title}"
        all_sections.append(child)
        _assign_ids(child, all_sections)


# ---------------------------------------------------------------------------
# Stage 3: Cross-reference rewriting
# ---------------------------------------------------------------------------

def build_xref_maps(all_sections: list) -> dict:
    """Build lookup maps for cross-reference rewriting.

    Returns dict with keys:
      'article':  {article_number_str: id}    e.g. {"6": "eu-ai-act:4.1.1"}
      'recital':  {recital_number_str: id}    e.g. {"27": "eu-ai-act:1.27"}
      'annex':    {roman_numeral: id}         e.g. {"III": "eu-ai-act:17"}
      'chapter':  {roman_numeral: id}         e.g. {"III": "eu-ai-act:4"}
    """
    maps = {"article": {}, "recital": {}, "annex": {}, "chapter": {}}

    for s in all_sections:
        if s.kind == "article" and s.src_id:
            num = s.src_id.lstrip("0") or "0"
            maps["article"][num] = s.id
        elif s.kind == "recital" and s.src_id:
            maps["recital"][s.src_id] = s.id
        elif s.kind == "annex" and s.src_id:
            maps["annex"][s.src_id] = s.id
        elif s.kind == "chapter":
            # Pull the Roman numeral out of the title ("Chapter III — ...")
            m = re.match(r"Chapter\s+([IVXLCDM]+)\b", s.title)
            if m:
                maps["chapter"][m.group(1)] = s.id

    return maps


# A negative lookahead to skip phrases that name a *different* document.
# We must NOT rewrite "Chapter II of Regulation (EU) 2022/2065" or
# "Article 16 of the TFEU" — those refer to other instruments, not this Act.
_OTHER_DOC = (
    r"(?!\s+of\s+(?:Regulation|Directive|Decision|Council|Commission|"
    r"the\s+Treaty|the\s+Charter|the\s+TFEU|the\s+TEU|the\s+UNCRC))"
)

# Patterns: each (regex, kind)
_XREF_PATTERNS = [
    # "Article 6(1)" or "Article 6"  — capture article number
    (re.compile(r"\bArticle\s+(\d+)(?:\((\d+)\))?" + _OTHER_DOC), "article"),
    # "Annex III" — capture roman
    (re.compile(r"\bAnnex\s+([IVXLCDM]+)\b" + _OTHER_DOC), "annex"),
    # "Chapter III" — capture roman
    (re.compile(r"\bChapter\s+([IVXLCDM]+)\b" + _OTHER_DOC), "chapter"),
    # "Recital (27)" or "recital (27)" — capture digits
    (re.compile(r"\b[Rr]ecital\s+\((\d+)\)"), "recital"),
]


def rewrite_xrefs(all_sections: list, maps: dict):
    """Rewrite plain-text cross-references in content_md to QIRA section IDs.

    Each rewritten reference becomes:  {original} (see {corpus}:{id})
    Cross-references that don't resolve are left untouched.
    """
    # Track positions we've already annotated to avoid double-annotation
    for section in all_sections:
        if not section.content_md:
            continue
        section.content_md = _rewrite_text(section.content_md, maps)


def _rewrite_text(text: str, maps: dict) -> str:
    """Apply all xref patterns to one text blob.

    Earlier patterns are processed first; once we annotate a span, later patterns
    won't re-match because we leave the original text in place and append the
    annotation parenthetical.
    """
    # We avoid annotating the same span twice by walking left-to-right per pattern
    # and skipping matches that already have a "(see eu-ai-act:" tail right after.
    for pattern, kind in _XREF_PATTERNS:
        def replace(match: re.Match) -> str:
            orig = match.group(0)
            # Skip if already annotated immediately after
            tail_start = match.end()
            if tail_start < len(text) and text[tail_start:tail_start + 6] == " (see ":
                return orig
            key = match.group(1)
            target = maps.get(kind, {}).get(key)
            if not target:
                return orig
            return f"{orig} (see {target})"

        text = pattern.sub(replace, text)
    return text


# ---------------------------------------------------------------------------
# Stage 4: Question generation via keprompt   (one call per section)
# ---------------------------------------------------------------------------

def call_keprompt(section: Section, keprompt_dir: Path) -> list:
    """Run keprompt once for one section, return its list of questions.

    Section content is passed directly via `--set content <text>`. We do not
    write a temp file: subprocess.run with an argv list is binary-safe and the
    AI Act's longest sections (~7 KB) fit comfortably under ARG_MAX. On any
    failure (non-zero exit, timeout, malformed JSON, parse error) the worker
    falls back to a single stub question rather than aborting the build.
    """
    content = section.content_md or section.title
    if not content.strip():
        content = section.title

    fallback = [f"What is {section.title}?"]

    crash_log(f"keprompt START {section.id} — building argv")
    argv = [
        "keprompt", "chat", "new",
        "--prompt", "generate_questions",
        "--set", "breadcrumb", section.breadcrumb,
        "--set", "title", section.title,
        "--set", "content", content,
    ]
    crash_log(f"keprompt ARGV  {section.id} — content len={len(content)}")

    try:
        crash_log(f"keprompt SPAWN {section.id} — calling subprocess.run")
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(keprompt_dir),
        )
        crash_log(f"keprompt DONE  {section.id} — rc={result.returncode} stdout={len(result.stdout)}b stderr={len(result.stderr)}b")
        if result.returncode != 0:
            crash_log(f"keprompt FAIL  {section.id} — stderr: {result.stderr[:200]}")
            return fallback

        crash_log(f"keprompt PARSE {section.id} — parsing JSON response")
        output = json.loads(result.stdout)
        ai_response = output.get("ai_response", "")

        qs = [q.strip() for q in ai_response.splitlines() if q.strip()]
        qs = [re.sub(r'^\d+[\.\)]\s*', '', q) for q in qs]
        qs = [q for q in qs if q and len(q) > 10]

        crash_log(f"keprompt OK    {section.id} — {len(qs)} questions")
        return qs or fallback

    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, OSError) as exc:
        crash_log(f"keprompt EXCEPT {section.id} — {type(exc).__name__}: {exc}")
        return fallback


# ---------------------------------------------------------------------------
# Stage 5: Pre-format one section's search_entry / read_entry
# ---------------------------------------------------------------------------

def build_section_entries(section: Section, questions: list) -> tuple:
    """Build (search_entry, read_entry) markdown for one section.

    Format is the QI/RA contract — see docs/qi-ra-interface.md.
    """
    # search_entry: breadcrumb + question bullets + excerpt (no h2 heading;
    # the runtime adds the heading at query time with the match distance).
    search_parts = [f"> {section.breadcrumb}"]
    for q in questions:
        search_parts.append(f"- *{q}*")
    search_parts.append("")
    excerpt = section.content_md[:200].strip() if section.content_md else section.title
    if len(excerpt) >= 200 and " " in excerpt:
        excerpt = excerpt[:excerpt.rfind(" ")] + "..."
    search_parts.append(excerpt)
    search_entry = "\n".join(search_parts)

    # read_entry: h1 heading + breadcrumb + full content + subsections list.
    read_parts = [f"# {section.id} {section.title}"]
    read_parts.append(f"> {section.breadcrumb}")
    read_parts.append("")
    if section.content_md:
        read_parts.append(section.content_md)
    if section.children:
        read_parts.append("")
        read_parts.append("## Subsections")
        for child in section.children:
            read_parts.append(f"- {child.id} {child.title}")
    read_entry = "\n".join(read_parts)

    return search_entry, read_entry


# ---------------------------------------------------------------------------
# Stage 6: Storage setup, per-section worker, and finalisation
# ---------------------------------------------------------------------------

def setup_output(output_dir: Path, *, fresh: bool = False) -> tuple:
    """Create (or reopen) the output dir + SQLite DB/table + ChromaDB collection.

    Returns (conn, collection, db_path, chroma_path). The connection is opened
    with check_same_thread=False so the worker pool can share it under the
    db_lock; ChromaDB writes also go through the same lock.

    If *fresh* is True, wipe both the DB and ChromaDB directory.
    Otherwise reuse existing SQLite data (resume mode).  ChromaDB is always
    rebuilt from SQLite on resume because it has no WAL and can corrupt on
    unclean shutdown.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / f"{CORPUS}.db"
    chroma_path = output_dir / "chroma"

    if fresh:
        if db_path.exists():
            db_path.unlink()
    # Always wipe chroma — it can't survive unclean shutdowns.
    # It gets rebuilt from SQLite below.
    if chroma_path.exists():
        shutil.rmtree(chroma_path)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            search_entry TEXT NOT NULL,
            read_entry TEXT NOT NULL
        )
    """)
    conn.commit()

    client = chromadb.PersistentClient(path=str(chroma_path))
    ef = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    collection = client.create_collection("questions", embedding_function=ef)

    return conn, collection, db_path, chroma_path


def rebuild_chroma_from_db(conn: sqlite3.Connection, collection) -> int:
    """Re-index existing SQLite sections into a fresh ChromaDB collection.

    Extracts questions from search_entry (lines matching '- *...*') and adds
    them to ChromaDB.  Returns the next doc_id to use.
    """
    import re
    rows = conn.execute("SELECT id, search_entry FROM sections").fetchall()
    if not rows:
        return 0
    doc_id = 0
    question_re = re.compile(r"^- \*(.+)\*$")
    for section_id, search_entry in rows:
        questions = []
        for line in search_entry.split("\n"):
            m = question_re.match(line)
            if m:
                questions.append(m.group(1))
        if questions:
            ids = [f"q{doc_id + i}" for i in range(len(questions))]
            collection.add(
                documents=questions,
                metadatas=[{"section_id": section_id}] * len(questions),
                ids=ids,
            )
            doc_id += len(questions)
    print(f"  Rebuilt ChromaDB: {doc_id} questions from {len(rows)} existing sections")
    return doc_id


def write_corpus_md(output_dir: Path):
    """Write corpus.md (corpus identity for `qira --initialize`)."""
    corpus_md = output_dir / "corpus.md"
    corpus_md.write_text(f"""## Name
EU AI Act

## Description
Regulation (EU) 2024/1689 — the EU Artificial Intelligence Act. Full text including 180 recitals, 113 articles across 13 chapters, and 13 annexes. Covers prohibited AI practices, classification and obligations for high-risk AI systems, transparency rules, general-purpose AI models, governance, market surveillance, and penalties. Source: EUR-Lex (CELEX 32024R1689), Formex 4 XML, CC BY 4.0.

## Embedding
sentence-transformers/all-MiniLM-L6-v2 (PyTorch)

## Example
User asks: "Is using AI to score job applicants a high-risk activity under the EU AI Act?"

1. Do I know enough to answer? No — I need to confirm whether recruitment AI is in the high-risk list, and what obligations apply.
   qira_search(corpus="{CORPUS}", question="Are AI systems for recruitment classified as high-risk?")

2. Browse results. The strongest match cites Annex III. Read it.
   qira_read(section_id="{CORPUS}:17")

3. Annex III lists employment as a high-risk area. Now find the obligations that apply.
   qira_search(corpus="{CORPUS}", question="What are the obligations for providers of high-risk AI systems?")

4. Read the relevant article(s) — e.g. Article 9 (risk management) or Article 16 (provider obligations).
   qira_read(section_id="{CORPUS}:4.2.1")

5. Do I know enough to answer? Yes — answer the user with article citations.
""", encoding="utf-8")


def process_section(
    section: Section,
    keprompt_dir: Path,
    conn: sqlite3.Connection,
    collection,
    index: int,
    total: int,
    doc_id_counter: list,
    skip_questions: bool,
    write_lock: threading.Lock,
) -> int:
    """Process one section: keprompt → build entries → persist.

    The keprompt call runs outside the lock (network-bound).
    SQLite/ChromaDB writes are serialized via write_lock.
    """
    tag = f"[{index}/{total}] {section.id} {section.title}"

    # 1. Question generation (no lock needed — subprocess + network I/O)
    if skip_questions:
        crash_log(f"SECTION {section.id} — skip-questions")
        print(f"  {tag} — skip-questions (stub)", flush=True)
        questions = [f"What is {section.title}?"]
    else:
        crash_log(f"SECTION {section.id} — starting keprompt call")
        print(f"  {tag} — calling keprompt...", flush=True)
        t0 = time.time()
        questions = call_keprompt(section, keprompt_dir)
        elapsed = time.time() - t0
        crash_log(f"SECTION {section.id} — keprompt returned ({elapsed:.1f}s, {len(questions)} questions)")
        print(f"  {tag} — keprompt done ({elapsed:.1f}s, {len(questions)} questions)", flush=True)

    # 2. Pre-format (no lock needed — pure computation on local data)
    crash_log(f"SECTION {section.id} — formatting entries")
    print(f"  {tag} — formatting entries...", flush=True)
    search_entry, read_entry = build_section_entries(section, questions)

    # 3+4. Persist under lock (SQLite + ChromaDB + counter)
    with write_lock:
        crash_log(f"SECTION {section.id} — writing SQLite")
        print(f"  {tag} — writing SQLite...", flush=True)
        conn.execute(
            "INSERT INTO sections (id, title, search_entry, read_entry) VALUES (?, ?, ?, ?)",
            (section.id, section.title, search_entry, read_entry),
        )
        conn.commit()

        crash_log(f"SECTION {section.id} — writing ChromaDB ({len(questions)} vectors)")
        print(f"  {tag} — writing ChromaDB ({len(questions)} vectors)...", flush=True)
        ids = []
        for _ in questions:
            ids.append(f"q{doc_id_counter[0]}")
            doc_id_counter[0] += 1
        collection.add(
            documents=list(questions),
            metadatas=[{"section_id": section.id}] * len(questions),
            ids=ids,
        )

    crash_log(f"SECTION {section.id} — DONE")
    print(f"  {tag} — DONE", flush=True)
    return len(questions)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def count_sections(section: Section) -> int:
    count = 1
    for child in section.children:
        count += count_sections(child)
    return count


def print_tree(section: Section, indent: int = 0):
    prefix = "  " * indent
    kind = f" [{section.kind}]" if section.kind else ""
    content_len = len(section.content_md) if section.content_md else 0
    print(f"{prefix}{section.id}  {section.title}{kind}  ({content_len} chars)")
    for child in section.children:
        print_tree(child, indent + 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build QIRA corpus from EU AI Act Formex 4 XML")
    parser.add_argument("--source", required=True,
                        help="Directory containing the extracted Formex files "
                             "(L_202401689EN.doc.fmx.xml + main act + 13 annexes)")
    parser.add_argument("--output", required=True, help="Output corpus directory")
    parser.add_argument("--skip-questions", action="store_true",
                        help="Skip LLM question generation (use fallback questions)")
    parser.add_argument("--parallel", type=int, default=10,
                        help="Number of parallel workers (default: 10)")
    parser.add_argument("--fresh", action="store_true",
                        help="Wipe existing corpus DB and start from scratch "
                             "(default: resume — skip sections already in DB)")
    parser.add_argument("--print-tree", action="store_true",
                        help="Print the parsed section tree and exit (no DB writes)")
    parser.add_argument("--limit", type=int, default=None,
                        help="For testing: only process the first N top-level sections "
                             "(top-level order is: Recitals, Chapter I..XIII, Annex I..XIII)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the cost-confirmation prompt (for non-interactive runs)")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        print(f"Error: {source} is not a directory", file=sys.stderr)
        sys.exit(1)

    doc_path = source / "L_202401689EN.doc.fmx.xml"
    if not doc_path.exists():
        print(f"Error: manifest not found at {doc_path}", file=sys.stderr)
        print("       Did you extract the Formex ZIP into --source?", file=sys.stderr)
        sys.exit(1)

    # Step 1: Read the manifest
    print(f"Reading manifest: {doc_path.name}")
    main_file, annex_files = parse_manifest(doc_path)
    print(f"  Main act: {main_file}")
    print(f"  Annex files: {len(annex_files)}")

    # Step 2: Parse the main act
    main_path = source / main_file
    if not main_path.exists():
        print(f"Error: main act file not found at {main_path}", file=sys.stderr)
        sys.exit(1)
    print(f"\nParsing main act: {main_file}")
    recitals_root, chapters = parse_main_act(main_path)
    print(f"  Recitals: {len(recitals_root.children)}")
    print(f"  Top-level chapters: {len(chapters)}")

    # Step 3: Parse annexes
    print(f"\nParsing {len(annex_files)} annexes...")
    annex_sections = []
    for idx, annex_file in enumerate(annex_files, 1):
        annex_path = source / annex_file
        if not annex_path.exists():
            print(f"  Warning: {annex_path} not found, skipping")
            continue
        annex = parse_annex(annex_path, idx)
        annex_sections.append(annex)
        print(f"  Annex {ROMAN[idx]}: {annex.title}")

    # Step 4: Assemble top-level sections in publication order
    top_sections = [recitals_root] + chapters + annex_sections

    if args.limit is not None and args.limit > 0:
        top_sections = top_sections[:args.limit]
        print(f"\n--limit {args.limit}: keeping {len(top_sections)} top-level section(s) for this run")

    # Step 5: Organize — assign IDs and breadcrumbs
    print("\nOrganizing sections...")
    all_sections = organize(top_sections)
    print(f"Total sections: {len(all_sections)}")

    if args.print_tree:
        print()
        for top in top_sections:
            print_tree(top)
        return

    # Step 6: Rewrite cross-references
    print("\nRewriting cross-references...")
    maps = build_xref_maps(all_sections)
    rewrite_xrefs(all_sections, maps)
    print(f"  Article xref targets: {len(maps['article'])}")
    print(f"  Recital xref targets: {len(maps['recital'])}")
    print(f"  Annex xref targets:   {len(maps['annex'])}")
    print(f"  Chapter xref targets: {len(maps['chapter'])}")

    # Step 7: Locate the keprompt project dir (for prompt lookup) and confirm cost
    if args.skip_questions:
        keprompt_dir = Path(__file__).resolve().parent
    else:
        keprompt_dir = Path(__file__).resolve().parent
        if not (keprompt_dir / "prompts").is_dir():
            keprompt_dir = Path.cwd()
        if not (keprompt_dir / "prompts").is_dir():
            print("Error: cannot find prompts/ directory. "
                  "Run from the keprompt project dir, or place generate_questions.prompt "
                  "into a prompts/ subdir of the example.", file=sys.stderr)
            sys.exit(1)

        workers = args.parallel
        print(f"\nReady to process {len(all_sections)} sections.")
        print(f"  Mode:           {'sequential' if workers <= 1 else f'{workers} parallel workers'}")
        print(f"  Embedding:      sentence-transformers/all-MiniLM-L6-v2 (PyTorch)")
        print(f"  Model:          cerebras/gpt-oss-120b (per generate_questions.prompt)")
        print(f"  Estimated cost: ~${len(all_sections) * 0.0007:.2f}")
        if args.yes:
            print("  (--yes: skipping confirmation)")
        else:
            response = input("Continue? [y/N] ")
            if response.lower() != "y":
                print("Aborted.")
                sys.exit(0)

    # Step 8: Set up output storage (DB + Chroma collection live for the worker pool)
    output = Path(args.output)
    print(f"\nSetting up output: {output}")

    # Open crash log (fsynced to disk on every write — survives hard resets)
    crash_log_open(output.parent / "crash.log")
    crash_log(f"sections={len(all_sections)} skip_questions={args.skip_questions}")

    conn, collection, db_path, chroma_path = setup_output(output, fresh=args.fresh)

    # Resume: rebuild chroma from SQLite, skip sections already in the DB
    existing_ids = set()
    existing_q_count = 0
    if not args.fresh:
        cursor = conn.execute("SELECT id FROM sections")
        existing_ids = {row[0] for row in cursor.fetchall()}
        if existing_ids:
            print(f"  Resuming: {len(existing_ids)} sections already in DB, skipping them")
            existing_q_count = rebuild_chroma_from_db(conn, collection)
    remaining = [s for s in all_sections if s.id not in existing_ids]

    # Step 9: Process sections
    workers = args.parallel if not args.skip_questions else 1
    mode = "sequentially" if workers <= 1 else f"with {workers} workers"
    print(f"\nProcessing {len(remaining)} sections {mode} "
          f"({len(all_sections) - len(remaining)} already done)...")
    doc_id_counter = [existing_q_count]
    write_lock = threading.Lock()
    total = len(remaining)

    errors = 0
    if workers <= 1:
        for i, section in enumerate(remaining, 1):
            try:
                process_section(
                    section, keprompt_dir, conn, collection,
                    i, total, doc_id_counter,
                    args.skip_questions, write_lock,
                )
            except Exception as e:
                print(f"  ERROR on {section.id} {section.title}: {e}",
                      file=sys.stderr, flush=True)
                errors += 1
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    process_section,
                    section, keprompt_dir, conn, collection,
                    i, total, doc_id_counter,
                    args.skip_questions, write_lock,
                ): section
                for i, section in enumerate(remaining, 1)
            }
            for future in as_completed(futures):
                section = futures[future]
                try:
                    future.result()
                except Exception as e:
                    print(f"  ERROR on {section.id} {section.title}: {e}",
                          file=sys.stderr, flush=True)
                    errors += 1

    # Step 10: Finalise — close DB, write corpus.md, summary
    conn.close()
    print(f"SQLite: {db_path}")
    print(f"ChromaDB: {chroma_path}")

    write_corpus_md(output)
    print(f"Corpus identity: {output / 'corpus.md'}")

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"Sections:  {len(all_sections)}")
    print(f"Questions: {doc_id_counter[0]}")
    print(f"Errors:    {errors}")
    print(f"Output:    {output}")
    print(f"\nTest with:")
    print(f'  echo \'{{"corpus":"{CORPUS}","question":"Which AI practices are prohibited?"}}\' '
          f'| ../../runtime/qira qira_search')


if __name__ == "__main__":
    main()
