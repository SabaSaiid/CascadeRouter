"""Lookalikes and unsupported frameworks are never confirmed SDK clients."""

from unrelated import OpenAI
from langchain_openai import ChatOpenAI
from openai import OpenAI as RealClient

client = OpenAI()
client.chat.completions.create(model="not-openai")
unknown.chat.completions.create(model="unknown-client")
wrapped = make_client(RealClient)
wrapped.chat.completions.create(model="wrapped-client")
chain = ChatOpenAI()
chain.invoke("PRIVATE_UNSUPPORTED_PROMPT")


def injected(client):
    return client.chat.completions.create(model="parameter-client")
