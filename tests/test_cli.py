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
        self.assertEqual("0.1.3", payload["checks"]["package"]["version"])
        self.assertEqual("offline", payload["checks"]["zoteroBridge"]["reason"])
        self.assertIn("skillReady", payload)
        self.assertIn("liveReady", payload)

    def test_skill_install_explains_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            codex_home = temp_root / ".codex"
            result, payload = self.json_cli(
                "skills",
                "install",
                "--codex",
                env={"CODEX_HOME": str(codex_home)},
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(payload["ok"])
            self.assertIn("Start a new Codex turn", payload["nextSteps"][0])
            self.assertTrue(any("uvx zotero-librarian --json doctor" in step for step in payload["nextSteps"]))
            self.assertTrue((codex_home / "skills" / "zotero-librarian" / "SKILL.md").exists())

            result, payload = self.json_cli(
                "doctor",
                "--offline",
                "--config",
                str(temp_root / "config.toml"),
                env={
                    "CODEX_HOME": str(codex_home),
                    "PATH": os.defpath,
                },
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(payload["ready"])
            self.assertTrue(payload["skillReady"])
            self.assertFalse(payload["liveReady"])
            self.assertFalse(payload["checks"]["zot"]["ok"])

            result = self.run_cli(
                "doctor",
                "--offline",
                "--config",
                str(temp_root / "config.toml"),
                env={
                    "CODEX_HOME": str(codex_home),
                    "PATH": os.defpath,
                },
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Skill install ready.", result.stdout)
            self.assertIn("Live Zotero access still requires", result.stdout)
            self.assertIn("zot            SKIP (live only)", result.stdout)
            self.assertNotIn("zot            FAIL", result.stdout)

            result = self.run_cli("skills", "install", "--help")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("uvx zotero-librarian skills install --codex", result.stdout)
            self.assertIn("uvx zotero-librarian --json doctor --offline", result.stdout)

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
