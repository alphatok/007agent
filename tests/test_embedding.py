"""Tests for app.embedding module — EmbeddingProvider."""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestEmbeddingProvider:
    """Tests for EmbeddingProvider with dual backend support."""

    def test_deepseek_embed_mock(self) -> None:
        """DeepSeek backend should call embeddings API."""
        from app.embedding import EmbeddingProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.1, 0.2, 0.3]
        mock_client.embeddings.create.return_value = mock_response

        provider = EmbeddingProvider(backend="deepseek")
        provider._deepseek_client = mock_client

        result = provider.embed("test query")
        assert result == [0.1, 0.2, 0.3]
        mock_client.embeddings.create.assert_called_once()

    def test_backend_switch(self) -> None:
        """EmbeddingProvider should accept backend parameter."""
        from app.embedding import EmbeddingProvider

        provider = EmbeddingProvider(backend="deepseek")
        assert provider._backend == "deepseek"

        provider = EmbeddingProvider(backend="fastembed")
        assert provider._backend == "fastembed"

    def test_embed_empty_string(self) -> None:
        """embed should handle empty string gracefully."""
        from app.embedding import EmbeddingProvider

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock()]
        mock_response.data[0].embedding = [0.0]
        mock_client.embeddings.create.return_value = mock_response

        provider = EmbeddingProvider(backend="deepseek")
        provider._deepseek_client = mock_client

        result = provider.embed("")
        assert isinstance(result, list)
        assert len(result) > 0