"""Hierarchical filesystem API; implementations live in focused modules."""

from fs_navigation import cd, ls, pwd, tree
from fs_ops import create_entry, read_file, remove_entry, write_file
from fs_transfer import copy, move, rename


class FileSystem:
    """Provide the full filesystem interface required by the specification."""

    def __init__(self, kernel):
        """Bind filesystem operations to a simulated kernel session."""
        self.kernel = kernel

    def mkdir(self, path, owner=None):
        """Create a directory in an existing parent directory."""
        return create_entry(self.kernel, path, "dir", owner)

    def rmdir(self, path):
        """Recursively delete a directory and its contents."""
        return remove_entry(self.kernel, path, "dir")

    def touch(self, path, owner=None):
        """Create a new empty file."""
        return create_entry(self.kernel, path, "file", owner)

    def write_file(self, path, content):
        """Overwrite a file's contents."""
        return write_file(self.kernel, path, content)

    def read_file(self, path):
        """Return file text or an empty string for a missing file."""
        return read_file(self.kernel, path)

    def rm(self, path):
        """Delete one file without removing its parent directory."""
        return remove_entry(self.kernel, path, "file")

    def copy(self, src, dst):
        """Recursively copy a file or directory tree."""
        return copy(self.kernel, src, dst)

    def move(self, src, dst):
        """Move a file or directory and update descendant paths."""
        return move(self.kernel, src, dst)

    def rename(self, path, new_name):
        """Rename a file or directory within its parent."""
        return rename(self.kernel, path, new_name)

    def cd(self, path):
        """Change the current working directory."""
        return cd(self.kernel, path)

    def pwd(self):
        """Return the current working directory."""
        return pwd(self.kernel)

    def ls(self, path=None):
        """List accessible children of a directory."""
        return ls(self.kernel, path or self.kernel.cwd)

    def tree(self, path=None):
        """Show an indented hierarchy of accessible files and folders."""
        return tree(self.kernel, path or self.kernel.cwd)
