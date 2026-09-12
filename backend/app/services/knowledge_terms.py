"""Bounded local terminology matching for retrieval, never answer evidence.

Aliases are curated equivalents, not definitions or inferred experimental facts.
Add a new concept only with ambiguity/boundary tests and a version bump.
"""

import re

TERMINOLOGY_VERSION = "scientific-zh-en-v1"
MAX_CONCEPTS = 6
MAX_ALIAS_CHARACTERS = 360

# Canonical Chinese/English first; alternative spellings and unambiguous acronyms follow.
# Q and RI are deliberately excluded as ambiguous standalone abbreviations.
CONCEPTS = (
    ("局域表面等离激元共振", "localized surface plasmon resonance", "LSPR", "局域表面等离子体共振"),
    ("表面等离激元共振", "surface plasmon resonance", "SPR", "表面等离子体共振"),
    ("超表面", "metasurface", "metasurfaces"),
    ("折射率灵敏度", "refractive index sensitivity"),
    ("折射率", "refractive index"),
    ("灵敏度", "sensitivity"),
    ("检测限", "limit of detection", "detection limit", "检出限"),
    ("非特异性吸附", "nonspecific adsorption", "non-specific adsorption", "非特异吸附"),
    ("金纳米颗粒", "gold nanoparticles", "gold nanoparticle", "金纳米粒子"),
    ("抗体", "antibody", "antibodies"),
    ("抗原", "antigen", "antigens"),
    ("品质因数", "quality factor", "品质因子"),
    ("优值", "figure of merit", "FOM"),
    ("共振线宽", "resonance linewidth"),
    ("酶联免疫吸附测定", "enzyme-linked immunosorbent assay", "ELISA", "酶联免疫吸附试验"),
    ("磷酸盐缓冲盐水", "phosphate buffered saline", "PBS", "磷酸盐缓冲生理盐水"),
    ("表面功能化", "surface functionalization", "surface functionalisation"),
    ("偏振", "polarization", "polarisation"),
    ("微流控", "microfluidics", "microfluidic"),
    ("脱氧核糖核酸", "deoxyribonucleic acid", "DNA"),
)


def _pattern(alias: str) -> re.Pattern:
    if alias.isascii():
        # English terms in PDFs may contain newlines or typographic hyphens.
        phrase = r"[\s\-‐‑–]+".join(re.escape(p) for p in re.split(r"[ -]+", alias))
        return re.compile(r"(?<![a-z0-9_])" + phrase + r"(?![a-z0-9_])", re.IGNORECASE)
    return re.compile(re.escape(alias))


PATTERNS = tuple(tuple(_pattern(alias) for alias in concept) for concept in CONCEPTS)


def retrieval_aliases(query: str) -> list[str]:
    """Match only original text, longest spans first, then expand in query order.

    Prevents SPR from matching inside LSPR's full name and avoids recursively
    expanding aliases. Budget exhaustion skips complete aliases, never truncates them.
    """
    matches = sorted(
        (
            (m.start(), m.end(), i)
            for i, patterns in enumerate(PATTERNS)
            for pattern in patterns
            for m in pattern.finditer(query)
        ),
        key=lambda match: (match[0] - match[1], match[0], match[2]),
    )
    accepted = []
    for start, end, concept in matches:
        if not any(start < b and end > a for a, b, _ in accepted):
            accepted.append((start, end, concept))
    concepts = list(dict.fromkeys(i for _, _, i in sorted(accepted)))[:MAX_CONCEPTS]
    aliases, used = [], 0
    for concept in concepts:
        for alias, pattern in zip(CONCEPTS[concept], PATTERNS[concept], strict=True):
            if pattern.search(query) or alias in aliases:
                continue
            if used + len(alias) > MAX_ALIAS_CHARACTERS:
                continue
            aliases.append(alias)
            used += len(alias)
    return aliases


def terminology_metadata(query: str) -> dict:
    return {"version": TERMINOLOGY_VERSION, "aliases": retrieval_aliases(query)}
