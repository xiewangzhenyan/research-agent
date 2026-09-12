"""Terminology must improve bilingual recall without inventing evidence or scope."""

import pytest

from app.services.knowledge_index import rank_chunks
from app.services.knowledge_terms import MAX_ALIAS_CHARACTERS, retrieval_aliases


@pytest.mark.parametrize(
    "query", ["xLSPR", "LSPR8675309", "project_LSPR", "metasurfacelike", "Q", "RI"]
)
def test_identifiers_and_ambiguous_abbreviations_do_not_expand(query):
    assert retrieval_aliases(query) == []


@pytest.mark.parametrize(
    "query", ["LSPR", "局域表面等离激元共振", "localized surface plasmon resonance"]
)
def test_localized_resonance_does_not_expand_to_propagating_resonance(query):
    aliases = retrieval_aliases(query)
    assert aliases
    assert "SPR" not in aliases
    assert "surface plasmon resonance" not in aliases
    assert "表面等离激元共振" not in aliases


def test_longest_match_does_not_hide_a_separate_explicit_concept():
    aliases = retrieval_aliases("对比 LSPR 和 SPR")
    assert "localized surface plasmon resonance" in aliases
    assert "surface plasmon resonance" in aliases


def test_quality_factor_and_figure_of_merit_are_different():
    assert "figure of merit" not in retrieval_aliases("品质因数")
    assert "quality factor" not in retrieval_aliases("FOM")
    assert "quality factor" in retrieval_aliases("品质因数")
    assert "figure of merit" in retrieval_aliases("优值")


def test_phosphate_buffer_does_not_imply_saline():
    assert retrieval_aliases("磷酸盐缓冲液") == []
    assert "phosphate buffered saline" in retrieval_aliases("磷酸盐缓冲盐水")


def test_pdf_whitespace_and_english_word_forms():
    # PDF extraction can introduce U+2010 instead of the ASCII hyphen.
    assert "折射率灵敏度" in retrieval_aliases("refractive‐index\nsensitivity")  # noqa: RUF001
    assert "抗体" in retrieval_aliases("ANTIBODIES")
    assert "酶联免疫吸附测定" in retrieval_aliases("enzyme-linked immunosorbent assay")


def test_expansion_is_bounded_unique_and_does_not_copy_unrelated_input():
    query = ("超表面 折射率 抗体 抗原 金纳米颗粒 微流控 偏振 DNA secret_991 " * 20).strip()
    aliases = retrieval_aliases(query)
    assert aliases == retrieval_aliases(query)
    assert len(set(aliases)) == len(aliases)
    assert sum(map(len, aliases)) <= MAX_ALIAS_CHARACTERS
    assert "secret_991" not in " ".join(aliases)
    assert "deoxyribonucleic acid" not in aliases  # Beyond the first six concepts.


def chunk(doc, text):
    return {"document_id": doc, "content": text, "embedding": [0, 1], "position": 0}


def test_chinese_query_retrieves_english_original_without_semantic_help():
    original = "The limit of detection is 7 picomolar."
    corpus = [chunk("paper", original), chunk("noise", "The price of a sample is unknown.")]
    assert rank_chunks("检测限是多少？", [1, 0], corpus, expand_terms=False) == []
    hits = rank_chunks("检测限是多少？", [1, 0], corpus)
    assert [h["document_id"] for h in hits] == ["paper"]
    assert hits[0]["content"] == original


def test_english_query_retrieves_chinese_original():
    hits = rank_chunks("microfluidics", [1, 0], [chunk("paper", "微流控输运样品。")])
    assert len(hits) == 1 and hits[0]["content"] == "微流控输运样品。"


def test_original_identifier_outranks_low_weight_alias_only_hit():
    corpus = [chunk("specific", "LSPR8675309 灵敏度 123"), chunk("generic", "sensitivity")]
    hits = rank_chunks("LSPR8675309 灵敏度 123", [1, 0], corpus)
    assert hits[0]["document_id"] == "specific"


def test_unrelated_queries_and_vectors_keep_original_ranking():
    corpus = [chunk("policy", "住宿每日 650 元"), chunk("noise", "limit of detection")]
    assert rank_chunks("住宿 650", [1, 0], corpus) == rank_chunks(
        "住宿 650", [1, 0], corpus, expand_terms=False
    )
