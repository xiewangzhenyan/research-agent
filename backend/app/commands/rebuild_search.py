"""Operator-only shadow-index rebuild from owned source text."""

import asyncio
from uuid import UUID

import click

from app.commands import command, success
from app.services.knowledge_search_rebuild import rebuild_document


@command("rebuild-search", help="Re-embed one owned document into the database search index")
@click.option("--user-id", required=True, type=click.UUID)
@click.option("--document-id", required=True, type=click.UUID)
def rebuild_search(user_id: UUID, document_id: UUID):
    count = asyncio.run(rebuild_document(user_id, document_id))
    success(f"Published {count} search chunks")
