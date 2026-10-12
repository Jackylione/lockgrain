"""Black-box CLI tests; all fixtures and temporary files stay in this project."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "lockgrain.py"
BASE = '''version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "demo"
version = "1.0.0"
source = { virtual = "." }
'''


class CliTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.workspace = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.workspace.cleanup)
        self.folder = Path(self.workspace.name)

    def compare(self, before, after):
        paths = [self.folder / "before.lock", self.folder / "after.lock"]
        values = [value.encode() if isinstance(value, str) else value
                  for value in (before, after)]
        for path, value in zip(paths, values):
            path.write_bytes(value)
        result = subprocess.run(
            [sys.executable, "-B", str(CLI), *map(str, paths)],
            cwd=self.folder, capture_output=True, text=True, timeout=5,
        )
        for path, value in zip(paths, values):
            self.assertEqual(path.read_bytes(), value, "CLI modified its input")
        return result

    def test_identical_lockfiles_have_no_changes(self):
        result = self.compare(BASE, BASE)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, "No field changes.\n", ""))

    def test_version_change_is_shown_with_package_and_field(self):
        result = self.compare(BASE, BASE.replace('"1.0.0"', '"1.1.0"'))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (
            1,
            '- package["demo"].version = "1.0.0"\n'
            '+ package["demo"].version = "1.1.0"\n',
            "",
        ))

    def test_resolution_marker_order_is_ignored_at_known_locations(self):
        markers = '''resolution-markers = ["sys_platform == 'linux'", "sys_platform == 'win32'"]
'''
        before = BASE.replace("revision = 3\n", "revision = 3\n" + markers) + markers
        after = before.replace(
            '''["sys_platform == 'linux'", "sys_platform == 'win32'"]''',
            '''["sys_platform == 'win32'", "sys_platform == 'linux'"]''',
        )
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout), (0, "No field changes.\n"))

    def test_extras_reordering_does_not_hide_an_unrelated_version_update(self):
        before = BASE + '''
[package.metadata]
requires-dist = [{ name = "httpx", extras = ["socks", "http2"] }]
'''
        after = before.replace('["socks", "http2"]', '["http2", "socks"]')
        after = after.replace('"1.0.0"', '"1.1.0"')
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout), (
            1, '- package["demo"].version = "1.0.0"\n'
               '+ package["demo"].version = "1.1.0"\n',
        ))

    def test_wheel_hash_change_is_isolated_despite_wheel_reordering(self):
        a = '{ url = "https://example.test/a.whl", hash = "sha256:a", size = 10 }'
        b = '{ url = "https://example.test/b.whl", hash = "sha256:old", size = 20 }'
        before = BASE + f"wheels = [{a}, {b}]\n"
        after = BASE + f"wheels = [{b.replace('sha256:old', 'sha256:new')}, {a}]\n"
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (
            1,
            '- package["demo"].wheels[url="https://example.test/b.whl"].hash = "sha256:old"\n'
            '+ package["demo"].wheels[url="https://example.test/b.whl"].hash = "sha256:new"\n',
            "",
        ))

    def test_dependency_order_is_ignored_but_marker_changes_remain(self):
        a = '{ name = "httpx", marker = "sys_platform == \'linux\'" }'
        b = '{ name = "idna" }'
        result = self.compare(
            BASE + f"dependencies = [{a}, {b}]\n",
            BASE + f"dependencies = [{b}, {a.replace('linux', 'win32')}]\n",
        )
        self.assertEqual((result.returncode, result.stdout), (
            1,
            '- package["demo"].dependencies[name="httpx"].marker = "sys_platform == \'linux\'"\n'
            '+ package["demo"].dependencies[name="httpx"].marker = "sys_platform == \'win32\'"\n',
        ))

    def test_same_name_forks_keep_distinct_versions_and_sources(self):
        before = BASE + '''resolution-markers = ["sys_platform == 'linux'"]
[[package]]
name = "demo"
version = "2.0.0"
source = { registry = "https://example.test/simple" }
[[package]]
name = "demo"
version = "1.0.0"
source = { registry = "https://example.test/simple" }
'''
        result = self.compare(before, before.replace("linux", "win32"))
        label = 'package["demo", version="1.0.0", source={"virtual": "."}].resolution-markers'
        self.assertEqual((result.returncode, result.stdout), (
            1, f'- {label} = ["sys_platform == \'linux\'"]\n'
               f'+ {label} = ["sys_platform == \'win32\'"]\n',
        ))

    def test_repeated_dependency_names_do_not_overwrite_each_other(self):
        before = BASE + '''dependencies = [
{ name = "httpx", version = "1.0" },
{ name = "httpx", version = "2.0" },
]
'''
        after = BASE + '''dependencies = [
{ name = "httpx", version = "2.0" },
{ name = "httpx", version = "1.1" },
]
'''
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout), (
            1,
            '- package["demo"].dependencies[name="httpx", occurrence=1].version = "1.0"\n'
            '+ package["demo"].dependencies[name="httpx", occurrence=1].version = "1.1"\n',
        ))

    def test_invalid_toml_is_an_input_error_without_partial_output(self):
        result = self.compare(BASE, 'version = 1\n[[package]\n')
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("invalid TOML", result.stderr)
        self.assertIn("after.lock", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_or_unsupported_format_version_is_rejected(self):
        for payload in ("", "# empty\n", "version = 2", 'version = "1"', "version = true"):
            with self.subTest(payload=payload):
                result = self.compare(BASE, payload)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("expected uv.lock format version 1", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_malformed_uv_records_are_rejected_even_when_inputs_match(self):
        cases = [
            'version = 1\npackage = "bad"',
            'version = 1\npackage = [42]',
            BASE.replace('name = "demo"', 'name = 42'),
            BASE.replace('name = "demo"', 'name = ""'),
            BASE.replace('version = "1.0.0"', 'version = false'),
            BASE.replace('source = { virtual = "." }', 'source = {}'),
            BASE.replace('source = { virtual = "." }', ''),
            BASE + 'dependencies = [{}]\n',
            BASE + 'dependencies = "bad"\n',
            BASE + 'wheels = [{}]\n',
            BASE + 'wheels = [42]\n',
            BASE + 'wheels = "bad"\n',
            BASE + 'resolution-markers = "bad"\n',
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                result = self.compare(payload, payload)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("lockgrain: error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_duplicate_package_or_wheel_identity_is_not_silently_collapsed(self):
        duplicate_package = BASE + '''
[[package]]
name = "demo"
version = "1.0.0"
source = { virtual = "." }
'''
        duplicate_wheel = BASE + '''wheels = [
{ url = "https://example.test/a.whl", hash = "sha256:one" },
{ url = "https://example.test/a.whl", hash = "sha256:two" },
]
'''
        for payload, message in ((duplicate_package, "duplicate package identity"),
                                 (duplicate_wheel, "duplicate wheel identity")):
            with self.subTest(message=message):
                result = self.compare(payload, payload)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn(message, result.stderr)

    def test_unknown_fields_keep_order_and_empty_tables(self):
        before = BASE + '''[package.future]
extras = ["z", "a"]
resolution-markers = ["second", "first"]
'''
        after = BASE + '''[package.future]
extras = ["a", "z"]
resolution-markers = ["first", "second"]
empty = {}
'''
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout), (
            1,
            '+ package["demo"].future.empty = {}\n'
            '- package["demo"].future.extras = ["z", "a"]\n'
            '+ package["demo"].future.extras = ["a", "z"]\n'
            '- package["demo"].future.resolution-markers = ["second", "first"]\n'
            '+ package["demo"].future.resolution-markers = ["first", "second"]\n',
        ))

    def test_quoted_keys_cannot_collide_with_nested_paths_or_inject_lines(self):
        before = BASE + '''[package.future]
"a.b" = "old"
a = { b = "unchanged" }
"line\\nkey" = "old"
"\\u001b[31m" = "old"
'''
        result = self.compare(before, before.replace('"old"', '"new"'))
        self.assertEqual(result.returncode, 1)
        self.assertIn('- package["demo"].future["a.b"] = "old"\n', result.stdout)
        self.assertIn('+ package["demo"].future["a.b"] = "new"\n', result.stdout)
        self.assertIn('future["line\\nkey"]', result.stdout)
        self.assertIn('future["\\u001b[31m"]', result.stdout)
        self.assertNotIn("\x1b", result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 6)

    def test_empty_package_set_preserves_additions_and_removals(self):
        empty = 'version = 1\nrevision = 3\nrequires-python = ">=3.11"\npackage = []\n'
        removed = self.compare(BASE, empty)
        self.assertEqual((removed.returncode, removed.stdout), (
            1, '+ package = []\n'
               '- package["demo"].name = "demo"\n'
               '- package["demo"].source.virtual = "."\n'
               '- package["demo"].version = "1.0.0"\n',
        ))

        added = self.compare(empty, BASE)
        self.assertEqual((added.returncode, added.stdout), (
            1, '- package = []\n'
               '+ package["demo"].name = "demo"\n'
               '+ package["demo"].source.virtual = "."\n'
               '+ package["demo"].version = "1.0.0"\n',
        ))

    def test_non_utf8_input_is_a_clear_error(self):
        result = self.compare(BASE, b"version = 1\n# \xff\n")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("expected UTF-8", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_files_directories_and_pipes_fail_without_hanging(self):
        good = self.folder / "good.lock"
        good.write_text(BASE)
        cases = [(self.folder / "missing.lock", "cannot read"),
                 (self.folder, "regular file")]
        if hasattr(os, "mkfifo"):
            fifo = self.folder / "input.pipe"
            os.mkfifo(fifo)
            cases.append((fifo, "regular file"))
        for path, message in cases:
            with self.subTest(path=path.name):
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI), str(good), str(path)],
                    cwd=self.folder, capture_output=True, text=True, timeout=3,
                )
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn(message, result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_help_and_bad_argument_counts_have_documented_exit_codes(self):
        for arguments, expected in ((["--help"], 0), ([], 2),
                                    (["one"], 2), (["one", "two", "three"], 2)):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, "-B", str(CLI), *arguments],
                    cwd=self.folder, capture_output=True, text=True, timeout=3,
                )
                self.assertEqual(result.returncode, expected)
                self.assertIn("BEFORE AFTER", result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_file_size_limit_has_an_inclusive_boundary(self):
        prefix = b"version = 1\n#"
        boundary = prefix + b"x" * (16 * 1024 * 1024 - len(prefix))
        too_big = self.compare(BASE, boundary + b"x")
        self.assertEqual((too_big.returncode, too_big.stdout), (2, ""))
        self.assertIn("16 MiB", too_big.stderr)
        accepted = self.compare(boundary, boundary)
        self.assertEqual((accepted.returncode, accepted.stdout), (0, "No field changes.\n"))

    def test_named_dependency_groups_and_metadata_ignore_only_order(self):
        before = BASE + '''
[package.optional-dependencies]
web = [{ name = "httpx" }, { name = "idna" }]
[package.dev-dependencies]
test = [{ name = "pytest" }, { name = "coverage" }]
[package.metadata]
requires-dist = [{ name = "httpx", extras = ["socks", "http2"] }, { name = "idna" }]
[package.metadata.requires-dev]
test = [{ name = "pytest" }, { name = "coverage" }]
'''
        after = BASE + '''
[package.optional-dependencies]
web = [{ name = "idna" }, { name = "httpx" }]
[package.dev-dependencies]
test = [{ name = "coverage" }, { name = "pytest" }]
[package.metadata]
requires-dist = [{ name = "idna" }, { name = "httpx", extras = ["http2", "socks"] }]
[package.metadata.requires-dev]
test = [{ name = "coverage" }, { name = "pytest" }]
'''
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout), (0, "No field changes.\n"))
        result = self.compare(after, after.replace('{ name = "idna" }', '{ name = "idna", marker = "python_version > \'3.11\'" }', 1))
        self.assertEqual((result.returncode, result.stdout), (
            1, '+ package["demo"].optional-dependencies.web[name="idna"].marker = "python_version > \'3.11\'"\n',
        ))

    def test_unknown_toml_dates_keep_their_type(self):
        before = BASE + 'future = [2026-10-12, 12:30:00, 2026-10-12T12:30:00Z]\n'
        after = BASE + 'future = ["2026-10-12", "12:30:00", "2026-10-12T12:30:00+00:00"]\n'
        result = self.compare(before, after)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (
            1,
            '- package["demo"].future = [2026-10-12, 12:30:00, 2026-10-12T12:30:00+00:00]\n'
            '+ package["demo"].future = ["2026-10-12", "12:30:00", "2026-10-12T12:30:00+00:00"]\n',
            "",
        ))

    def test_excessive_nesting_is_a_controlled_input_error(self):
        nested = BASE + 'future = ' + '[' * 1200 + '0' + ']' * 1200
        result = self.compare(BASE, nested)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("nesting is too deep", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
