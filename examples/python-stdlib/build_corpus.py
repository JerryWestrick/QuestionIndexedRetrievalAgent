#!/usr/bin/env python3
"""Build a QIRA corpus from Python standard library RST documentation.

Steps 1-5: Parse RST → markdown, organize sections, rewrite cross-references.
Steps 6-8: Generate questions (LLM), pre-format, vectorize, store. (TODO)

Usage:
    python build_corpus.py --source /path/to/cpython/Doc/library [--modules json,datetime,...]
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import chromadb


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

CORPUS = "python-stdlib"

@dataclass
class Section:
    """A section extracted from the RST docs."""
    id: str = ""                    # e.g. python-stdlib:1.2.3
    title: str = ""                 # e.g. json.dumps
    breadcrumb: str = ""            # e.g. Python Standard Library > json > json.dumps
    content_md: str = ""            # markdown content (body only, no heading)
    children: list = field(default_factory=list)
    level: int = 0                  # depth in hierarchy
    source_file: str = ""           # which .rst file this came from
    directive_type: str = ""        # function, class, method, exception, data, or ""


# ---------------------------------------------------------------------------
# RST heading detection
# ---------------------------------------------------------------------------

# RST heading underline characters, in typical Python docs order
UNDERLINE_CHARS = set("=-~^\"'`")

def is_underline(line: str) -> bool:
    """Check if a line is an RST heading underline."""
    stripped = line.rstrip()
    return (len(stripped) >= 3 and
            len(set(stripped)) == 1 and
            stripped[0] in UNDERLINE_CHARS)


def heading_rank(underline_char: str, seen_chars: list) -> int:
    """Determine heading level based on underline character order of appearance."""
    if underline_char not in seen_chars:
        seen_chars.append(underline_char)
    return seen_chars.index(underline_char)


# ---------------------------------------------------------------------------
# RST directive detection
# ---------------------------------------------------------------------------

DIRECTIVE_PATTERN = re.compile(
    r'^\.\.\s+(function|class|classmethod|staticmethod|method|exception|data|attribute|decorator)'
    r'::\s*(.*)',
    re.MULTILINE
)


def is_directive(line: str) -> tuple:
    """Check if a line starts an API directive. Returns (type, signature) or None."""
    m = DIRECTIVE_PATTERN.match(line.strip())
    if m:
        dtype = m.group(1)
        sig = m.group(2).strip()
        # Normalize classmethod/staticmethod to method
        if dtype in ("classmethod", "staticmethod"):
            dtype = "method"
        return dtype, sig
    return None


# ---------------------------------------------------------------------------
# Step 1-2: Parse RST → Section tree with markdown content
# ---------------------------------------------------------------------------

def parse_rst_file(filepath: Path) -> Section:
    """Parse an RST file into a Section tree with markdown content."""
    lines = filepath.read_text(encoding="utf-8").splitlines()
    source_name = filepath.stem

    # Track heading underline character order for level detection
    seen_chars = []

    # First pass: find module title (first heading)
    module_title = source_name
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and is_underline(lines[i + 1]):
            title = lines[i].strip()
            # Clean RST module title: :mod:`!json` --- desc → json — desc
            title = re.sub(r':mod:`!?([^`]+)`', r'\1', title)
            title = title.replace('---', '—').strip()
            module_title = title
            heading_rank(lines[i + 1].strip()[0], seen_chars)
            i += 2
            break
        i += 1

    root = Section(
        title=module_title,
        source_file=source_name,
        level=0
    )

    # Second pass: extract all sections and directives
    _parse_block(lines, i, root, seen_chars, source_name)

    return root


def _parse_block(lines: list, start: int, parent: Section, seen_chars: list,
                 source_name: str) -> int:
    """Parse lines into the parent section, creating children for headings and directives."""
    content_lines = []
    i = start

    while i < len(lines):
        line = lines[i]

        # Check for heading (next line is underline)
        if (i + 1 < len(lines) and
            is_underline(lines[i + 1]) and
            line.strip() and
            not line.startswith(" ")):

            # Flush content to parent
            if content_lines:
                md = _lines_to_markdown(content_lines)
                if md:
                    parent.content_md = (parent.content_md + "\n\n" + md).strip()
                content_lines = []

            title = line.strip()
            title = re.sub(r':mod:`!?([^`]+)`', r'\1', title)
            title = title.replace('---', '—').strip()
            rank = heading_rank(lines[i + 1].strip()[0], seen_chars)

            # If this heading is at a higher or equal level to parent,
            # we've exited the parent's scope — unwind
            if rank <= parent.level and parent.level > 0:
                return i  # don't consume this heading

            child = Section(
                title=title,
                source_file=source_name,
                level=rank
            )
            parent.children.append(child)

            i += 2  # skip title + underline

            # Recurse into the child section
            i = _parse_block(lines, i, child, seen_chars, source_name)
            continue

        # Check for API directive
        directive = is_directive(line)
        if directive and not line.startswith("   "):
            dtype, sig = directive

            # Flush content
            if content_lines:
                md = _lines_to_markdown(content_lines)
                if md:
                    parent.content_md = (parent.content_md + "\n\n" + md).strip()
                content_lines = []

            # Clean up signature
            name = sig.split("(")[0].strip()
            # Handle continuation lines for long signatures
            full_sig = sig
            while full_sig.rstrip().endswith("\\") and i + 1 < len(lines):
                i += 1
                full_sig = full_sig.rstrip("\\").rstrip() + " " + lines[i].strip()
            full_sig = " ".join(full_sig.split())  # normalize whitespace

            child = Section(
                title=name,
                source_file=source_name,
                level=parent.level + 1,
                directive_type=dtype
            )

            i += 1

            # Collect indented body
            body_lines = []
            while i < len(lines):
                if lines[i].strip() == "":
                    body_lines.append("")
                    i += 1
                elif lines[i].startswith("   "):
                    body_lines.append(lines[i])
                    i += 1
                else:
                    break

            # Convert body to markdown
            body_md = _directive_body_to_markdown(full_sig, body_lines, dtype)
            child.content_md = body_md

            # Check for nested directives in the body (methods inside classes)
            _extract_nested_directives(body_lines, child, source_name)

            parent.children.append(child)
            continue

        # Skip RST directives we don't care about (.. module::, .. note::, etc.)
        if line.strip().startswith(".. ") and "::" in line:
            non_api = is_directive(line) is None
            if non_api:
                # Skip the directive and its indented body
                i += 1
                # Collect body for conversion (notes, warnings are useful content)
                directive_match = re.match(r'\.\.\s+(\w+)::', line.strip())
                directive_name = directive_match.group(1) if directive_match else ""

                dir_body = []
                while i < len(lines):
                    if lines[i].strip() == "":
                        dir_body.append("")
                        i += 1
                    elif lines[i].startswith("   "):
                        dir_body.append(lines[i].strip())
                        i += 1
                    else:
                        break

                # Include notes and warnings in content
                if directive_name in ("note", "warning", "important"):
                    body_text = "\n".join(l for l in dir_body if l).strip()
                    if body_text:
                        label = directive_name.capitalize()
                        content_lines.append(f"> **{label}:** {body_text}")
                        content_lines.append("")
                elif directive_name in ("deprecated", "versionadded", "versionchanged"):
                    body_text = " ".join(l for l in dir_body if l).strip()
                    if body_text:
                        content_lines.append(f"*{directive_name.capitalize()}: {body_text}*")
                        content_lines.append("")
                continue

        # Regular content line
        content_lines.append(line)
        i += 1

    # Flush remaining content
    if content_lines:
        md = _lines_to_markdown(content_lines)
        if md:
            parent.content_md = (parent.content_md + "\n\n" + md).strip()

    return i


def _extract_nested_directives(body_lines: list, parent: Section, source_name: str):
    """Extract nested API directives (methods inside classes) from a directive body."""
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        stripped = line.strip()
        directive = is_directive(stripped)
        if directive:
            dtype, sig = directive
            name = sig.split("(")[0].strip()

            full_sig = sig
            while full_sig.rstrip().endswith("\\") and i + 1 < len(body_lines):
                i += 1
                full_sig = full_sig.rstrip("\\").rstrip() + " " + body_lines[i].strip()
            full_sig = " ".join(full_sig.split())

            child = Section(
                title=name,
                source_file=source_name,
                level=parent.level + 1,
                directive_type=dtype
            )

            i += 1
            # Collect nested body (extra indentation level)
            nested_body = []
            while i < len(body_lines):
                if body_lines[i].strip() == "":
                    nested_body.append("")
                    i += 1
                elif len(body_lines[i]) > len(line) - len(stripped) + 3:
                    # More indented than the directive
                    nested_body.append(body_lines[i])
                    i += 1
                else:
                    break

            child.content_md = _directive_body_to_markdown(full_sig, nested_body, dtype)
            parent.children.append(child)
        else:
            i += 1


def _directive_body_to_markdown(signature: str, body_lines: list, dtype: str) -> str:
    """Convert a directive's signature and body to markdown."""
    parts = []

    # Include signature as code if it has parameters
    if "(" in signature:
        parts.append(f"`{signature}`")
        parts.append("")

    # Strip common indentation and convert body
    stripped = _dedent(body_lines)
    md = _lines_to_markdown(stripped)
    if md:
        parts.append(md)

    return "\n".join(parts)


def _dedent(lines: list) -> list:
    """Remove common leading whitespace from lines."""
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return lines
    min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
    return [l[min_indent:] if l.strip() else "" for l in lines]


# ---------------------------------------------------------------------------
# RST → Markdown conversion (line-based)
# ---------------------------------------------------------------------------

def _lines_to_markdown(lines: list) -> str:
    """Convert RST-ish lines to clean markdown."""
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Skip RST-specific markers
        if line.strip().startswith(".. ") and "::" in line.strip():
            # Skip directive and its body
            i += 1
            while i < len(lines) and (lines[i].startswith("   ") or not lines[i].strip()):
                i += 1
            continue

        # Literal block (line ending with ::)
        if line.rstrip().endswith("::") and not line.strip().startswith(".."):
            # Add the text before ::
            prefix = line.rstrip()[:-2].rstrip()
            if prefix:
                result.append(_clean_rst_inline(prefix) + ":")
            result.append("")
            result.append("```python")
            i += 1
            # Skip blank line after ::
            if i < len(lines) and not lines[i].strip():
                i += 1
            # Collect indented code
            while i < len(lines) and (lines[i].startswith("   ") or not lines[i].strip()):
                if lines[i].strip():
                    result.append(lines[i].rstrip())
                else:
                    result.append("")
                i += 1
            # Remove trailing blanks in code block
            while result and result[-1] == "":
                result.pop()
            result.append("```")
            result.append("")
            continue

        # Field list (:param ...:)
        if re.match(r'\s*:param\s', line):
            m = re.match(r'\s*:param\s+(?:(\w+)\s+)?(\w+):\s*(.*)', line)
            if m:
                ptype = m.group(1) or ""
                pname = m.group(2)
                pdesc = m.group(3)
                # Collect continuation lines
                i += 1
                while i < len(lines) and lines[i].startswith("      "):
                    pdesc += " " + lines[i].strip()
                    i += 1
                pdesc = _clean_rst_inline(pdesc)
                result.append(f"- **{pname}** — {pdesc}")
                continue

        if re.match(r'\s*:type\s', line):
            i += 1  # skip type-only fields
            continue

        if re.match(r'\s*:returns?:', line):
            m = re.match(r'\s*:returns?:\s*(.*)', line)
            if m:
                desc = m.group(1)
                i += 1
                while i < len(lines) and lines[i].startswith("      "):
                    desc += " " + lines[i].strip()
                    i += 1
                result.append(f"- **Returns:** {_clean_rst_inline(desc)}")
                continue

        if re.match(r'\s*:rtype:', line):
            i += 1
            continue

        if re.match(r'\s*:raises?\s', line):
            m = re.match(r'\s*:raises?\s+(\w+):\s*(.*)', line)
            if m:
                exc = m.group(1)
                desc = m.group(2)
                i += 1
                while i < len(lines) and lines[i].startswith("      "):
                    desc += " " + lines[i].strip()
                    i += 1
                result.append(f"- **Raises `{exc}`:** {_clean_rst_inline(desc)}")
                continue

        # Transition (----)
        if re.match(r'^-{4,}$', line.strip()):
            i += 1
            continue

        # Regular line
        result.append(_clean_rst_inline(line.rstrip()))
        i += 1

    text = "\n".join(result)
    # Clean up excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _clean_rst_inline(text: str) -> str:
    """Convert RST inline markup to markdown."""
    # :func:`name` → `name`
    text = re.sub(r':(?:func|class|meth|mod|exc|data|attr|obj|ref|term|const|envvar)'
                  r':`~?!?([^`]+)`', r'`\1`', text)
    # :source:`path` → `path`
    text = re.sub(r':source:`([^`]+)`', r'`\1`', text)
    # :rfc:`1234` → RFC 1234
    text = re.sub(r':rfc:`(\d+)`', r'RFC \1', text)
    # :pep:`123` → PEP 123
    text = re.sub(r':pep:`(\d+)`', r'PEP \1', text)
    # ``code`` → `code`
    text = re.sub(r'``([^`]+)``', r'`\1`', text)
    # *emphasis* stays as-is
    # **strong** stays as-is
    return text


# ---------------------------------------------------------------------------
# Step 4: Organize — assign IDs and breadcrumbs
# ---------------------------------------------------------------------------

def organize(modules: list) -> list:
    """Assign hierarchical IDs and breadcrumbs to all sections."""
    all_sections = []

    for module_idx, module in enumerate(modules, 1):
        module.id = f"{CORPUS}:{module_idx}"
        mod_short = module.title.split("—")[0].strip()
        module.breadcrumb = f"Python Standard Library > {mod_short}"
        all_sections.append(module)
        _assign_ids(module, all_sections)

    return all_sections


def _assign_ids(parent: Section, all_sections: list):
    """Recursively assign IDs and breadcrumbs to children."""
    for child_idx, child in enumerate(parent.children, 1):
        parent_num = parent.id.split(":", 1)[1]
        child.id = f"{CORPUS}:{parent_num}.{child_idx}"

        parent_crumb = parent.breadcrumb
        child_name = child.title.split("—")[0].strip()
        child.breadcrumb = f"{parent_crumb} > {child_name}"

        all_sections.append(child)
        _assign_ids(child, all_sections)


# ---------------------------------------------------------------------------
# Step 5: Rewrite cross-references
# ---------------------------------------------------------------------------

def build_xref_map(all_sections: list) -> dict:
    """Build a map of Python names to QIRA section IDs."""
    xref_map = {}
    for section in all_sections:
        title = section.title.split("—")[0].strip()
        if title:
            xref_map[title] = section.id
    return xref_map


def rewrite_xrefs(all_sections: list, xref_map: dict):
    """Rewrite cross-references in content to QIRA section IDs."""
    for section in all_sections:
        if section.content_md:
            section.content_md = _rewrite_content_xrefs(section.content_md, xref_map)


def _rewrite_content_xrefs(text: str, xref_map: dict) -> str:
    """Replace known names in backticks with QIRA section ID references."""
    def replace_ref(match):
        name = match.group(1)
        clean = name.lstrip("~!")
        if clean in xref_map:
            return f"`{clean}` (see {xref_map[clean]})"
        return match.group(0)
    return re.sub(r'`([^`]+)`', replace_ref, text)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def count_sections(section: Section) -> int:
    """Count total sections in a tree."""
    count = 1
    for child in section.children:
        count += count_sections(child)
    return count


def print_tree(section: Section, indent: int = 0):
    """Print section tree for inspection."""
    prefix = "  " * indent
    dtype = f" [{section.directive_type}]" if section.directive_type else ""
    content_len = len(section.content_md) if section.content_md else 0
    print(f"{prefix}{section.id}  {section.title}{dtype}  ({content_len} chars)")
    for child in section.children:
        print_tree(child, indent + 1)


# ---------------------------------------------------------------------------
# Step 6: Generate questions via keprompt
# ---------------------------------------------------------------------------

def generate_questions(all_sections: list, keprompt_dir: Path) -> dict:
    """Call keprompt to generate questions for each section.

    Returns dict mapping section.id → list of question strings.
    Must be run from the keprompt project directory (where prompts/ lives).
    """
    questions = {}
    total = len(all_sections)
    failed = 0

    # Use a temp file for section content
    tmp_file = keprompt_dir / "tmp_section.md"

    for i, section in enumerate(all_sections, 1):
        content = section.content_md or section.title
        if not content.strip():
            content = section.title

        # Write content to temp file
        tmp_file.write_text(content, encoding="utf-8")

        print(f"  [{i}/{total}] {section.id} {section.title}...", end="", flush=True)

        try:
            result = subprocess.run(
                [
                    "keprompt", "chat", "new",
                    "--prompt", "generate_questions",
                    "--set", "breadcrumb", section.breadcrumb,
                    "--set", "title", section.title,
                    "--set", "section_file", "tmp_section.md",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(keprompt_dir),
            )

            if result.returncode != 0:
                print(f" FAILED: {result.stderr[:100]}")
                failed += 1
                questions[section.id] = [f"What is {section.title}?"]
                continue

            # Parse JSON output
            output = json.loads(result.stdout)
            ai_response = output.get("ai_response", "")

            # Split into individual questions (one per line)
            qs = [q.strip() for q in ai_response.splitlines() if q.strip()]

            # Filter out any non-question lines (preamble, numbering)
            qs = [re.sub(r'^\d+[\.\)]\s*', '', q) for q in qs]  # strip numbering
            qs = [q for q in qs if q and len(q) > 10]  # skip tiny fragments

            if not qs:
                qs = [f"What is {section.title}?"]

            questions[section.id] = qs
            cost = output.get("data", {}).get("metadata", {}).get("total_cost", 0)
            print(f" {len(qs)} questions (${cost:.4f})")

        except subprocess.TimeoutExpired:
            print(" TIMEOUT")
            failed += 1
            questions[section.id] = [f"What is {section.title}?"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f" PARSE ERROR: {e}")
            failed += 1
            questions[section.id] = [f"What is {section.title}?"]

    # Clean up
    if tmp_file.exists():
        tmp_file.unlink()

    print(f"\nQuestion generation complete: {total - failed}/{total} succeeded, {failed} failed")
    total_qs = sum(len(qs) for qs in questions.values())
    print(f"Total questions generated: {total_qs}")

    return questions


# ---------------------------------------------------------------------------
# Step 7: Pre-format markdown entries
# ---------------------------------------------------------------------------

def preformat_entries(all_sections: list, questions: dict) -> list:
    """Build search_entry and read_entry for each section.

    Returns list of dicts ready for SQLite insertion.
    """
    entries = []

    for section in all_sections:
        qs = questions.get(section.id, [])

        # search_entry: body only (RA adds heading with distance at runtime)
        search_parts = [f"> {section.breadcrumb}"]
        for q in qs:
            search_parts.append(f"- *{q}*")
        search_parts.append("")
        # Excerpt: first ~200 chars of content
        excerpt = section.content_md[:200].strip() if section.content_md else section.title
        # Cut at last complete word
        if len(excerpt) >= 200:
            excerpt = excerpt[:excerpt.rfind(" ")] + "..."
        search_parts.append(excerpt)

        search_entry = "\n".join(search_parts)

        # read_entry: full content served verbatim by qira_read
        read_parts = [f"# {section.id} {section.title}"]
        read_parts.append(f"> {section.breadcrumb}")
        read_parts.append("")
        if section.content_md:
            read_parts.append(section.content_md)

        # Subsections list (direct children only)
        if section.children:
            read_parts.append("")
            read_parts.append("## Subsections")
            for child in section.children:
                read_parts.append(f"- {child.id} {child.title}")

        read_entry = "\n".join(read_parts)

        entries.append({
            "id": section.id,
            "title": section.title,
            "search_entry": search_entry,
            "read_entry": read_entry,
            "questions": qs,
        })

    return entries


# ---------------------------------------------------------------------------
# Step 8: Vectorize and store
# ---------------------------------------------------------------------------

def store_corpus(entries: list, output_dir: Path):
    """Write SQLite database and ChromaDB vector index."""
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / f"{CORPUS}.db"
    chroma_path = output_dir / "chroma"

    # Clean previous build
    if db_path.exists():
        db_path.unlink()
    if chroma_path.exists():
        shutil.rmtree(chroma_path)

    # SQLite
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE sections (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            search_entry TEXT NOT NULL,
            read_entry TEXT NOT NULL
        )
    """)

    for entry in entries:
        conn.execute(
            "INSERT INTO sections (id, title, search_entry, read_entry) VALUES (?, ?, ?, ?)",
            (entry["id"], entry["title"], entry["search_entry"], entry["read_entry"])
        )
    conn.commit()
    conn.close()
    print(f"SQLite: {db_path} ({len(entries)} sections)")

    # ChromaDB
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.create_collection("questions")

    doc_id = 0
    for entry in entries:
        for q in entry["questions"]:
            collection.add(
                documents=[q],
                metadatas=[{"section_id": entry["id"]}],
                ids=[f"q{doc_id}"]
            )
            doc_id += 1

    print(f"ChromaDB: {chroma_path} ({doc_id} questions)")

    # corpus.md
    corpus_md = output_dir / "corpus.md"
    corpus_md.write_text(f"""## Name
Python Standard Library

## Description
Python standard library module documentation including functions, classes, methods, parameters, and usage examples.

## Embedding
chromadb/default (all-MiniLM-L6-v2)

## Example
User asks: "How do I pretty-print a JSON string in Python?"

1. Do I know enough to answer? No — I need the specific function and parameters.
   qira_search(corpus="{CORPUS}", question="How to format JSON output with indentation?")

2. Browse results. Read the most relevant hit.
   qira_read(section_id="{CORPUS}:1.1.2")

3. Do I know enough to answer? Yes — json.dumps() with indent parameter. Answer the user.
""", encoding="utf-8")
    print(f"Corpus identity: {corpus_md}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

DEFAULT_MODULES = [
    "json", "datetime", "pathlib", "re", "os.path",
    "collections", "itertools", "argparse", "csv", "logging"
]


def main():
    parser = argparse.ArgumentParser(description="Build QIRA corpus from Python stdlib RST docs")
    parser.add_argument("--source", required=True, help="Path to CPython Doc/library/ directory")
    parser.add_argument("--modules", default=None,
                        help="Comma-separated module names (default: 10 common modules)")
    parser.add_argument("--output", required=True, help="Output corpus directory")
    parser.add_argument("--skip-questions", action="store_true",
                        help="Skip question generation (use fallback questions)")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.is_dir():
        print(f"Error: {source} is not a directory", file=sys.stderr)
        sys.exit(1)

    output = Path(args.output)
    module_names = args.modules.split(",") if args.modules else DEFAULT_MODULES

    # Steps 1-3: Parse RST → section trees with markdown content
    print(f"Parsing {len(module_names)} modules from {source}...")
    modules = []
    for name in module_names:
        rst_file = source / f"{name}.rst"
        if not rst_file.exists():
            print(f"  Warning: {rst_file} not found, skipping")
            continue
        print(f"  Parsing {name}...", end="")
        root = parse_rst_file(rst_file)
        n = count_sections(root)
        print(f" {n} sections")
        modules.append(root)

    if not modules:
        print("Error: no modules parsed", file=sys.stderr)
        sys.exit(1)

    # Step 4: Organize — assign IDs and breadcrumbs
    print("\nOrganizing sections...")
    all_sections = organize(modules)
    print(f"Total sections: {len(all_sections)}")

    # Step 5: Rewrite cross-references
    print("\nRewriting cross-references...")
    xref_map = build_xref_map(all_sections)
    rewrite_xrefs(all_sections, xref_map)
    print(f"Cross-reference map: {len(xref_map)} entries")

    # Step 6: Generate questions
    if args.skip_questions:
        print("\nSkipping question generation (--skip-questions)")
        questions = {s.id: [f"What is {s.title}?"] for s in all_sections}
    else:
        # keprompt must be run from its project directory
        keprompt_dir = Path(__file__).resolve().parent
        if not (keprompt_dir / "prompts").is_dir():
            # Try cwd
            keprompt_dir = Path.cwd()
        if not (keprompt_dir / "prompts").is_dir():
            print("Error: cannot find prompts/ directory. Run from the keprompt project dir.",
                  file=sys.stderr)
            sys.exit(1)

        print(f"\nReady to generate questions for {len(all_sections)} sections.")
        print(f"This will make {len(all_sections)} LLM calls to cerebras/gpt-oss-120b.")
        print(f"Estimated cost: ~${len(all_sections) * 0.0007:.2f}")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            sys.exit(0)

        print(f"\nGenerating questions via keprompt...")
        questions = generate_questions(all_sections, keprompt_dir)

    # Step 7: Pre-format entries
    print("\nPre-formatting entries...")
    entries = preformat_entries(all_sections, questions)
    print(f"Formatted {len(entries)} entries")

    # Step 8: Store
    print(f"\nStoring corpus in {output}...")
    store_corpus(entries, output)

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    total_qs = sum(len(e["questions"]) for e in entries)
    print(f"Sections:  {len(entries)}")
    print(f"Questions: {total_qs}")
    print(f"Output:    {output}")
    print(f"\nTest with:")
    print(f'  echo \'{{"corpus":"{CORPUS}","question":"How do I pretty-print JSON?"}}\' | python src/qira qira_search')


if __name__ == "__main__":
    main()
