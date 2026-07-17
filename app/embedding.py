"""Embedding provider with dual backend support.

- fastembed (default): Local CPU-optimized ONNX, no network required.
- deepseek: Cloud API using existing DeepSeek credentials.
"""
from __future__ import annotations


class EmbeddingProvider:
    """Unified embedding interface supporting multiple backends.

    Usage::

        # Default: FastEmbed local
        provider = EmbeddingProvider(backend="fastembed")
        embedding = provider.embed("你好世界")

        # DeepSeek API
        provider = EmbeddingProvider(backend="deepseek")
        embedding = provider.embed("Hello world")
    """

    def __init__(self, backend: str = "fastembed",
                 model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self._backend = backend
        self._model_name = model_name
        self._fastembed_model = None
        self._deepseek_client = None

    def _init_fastembed(self) -> None:
        """Initialize FastEmbed model (ONNX, no PyTorch)."""
        from fastembed import TextEmbedding

        self._fastembed_model = TextEmbedding(
            model_name=self._model_name,
        )

    def _init_deepseek(self) -> None:
        """Initialize DeepSeek API client."""
        import os

        from openai import OpenAI

        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self._deepseek_client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for a single text.

        Args:
            text: Input text to embed.

        Returns:
            List of float values representing the embedding vector.
        """
        if self._backend == "fastembed":
            if self._fastembed_model is None:
                self._init_fastembed()
            result = list(self._fastembed_model.embed([text]))
            if result:
                return result[0].tolist()
            return []

        elif self._backend == "deepseek":
            if self._deepseek_client is None:
                self._init_deepseek()
            response = self._deepseek_client.embeddings.create(
                model="deepseek-embedding",
                input=text,
            )
            return response.data[0].embedding

        return []