"""User-visible resource statistics and recent activity reports."""


def logs(kernel, limit=15):
    """List recent system calls without exposing other users' history."""
    user = kernel.require_login()
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        from errors import InvalidOperation
        raise InvalidOperation("Укажите количество записей от 1 до 100")
    if kernel.is_admin():
        return kernel.database.fetchall(
            "SELECT l.id, l.name, l.arguments, l.status, l.created_at, "
            "COALESCE(u.login, 'guest') AS owner "
            "FROM syscalls_log l LEFT JOIN users u ON u.id=l.user_id "
            "ORDER BY l.id DESC LIMIT ?", (limit,)
        )
    return kernel.database.fetchall(
        "SELECT l.id, l.name, l.arguments, l.status, l.created_at, "
        "u.login AS owner FROM syscalls_log l JOIN users u ON u.id=l.user_id "
        "WHERE l.user_id=? ORDER BY l.id DESC LIMIT ?", (user["id"], limit)
    )


def report(kernel):
    """Count accessible files, directories, bytes and recent user actions."""
    user = kernel.require_login()
    where = "" if kernel.is_admin() else " WHERE owner_id = ?"
    params = () if kernel.is_admin() else (user["id"],)
    objects = kernel.database.fetchall(
        "SELECT kind, content FROM files" + where, params
    )
    file_count = sum(node["kind"] == "file" for node in objects)
    dir_count = sum(node["kind"] == "dir" for node in objects)
    total_bytes = sum(len(node["content"].encode("utf-8"))
                      for node in objects if node["kind"] == "file")
    # Reports explicitly include the actions of the current user.
    actions = kernel.database.fetchall(
        "SELECT name, status, created_at FROM syscalls_log "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user["id"],)
    )
    return {"files": file_count, "directories": dir_count,
            "bytes": total_bytes, "recent_actions": actions}
