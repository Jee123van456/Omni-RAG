import hashlib
import numpy as np
from typing import List
from shared.config.settings import settings
from shared.logging.logger import logger
from langchain_openai import OpenAIEmbeddings

class Embedder:
    def __init__(self):
        self.use_mock = False
        api_key = settings.OPENAI_API_KEY
        
        if not api_key or api_key == "mock-key" or api_key == "your-openai-api-key":
            self.use_mock = True
            logger.warning("No valid OpenAI API key found. Using deterministic mock embeddings (1536-dim).")
            self.embeddings = None
        else:
            try:
                self.embeddings = OpenAIEmbeddings(
                    openai_api_key=api_key,
                    model="text-embedding-3-small"
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAIEmbeddings: {e}. Falling back to mock embeddings.")
                self.use_mock = True
                self.embeddings = None

    def embed_text(self, text: str) -> List[float]:
        """
        Embeds a single string of text. Returns a list of 1536 floats.
        """
        if self.use_mock:
            # Generate deterministic mock embedding using hash of text
            sha256 = hashlib.sha256(text.encode("utf-8")).digest()
            # Seed numpy random with the integer value of the hash
            seed = int.from_bytes(sha256[:4], "big")
            rng = np.random.default_rng(seed)
            # Create a 1536 float list and normalize it
            vec = rng.standard_normal(1536)
            norm_vec = vec / np.linalg.norm(vec)
            return norm_vec.tolist()
            
        try:
            return self.embeddings.embed_query(text)
        except Exception as e:
            logger.error(f"Error during OpenAI embedding: {e}. Falling back to mock.")
            # Fallback
            sha256 = hashlib.sha256(text.encode("utf-8")).digest()
            seed = int.from_bytes(sha256[:4], "big")
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(1536)
            norm_vec = vec / np.linalg.norm(vec)
            return norm_vec.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds a batch of texts.
        """
        return [self.embed_text(t) for t in texts]

# Instantiate global embedder
embedder = Embedder()
