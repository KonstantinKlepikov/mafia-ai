"""VectorDB client for retrieving agent persona documents from ChromaDB."""

import chromadb

from .models import SystemPrompt


class VectorDBClient:
    """Wrapper around chromadb.HttpClient for reading agent personas.

    Args:
        host: ChromaDB server hostname.
        port: ChromaDB server HTTP port.
        collection_name: Name of the personas collection.

    """

    def __init__(
        self,
        host: str = 'mafia-ai-vectordb',
        port: int = 8000,
        collection_name: str = 'agent_personas',
    ) -> None:
        self._client = chromadb.HttpClient(host=host, port=port)
        self._collection = self._client.get_collection(collection_name)

    def get_persona(self, persona_id: str) -> SystemPrompt:
        """Retrieve a single persona by its Chroma document id.

        Args:
            persona_id: UUID assigned to the persona at seed time.

        Returns:
            SystemPrompt populated from the stored document and metadata.

        Raises:
            ValueError: If no document with the given id exists.

        """
        result = self._collection.get(
            ids=[persona_id],
            include=['documents', 'metadatas'],
        )
        if not result['ids']:
            raise ValueError(f'Persona not found: {persona_id}')

        return self._to_system_prompt(
            persona_id=result['ids'][0],
            document=result['documents'][0],
            metadata=result['metadatas'][0],
        )

    def list_personas(self) -> list[SystemPrompt]:
        """Return all personas stored in the collection.

        Returns:
            List of SystemPrompt objects, one per stored persona document.

        """
        result = self._collection.get(include=['documents', 'metadatas'])
        return [
            self._to_system_prompt(pid, doc, meta)
            for pid, doc, meta in zip(
                result['ids'], result['documents'], result['metadatas']
            )
        ]

    @staticmethod
    def _to_system_prompt(
        persona_id: str,
        document: str,
        metadata: dict,
    ) -> SystemPrompt:
        """Build a SystemPrompt from raw Chroma result fields."""
        return SystemPrompt(
            persona_id=persona_id,
            name=metadata.get('name', ''),
            persona_type=metadata.get('type', ''),
            prompt=document,
        )
