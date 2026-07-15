"""rule_parser.py — Slice rule extraction + entry-symbol map.

Two responsibilities:

  * ``extract_rules_from_slice`` / ``rules_for_file`` — parse the
    "代码生成约束 / 生成规则" sections of slice .md files into structured
    MUST/MUST NOT rules (still used for documentation/inspection).
  * ``COMPOSABLE_TO_SLICE`` / ``entry_symbols_for_slice`` — the slice ↔ entry
    symbol map. The structural gate (``tools/apply.py`` default CLI)
    uses this to check that a slice's entry composable/component is wired up
    in the generated code. (The gate no longer greps each rule's backtick
    patterns — that produced false negatives on symbols living inside string
    literals; see apply.py's module docstring.)

Each rule has:
  - type: "MUST" or "MUST NOT"
  - text: The full rule description
  - patterns: List of grep-able code patterns extracted from backtick segments
  - verify_hint: The "Verify:" instruction if present
  - source_file: Path to the slice .md file
  - slice_id: e.g. "conference/login-auth"
"""
import re
from pathlib import Path
from typing import Optional


# Match numbered MUST/MUST NOT rules in slice files.
# Format: "N. **text** — explanation\n   **Verify**: check"
_RULE_BLOCK_RE = re.compile(
    r'^\d+\.\s+\*\*(.*?)\*\*\s*[—–-]\s*(.*?)$',
    re.MULTILINE
)

# Match the section headers for MUST / MUST NOT
_MUST_SECTION_RE = re.compile(
    r'^#{2,4}\s+MUST(?:\s+NOT)?\s*[（(].*?[）)]',
    re.MULTILINE
)

# Extract code patterns from backtick-quoted segments
_BACKTICK_RE = re.compile(r'`([^`]+)`')

# Match "**Verify**:" lines
_VERIFY_RE = re.compile(r'\*\*Verify\*\*:\s*(.+?)$', re.MULTILINE)


# Entry composable / component / value → slice_id.
#
# This is the single source for "what is this slice's entry symbol". It is
# consumed in two places:
#   * rules_for_file() — to decide which slice's rules apply to a file.
#   * the apply gate (apply.py) — to check that a slice's entry symbol
#     actually appears in the generated code.
#
# Entry symbols are stable code identifiers (composables / components / exported
# values), never string literals — which is what makes the entry-presence check
# immune to the comment/string-literal stripping false-negative that the old
# MUST-symbol grep suffered from.
COMPOSABLE_TO_SLICE = {
    'useLoginState': 'conference/login-auth',
    'useRoomState': 'conference/room-lifecycle',
    'useDeviceState': 'conference/device-control',
    'useRoomParticipantState': 'conference/participant-list',
    'RoomView': 'conference/video-layout',
    'RoomLayoutTemplate': 'conference/video-layout',
    'networkInfo': 'conference/network-quality',
    'NetworkQuality': 'conference/network-quality',
    'useConversationListState': 'conference/room-chat',
    'useMessageListState': 'conference/room-chat',
    'useMessageInputState': 'conference/room-chat',
    'setActiveConversation': 'conference/room-chat',
    'startScreenShare': 'conference/screen-share',
    'stopScreenShare': 'conference/screen-share',
}


def entry_symbols_for_slice(slice_id: str) -> list:
    """Return the known entry symbols for a slice (inverse of COMPOSABLE_TO_SLICE).

    Empty list means the slice has no registered entry symbol; callers should
    treat that as "cannot check mechanically" rather than a failure.
    """
    return [sym for sym, sid in COMPOSABLE_TO_SLICE.items() if sid == slice_id]


def extract_rules_from_slice(md_path: Path) -> list:
    """Parse a slice markdown file for MUST/MUST NOT rules.

    Looks for the "代码生成约束" / "生成规则" section and extracts
    structured rules from the MUST/MUST NOT subsections.

    Returns list of rule dicts.
    """
    if not md_path.exists():
        return []

    content = md_path.read_text(encoding='utf-8')

    # Find the code generation constraints section
    constraint_start = _find_constraint_section(content)
    if constraint_start is None:
        return []

    constraint_text = content[constraint_start:]
    rules = []

    # Split into MUST and MUST NOT sections
    must_section = _extract_section(constraint_text, 'MUST（生成时必须包含）')
    must_not_section = _extract_section(constraint_text, 'MUST NOT（生成时绝不能出现）')

    if must_section:
        rules.extend(_parse_rules_in_section(must_section, 'MUST', md_path))
    if must_not_section:
        rules.extend(_parse_rules_in_section(must_not_section, 'MUST NOT', md_path))

    return rules


def _find_constraint_section(content: str) -> Optional[int]:
    """Find the start of the code generation constraints section."""
    markers = [
        '## 代码生成约束',
        '### 生成规则',
        '#### MUST（生成时必须包含）',
        '#### MUST（',
    ]
    for marker in markers:
        idx = content.find(marker)
        if idx != -1:
            return idx
    return None


def _extract_section(text: str, header_fragment: str) -> Optional[str]:
    """Extract text from a section header to the next same-or-higher-level header."""
    idx = text.find(header_fragment)
    if idx == -1:
        return None

    # Find the end: next #### or ### or ## header
    section_start = text.find('\n', idx) + 1
    remaining = text[section_start:]

    # End at next heading of same or higher level
    end_match = re.search(r'^#{2,4}\s+', remaining, re.MULTILINE)
    if end_match:
        return remaining[:end_match.start()]
    return remaining


def _parse_rules_in_section(section_text: str, rule_type: str, source_file: Path) -> list:
    """Parse numbered rules from a MUST or MUST NOT section."""
    rules = []

    # Split by numbered items (1. ... 2. ... 3. ...)
    items = re.split(r'\n(?=\d+\.\s+)', section_text)

    for item in items:
        item = item.strip()
        if not item or not re.match(r'^\d+\.', item):
            continue

        # Extract the rule title (bold text after number)
        title_match = re.match(r'^\d+\.\s+\*\*(.*?)\*\*', item)
        if not title_match:
            # Try without bold
            title_match = re.match(r'^\d+\.\s+(.+?)(?:\s*[—–-]|$)', item)

        title = title_match.group(1) if title_match else item[:80]

        # Extract code patterns from backticks
        patterns = _BACKTICK_RE.findall(item)

        # Extract verify hint
        verify_match = _VERIFY_RE.search(item)
        verify_hint = verify_match.group(1) if verify_match else None

        # Derive slice_id from file path
        slice_id = _derive_slice_id(source_file)

        rules.append({
            'type': rule_type,
            'text': title.strip(),
            'patterns': patterns,
            'verify_hint': verify_hint,
            'source_file': str(source_file),
            'slice_id': slice_id,
        })

    return rules


def _derive_slice_id(md_path: Path) -> str:
    """Derive slice_id from file path.

    e.g. .../slices/conference/web/login-auth.md → conference/login-auth
    """
    parts = md_path.parts
    try:
        slices_idx = parts.index('slices')
        # Pattern: slices/{product}/{platform}/{ability}.md
        # or: slices/{product}/{ability}.md
        remaining = parts[slices_idx + 1:]
        if len(remaining) >= 3:
            # slices/conference/web/login-auth.md
            product = remaining[0]
            ability = remaining[-1].replace('.md', '')
            return f"{product}/{ability}"
        elif len(remaining) == 2:
            # slices/conference/login-auth.md
            product = remaining[0]
            ability = remaining[1].replace('.md', '')
            return f"{product}/{ability}"
    except (ValueError, IndexError):
        pass
    return str(md_path.stem)


def load_rules_for_product_platform(
    kb_root: Path,
    product: str,
    platform: str,
) -> list:
    """Load all rules for a given product and platform.

    Loads both product-level and platform-specific slice files.
    """
    slices_dir = kb_root / 'knowledge-base' / 'slices' / product
    all_rules = []

    # Product-level slices
    for md_file in slices_dir.glob('*.md'):
        all_rules.extend(extract_rules_from_slice(md_file))

    # Platform-specific slices
    platform_dir = slices_dir / platform
    if platform_dir.exists():
        for md_file in platform_dir.glob('*.md'):
            all_rules.extend(extract_rules_from_slice(md_file))

    return all_rules


def rules_for_file(all_rules: list, file_content: str) -> list:
    """Filter rules relevant to a specific file based on what it imports.

    A rule is relevant if the file contains any composable/import that
    the rule's slice defines.
    """
    # Build a map: slice_id → rules
    by_slice = {}
    for rule in all_rules:
        sid = rule.get('slice_id', '')
        by_slice.setdefault(sid, []).append(rule)

    # Determine which slices this file touches
    active_slices = set()
    for composable, slice_id in COMPOSABLE_TO_SLICE.items():
        if composable in file_content:
            active_slices.add(slice_id)

    # Return rules from active slices only
    relevant = []
    for sid in active_slices:
        relevant.extend(by_slice.get(sid, []))

    return relevant
