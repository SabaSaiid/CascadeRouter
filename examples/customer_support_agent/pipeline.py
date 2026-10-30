"""Customer Support Multi-Agent AI Pipeline.

Demonstrates a 3-stage LLM agent architecture for enterprise support:
1. Triage Agent: Classifies support ticket into billing, technical, or general.
2. Extraction Agent: Extracts structured customer entities and urgency from ticket.
3. Resolution Agent: Synthesizes final response for the customer.
"""

from openai import OpenAI

client = OpenAI()

# Step 1: Customer Ticket Triage
# Simple classification task initially assigned to an expensive 70B model.
# Ripe for FinOps optimization to Llama-3.1-8B (91% cost savings).
triage_response = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    messages=[
        {"role": "system", "content": "Classify customer ticket category into billing, tech, or general."},
        {"role": "user", "content": "My monthly invoice shows an unexpected $45 data transfer fee."}
    ],
    response_format={"type": "json_object"},
)
triage_intent = triage_response.choices[0].message.content

# Step 2: Context & Entity Extraction
# Complex structured JSON extraction chained from the triage output.
# Perfect target for NVIDIA Llama-3.1-Nemotron-70B-Instruct for strict JSON schema compliance.
extraction_response = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    messages=[
        {"role": "system", "content": "Extract customer account ID, urgency level, and billing item."},
        {"role": "user", "content": triage_intent}
    ],
    response_format={"type": "json_object"},
)
extracted_context = extraction_response.choices[0].message.content

# Step 3: Support Resolution & Draft Generation
# Generates final empathetic customer email based on extracted details.
resolution_response = client.chat.completions.create(
    model="meta-llama/Meta-Llama-3.1-70B-Instruct",
    messages=[
        {"role": "system", "content": "Draft an empathetic resolution email explaining fee credit options."},
        {"role": "user", "content": extracted_context}
    ],
)

