"""C06 Index construction and chunking package.

Owned by Sampreeth (H05).
"""

from recycleguard.contracts.retrieval import (
    DenseConfiguration,
    IndexManifest,
    LexicalConfiguration,
)
from recycleguard.indexing.builder import IndexBuilder
from recycleguard.indexing.chunker import ProvisionChunker
from recycleguard.indexing.fts_index import FTS5Index
from recycleguard.indexing.models import ChunkDisposition, ChunkType, IndexedChunk

__all__ = [
    "ChunkDisposition",
    "ChunkType",
    "DenseConfiguration",
    "FTS5Index",
    "IndexBuilder",
    "IndexManifest",
    "IndexedChunk",
    "LexicalConfiguration",
    "ProvisionChunker",
]
