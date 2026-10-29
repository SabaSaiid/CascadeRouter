"""Source-only fixture; no SDK installation or API access is needed."""

import openai as oai
from openai import AsyncOpenAI as AsyncClient


async def module_alias(messages):
    client = oai.AsyncOpenAI()
    return await client.chat.completions.create(
        model="fixture/async-model", messages=messages,
    )


async def constructor_alias(messages):
    client = AsyncClient()
    alias = client
    return await alias.chat.completions.create(
        model=configuration.model, messages=messages,
    )
