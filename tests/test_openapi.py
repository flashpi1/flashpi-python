"""The generator of src/flashpi/types/_generated.py and the faithfulness of what it generates."""

import json
import types
import typing
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, Union, cast, get_args, get_origin

import pytest
from scripts import openapi
from scripts.openapi import GenerationError, generate

from flashpi.types import _generated

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "openapi" / "openapi.json").read_text(encoding="utf-8"))
SCHEMAS: dict[str, Any] = CONTRACT["components"]["schemas"]


def test_the_generated_types_match_the_committed_contract() -> None:
    contract = (ROOT / "openapi" / "openapi.json").read_text(encoding="utf-8")
    expected = (ROOT / "src" / "flashpi" / "types" / "_generated.py").read_text(encoding="utf-8")
    assert generate(contract) == expected


def test_check_passes_and_bad_arguments_are_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert openapi.main(["openapi.py", "check"]) == 0
    assert "matches" in capsys.readouterr().out
    assert openapi.main(["openapi.py", "publish"]) == 2
    assert openapi.main(["openapi.py", "check", "extra"]) == 2


def test_check_fails_when_the_generated_file_is_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = tmp_path / "_generated.py"
    stale.write_text("# stale\n", encoding="utf-8")
    monkeypatch.setattr(openapi, "TYPES_PATH", stale)
    monkeypatch.setattr(openapi, "ROOT", tmp_path)
    assert openapi.main(["openapi.py", "check"]) == 1
    assert "out of date" in capsys.readouterr().err
    assert openapi.main(["openapi.py", "generate"]) == 0
    assert openapi.main(["openapi.py", "check"]) == 0


def test_sync_copies_a_local_file_and_generates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.json"
    source.write_text((ROOT / "openapi" / "openapi.json").read_text(encoding="utf-8").rstrip())
    contract = tmp_path / "openapi.json"
    generated = tmp_path / "_generated.py"
    monkeypatch.setenv("FLASHPI_OPENAPI_FILE", str(source))
    monkeypatch.setattr(openapi, "CONTRACT_PATH", contract)
    monkeypatch.setattr(openapi, "TYPES_PATH", generated)
    monkeypatch.setattr(openapi, "ROOT", tmp_path)
    assert openapi.main(["openapi.py", "sync"]) == 0
    assert contract.read_text(encoding="utf-8").endswith("}\n")
    assert generated.read_text(encoding="utf-8") == generate(contract.read_text(encoding="utf-8"))


def test_sync_refuses_a_plain_http_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLASHPI_OPENAPI_FILE", raising=False)
    monkeypatch.setenv("FLASHPI_OPENAPI_URL", "http://example.com/openapi.json")
    with pytest.raises(SystemExit, match="non-HTTPS"):
        openapi.main(["openapi.py", "sync"])


# Faithfulness: every member of every schema has the type and the required flag of the document.


def resolve(name: str) -> Any:
    return getattr(_generated, name)


def is_typed_dict(value: object) -> bool:
    return isinstance(value, type) and hasattr(value, "__required_keys__")


def flatten(annotation: Any) -> list[Any]:
    """The members of a union (aliases of unions included)."""
    if get_origin(annotation) in (Union, types.UnionType):
        return [member for argument in get_args(annotation) for member in flatten(argument)]
    return [annotation]


def check(schema: dict[str, Any], annotation: Any, where: str) -> None:
    """Asserts that `annotation` is the faithful translation of `schema`."""
    members = flatten(annotation)
    declared = schema.get("type")
    nullable = (isinstance(declared, list) and "null" in declared) or None in schema.get("enum", [])
    if "$ref" in schema:
        assert members == flatten(resolve(schema["$ref"].rsplit("/", 1)[1])), where
        return
    if "allOf" in schema:
        check(schema["allOf"][0], annotation, where)
        return
    for combinator in ("anyOf", "oneOf"):
        if combinator in schema:
            # The document only combines references and null: compare the flattened members.
            expected: list[Any] = []
            for option in schema[combinator]:
                if "$ref" in option:
                    expected += flatten(resolve(option["$ref"].rsplit("/", 1)[1]))
                else:
                    assert option == {"type": "null"}, where
                    expected.append(type(None))
            assert members == expected, where
            return
    if nullable:
        assert type(None) in members, where
        members = [member for member in members if member is not type(None)]
    elif declared == "null":
        assert members == [type(None)], where
        return
    else:
        assert type(None) not in members, where
    assert len(members) == 1, where
    member = members[0]
    kinds = [declared] if isinstance(declared, str) else cast("list[str]", declared or [])
    kind = next(k for k in kinds if k != "null")
    if "enum" in schema or "const" in schema:
        values = [value for value in schema.get("enum", [schema.get("const")]) if value is not None]
        assert get_origin(member) is Literal, where
        assert list(get_args(member)) == values, where
    elif kind == "array":
        assert get_origin(member) is list, where
        check(schema["items"], get_args(member)[0], f"{where}[]")
    elif kind == "object" and "properties" not in schema:
        assert get_origin(member) is dict, where
        check(schema["additionalProperties"], get_args(member)[1], f"{where}{{}}")
    elif kind == "object":
        check_typed_dict(schema, member, where)
    else:
        scalars: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}
        scalar = bytes if schema.get("format") == "binary" else scalars[kind]
        assert member is scalar, where


def check_typed_dict(schema: dict[str, Any], typed_dict: Any, where: str) -> None:
    assert is_typed_dict(typed_dict), where
    properties: dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))
    assert set(typed_dict.__required_keys__) == required, where
    assert set(typed_dict.__optional_keys__) == set(properties) - required, where
    hints = typing.get_type_hints(typed_dict)
    assert list(hints) == list(properties), where
    for key, member in properties.items():
        check(member, hints[key], f"{where}.{key}")


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_each_schema_is_translated_faithfully(name: str) -> None:
    schema = SCHEMAS[name]
    generated = resolve(name)
    if is_typed_dict(generated):
        check_typed_dict(schema, generated, name)
    else:
        check(schema, generated, name)


def test_each_list_query_is_a_typed_dict_of_optional_members() -> None:
    queries = {
        operation["operationId"]: [
            p for p in operation.get("parameters", []) if p.get("in") == "query"
        ]
        for item in CONTRACT["paths"].values()
        for operation in item.values()
    }
    with_query = {name: parameters for name, parameters in queries.items() if parameters}
    assert sorted(with_query) == [
        "certificatesList",
        "documentsList",
        "emissionPointsList",
        "establishmentsList",
        "eventsList",
        "issuersList",
        "webhookEndpointsDeliveriesList",
        "webhookEndpointsList",
    ]
    for operation_id, parameters in with_query.items():
        query = resolve(f"{operation_id[0].upper()}{operation_id[1:]}Query")
        check_typed_dict(
            {"properties": {p["name"]: p["schema"] for p in parameters}, "required": []},
            query,
            operation_id,
        )


def test_events_are_a_union_discriminated_by_type() -> None:
    members = flatten(_generated.Event)
    assert members == [
        _generated.DocumentEvent,
        _generated.CertificateEvent,
        _generated.AccountEvent,
    ]
    mapping: dict[str, str] = SCHEMAS["Event"]["discriminator"]["mapping"]
    for event_type, target in mapping.items():
        member = resolve(target.rsplit("/", 1)[1])
        assert event_type in get_args(typing.get_type_hints(member)["type"])
    assert "data" not in _generated.EventThin.__annotations__


# The generator refuses what it cannot translate faithfully.


def document(schemas: dict[str, Any], **extra: Any) -> str:
    return json.dumps(
        {"openapi": "3.1.0", "paths": {}, "components": {"schemas": schemas}, **extra}
    )


UNSUPPORTED = cast(
    "list[tuple[dict[str, Any], str]]",
    [
        (
            {"A": {"type": "object", "properties": {"x": {"type": "string", "if": {}}}}},
            "unsupported",
        ),
        ({"A": {"allOf": [{"type": "string"}, {"type": "integer"}]}}, "one member"),
        ({"A": {"type": ["string", "integer"]}}, "several non-null types"),
        ({"A": {"type": "string", "not": {"const": "x"}}}, "only supported on objects"),
        ({"A": {"type": "object", "not": {"const": 1}, "properties": {}}}, "not.required"),
        (
            {"A": {"type": "object", "not": {"required": ["x"]}, "properties": {"x": {}}}},
            "declared and forbidden",
        ),
        ({"A": {"type": "object", "properties": {"class": {"type": "string"}}}}, "valid Python"),
        ({"A": {"type": "object", "properties": {"x-y": {"type": "string"}}}}, "valid Python"),
        ({"A": {"type": "object", "properties": {}, "required": ["x"]}}, "without a schema"),
        ({"A": {"$ref": "#/components/schemas/B"}}, "unknown reference"),
        ({"A": {"$ref": "#/components/schemas/A", "type": "string"}}, "sibling"),
        ({"A": {"type": "string", "enum": [1.5]}}, "enum values"),
        ({"A": {"type": "string", "enum": [None]}}, "no values"),
        ({"A": {"type": "tuple"}}, "unsupported type"),
        ({"A": {"anyOf": [{"type": "string"}], "type": "object"}}, "anyOf with type"),
        ({"A": {"type": "string", "properties": {}}}, "mixed with other types"),
        ({"A": {"enum": ["a"], "properties": {}}}, "mixed with other types"),
        (
            {
                "A": {"type": "object", "properties": {"x": {"type": "string", "enum": ["a"]}}},
                "AX": {"type": "string"},
            },
            "Two definitions",
        ),
        (
            {"A": {"type": "object", "properties": {"b": {"$ref": "#/components/schemas/A"}}}},
            "refers to itself",
        ),
        (
            {
                "A": {"type": "object", "properties": {"t": {"type": "string", "enum": ["a"]}}},
                "U": {
                    "oneOf": [{"$ref": "#/components/schemas/A"}],
                    "discriminator": {
                        "propertyName": "t",
                        "mapping": {"b": "#/components/schemas/A"},
                    },
                },
            },
            "does not allow b",
        ),
        (
            {
                "A": {"type": "object", "properties": {}},
                "B": {"type": "object", "properties": {}},
                "U": {
                    "oneOf": [{"$ref": "#/components/schemas/A"}],
                    "discriminator": {
                        "propertyName": "t",
                        "mapping": {"b": "#/components/schemas/B"},
                    },
                },
            },
            "outside the union",
        ),
        (
            {
                "U": {
                    "oneOf": [{"type": "object", "properties": {}}],
                    "discriminator": {"propertyName": "t"},
                },
            },
            "references only",
        ),
        ({"A": {"type": "object", "properties": {}, "additionalProperties": {}}}, "typed members"),
    ],
)


@pytest.mark.parametrize(("schemas", "message"), UNSUPPORTED)
def test_unsupported_constructs_fail_loudly(schemas: dict[str, Any], message: str) -> None:
    with pytest.raises(GenerationError, match=message):
        generate(document(schemas))


def test_refuses_other_openapi_versions() -> None:
    with pytest.raises(GenerationError, match=r"3\.1"):
        generate(json.dumps({"openapi": "3.0.3", "paths": {}}))


def test_refuses_unknown_parameter_references() -> None:
    paths = {"/x": {"get": {"operationId": "x", "parameters": [{"$ref": "#/nowhere"}]}}}
    with pytest.raises(GenerationError, match="unknown parameter"):
        generate(json.dumps({"openapi": "3.1.0", "paths": paths}))


def test_refuses_query_names_that_are_not_python_names() -> None:
    parameter = {"name": "from", "in": "query", "schema": {"type": "string"}}
    paths = {"/x": {"get": {"operationId": "x", "parameters": [parameter]}}}
    with pytest.raises(GenerationError, match="valid Python name"):
        generate(json.dumps({"openapi": "3.1.0", "paths": paths}))


def test_translates_the_other_supported_constructs() -> None:
    schemas: dict[str, Any] = {
        "Bag": {"type": "object", "additionalProperties": {"type": "integer"}},
        "Anything": {"type": "object"},
        "Free": {"type": "object", "additionalProperties": True},
        "Flag": {"type": ["boolean", "null"], "const": True, "description": 'Say "yes"'},
        "Plain": {"description": "Any JSON value."},
        "Empty": {"type": "object", "properties": {}},
        "ALongEnoughNameForTheUnionToGoBeyondTheLimit": {"type": "string"},
        "Long": {
            "anyOf": [
                {"$ref": f"#/components/schemas/{name}"}
                for name in (
                    "Bag",
                    "Free",
                    "Empty",
                    "ALongEnoughNameForTheUnionToGoBeyondTheLimit",
                    "Anything",
                )
            ]
            + [{"type": "string"}, {"type": "null"}],
            "description": "word " * 40,
        },
    }
    source = generate(document(schemas))
    assert "Bag: TypeAlias = dict[str, int]" in source
    assert "Anything: TypeAlias = dict[str, object]" in source
    assert "Free: TypeAlias = dict[str, object]" in source
    assert 'Flag: TypeAlias = Literal[True] | None\n"""Say "yes\\""""' in source
    assert "Plain: TypeAlias = object" in source
    assert "class Empty(TypedDict):\n    pass" in source
    assert (
        "Long: TypeAlias = (\n    Bag\n    | Free\n    | Empty\n"
        "    | ALongEnoughNameForTheUnionToGoBeyondTheLimit\n"
        "    | Anything\n    | str\n    | None\n)\n" + '"""word word'
    ) in source
    assert 'word"""' in source
    namespace: dict[str, object] = {}
    exec(compile(source, "<generated>", "exec"), namespace)  # noqa: S102
    assert cast(type, namespace["Empty"]).__name__ == "Empty"


def test_the_generated_module_is_valid_typed_python() -> None:
    class Probe(TypedDict):
        optional: NotRequired[int]

    assert Probe.__optional_keys__ == frozenset({"optional"})
    assert _generated.Document.__required_keys__ >= {"id", "type", "status", "environment"}
    assert "options" in _generated.CreateInvoice.__optional_keys__
