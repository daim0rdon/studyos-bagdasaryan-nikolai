"""Working directory, directory listings and indented hierarchy output."""

from errors import InvalidOperation
from fs_core import can_read, get_node, normalize, require_access


def pwd(kernel):
    """Return the current absolute working directory."""
    kernel.require_login()
    return kernel.cwd


def cd(kernel, path):
    """Set the current directory after checking its type and permissions."""
    path = normalize(path)
    node = get_node(kernel, path)
    require_access(kernel, node)
    if node["kind"] != "dir":
        raise InvalidOperation("cd ожидает каталог")
    kernel.cwd = path
    return path


def children(kernel, parent_id):
    """Return only children visible to the current user."""
    rows = kernel.database.fetchall(
        "SELECT * FROM files WHERE parent_id = ? "
        "ORDER BY CASE kind WHEN 'dir' THEN 0 ELSE 1 END, name",
        (parent_id,),
    )
    return [node for node in rows if can_read(kernel, node)]


def ls(kernel, path):
    """List files/directories under an accessible absolute path."""
    node = get_node(kernel, path)
    require_access(kernel, node)
    if node["kind"] != "dir":
        raise InvalidOperation("ls ожидает каталог")
    return [{"name": item["name"], "kind": item["kind"],
             "path": item["path"]} for item in children(kernel, node["id"])]


def tree(kernel, path):
    """Produce an indented, human-readable directory tree."""
    path = normalize(path)
    node = get_node(kernel, path)
    require_access(kernel, node)
    if node["kind"] != "dir":
        raise InvalidOperation("tree ожидает каталог")
    lines = [path + ("" if path == "/" else "/")]

    def append_branch(parent_id, prefix=""):
        """Recursively append visible branches using box-drawing glyphs."""
        entries = children(kernel, parent_id)
        for index, entry in enumerate(entries):
            last = index == len(entries) - 1
            suffix = "/" if entry["kind"] == "dir" else ""
            lines.append(prefix + ("└── " if last else "├── ") + entry["name"] + suffix)
            if entry["kind"] == "dir":
                append_branch(entry["id"], prefix + ("    " if last else "│   "))

    append_branch(node["id"])
    return "\n".join(lines)
