"""Source-only fixture. Tests must never import this module."""

from openai import OpenAI

client = OpenAI()
SYSTEM_PROMPT = "PRIVATE_PROMPT_LITERAL_MUST_NOT_APPEAR_IN_RESULTS"
MODEL = choose_model()
messages = [{"role": "system", "content": SYSTEM_PROMPT}]

first = client.chat.completions.create(
    model="fixture/model-one",
    messages=messages,
    response_format={"type": "json_object"},
)


def outer(query):
    def inner():
        return client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": query}],
        )

    return inner()
