# lockgrain

Read two `uv.lock` files one changed field at a time, without known ordering noise.

[中文说明](docs/中文说明.md) · [Problem evidence and alternatives](docs/problem.md) · [TDD record](docs/tdd.md)

## Install

Requires **Python 3.11+**. No dependencies, package installation, account, or network access.
Keep `lockgrain.py` in this directory, or copy that single file into your project. Run it with Python:

```sh
python3 lockgrain.py --help
```

On Unix, optionally `chmod +x lockgrain.py` to run `./lockgrain.py` directly.
On Windows, use a Python 3.11+ interpreter, for example `py -3 lockgrain.py`.

## Minimal example

```sh
python3 lockgrain.py examples/before.lock examples/after.lock
```

```text
- package["corelib"].wheels[url="https://example.test/corelib-1.0.0.whl"].hash = "sha256:old"
+ package["corelib"].wheels[url="https://example.test/corelib-1.0.0.whl"].hash = "sha256:new"
```

The example also reorders resolution markers and extras; those changes disappear.
These fixtures are synthetic and are not intended for installation.
Exit **1** means the comparison succeeded and found changes.

For your own files:

```sh
python3 lockgrain.py saved-before.lock uv.lock
```

Both paths are explicit local files; filenames do not affect parsing. Use `--` before paths starting with `-`.
The tool never changes either input or invokes uv, Git, project code, or a service API.

## Reading the output

`-` is the previous value and `+` is the new value. Added and removed fields have one line.
Lines are sorted by field path. Strings and unusual keys are escaped, including terminal control characters.
TOML dates/times are printed without quotes to distinguish them from strings.
The output is a readable report, not a patch or a JSON document.

| Exit | Meaning |
| --- | --- |
| 0 | No field changes under the rules below |
| 1 | Field changes found |
| 2 | Invalid input or command usage; diagnostics on stderr |

## Exactly what ordering is ignored

TOML comments, whitespace, key order, and `[[package]]` order are ignored.
Within each package, the following known collections ignore order while retaining duplicates:

| Collection | Matching / normalization |
| --- | --- |
| Top-level and package `resolution-markers` | Sort strings; preserve the strings themselves |
| `wheels` | Match by exact `url` or `path`; compare each field, including hashes |
| `dependencies` | Match by exact name; repeated names use sorted occurrence numbers |
| `optional-dependencies.<group>` and `dev-dependencies.<group>` | Same dependency matching |
| `metadata.requires-dist` and `metadata.requires-dev.<group>` | Same dependency matching |
| `metadata.requires-dist[].extras` | Sort strings |

Unknown fields remain visible. **All other array ordering is preserved**, even when a field happens to be named `extras` or `resolution-markers` elsewhere.
Empty and absent containers are different.

Packages with unique names match by name. If either file has multiple packages with the same name,
the path includes exact version and source. A changed fork identity appears as removal plus addition.
Duplicate package identities or wheel identities are rejected instead of overwritten.

## Limits

- Supports UTF-8 `uv.lock` **format version 1**, inspected against uv **0.13.0** / revision 3. Each file is limited to **16 MiB**, inclusive. Requires ordinary files (symlinks to ordinary files work); no stdin, directories, or FIFOs.
- Validates the structures needed for comparison, not the entire uv schema or dependency graph. `No field changes` does not certify a valid, authentic, secure, or installable lockfile.
- Does not solve marker expressions, normalize version specifiers, strip URL slashes, or resolve dependencies. Equivalent strings can still appear as changes.
- Repeated dependency names are paired by sorted occurrence, not by a dependency solver. Adding a duplicate may produce extra removal/addition lines. No records are discarded.
- Reads each file once into memory. Keep inputs stable during the command; there is no concurrent-writer snapshot guarantee. Very deep nesting is rejected; memory use exceeds input size.
- An upgrade with many artifacts can still produce a long report. There is no truncation, risk scoring, Git integration, or support for other lockfile formats.
- Automated validation was run on Linux with Python 3.14.4. Python 3.11–3.13 and other operating systems were not executed in this environment.

## Develop and test

```sh
python3 -B -m unittest discover -s tests -v
```

Tests invoke the CLI as a real subprocess and verify exit codes, output, and unchanged input bytes.
Temporary files stay inside `.test-tmp/` in this project. The test suite runs without network access or third-party packages.
Each behavior was introduced through a failing test followed by its minimal implementation; see [the recorded cycles](docs/tdd.md).
