"""Path resolution and access checks shared by file-system modules."""

import posixpath

from errors import AccessDenied, AlreadyExists, InvalidOperation, NotFound


def normalize(path):
    """Normalize an absolute POSIX path; reject relative API inputs."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise InvalidOperation("Требуется полный путь, начинающийся с /")
    return posixpath.normpath(path)


def get_node(kernel, path):
    """Look up a node by absolute path, or report that it is absent."""
    result = kernel.database.fetchone(
        "SELECT * FROM files WHERE path = ?", (normalize(path),)
    )
    if not result:
        raise NotFound(f"Объект не найден: {path}")
    return result


def optional_node(kernel, path):
    """Look up an optional node by absolute path."""
    return kernel.database.fetchone(
        "SELECT * FROM files WHERE path = ?", (normalize(path),)
    )


def home_path(kernel):
    """Return the home directory of the authenticated user."""
    user = kernel.require_login()
    return f"/home/{user['login']}"


def require_scope(kernel, path):
    """Reject non-admin access outside the user's own home subtree."""
    path = normalize(path)
    if kernel.is_admin():
        return
    home = home_path(kernel)
    if path != home and not path.startswith(home + "/"):
        raise AccessDenied("Доступ разрешён только внутри домашнего каталога")


def can_read(kernel, node):
    """Return whether a node is visible to the current user."""
    user = kernel.require_login()
    return (kernel.is_admin() or node["path"] in ("/", "/home")
            or (node["owner_id"] == user["id"]
                and (node["path"] == home_path(kernel)
                     or node["path"].startswith(home_path(kernel) + "/"))))


def require_access(kernel, node):
    """Raise DENIED when the current user cannot access the node."""
    if not can_read(kernel, node):
        raise AccessDenied(f"Чужой файл или каталог: {node['path']}")


def require_owner(kernel, node):
    """Enforce ownership for all modifying operations."""
    kernel.require_login()
    require_scope(kernel, node["path"])
    if not kernel.is_admin() and node["owner_id"] != kernel.current_user["id"]:
        raise AccessDenied("Изменение чужого объекта запрещено")


def writable_parent(kernel, path):
    """Check the parent directory and destination scope before creation."""
    path = normalize(path)
    if path == "/":
        raise InvalidOperation("Корневой каталог нельзя заменить")
    require_scope(kernel, path)
    parent = get_node(kernel, posixpath.dirname(path))
    if parent["kind"] != "dir":
        raise InvalidOperation("Родительский объект не является каталогом")
    if not kernel.is_admin():
        require_owner(kernel, parent)
    return parent


def ensure_available(kernel, path):
    """Reject an existing destination path."""
    if optional_node(kernel, path):
        raise AlreadyExists(f"Объект уже существует: {path}")


def validate_name(name):
    """Validate a single file or directory name."""
    if (not isinstance(name, str) or not name or name in (".", "..")
            or "/" in name or "\x00" in name or len(name) > 255):
        raise InvalidOperation("Некорректное имя файла или каталога")
    return name


def subtree(kernel, path):
    """Return a node and all descendants in parent-first order."""
    path = normalize(path)
    return kernel.database.fetchall(
        "SELECT * FROM files WHERE path = ? "
        "OR substr(path, 1, length(?)) = ? "
        "ORDER BY length(path), id", (path, path + "/", path + "/")
    )


def guard_subtree(kernel, path):
    """Forbid operations on trees containing someone else's objects."""
    nodes = subtree(kernel, path)
    for node in nodes:
        require_owner(kernel, node)
    return nodes


def ensure_mutable(path):
    """Prevent accidental removal of structural system directories."""
    if normalize(path) in ("/", "/home"):
        raise AccessDenied("Системный каталог защищён от изменения")
