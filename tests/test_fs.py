"""Filesystem integration tests; run with python -m tests.test_fs."""

import tempfile
import unittest
from pathlib import Path

import auth
from db import Database
from errors import AccessDenied, AlreadyExists, InvalidOperation, NotFound
from fs import FileSystem
from kernel import Kernel
from shell import Shell


class FileSystemTests(unittest.TestCase):
    """Check hierarchical storage, navigation and user permissions."""

    def setUp(self):
        """Create a fresh SQLite database for each test."""
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tmp.name) / "system.db"))
        self.kernel = Kernel(self.db)
        auth.create_initial_admin(self.kernel, "administrator123")
        auth.login(self.kernel, "admin", "administrator123")
        self.fs = FileSystem(self.kernel)
        self.root = "/home/admin"

    def tearDown(self):
        """Close and remove the isolated test database."""
        self.db.close()
        self.tmp.cleanup()

    def test_mkdir_creates_directory_with_parent(self):
        """mkdir stores parent_id, correct path and directory type."""
        self.fs.mkdir(self.root + "/docs")
        node = self.db.fetchone("SELECT * FROM files WHERE path=?", (self.root + "/docs",))
        parent = self.db.fetchone("SELECT * FROM files WHERE id=?", (node["parent_id"],))
        self.assertEqual(node["kind"], "dir")
        self.assertEqual(parent["path"], self.root)

    def test_mkdir_missing_parent_fails(self):
        """mkdir rejects directories whose parent does not exist."""
        with self.assertRaises(NotFound):
            self.fs.mkdir(self.root + "/absent/child")

    def test_mkdir_duplicate_fails(self):
        """No file or directory can occupy an existing path."""
        self.fs.mkdir(self.root + "/docs")
        with self.assertRaises(AlreadyExists):
            self.fs.mkdir(self.root + "/docs")

    def test_touch_and_empty_read(self):
        """touch creates a file with an initially empty string."""
        self.fs.touch(self.root + "/note.txt")
        self.assertEqual(self.fs.read_file(self.root + "/note.txt"), "")

    def test_write_and_read(self):
        """write and cat preserve Russian characters exactly."""
        path = self.root + "/note.txt"
        self.fs.touch(path)
        self.fs.write_file(path, "Привет, StudyOS!")
        self.assertEqual(self.fs.read_file(path), "Привет, StudyOS!")

    def test_read_missing_file_returns_empty_string(self):
        """Missing files are read as an empty string per the specification."""
        self.assertEqual(self.fs.read_file(self.root + "/missing.txt"), "")

    def test_rm_removes_only_a_file(self):
        """rm deletes a file and leaves its parent directory intact."""
        self.fs.mkdir(self.root + "/docs")
        self.fs.touch(self.root + "/docs/note.txt")
        self.fs.rm(self.root + "/docs/note.txt")
        self.assertIsNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/docs/note.txt",)))
        self.assertIsNotNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/docs",)))

    def test_rmdir_recursively_removes_descendants(self):
        """Deleting a directory cascades through all nested children."""
        self.fs.mkdir(self.root + "/a")
        self.fs.mkdir(self.root + "/a/b")
        self.fs.touch(self.root + "/a/b/c.txt")
        self.fs.rmdir(self.root + "/a")
        self.assertIsNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/a/b/c.txt",)))

    def test_rename_directory_updates_descendant_paths(self):
        """Renaming a folder preserves contents and updates all paths."""
        self.fs.mkdir(self.root + "/a")
        self.fs.touch(self.root + "/a/file.txt")
        self.fs.rename(self.root + "/a", "renamed")
        self.assertIsNotNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/renamed/file.txt",)))
        self.assertIsNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/a/file.txt",)))

    def test_copy_directory_is_deep_and_independent(self):
        """Recursive copies retain text but use independent parent IDs."""
        self.fs.mkdir(self.root + "/a")
        self.fs.touch(self.root + "/a/file.txt")
        self.fs.write_file(self.root + "/a/file.txt", "original")
        self.fs.copy(self.root + "/a", self.root + "/b")
        self.fs.write_file(self.root + "/b/file.txt", "changed")
        self.assertEqual(self.fs.read_file(self.root + "/a/file.txt"), "original")
        self.assertEqual(self.fs.read_file(self.root + "/b/file.txt"), "changed")

    def test_copy_file_into_existing_directory(self):
        """copy SRC existing-dir inserts a child with the same basename."""
        self.fs.touch(self.root + "/a.txt")
        self.fs.mkdir(self.root + "/folder")
        self.fs.copy(self.root + "/a.txt", self.root + "/folder")
        self.assertIsNotNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/folder/a.txt",)))

    def test_move_updates_parent_and_all_paths(self):
        """move changes parent links while preserving nested files."""
        self.fs.mkdir(self.root + "/a")
        self.fs.mkdir(self.root + "/a/b")
        self.fs.touch(self.root + "/a/b/f.txt")
        self.fs.move(self.root + "/a", self.root + "/new")
        self.assertIsNotNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/new/b/f.txt",)))
        self.assertIsNone(self.db.fetchone(
            "SELECT id FROM files WHERE path=?", (self.root + "/a",)))

    def test_pwd_cd_ls_and_tree(self):
        """Navigation and indentation expose the expected hierarchy."""
        self.fs.mkdir(self.root + "/docs")
        self.fs.touch(self.root + "/docs/note.txt")
        self.fs.cd(self.root + "/docs")
        self.assertEqual(self.fs.pwd(), self.root + "/docs")
        self.assertEqual(self.fs.ls()[0]["name"], "note.txt")
        self.assertIn("└── note.txt", self.fs.tree())

    def test_copy_into_own_subdirectory_fails(self):
        """copy rejects trying to copy a directory into its own child."""
        self.fs.mkdir(self.root + "/a")
        self.fs.mkdir(self.root + "/a/child")
        with self.assertRaises(InvalidOperation):
            self.fs.copy(self.root + "/a", self.root + "/a/child")

    def test_root_and_home_are_undeletable(self):
        """Protected system directories cannot be destroyed."""
        for path in ("/", "/home"):
            with self.assertRaises(AccessDenied):
                self.fs.rmdir(path)

    def test_user_cannot_create_outside_home(self):
        """A non-admin is confined to /home/<login>."""
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        with self.assertRaises(AccessDenied):
            self.fs.touch("/home/admin/hack.txt")
        with self.assertRaises(AccessDenied):
            self.fs.mkdir("/tmp")

    def test_user_cannot_read_or_modify_foreign_file(self):
        """An ordinary user cannot read, rename or remove another's data."""
        self.fs.touch(self.root + "/secret.txt")
        self.fs.write_file(self.root + "/secret.txt", "SECRET")
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        with self.assertRaises(AccessDenied):
            self.fs.read_file(self.root + "/secret.txt")
        with self.assertRaises(AccessDenied):
            self.fs.rm(self.root + "/secret.txt")
        with self.assertRaises(AccessDenied):
            self.fs.rename(self.root + "/secret.txt", "stolen.txt")

    def test_tree_hides_other_users(self):
        """Public /home navigation cannot enumerate other users' files."""
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        self.fs.cd("/home")
        self.assertEqual([item["name"] for item in self.fs.ls()], ["student"])
        self.assertNotIn("admin/", self.fs.tree("/home"))

    def test_copy_and_move_reject_foreign_tree(self):
        """Users cannot copy or relocate other users' folders."""
        self.fs.mkdir(self.root + "/private")
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        for operation in (self.fs.copy, self.fs.move):
            with self.assertRaises(AccessDenied):
                operation(self.root + "/private", "/home/student/other")

    def test_shell_relative_paths(self):
        """The CLI resolves relative paths before sending system calls."""
        shell = Shell(str(Path(self.tmp.name) / "cli.db"))
        try:
            auth.create_initial_admin(shell.kernel, "administrator123")
            auth.login(shell.kernel, "admin", "administrator123")
            shell.execute("mkdir docs")
            shell.execute("cd docs")
            shell.execute("touch note.txt")
            self.assertIn("note.txt", shell.execute("ls ."))
            self.assertEqual(shell.execute("pwd"), "/home/admin/docs")
        finally:
            shell.database.close()


if __name__ == "__main__":
    unittest.main()
