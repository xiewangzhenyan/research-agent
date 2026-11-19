"""Real bytes, malformed formats, bounded Office parsing and truthful check reports."""

import asyncio
import hashlib
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.services.artifact_validation import (
    ArtifactValidationError,
    inspect_artifact,
    validate_files,
)
from app.services.document_export import DocumentRequest, render_document


def file(content, name="data.json", **changes):
    return {
        "content": content,
        "name": name,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        **changes,
    }


@pytest.mark.parametrize("format", ["md", "docx", "xlsx", "pptx"])
def test_generated_documents_have_byte_bound_structural_report(format):
    artifact = render_document(
        DocumentRequest(
            title="实验记录",
            format=format,
            content="# 数据\n\n| 项 | 值 |\n| - | - |\n| A | 1.25 |",
        )
    )
    report = inspect_artifact(artifact)
    assert report["sha256"] == artifact["sha256"]
    assert report["size"] == artifact["size"]
    assert report["structure"] == "checked"
    assert report["content_validation"] == "not_verified"
    assert "实验记录" not in str(report)


@pytest.mark.parametrize(
    "content,name",
    [
        (b'{"x": [1,2]}', "data.json"),
        (b"\xef\xbb\xbf{}", "bom.json"),
        (b'{"quoted": "' + b"[" * 200 + b'", "escaped": "\\""}', "strings.json"),
        (b'a,b\r\n"one\ntwo",3', "multiline.csv"),
        (b"ragged,rows\none", "ragged.csv"),
        (b"", "empty.csv"),
        ("资料".encode(), "data.txt"),
    ],
)
def test_valid_text_structures(content, name):
    assert inspect_artifact(file(content, name))["structure"] == "checked"


@pytest.mark.parametrize(
    "content,name",
    [
        (b'{"unfinished":', "data.json"),
        (b"NaN", "data.json"),
        (b"Infinity", "data.json"),
        pytest.param(b"[" * 2000 + b"]" * 2000, "deep.json", id="deep-json"),
        (b'"unterminated', "data.csv"),
        (b"\xff\xfe", "data.txt"),
        (b"not a zip", "fake.docx"),
    ],
)
def test_invalid_structures_rejected(content, name):
    with pytest.raises(ArtifactValidationError):
        inspect_artifact(file(content, name))


@pytest.mark.parametrize("changes", [{"size": True}, {"size": 0}, {"sha256": "0" * 64}])
def test_metadata_cannot_override_actual_bytes(changes):
    with pytest.raises(ArtifactValidationError):
        inspect_artifact(file(b"{}", **changes))


def test_unimplemented_parsers_and_oversize_csv_field_are_not_marked_checked():
    for name in ["image.png", "report.pdf"]:
        report = inspect_artifact(file(b"opaque", name))
        assert report["structure"] == "not_checked"
        assert report["checks"] == ["size", "sha256"]
    report = inspect_artifact(file(b"x" * 200000, "wide.csv"))
    assert report["structure"] == "not_checked"
    assert "csv_field_limit_reached" in report["checks"]


def test_repair_feedback_identifies_format_without_echoing_file_contents():
    with pytest.raises(ArtifactValidationError) as exc:
        inspect_artifact(file(b'{"private-secret": NaN}'))
    assert "JSON" in str(exc.value) and "NaN/Infinity" in str(exc.value)
    assert "private-secret" not in str(exc.value)


@pytest.mark.parametrize(
    "problem", ["wrong_format", "xml", "dtd", "missing_main", "expansion", "path"]
)
def test_office_package_boundaries(problem):
    artifact = render_document(DocumentRequest(title="Title", content="Text", format="docx"))
    if problem == "wrong_format":
        artifact["name"] = "renamed.xlsx"
    else:
        output = BytesIO()
        with (
            ZipFile(BytesIO(artifact["content"])) as source,
            ZipFile(output, "w", ZIP_DEFLATED) as target,
        ):
            for name in source.namelist():
                data = source.read(name)
                if name == "word/document.xml":
                    if problem == "missing_main":
                        continue
                    if problem == "xml":
                        data = b"<broken"
                    if problem == "dtd":
                        data = b'<!DOCTYPE document [<!ENTITY x "hidden">]><document>&x;</document>'
                target.writestr(name, data)
            if problem == "expansion":
                target.writestr("huge.txt", b"x" * (16 * 1024**2 + 1))
            if problem == "path":
                target.writestr("../outside.xml", b"<x/>")
        artifact = file(output.getvalue(), "report.docx")
    with pytest.raises(ArtifactValidationError):
        inspect_artifact(artifact)


def test_batch_rejects_duplicate_names_and_invalid_later_file():
    async def check():
        for files in [
            [file(b"{}")] * 2,
            [file(b"{}")] * 11,
            [file(b"{}", "good.json"), file(b"bad", "bad.json")],
        ]:
            with pytest.raises(ArtifactValidationError):
                await validate_files(files)

    asyncio.run(check())
