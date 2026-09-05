"""Hello skill for testing plugin system."""

PLUGIN = {
    "name": "hello_skill",
    "description": "Returns a greeting message. Use when user says hello or wants a friendly response.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name to greet, optional"}
        },
        "required": [],
    },
    "category": "general",
    "version": "1.0.0",
    "author": "ZARA",
}

def run(parameters: dict, context=None) -> str:
    """Return a greeting."""
    name = parameters.get("name", "Alex")
    return f"Hello, {name}! How can I assist you today?"
