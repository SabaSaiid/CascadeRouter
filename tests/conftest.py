"""Isolated, explicit local API test policy; no environment/provider setup."""

import pytest

from backend.config import BackendConfig


SOURCE = '''from openai import OpenAI
client = OpenAI()
first = client.chat.completions.create(model="fixture/model", messages=[])
second = client.chat.completions.create(model=MODEL, messages=first)
'''


@pytest.fixture
def api_environment(tmp_path):
    root = tmp_path / "allowed"
    repository = root / "repository"
    storage = tmp_path / "storage"
    repository.mkdir(parents=True)
    storage.mkdir()
    (repository / "app.py").write_text(SOURCE, encoding="utf-8")
    settings = BackendConfig(permitted_repository_roots=[root], storage_directory=storage)
    return settings, repository, storage
