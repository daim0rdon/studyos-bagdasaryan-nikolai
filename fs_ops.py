"""Creating, reading, writing and recursively removing files or folders."""

import posixpath

from errors import InvalidOperation
from fs_core import (ensure_available, ensure_mutable, get_node,
                     guard_subtree, normalize, require_access,
                     require_owner, require_scope, validate_name,
                     writable_parent)


def resolve_owner(kernel, owner):
    """Resolve the owner of a newly created object without privilege bypass."""
    user = kernel.require_login()
    if owner is None:
        return user["id"]
    if isinstance(owner, str):
        record = kernel.database.fetchone(
            "SELECT id FROM users WHERE login = ?", (owner,)
        )
        if not record:
            raise InvalidOperation("Такого владельца не существует")
        owner = record["id"]
    if not isinstance(owner, int):
        raise InvalidOperation("Владелец должен быть ID или логином")
    if not kernel.is_admin() and owner != user["id"]:
        from errors import AccessDenied
        raise AccessDenied("Нельзя указать другого владельца")
    if not kernel.database.fetchone("SELECT id FROM users WHERE id = ?", (owner,)):
        raise InvalidOperation("Такого владельца не существует")
    return owner


def create_entry(kernel, path, kind, owner=None):
    """Create a file or directory under an existing writable parent."""
    path = normalize(path)
    name = validate_name(posixpath.basename(path))
    owner_id = resolve_owner(kernel, owner)
    with kernel.database.transaction():
        parent = writable_parent(kernel, path)
        ensure_available(kernel, path)
        kernel.database.execute(
            "INSERT INTO files(name, path, parent_id, kind, owner_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, path, parent["id"], kind, owner_id),
        )
    return f"Создан {('каталог' if kind == 'dir' else 'файл')}: {path}"


def write_file(kernel, path, content):
    """Replace a file's contents with the supplied UTF-8 text."""
    path = normalize(path)
    node = get_node(kernel, path)
    require_owner(kernel, node)
    if node["kind"] != "file":
        raise InvalidOperation("Запись возможна только в файл")
    with kernel.database.transaction():
        kernel.database.execute(
            "UPDATE files SET content = ? WHERE id = ?", (content, node["id"])
        )
    return f"Записано {len(content.encode('utf-8'))} байт: {path}"


def read_file(kernel, path):
    """Return file text, or an empty string when the file does not exist."""
    path = normalize(path)
    kernel.require_login()
    if path not in ("/", "/home"):
        require_scope(kernel, path)
    node = kernel.database.fetchone("SELECT * FROM files WHERE path = ?", (path,))
    if node is None:
        return ""
    require_access(kernel, node)
    if node["kind"] != "file":
        raise InvalidOperation("cat ожидает путь к файлу")
    return node["content"]


def remove_entry(kernel, path, expected_kind):
    """Remove a file or cascade-delete a directory and its children."""
    path = normalize(path)
    ensure_mutable(path)
    node = get_node(kernel, path)
    if node["kind"] != expected_kind:
        raise InvalidOperation("Тип объекта не подходит для команды")
    guard_subtree(kernel, path)
    with kernel.database.transaction():
        kernel.database.execute("DELETE FROM files WHERE id = ?", (node["id"],))
    if kernel.cwd == path or kernel.cwd.startswith(path + "/"):
        kernel.cwd = "/home" if kernel.is_admin() else f"/home/{kernel.current_user['login']}"
    return f"Удалено: {path}"
