import pytest

import strands_poc.models as models


def test_build_model_defaults_to_bedrock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)

    created: dict[str, object] = {}

    class FakeBedrockModel:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    monkeypatch.setattr(models, "BedrockModel", FakeBedrockModel)

    result = models.build_model()

    assert isinstance(result, FakeBedrockModel)
    assert created == {
        "model_id": "apac.amazon.nova-lite-v1:0",
        "max_tokens": 4096,
    }


def test_build_model_requires_openrouter_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openrouter")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        models.build_model()


def test_build_model_configures_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test/model")

    created: dict[str, object] = {}

    class FakeLiteLLMModel:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    monkeypatch.setattr(models, "LiteLLMModel", FakeLiteLLMModel)

    result = models.build_model()

    assert isinstance(result, FakeLiteLLMModel)
    assert created == {
        "client_args": {"api_key": "test-key"},
        "model_id": "openrouter/test/model",
        "params": {"max_tokens": 4096},
    }
