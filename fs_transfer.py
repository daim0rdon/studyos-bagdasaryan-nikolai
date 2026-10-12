"""Safe recursive copy, move and rename operations."""

import posixpath

from errors import InvalidOperation
from fs_core import (ensure_available, ensure_mutable, get_node,
                     guard_subtree, normalize, validate_name, writable_parent)


def destination(kernel, src, dst):
    """Resolve a destination directory to a final full destination path."""
    dst = normalize(dst)
    existing = kernel.database.fetchone("SELECT * FROM files WHERE path = ?", (dst,))
    if existing and existing["kind"] == "dir":
        dst = posixpath.join(dst, posixpath.basename(src))
    elif existing:
        ensure_available(kernel, dst)
    return dst


def validate_transfer(kernel, src, dst):
    """Check source ownership, safe destination and tree boundaries."""
    src = normalize(src)
    ensure_mutable(src)
    node = get_node(kernel, src)
    nodes = guard_subtree(kernel, src)
    dst = destination(kernel, src, dst)
    validate_name(posixpath.basename(dst))
    if dst == src or dst.startswith(src + "/"):
        raise InvalidOperation("Нельзя копировать/перемещать каталог внутрь себя")
    parent = writable_parent(kernel, dst)
    ensure_available(kernel, dst)
    return node, nodes, dst, parent


def repath(kernel, src, dst, node, parent):
    """Update an entire directory subtree and its root's parent link."""
    database = kernel.database
    prefix = src + "/"
    database.execute(
        "UPDATE files SET path = ? || substr(path, length(?) + 1) "
        "WHERE substr(path, 1, length(?)) = ?",
        (dst + "/", prefix, prefix, prefix),
    )
    database.execute(
        "UPDATE files SET path = ?, name = ?, parent_id = ? WHERE id = ?",
        (dst, posixpath.basename(dst), parent["id"], node["id"]),
    )


def move(kernel, src, dst):
    """Move a file or a whole directory tree preserving object ownership."""
    src = normalize(src)
    node, _, dst, parent = validate_transfer(kernel, src, dst)
    with kernel.database.transaction():
        repath(kernel, src, dst, node, parent)
    if kernel.cwd == src or kernel.cwd.startswith(src + "/"):
        kernel.cwd = dst + kernel.cwd[len(src):]
    return f"Перемещено: {src} -> {dst}"


def rename(kernel, path, new_name):
    """Rename an object without changing its parent directory."""
    validate_name(new_name)
    path = normalize(path)
    ensure_mutable(path)
    dst = posixpath.join(posixpath.dirname(path), new_name)
    return move(kernel, path, dst)


def copy(kernel, src, dst):
    """Deep-copy all nodes and fix parent IDs in the copied subtree."""
    src = normalize(src)
    _, nodes, dst, parent = validate_transfer(kernel, src, dst)
    database = kernel.database
    actor_id = kernel.require_login()["id"]
    id_map = {}
    with database.transaction():
        for index, node in enumerate(nodes):
            new_path = dst + node["path"][len(src):]
            new_parent = parent["id"] if index == 0 else id_map[node["parent_id"]]
            cursor = database.execute(
                "INSERT INTO files(name, path, parent_id, kind, content, owner_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (posixpath.basename(new_path), new_path, new_parent,
                 node["kind"], node["content"], actor_id),
            )
            id_map[node["id"]] = cursor.lastrowid
    return f"Скопировано: {src} -> {dst}"
