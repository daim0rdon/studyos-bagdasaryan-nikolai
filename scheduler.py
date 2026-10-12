"""Simulated process scheduler with a persistent memory budget."""

from errors import AccessDenied, InsufficientMemory, InvalidOperation, NotFound


class Scheduler:
    """Manage fake processes rather than launching host OS programs."""

    def __init__(self, kernel):
        """Bind the scheduler to persistent and transient kernel state."""
        self.kernel = kernel

    def run(self, name, memory_kb=64):
        """Create a running process and allocate its requested memory."""
        user = self.kernel.require_login()
        if not name or len(name) > 100:
            raise InvalidOperation("Название процесса должно содержать 1–100 символов")
        if not isinstance(memory_kb, int) or memory_kb <= 0:
            raise InvalidOperation("Память должна быть целым положительным числом")
        db = self.kernel.database
        with db.transaction():
            memory = db.fetchone("SELECT * FROM memory_state WHERE id = 1")
            if memory["used_kb"] + memory_kb > memory["limit_kb"]:
                raise InsufficientMemory("Превышен лимит оперативной памяти")
            pid = self.kernel.next_pid
            db.execute(
                "INSERT INTO processes(pid, name, state, owner_id, memory_kb) "
                "VALUES (?, ?, 'running', ?, ?)",
                (pid, name, user["id"], memory_kb),
            )
            db.execute(
                "UPDATE memory_state SET used_kb = used_kb + ? WHERE id = 1",
                (memory_kb,),
            )
        self.kernel.refresh_resources()
        return f"Процесс запущен: PID={pid}, {name}, {memory_kb} KB"

    def ps(self):
        """List all processes for admins or own processes for users."""
        user = self.kernel.require_login()
        if self.kernel.is_admin():
            return self.kernel.database.fetchall(
                "SELECT p.pid, p.name, p.state, p.memory_kb, u.login AS owner "
                "FROM processes p JOIN users u ON p.owner_id = u.id ORDER BY p.pid"
            )
        return self.kernel.database.fetchall(
            "SELECT p.pid, p.name, p.state, p.memory_kb, u.login AS owner "
            "FROM processes p JOIN users u ON p.owner_id = u.id "
            "WHERE p.owner_id = ? ORDER BY p.pid", (user["id"],)
        )

    def kill(self, pid):
        """Stop an active process and return its memory to the pool."""
        user = self.kernel.require_login()
        db = self.kernel.database
        with db.transaction():
            process = db.fetchone("SELECT * FROM processes WHERE pid = ?", (pid,))
            if process is None:
                raise NotFound("Процесс с указанным PID не найден")
            if not self.kernel.is_admin() and process["owner_id"] != user["id"]:
                raise AccessDenied("Нельзя завершать чужой процесс")
            if process["state"] != "running":
                raise InvalidOperation("Процесс уже завершён")
            db.execute(
                "UPDATE processes SET state='stopped', "
                "terminated_at=CURRENT_TIMESTAMP WHERE pid=?", (pid,)
            )
            db.execute(
                "UPDATE memory_state SET used_kb = used_kb - ? WHERE id = 1",
                (process["memory_kb"],),
            )
        self.kernel.refresh_resources()
        return f"Процесс PID={pid} завершён"

    def mem(self):
        """Show simulated total, used and free memory in kilobytes."""
        self.kernel.require_login()
        memory = self.kernel.database.fetchone(
            "SELECT used_kb, limit_kb FROM memory_state WHERE id=1"
        )
        return {"used_kb": memory["used_kb"],
                "limit_kb": memory["limit_kb"],
                "free_kb": memory["limit_kb"] - memory["used_kb"]}
