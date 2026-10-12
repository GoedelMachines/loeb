from loeb.llm.anthropic import AnthropicProvider
from loeb.llm.base import (
    CompletionResult,
    LLMProvider,
    StreamEvent,
    ToolCall,
    compress_messages,
    estimate_tokens,
    is_tool_error,
)
from loeb.llm.openai import OpenAIProvider


def create_provider(config) -> LLMProvider:
    """Create the appropriate LLM provider based on config."""
    if config.provider == "openai":
        if not config.openai_api_key:
            raise ValueError("OPENAI_API_KEY required when provider is 'openai'")
        return OpenAIProvider(
            api_key=config.openai_api_key,
            model=config.openai_model,
            base_url=config.openai_base_url or None,
        )
    if config.provider != "anthropic":
        raise ValueError(f"Unknown LLM provider '{config.provider}' (anthropic or openai)")
    if not config.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY required when provider is 'anthropic'")
    return AnthropicProvider(
        api_key=config.anthropic_api_key,
        model=config.model,
    )


__all__ = [
    "AnthropicProvider",
    "CompletionResult",
    "LLMProvider",
    "OpenAIProvider",
    "StreamEvent",
    "ToolCall",
    "compress_messages",
    "create_provider",
    "estimate_tokens",
    "is_tool_error",
]
