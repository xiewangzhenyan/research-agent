"""Exercise real Git commits/pushes against disposable local bare repositories."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "git_sync.py"


class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="research-agent-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "work"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        self.env = {
            **os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "RESEARCH_AGENT_SKIP_PUSH": "0",
        }
        # Hooks inherit Git-local environment; don't let a parent checkout leak in.
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
            self.env.pop(key, None)
        self.git("init", "--bare", str(self.remote))
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Sync Test")
        self.git("config", "user.email", "sync@example.invalid")
        self.git("remote", "add", "origin", str(self.remote))
        (self.repo / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.repo / "scripts/git_sync.py")
        self.write(".gitignore", ".env\n.env.*\n!.env.example\ndata/\n")
        self.write("README.md", "Research Agent\n")
        self.git("add", ".")
        self.git("commit", "-m", "Initial snapshot")
        self.sync("install")

    def run_command(self, command, check=True, env=None):
        result = subprocess.run(
            command, cwd=self.repo, env=env or self.env,
            capture_output=True, text=True, timeout=20,
        )
        if check and result.returncode:
            self.fail(result.stdout + result.stderr)
        return result

    def git(self, *args, check=True, env=None):
        return self.run_command(["git", *args], check, env)

    def sync(self, action, check=True):
        return self.run_command([sys.executable, "scripts/git_sync.py", action], check)

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)

    def remote_head(self, branch="main"):
        return self.git("--git-dir", str(self.remote), "rev-parse", f"refs/heads/{branch}").stdout.strip()

    def test_commit_pushes_current_branch_and_preserves_pre_commit(self):
        self.write(".git/hooks/pre-commit", "#!/bin/sh\necho checked > .git/pre-commit-ran\n")
        (self.repo / ".git/hooks/pre-commit").chmod(0o755)
        self.sync("install")
        self.git("checkout", "-b", "feature/research")
        self.write("README.md", "Updated\n")
        self.git("commit", "-am", "Document research")
        self.assertEqual(self.remote_head("feature/research"), self.git("rev-parse", "HEAD").stdout.strip())
        self.assertTrue((self.repo / ".git/pre-commit-ran").exists())
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "@{upstream}").stdout.strip(), "origin/feature/research")

    def test_secret_removed_in_later_commit_still_blocks_without_logging_value(self):
        secret = "ghp_" + "a" * 36
        self.write("credentials.txt", secret)
        self.git("add", "credentials.txt")
        result = self.git("commit", "-m", "Unsafe fixture")
        self.assertIn("Upload check blocked", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)
        self.git("rm", "credentials.txt")
        result = self.git("commit", "-m", "Remove fixture")
        self.assertIn("Upload check blocked", result.stderr)
        self.assertNotEqual(self.git("--git-dir", str(self.remote), "rev-parse", "refs/heads/main", check=False).returncode, 0)

    def test_force_added_env_blocks_even_for_manual_push(self):
        self.write(".env", "NOT_A_SECRET=local-only\n")
        self.git("add", "-f", ".env")
        self.git("commit", "-m", "Local configuration", env={**self.env, "RESEARCH_AGENT_SKIP_PUSH": "1"})
        result = self.git("push", "origin", "main", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("excluded by ignore rules", result.stderr)

    def test_local_env_secret_copied_to_source_blocks_push(self):
        secret = "local-" + "sensitive-value-" * 2
        self.write(".env", f"API_KEY={secret}\n")
        self.write("example.txt", secret)
        self.git("add", "example.txt")
        result = self.git("commit", "-m", "Accidental credential copy")
        self.assertIn("matches a local environment secret", result.stderr)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_divergent_remote_is_preserved_and_local_commit_survives(self):
        self.sync("push")
        other = self.root / "other"
        self.git("clone", "--branch", "main", str(self.remote), str(other))
        self.git("-C", str(other), "config", "user.name", "Other Developer")
        self.git("-C", str(other), "config", "user.email", "other@example.invalid")
        (other / "remote.txt").write_text("remote change")
        self.git("-C", str(other), "add", "remote.txt")
        self.git("-C", str(other), "commit", "-m", "Remote work")
        self.git("-C", str(other), "push")
        remote_before = self.remote_head()
        self.write("README.md", "Local change\n")
        result = self.git("commit", "-am", "Local work")
        self.assertIn("Auto-push failed", result.stderr)
        self.assertEqual(self.remote_head(), remote_before)
        self.assertNotEqual(self.git("rev-parse", "HEAD").stdout.strip(), remote_before)

    def test_network_failure_keeps_local_commit(self):
        self.sync("push")
        self.remote.rename(self.root / "remote-offline.git")
        self.write("README.md", "Offline work\n")
        result = self.git("commit", "-am", "Offline work")
        self.assertIn("Auto-push failed", result.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%s").stdout.strip(), "Offline work")

    def test_changed_remote_requires_review(self):
        self.git("remote", "set-url", "origin", str(self.root / "unexpected.git"))
        result = self.sync("push", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Origin changed", result.stderr)

    def test_existing_hook_is_not_overwritten(self):
        hook = self.repo / ".git/hooks/pre-push"
        hook.write_text("#!/bin/sh\necho existing\n")
        result = self.sync("install", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(hook.read_text(), "#!/bin/sh\necho existing\n")

    def test_missing_upload_hook_blocks_auto_push(self):
        (self.repo / ".git/hooks/pre-push").unlink()
        result = self.sync("push", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Upload hook changed or is missing", result.stderr)

    def test_paused_sync_keeps_new_commit_local(self):
        self.sync("push")
        before = self.remote_head()
        self.git("config", "--local", "researchAgent.autoPush", "false")
        self.write("README.md", "Draft\n")
        result = self.git("commit", "-am", "Draft")
        self.assertIn("Auto-push disabled", result.stdout + result.stderr)
        self.assertEqual(self.remote_head(), before)


if __name__ == "__main__":
    unittest.main()
