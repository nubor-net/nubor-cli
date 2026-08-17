from __future__ import annotations

import json

from nubor.core.output import emit


def test_table_uses_uppercase_headers_and_row_values(capsys):
    emit([{"name": "probe", "status": "ACTIVE"}], ["name", "status"], "table")
    out = capsys.readouterr().out
    assert "NAME" in out
    assert "probe" in out


def test_json_output_parses(capsys):
    emit([{"name": "probe", "size": 10}], ["name", "size"], "json")
    rows = json.loads(capsys.readouterr().out)
    assert rows == [{"name": "probe", "size": 10}]


def test_yaml_never_leaks_python_object_tags(capsys):
    # SDK resources carry internal wrapper types; the JSON round-trip in
    # emit() must flatten them before yaml serialization sees them.
    class Wrapper:
        def __str__(self):
            return "flattened"

    emit([{"location": Wrapper()}], ["location"], "yaml")
    out = capsys.readouterr().out
    assert "python/object" not in out
    assert "flattened" in out
