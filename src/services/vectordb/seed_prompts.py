"""Seed script for vector DB (Chroma) to create agent_personas collection.

This script connects to a ChromaDB REST server and writes 10 persona
documents into the `agent_personas` collection. Each document has
metadata with `persona_id` and `name`.

Run inside a container that can reach the Chroma server (e.g. via
service name `mafia-ai-vectordb:8000`).

TODO: move specs to yaml
TODO: names generator
TODO: character roleplay prompts
"""

import sys
import time
import uuid

import chromadb
from chromadb.config import Settings
from loguru import logger
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    chroma_host: str = 'mafia-ai-vectordb'
    chroma_port: int = 8000
    collection_name: str = 'agent_personas'
    persona_types: list[str] = [
        'добряк',
        'истеричка',
        'конспиролог',
        'аристократ',
        'домохозяйка',
        'проститутка',
        'невростеник',
        'клерикал',
        'поэтесса',
        'простофиля',
    ]


class Persona(BaseModel):
    id: str
    name: str
    type: str
    prompt: str

    @property
    def metadata(self) -> dict[str, str]:
        return {'type': self.type, 'name': self.name}


def make_persona_doc(ptype: str, idx: int) -> Persona:
    """Make persona dock

    Args:
        ptype (str): persone type
        idx (int): person id

    Returns:
        Persona: persona metadata
    """
    pid = str(uuid.uuid4())
    name = f'persona_{idx + 1}_{ptype}'
    prompt = (
        f'Имя: {name}.\n'
        f'Характер: {ptype}.\n'
        'Манера речи: используйте короткие фразы, иногда эмоциональные, '
        'адаптируйте тон к роли.\n'
        'Ограничения: отвечать только на игровые темы, не выдавать служебную '
        'информацию, не обсуждать внешние политики или приватные данные.\n'
        'Роль в игре: отвечать как игрок-мафия/горожанин в зависимости от '
        'назначения оркестратора.'
    )
    return Persona(id=pid, prompt=prompt, name=name, type=ptype)


def main() -> None:
    """Connect to Chroma server provided by environment or default service name"""
    app_settings = AppSettings()  # load from env if provided

    settings = Settings(
        chroma_server_host=app_settings.chroma_host,
        chroma_server_http_port=app_settings.chroma_port,
    )

    client = chromadb.Client(settings)

    # Ensure Chroma is healthy / reachable
    for _ in range(10):
        try:
            # try listing collections as a health probe
            _ = client.list_collections()
            break
        except Exception:
            logger.warning('Waiting for ChromaDB server...')
            time.sleep(1)
    else:
        logger.error('ChromaDB server is not reachable')
        sys.exit(2)

    try:
        collection = client.get_collection(app_settings.collection_name)
        # Try to inspect count if available
        try:
            existing_count = collection.count()
        except Exception:
            existing_count = None
        if (
            existing_count
            and isinstance(existing_count, int)
            and existing_count >= len(app_settings.persona_types)
        ):
            logger.info(
                f"Collection '{app_settings.collection_name}' already seeded "
                f'({existing_count} entries). Skipping.'
            )
            return
    except Exception:
        collection = client.create_collection(name=app_settings.collection_name)

    prompts: list[str] = []
    metadatas: list[dict[str, str]] = []
    ids: list[str] = []

    for idx, ptype in enumerate(app_settings.persona_types):
        item = make_persona_doc(ptype, idx)
        ids.append(item.id)
        prompts.append(item.prompt)
        metadatas.append(item.metadata)

    # Add documents to collection (upsert semantics)
    collection.add(ids=ids, documents=prompts, metadatas=metadatas)  # type: ignore

    logger.info(
        f"Seeded collection '{app_settings.collection_name}' with {len(ids)} personas"
    )


if __name__ == '__main__':
    main()
