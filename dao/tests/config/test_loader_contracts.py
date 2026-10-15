"""Protect persisted configuration and UI schema contracts during Pydantic upgrades."""

import json
from pathlib import Path

import pytest

from dao.prog.config.loader import CURRENT_VERSION, VERSION_MODELS, ConfigurationLoader
from dao.prog.config.models.devices.boiler import BoilerDisabled, BoilerEnabled

EXAMPLE = Path(__file__).resolve().parents[2] / "data/options_example.json"


@pytest.mark.parametrize("boiler_enabled", [False, True])
def test_full_configuration_file_roundtrip_preserves_private_and_unknown_values(tmp_path, boiler_enabled):
    data = json.loads(EXAMPLE.read_text())
    data["boiler"]["boiler present"] = boiler_enabled
    data["future extension"] = {"label": "onbekend", "enabled": False, "limit": 0}
    data["homeassistant"]["token"] = "!secret ha_token"
    data["homeassistant"]["future nested field"] = {"keep": [0, False, None]}
    options = tmp_path / "options.json"
    secrets = tmp_path / "secrets.json"
    options.write_text(json.dumps(data))
    secrets.write_text(json.dumps({"ha_token": "synthetic-private-token"}))
    loader = ConfigurationLoader(options, secrets)
    first = loader.load_and_validate()
    dumped = first.model_dump(mode="json", by_alias=True, exclude_none=True)
    loader.save(dumped)
    persisted = json.loads(options.read_text())
    second = ConfigurationLoader(options, secrets).load_and_validate()

    assert second.model_dump(mode="json", by_alias=True, exclude_none=True) == dumped
    assert persisted["future extension"] == data["future extension"]
    assert persisted["homeassistant"]["future nested field"] == {"keep": [0, False, None]}
    assert persisted["homeassistant"]["token"] == "!secret ha_token"
    assert "synthetic-private-token" not in options.read_text()
    assert second.homeassistant.hasstoken.resolve(loader.secrets) == "synthetic-private-token"
    assert persisted["config_version"] == CURRENT_VERSION
    assert isinstance(second.boiler, BoilerEnabled if boiler_enabled else BoilerDisabled)
    assert persisted["boiler"]["entity actual temp."] == data["boiler"]["entity actual temp."]


def test_full_ui_schema_retains_aliases_discriminators_defaults_and_references():
    schema = VERSION_MODELS[CURRENT_VERSION].model_json_schema(by_alias=True)
    definitions = schema["$defs"]
    assert "homeassistant" in schema["properties"]
    assert definitions["EntityId"]["type"] == "string"
    for model in (BoilerDisabled, BoilerEnabled):
        branch = definitions[model.__name__]
        assert "boiler present" in branch["properties"]
        assert "boiler_present" not in branch["properties"]
        assert branch["properties"]["boiler present"]["default"] is (model is BoilerEnabled)
    enabled = definitions["BoilerEnabled"]
    assert "entity actual temp." in enabled["required"]
    assert enabled["properties"]["entity actual temp."]["$ref"].endswith("/EntityId")
    assert enabled["properties"]["cop"]["default"] == 3.0
    assert definitions["BoilerDisabled"]["additionalProperties"] is True
    boiler = next(branch for branch in schema["properties"]["boiler"]["anyOf"] if "discriminator" in branch)
    assert boiler["discriminator"]["propertyName"] == "boiler present"
    assert len(boiler["oneOf"]) == 2
