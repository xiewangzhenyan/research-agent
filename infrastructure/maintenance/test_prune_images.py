"""Retention tests: a mistaken selection can destroy a required rollback."""

import unittest
from unittest.mock import patch

from prune_images import apply, select


def image(number, *tags, digests=None):
    return {"Id": str(number), "Created": f"2026-09-{number:02d}", "RepoTags": list(tags), "RepoDigests": digests or []}


class RetentionTests(unittest.TestCase):
    def test_keeps_all_container_images_and_two_unused_rollbacks_per_repository(self):
        images = [image(i, f"agent_backend:rollback-{i}") for i in range(1, 7)]
        images += [image(i + 10, f"agent-frontend:rollback-{i}") for i in range(1, 5)]
        remove, protected = select(images, {"1", "6"})
        self.assertEqual(protected, {"1", "6", "5", "4", "14", "13"})
        self.assertEqual({entry["id"] for entry in remove}, {"2", "3", "11", "12"})

    def test_excludes_other_projects_digests_dangling_and_current_tags(self):
        images = [
            image(1, "agent_backend:rollback-old", "other:backup"),
            image(2, "agent_backend:rollback-old", "agent_backend:dev"),
            image(3, "agent-frontend:rollback-old", "agent-frontend:latest"),
            image(4, "other:rollback-old"),
            image(5),
            image(6, "agent_backend:candidate"),
            image(7, "agent_backend:before-old", digests=["other@sha256:abc"]),
        ]
        self.assertEqual(select(images, set(), keep=0)[0], [])

    def test_all_obsolete_aliases_are_included(self):
        old = image(1, "agent_backend:rollback-old", "agent_backend:m1-review", digests=["agent_backend@sha256:abc"])
        self.assertEqual(select([old], set(), keep=0)[0], [{"id": "1", "tags": sorted(old["RepoTags"])}])

    def test_changed_inventory_aborts_before_any_deletion(self):
        images = [image(i, f"agent_backend:rollback-{i}") for i in range(1, 5)]
        remove, _ = select(images, set())
        with patch("prune_images.docker") as command:
            with self.assertRaises(RuntimeError):
                apply({"keep_unused_rollbacks": 2, "remove": remove}, images, {"1"})
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
