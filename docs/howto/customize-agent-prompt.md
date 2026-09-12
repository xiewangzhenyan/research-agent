# How to: Customize the Agent Prompt

## Where to Edit

All agent prompts are centralized in:

```
app/agents/prompts.py
```

## Default Prompt

```python
DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant."""
```

## Best Practices

### 1. Be specific about the agent's role

```python
DEFAULT_SYSTEM_PROMPT = """You are a customer support agent for agent.

Your responsibilities:
- Answer questions about our products and services
- Help users troubleshoot issues
- Escalate complex problems to human support

Tone: Professional but friendly. Use simple language."""
```

### 2. Define output format

```python
DEFAULT_SYSTEM_PROMPT = """You are a data analyst assistant.

When presenting data:
- Use tables for comparisons
- Include specific numbers and percentages
- Cite your data sources

When you don't know something, say so clearly."""
```

### 4. Multi-persona agents

Create different prompts for different use cases:

```python
SUPPORT_PROMPT = """You are a customer support agent..."""
ANALYST_PROMPT = """You are a data analyst..."""
WRITER_PROMPT = """You are a content writer..."""

def get_prompt(persona: str = "default") -> str:
    prompts = {
        "default": DEFAULT_SYSTEM_PROMPT,
        "support": SUPPORT_PROMPT,
        "analyst": ANALYST_PROMPT,
        "writer": WRITER_PROMPT,
    }
    return prompts.get(persona, DEFAULT_SYSTEM_PROMPT)
```

## Tips

- Keep prompts concise — shorter prompts = faster, cheaper responses
- Test with real user queries, not just ideal cases
- Include example outputs in the prompt for consistent formatting
- Use the temperature setting (`AI_TEMPERATURE` in `.env`) to control creativity
