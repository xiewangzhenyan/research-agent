"""Versioned local model and lexical index construction; no remote downloads."""

import hashlib
import json
import logging
import re
from collections import Counter
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path

import jieba

from app.services.knowledge_index import MODEL, encoder
from app.services.knowledge_terms import retrieval_aliases

QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def model_fingerprint():
    model = encoder().model
    folder = Path(model._model_dir)
    files = [model.model_description.model_file, "tokenizer.json", "config.json"]
    files += [
        name
        for name in ("tokenizer_config.json", "special_tokens_map.json")
        if (folder / name).is_file()
    ]
    identity = {
        "model": MODEL,
        "dimension": 512,
        "query_prefix": QUERY_PREFIX,
        "fastembed": version("fastembed"),
        "document_prefix": "",
        "files": {name: file_hash(folder / name) for name in files},
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=1)
def tokenizer_version():
    dictionary = Path(jieba.__file__).parent / "dict.txt"
    return f"jieba-{version('jieba')}-search-hmm0-{file_hash(dictionary)[:16]}"


@lru_cache(maxsize=1)
def tokenizer():
    jieba.setLogLevel(logging.WARNING)
    instance = jieba.Tokenizer()
    instance.initialize()
    return instance


def tokenize(text):
    return [
        word
        for word in tokenizer().cut_for_search(text.lower(), HMM=False)
        if re.fullmatch(r"[a-z0-9_\u3400-\u9fff]+", word)
    ]


def lexical_data(content):
    terms = Counter(tokenize(content))
    return {"terms": dict(terms), "term_list": sorted(terms), "token_count": sum(terms.values())}


def query_weights(query):
    result = dict.fromkeys(tokenize(query), 1.0)
    stopwords = {"a", "an", "and", "of", "the", "to", "in", "for", "with", "on"}
    for term in tokenize(" ".join(retrieval_aliases(query))):
        if term not in stopwords:
            result.setdefault(term, 0.35)
    return result
