#!/usr/bin/env python3
"""Read uv.lock changes one field at a time."""

import argparse
import json
from collections import Counter
from datetime import date, time
from pathlib import Path
import re
import stat
import sys
import tomllib

MAX_BYTES = 16 * 1024 * 1024


class InputError(Exception):
    """An input cannot be compared reliably."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def nonempty_string(value):
    return isinstance(value, str) and bool(value)


def records(value, label):
    require(isinstance(value, list) and all(isinstance(item, dict) for item in value),
            f"{label}: expected an array of tables")
    return value


def validate(document):
    identities = set()
    for package in records(document.get("package", []), "package"):
        require(nonempty_string(package.get("name")), "package.name: expected a nonempty string")
        require("version" not in package or nonempty_string(package["version"]),
                "package.version: expected a nonempty string")
        require(isinstance(package.get("source"), dict) and bool(package["source"]),
                "package.source: expected a nonempty table")
        identity = literal([package["name"], package.get("version"), package["source"]])
        require(identity not in identities, "duplicate package identity")
        identities.add(identity)
        for dependency in records(package.get("dependencies", []), "dependencies"):
            require(nonempty_string(dependency.get("name")),
                    "dependency.name: expected a nonempty string")
        wheel_identities = set()
        for wheel in records(package.get("wheels", []), "wheels"):
            keys = [key for key in ("url", "path") if key in wheel]
            require(len(keys) == 1 and nonempty_string(wheel[keys[0]]),
                    "wheel: expected exactly one nonempty url or path")
            identity = (keys[0], wheel[keys[0]])
            require(identity not in wheel_identities, "duplicate wheel identity")
            wheel_identities.add(identity)


def read_lock(path):
    try:
        source = Path(path)
        require(stat.S_ISREG(source.stat().st_mode), f"{literal(path)}: expected a regular file")
        with source.open("rb") as stream:
            data = stream.read(MAX_BYTES + 1)
        require(len(data) <= MAX_BYTES, f"{literal(path)}: file exceeds 16 MiB limit")
        document = tomllib.loads(data.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise InputError(f"{literal(path)}: invalid TOML") from error
    except UnicodeError as error:
        raise InputError(f"{literal(path)}: expected UTF-8") from error
    except OSError as error:
        raise InputError(f"{literal(path)}: cannot read ({error.strerror})") from error
    except RecursionError as error:
        raise InputError(f"{literal(path)}: nesting is too deep") from error
    if type(document.get("version")) is not int or document["version"] != 1:
        raise InputError(f"{literal(path)}: expected uv.lock format version 1")
    try:
        validate(document)
        document = normalize(document)
    except (InputError, RecursionError) as error:
        if isinstance(error, RecursionError):
            raise InputError(f"{literal(path)}: nesting is too deep") from error
        raise InputError(f"{literal(path)}: {error}") from error
    return document


def literal(value):
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(literal(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{literal(key)}: {literal(value[key])}" for key in sorted(value)) + "}"
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def field_path(parent, key):
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
        return f"{parent}.{key}"
    return f"{parent}[{literal(key)}]"


UNORDERED = {
    ("resolution-markers",),
    ("package", "*", "resolution-markers"),
    ("package", "*", "metadata", "requires-dist", "*", "extras"),
}


def normalize(value, location=()):
    if location in UNORDERED:
        require(isinstance(value, list) and all(isinstance(item, str) for item in value),
                f"{literal(location)}: expected a string array")
    if is_dependencies(location):
        for dependency in records(value, literal(location)):
            require(nonempty_string(dependency.get("name")),
                    "dependency.name: expected a nonempty string")
    if isinstance(value, dict):
        return {key: normalize(child, location + (key,)) for key, child in value.items()}
    if isinstance(value, list):
        children = [normalize(child, location + ("*",)) for child in value]
        return sorted(children, key=literal) if location in UNORDERED else children
    return value


def is_dependencies(location):
    if location in {
        ("package", "*", "dependencies"),
        ("package", "*", "metadata", "requires-dist"),
    }:
        return True
    return (
        len(location) == 4 and location[:2] == ("package", "*")
        and location[2] in {"optional-dependencies", "dev-dependencies"}
    ) or (
        len(location) == 5
        and location[:4] == ("package", "*", "metadata", "requires-dev")
    )


def fields(value, path, location):
    if isinstance(value, (dict, list)) and not value:
        return {path: literal(value)}
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            result.update(fields(child, field_path(path, key), location + (key,)))
        return result
    if isinstance(value, list) and is_dependencies(location):
        result = {}
        counts = Counter(dependency["name"] for dependency in value)
        occurrences = Counter()
        for dependency in sorted(value, key=literal):
            name = dependency["name"]
            occurrences[name] += 1
            suffix = f", occurrence={occurrences[name]}" if counts[name] > 1 else ""
            label = f'{path}[name={literal(name)}{suffix}]'
            result.update(fields(dependency, label, location + ("*",)))
        return result
    if isinstance(value, list) and location == ("package", "*", "wheels"):
        result = {}
        for wheel in value:
            key = "url" if "url" in wheel else "path"
            label = f"{path}[{key}={literal(wheel[key])}]"
            result.update(fields(wheel, label, location + ("*",)))
        return result
    return {path: literal(value)}


def project(document, forked_names):
    document = normalize(document)
    result = {}
    for key, value in document.items():
        if key == "package":
            if not value:
                result["package"] = "[]"
            for package in value:
                identity = literal(package["name"])
                if package["name"] in forked_names:
                    identity += f', version={literal(package.get("version"))}, source={literal(package["source"])}'
                result.update(fields(package, f"package[{identity}]", ("package", "*")))
        else:
            result.update(fields(value, field_path("lock", key), (key,)))
    return result


def main():
    parser = argparse.ArgumentParser(
        prog="lockgrain",
        description="Compare two uv.lock files by field, ignoring known ordering noise. Offline and read-only.",
        epilog="Exit status: 0 no field changes; 1 changes; 2 input or usage error.",
    )
    parser.add_argument("before", metavar="BEFORE", help="original uv.lock (any filename)")
    parser.add_argument("after", metavar="AFTER", help="updated uv.lock (any filename)")
    args = parser.parse_args()
    documents = [read_lock(path) for path in (args.before, args.after)]
    forked_names = set()
    for document in documents:
        counts = Counter(package["name"] for package in document.get("package", []))
        forked_names.update(name for name, count in counts.items() if count > 1)
    before, after = [project(document, forked_names) for document in documents]
    changes = []
    for path in sorted(before.keys() | after.keys()):
        if before.get(path) == after.get(path):
            continue
        if path in before:
            changes.append(f"- {path} = {before[path]}")
        if path in after:
            changes.append(f"+ {path} = {after[path]}")
    print("\n".join(changes) if changes else "No field changes.")
    return int(bool(changes))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except InputError as error:
        print(f"lockgrain: error: {error}", file=sys.stderr)
        sys.exit(2)
