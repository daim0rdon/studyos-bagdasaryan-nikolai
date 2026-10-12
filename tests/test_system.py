"""User, process, memory, system-call logging and report tests."""

import tempfile
import unittest
from pathlib import Path

import auth
import reports
from db import Database
from errors import AccessDenied, AlreadyExists, InsufficientMemory, InvalidOperation
from kernel import Kernel
from scheduler import Scheduler
from syscalls import SyscallRouter


class SystemTests(unittest.TestCase):
    """Test the remaining components of the simulated operating system."""

    def setUp(self):
        """Start a fresh instance with a privileged admin session."""
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "system.db")
        self.db = Database(self.path, memory_limit_kb=128)
        self.kernel = Kernel(self.db)
        auth.create_initial_admin(self.kernel, "administrator123")
        auth.login(self.kernel, "admin", "administrator123")
        self.router = SyscallRouter(self.kernel)
        self.scheduler = Scheduler(self.kernel)

    def tearDown(self):
        """Release all SQLite resources and the temporary directory."""
        self.db.close()
        self.tmp.cleanup()

    def test_password_is_exact_sha256(self):
        """Users store SHA-256 hashes rather than plaintext passwords."""
        digest = self.db.scalar("SELECT password_hash FROM users WHERE login='admin'")
        self.assertEqual(digest, auth.hash_password("administrator123"))
        self.assertEqual(len(digest), 64)

    def test_login_rejects_bad_password(self):
        """Invalid credentials cannot establish an authenticated session."""
        with self.assertRaises(AccessDenied):
            auth.login(self.kernel, "admin", "wrong password")

    def test_duplicate_registration_fails(self):
        """Duplicate logins are rejected before inserting home directories."""
        with self.assertRaises(AlreadyExists):
            auth.register_user(self.kernel, "admin", "password123")

    def test_regular_user_cannot_create_admin(self):
        """Register cannot be used to escalate privileges."""
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        with self.assertRaises(AccessDenied):
            auth.register_user(self.kernel, "otheruser", "password123", "admin")

    def test_user_process_runs_and_kills(self):
        """run allocates memory and kill releases the allocation."""
        self.scheduler.run("editor", 40)
        self.assertEqual(self.scheduler.mem()["used_kb"], 40)
        self.assertEqual(self.scheduler.ps()[0]["state"], "running")
        self.scheduler.kill(1)
        self.assertEqual(self.scheduler.mem()["used_kb"], 0)
        self.assertEqual(self.scheduler.ps()[0]["state"], "stopped")

    def test_memory_limit_blocks_excessive_process(self):
        """Processes that exceed the memory limit do not get created."""
        self.scheduler.run("first", 100)
        with self.assertRaises(InsufficientMemory):
            self.scheduler.run("too_big", 40)
        self.assertEqual(self.scheduler.mem()["used_kb"], 100)
        self.assertEqual(len(self.scheduler.ps()), 1)

    def test_user_cannot_kill_foreign_process(self):
        """Only the process owner or an admin can issue kill."""
        self.scheduler.run("rootjob", 20)
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        with self.assertRaises(AccessDenied):
            self.scheduler.kill(1)
        self.assertEqual(self.scheduler.mem()["used_kb"], 20)

    def test_admin_can_kill_foreign_process(self):
        """Admins can stop processes created by other users."""
        auth.register_user(self.kernel, "student", "password123")
        auth.login(self.kernel, "student", "password123")
        self.scheduler.run("studentjob", 12)
        auth.login(self.kernel, "admin", "administrator123")
        self.scheduler.kill(1)
        self.assertEqual(self.scheduler.mem()["free_kb"], 128)

    def test_log_records_denied_access(self):
        """System-call permission failures are logged with status DENIED."""
        auth.register_user(self.kernel, "student", "password123")
        self.router.invoke("login", "student", "password123")
        with self.assertRaises(AccessDenied):
            self.router.invoke("touch", "/home/admin/no.txt")
        record = self.db.fetchone(
            "SELECT name, status FROM syscalls_log ORDER BY id DESC LIMIT 1")
        self.assertEqual((record["name"], record["status"]), ("touch", "DENIED"))

    def test_log_redacts_password(self):
        """Successful login syscalls never store plaintext passwords."""
        self.router.invoke("login", "admin", "administrator123")
        record = self.db.fetchone(
            "SELECT arguments FROM syscalls_log ORDER BY id DESC LIMIT 1")
        self.assertIn("[REDACTED]", record["arguments"])
        self.assertNotIn("administrator123", record["arguments"])

    def test_report_counts_utf8_bytes_and_actions(self):
        """Reports count objects, UTF-8 bytes and recent user syscalls."""
        self.router.invoke("mkdir", "/home/admin/docs")
        self.router.invoke("touch", "/home/admin/docs/n.txt")
        self.router.invoke("write", "/home/admin/docs/n.txt", "ёж")
        result = self.router.invoke("report")
        self.assertEqual(result["bytes"], len("ёж".encode("utf-8")))
        self.assertGreaterEqual(result["files"], 1)
        self.assertTrue(result["recent_actions"])

    def test_process_and_memory_survive_restart(self):
        """Persisted process table and memory remain consistent on reopen."""
        self.scheduler.run("keeper", 24)
        self.db.close()
        self.db = Database(self.path)
        kernel = Kernel(self.db)
        self.assertEqual(kernel.next_pid, 2)
        self.assertEqual(kernel.used_memory, 24)

    def test_invalid_memory_value_is_rejected(self):
        """Zero and negative process memory allocations are rejected."""
        with self.assertRaises(InvalidOperation):
            self.scheduler.run("bad", 0)
        with self.assertRaises(InvalidOperation):
            self.scheduler.run("bad", -1)


if __name__ == "__main__":
    unittest.main()
