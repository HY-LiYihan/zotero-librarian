from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        merged_env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        if env:
            merged_env.update(env)
        return subprocess.run(
            [sys.executable, "-m", "zotero_librarian", *args],
            cwd=ROOT,
            env=merged_env,
            text=True,
            capture_output=True,
            check=False,
        )

    def json_cli(self, *args: str, env: dict[str, str] | None = None) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
        result = self.run_cli("--json", *args, env=env)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - assertion detail
            self.fail(f"stdout is not JSON: {exc}\nstdout={result.stdout}\nstderr={result.stderr}")
        return result, payload

    def test_doctor_offline_is_machine_readable(self) -> None:
        result, payload = self.json_cli("doctor", "--offline")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual("0.1.1", payload["checks"]["package"]["version"])
        self.assertEqual("offline", payload["checks"]["zoteroBridge"]["reason"])

    def test_schema_and_skill_read(self) -> None:
        result, payload = self.json_cli("schema", "plan")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("key", payload["schema"]["fields"])

        result, payload = self.json_cli("skills", "read", "zotero-librarian")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("name: zotero-librarian", payload["content"])

    def test_writes_require_confirmation_or_explicit_raw_allowance(self) -> None:
        result, payload = self.json_cli("plan", "apply", "examples/edits.example.jsonl")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("confirmation_required", payload["error"]["code"])

        result, payload = self.json_cli("raw", "zot", "--", "exec", "return 1")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("forbidden_raw_command", payload["error"]["code"])

        result, payload = self.json_cli("raw", "zot", "--", "apply", "plan.jsonl")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("write_confirmation_required", payload["error"]["code"])

    def test_plan_apply_backs_up_before_fake_zot_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            log = tmp / "zot.log"
            fake_zot = tmp / "zot"
            fake_zot.write_text(
                "#!/bin/sh\n"
                f"echo \"$@\" >> {log}\n"
                "if [ \"$1\" = backup ]; then echo 'Backed up to: /tmp/fake.sqlite'; exit 0; fi\n"
                "if [ \"$1\" = apply ]; then echo '{\"ok\":true,\"applied\":1,\"opId\":\"fake\"}'; exit 0; fi\n"
                "echo '{}'\n",
                encoding="utf-8",
            )
            fake_zot.chmod(0o755)
            plan = tmp / "plan.jsonl"
            plan.write_text('{"key":"ABCD1234","addTags":["topic:nlp"]}\n', encoding="utf-8")
            result, payload = self.json_cli(
                "plan",
                "apply",
                str(plan),
                "--yes",
                env={"PATH": f"{tmp}:{os.environ['PATH']}"},
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(payload["ok"])
            self.assertIn("Backed up", payload["backup"])
            self.assertEqual({"ok": True, "applied": 1, "opId": "fake"}, payload["result"])
            self.assertEqual(["backup", f"apply {plan} --yes --json"], log.read_text(encoding="utf-8").splitlines())


if __name__ == "__main__":
    unittest.main()
