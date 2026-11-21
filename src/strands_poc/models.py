import os

from strands.models import BedrockModel
from strands.models.litellm import LiteLLMModel


def build_model():
    provider = os.environ.get("MODEL_PROVIDER", "bedrock").lower()

    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY env var is required when MODEL_PROVIDER=openrouter")
        model_id = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
        print(f"Using OpenRouter — model: {model_id}")
        return LiteLLMModel(
            client_args={"api_key": api_key},
            model_id=f"openrouter/{model_id}",
            params={"max_tokens": 4096},
        )

    model_id = os.environ.get("BEDROCK_MODEL_ID", "apac.amazon.nova-pro-v1:0")
    print(f"Using Bedrock — model: {model_id}")
    return BedrockModel(
        model_id=model_id,
        max_tokens=4096,
    )
