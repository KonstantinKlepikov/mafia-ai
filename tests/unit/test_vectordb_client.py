"""Unit tests for VectorDBClient."""

from unittest.mock import MagicMock

import pytest
from _pytest.monkeypatch import MonkeyPatch

import shared.vectordb_client as vdb_module
from shared.models import SystemPrompt
from shared.vectordb_client import VectorDBClient


def _make_chroma_result(
    persona_id: str = 'uuid-1',
    document: str = 'You are a kind villager.',
    name: str = 'persona_1_good_natured',
    persona_type: str = 'good_natured',
) -> dict:
    return {
        'ids': [persona_id],
        'documents': [document],
        'metadatas': [{'name': name, 'type': persona_type}],
    }


def _make_multi_chroma_result(n: int) -> dict:
    return {
        'ids': [f'uuid-{i}' for i in range(n)],
        'documents': [f'Prompt {i}' for i in range(n)],
        'metadatas': [
            {'name': f'persona_{i}', 'type': 'good_natured'} for i in range(n)
        ],
    }


@pytest.fixture
def mock_http_client() -> MagicMock:
    """Mocked chromadb.HttpClient instance."""
    return MagicMock()


@pytest.fixture
def mock_collection(mock_http_client: MagicMock) -> MagicMock:
    """Mocked chromadb Collection returned by get_collection."""
    coll = MagicMock()
    mock_http_client.get_collection.return_value = coll
    return coll


@pytest.fixture
def client(mock_http_client: MagicMock, monkeypatch: MonkeyPatch) -> VectorDBClient:
    """VectorDBClient with mocked chromadb module."""
    mock_chromadb = MagicMock()
    mock_chromadb.HttpClient.return_value = mock_http_client
    monkeypatch.setattr(vdb_module, 'chromadb', mock_chromadb)
    return VectorDBClient(host='localhost', port=8000)


class TestVectorDBClientInit:
    """Tests for VectorDBClient construction."""

    def test_collection_is_none_on_init(self, client: VectorDBClient) -> None:
        """Test _collection is None before any method is called."""
        assert client._collection is None, '_collection must be None until first use'

    def test_default_collection_name_stored(self, client: VectorDBClient) -> None:
        """Test default collection name is stored."""
        assert client._collection_name == 'agent_personas', (
            f'wrong default collection name: {client._collection_name}'
        )

    def test_custom_collection_name_stored(
        self, mock_http_client: MagicMock, monkeypatch: MonkeyPatch
    ) -> None:
        """Test custom collection name is stored when provided."""
        mock_chromadb = MagicMock()
        mock_chromadb.HttpClient.return_value = mock_http_client
        monkeypatch.setattr(vdb_module, 'chromadb', mock_chromadb)

        c = VectorDBClient(host='localhost', port=8000, collection_name='my_coll')

        assert c._collection_name == 'my_coll', (
            f'wrong collection name: {c._collection_name}'
        )


class TestVectorDBClientGetCollection:
    """Tests for VectorDBClient._get_collection lazy initialisation."""

    def test_calls_get_collection_on_first_access(
        self,
        client: VectorDBClient,
        mock_http_client: MagicMock,
        mock_collection: MagicMock,
    ) -> None:
        """Test get_collection is called on the first _get_collection call."""
        client._get_collection()

        mock_http_client.get_collection.assert_called_once()

    def test_uses_stored_collection_name(
        self,
        client: VectorDBClient,
        mock_http_client: MagicMock,
        mock_collection: MagicMock,
    ) -> None:
        """Test _get_collection passes collection_name to the chroma client."""
        client._get_collection()

        mock_http_client.get_collection.assert_called_once_with('agent_personas')

    def test_caches_collection_after_first_call(
        self,
        client: VectorDBClient,
        mock_http_client: MagicMock,
        mock_collection: MagicMock,
    ) -> None:
        """Test get_collection is called only once across multiple accesses."""
        client._get_collection()
        client._get_collection()
        client._get_collection()

        assert mock_http_client.get_collection.call_count == 1, (
            'get_collection must be called once'
        )

    def test_returns_collection_object(
        self,
        client: VectorDBClient,
        mock_http_client: MagicMock,
        mock_collection: MagicMock,
    ) -> None:
        """Test _get_collection returns the collection from chroma client."""
        result = client._get_collection()

        assert result is mock_collection, (
            'must return the collection from get_collection'
        )


class TestVectorDBClientGetPersona:
    """Tests for VectorDBClient.get_persona."""

    def test_returns_system_prompt(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test get_persona returns a SystemPrompt instance."""
        mock_collection.get.return_value = _make_chroma_result()

        result = client.get_persona('uuid-1')

        assert isinstance(result, SystemPrompt), (
            f'expected SystemPrompt, got {type(result)}'
        )

    def test_returns_correct_persona_id(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test persona_id in returned SystemPrompt matches the stored id."""
        mock_collection.get.return_value = _make_chroma_result(persona_id='uuid-42')

        result = client.get_persona('uuid-42')

        assert result.persona_id == 'uuid-42', f'wrong persona_id: {result.persona_id}'

    def test_returns_correct_prompt_text(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test prompt field in returned SystemPrompt matches stored document."""
        mock_collection.get.return_value = _make_chroma_result(
            document='You are a suspicious detective.'
        )

        result = client.get_persona('uuid-1')

        assert result.prompt == 'You are a suspicious detective.', (
            f'wrong prompt: {result.prompt}'
        )

    def test_calls_get_with_correct_ids(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test ChromaDB get is called with the provided persona_id in ids list."""
        mock_collection.get.return_value = _make_chroma_result()

        client.get_persona('uuid-99')

        mock_collection.get.assert_called_once_with(
            ids=['uuid-99'],
            include=['documents', 'metadatas'],
        )

    def test_raises_value_error_when_not_found(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test ValueError is raised when persona_id does not exist."""
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}

        with pytest.raises(ValueError, match='uuid-missing'):
            client.get_persona('uuid-missing')


class TestVectorDBClientListPersonas:
    """Tests for VectorDBClient.list_personas."""

    def test_returns_list_of_system_prompts(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test list_personas returns a list of SystemPrompt objects."""
        mock_collection.get.return_value = _make_multi_chroma_result(3)

        result = client.list_personas()

        assert all(isinstance(p, SystemPrompt) for p in result), (
            'all items must be SystemPrompt instances'
        )

    def test_returns_correct_count(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test list_personas returns one entry per stored document."""
        mock_collection.get.return_value = _make_multi_chroma_result(5)

        result = client.list_personas()

        assert len(result) == 5, f'expected 5 personas, got {len(result)}'

    def test_returns_empty_list_when_no_personas(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test list_personas returns an empty list when collection is empty."""
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}

        result = client.list_personas()

        assert result == [], f'expected empty list, got {result}'

    def test_preserves_persona_ids(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test each returned SystemPrompt has the correct persona_id."""
        mock_collection.get.return_value = _make_multi_chroma_result(3)

        result = client.list_personas()

        assert [p.persona_id for p in result] == ['uuid-0', 'uuid-1', 'uuid-2'], (
            f'wrong persona ids: {[p.persona_id for p in result]}'
        )


class TestVectorDBClientGetPersonaByName:
    """Tests for VectorDBClient.get_persona_by_name."""

    def test_returns_system_prompt(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test get_persona_by_name returns a SystemPrompt instance."""
        mock_collection.get.return_value = _make_chroma_result(
            name='persona_1_good_natured'
        )

        result = client.get_persona_by_name('persona_1_good_natured')

        assert isinstance(result, SystemPrompt), (
            f'expected SystemPrompt, got {type(result)}'
        )

    def test_returns_correct_name(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test name field in returned SystemPrompt matches requested name."""
        mock_collection.get.return_value = _make_chroma_result(
            name='persona_3_detective'
        )

        result = client.get_persona_by_name('persona_3_detective')

        assert result.name == 'persona_3_detective', f'wrong name: {result.name}'

    def test_calls_get_with_where_filter(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test ChromaDB get is called with a where filter on the name field."""
        mock_collection.get.return_value = _make_chroma_result()

        client.get_persona_by_name('persona_1_good_natured')

        call_kwargs = mock_collection.get.call_args.kwargs
        assert 'where' in call_kwargs, 'where filter must be passed to get()'
        assert call_kwargs['where'] == {'name': {'$eq': 'persona_1_good_natured'}}, (
            f'wrong where filter: {call_kwargs["where"]}'
        )

    def test_raises_value_error_when_not_found(
        self,
        client: VectorDBClient,
        mock_collection: MagicMock,
    ) -> None:
        """Test ValueError is raised when no persona with the given name exists."""
        mock_collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}

        with pytest.raises(ValueError, match='unknown_persona'):
            client.get_persona_by_name('unknown_persona')


class TestVectorDBClientToSystemPrompt:
    """Tests for VectorDBClient._to_system_prompt static method."""

    def test_maps_persona_id(self) -> None:
        """Test persona_id is set from the id argument."""
        result = VectorDBClient._to_system_prompt(
            persona_id='uuid-test',
            document='Some prompt.',
            metadata={'name': 'p1', 'type': 'good_natured'},
        )

        assert result.persona_id == 'uuid-test', (
            f'wrong persona_id: {result.persona_id}'
        )

    def test_maps_name_from_metadata(self) -> None:
        """Test name is taken from metadata dict."""
        result = VectorDBClient._to_system_prompt(
            persona_id='uuid-test',
            document='Some prompt.',
            metadata={'name': 'persona_5_schemer', 'type': 'schemer'},
        )

        assert result.name == 'persona_5_schemer', f'wrong name: {result.name}'

    def test_maps_persona_type_from_metadata(self) -> None:
        """Test persona_type is taken from metadata type key."""
        result = VectorDBClient._to_system_prompt(
            persona_id='uuid-test',
            document='Some prompt.',
            metadata={'name': 'p1', 'type': 'paranoid'},
        )

        assert result.persona_type == 'paranoid', (
            f'wrong persona_type: {result.persona_type}'
        )

    def test_maps_prompt_from_document(self) -> None:
        """Test prompt field is taken from the document argument."""
        result = VectorDBClient._to_system_prompt(
            persona_id='uuid-test',
            document='You suspect everyone around you.',
            metadata={'name': 'p1', 'type': 'paranoid'},
        )

        assert result.prompt == 'You suspect everyone around you.', (
            f'wrong prompt: {result.prompt}'
        )

    def test_returns_system_prompt_instance(self) -> None:
        """Test return type is SystemPrompt."""
        result = VectorDBClient._to_system_prompt(
            persona_id='uuid-test',
            document='Prompt.',
            metadata={'name': 'p1', 'type': 'good_natured'},
        )

        assert isinstance(result, SystemPrompt), (
            f'expected SystemPrompt, got {type(result)}'
        )
