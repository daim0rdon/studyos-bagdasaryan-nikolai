"""Audited system-call gateway from the shell to the OS components."""

import json

import auth
import reports
from errors import AccessDenied, StudyOSError
from fs import FileSystem
from scheduler import Scheduler


class SyscallRouter:
    """Route all commands to subsystems and record their outcomes."""

    def __init__(self, kernel):
        """Initialize the file system and process scheduler."""
        self.kernel = kernel
        self.fs = FileSystem(kernel)
        self.scheduler = Scheduler(kernel)

    def invoke(self, name, *args):
        """Perform a system call and log OK, DENIED or ERROR outcomes."""
        before = self.kernel.current_user
        user_id = before["id"] if before else None
        outcome = "OK"
        try:
            result = self._dispatch(name, *args)
            return result
        except AccessDenied:
            outcome = "DENIED"
            raise
        except StudyOSError:
            outcome = "ERROR"
            raise
        except (ValueError, TypeError):
            outcome = "ERROR"
            raise
        finally:
            if name == "login" and self.kernel.current_user:
                user_id = self.kernel.current_user["id"]
            self._record(name, args, user_id, outcome)

    def _record(self, name, args, user_id, status):
        """Write a log entry without ever storing supplied passwords."""
        safe_args = list(args)
        if name in ("login", "register") and len(safe_args) > 1:
            safe_args[1] = "[REDACTED]"
        payload = json.dumps(safe_args, ensure_ascii=False, default=str)
        db = self.kernel.database
        with db.transaction():
            db.execute(
                "INSERT INTO syscalls_log(name, arguments, user_id, status) "
                "VALUES (?, ?, ?, ?)", (name, payload, user_id, status)
            )

    def _dispatch(self, name, *args):
        """Map the public syscall name to its implementation."""
        public = {
            "register": lambda: auth.register_user(self.kernel, *args),
            "login": lambda: auth.login(self.kernel, *args),
            "logout": lambda: auth.logout(self.kernel),
            "whoami": self.whoami,
            "pwd": self.fs.pwd,
            "ls": lambda: self.fs.ls(*args),
            "cd": lambda: self.fs.cd(*args),
            "mkdir": lambda: self.fs.mkdir(*args),
            "rmdir": lambda: self.fs.rmdir(*args),
            "touch": lambda: self.fs.touch(*args),
            "cat": lambda: self.fs.read_file(*args),
            "write": lambda: self.fs.write_file(*args),
            "rm": lambda: self.fs.rm(*args),
            "rename": lambda: self.fs.rename(*args),
            "copy": lambda: self.fs.copy(*args),
            "move": lambda: self.fs.move(*args),
            "tree": lambda: self.fs.tree(*args),
            "run": lambda: self.scheduler.run(*args),
            "ps": self.scheduler.ps,
            "kill": lambda: self.scheduler.kill(*args),
            "mem": self.scheduler.mem,
            "logs": lambda: reports.logs(self.kernel, *args),
            "report": lambda: reports.report(self.kernel),
        }
        if name not in public:
            from errors import InvalidOperation
            raise InvalidOperation("Неизвестный системный вызов")
        return public[name]()

    def whoami(self):
        """Return the active username and role."""
        user = self.kernel.require_login()
        return f"{user['login']} ({user['role']})"
