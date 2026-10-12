"""User registration, SHA-256 password verification and sessions."""

import hashlib
import hmac
import re

from errors import AccessDenied, AlreadyExists, InvalidOperation

LOGIN_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")


def hash_password(password):
    """Return the SHA-256 hex digest required by the assignment."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def has_admin(kernel):
    """Determine whether the initial administrator has been created."""
    return bool(kernel.database.scalar(
        "SELECT COUNT(*) FROM users WHERE role = 'admin'"
    ))


def register_user(kernel, login, password, role="user"):
    """Create an account and its /home/<login> directory atomically."""
    if role not in ("user", "admin"):
        raise InvalidOperation("Недопустимая роль")
    if role == "admin":
        if has_admin(kernel) and not kernel.is_admin():
            raise AccessDenied("Создавать администраторов может только admin")
        if not has_admin(kernel) and kernel.database.scalar(
            "SELECT COUNT(*) FROM users"
        ):
            raise AccessDenied("Первого администратора создают при инициализации")
    if not LOGIN_PATTERN.fullmatch(login):
        raise InvalidOperation("Логин: 3–32 латинские буквы, цифры, _ или -")
    if len(password) < 6:
        raise InvalidOperation("Пароль должен содержать не менее 6 символов")
    database = kernel.database
    if database.fetchone("SELECT id FROM users WHERE login = ?", (login,)):
        raise AlreadyExists("Пользователь уже существует")
    with database.transaction():
        cursor = database.execute(
            "INSERT INTO users(login, password_hash, role) VALUES (?, ?, ?)",
            (login, hash_password(password), role),
        )
        user_id = cursor.lastrowid
        parent = database.fetchone("SELECT id FROM files WHERE path = '/home'")
        database.execute(
            "INSERT INTO files(name, path, parent_id, kind, owner_id) "
            "VALUES (?, ?, ?, 'dir', ?)",
            (login, f"/home/{login}", parent["id"], user_id),
        )
    return f"Пользователь {login} зарегистрирован"


def create_initial_admin(kernel, password):
    """Create the first admin only while the user table is empty."""
    if kernel.database.scalar("SELECT COUNT(*) FROM users") != 0:
        raise AccessDenied("Первый администратор уже создан")
    return register_user(kernel, "admin", password, "admin")


def login(kernel, username, password):
    """Authenticate by comparing the stored SHA-256 password digest."""
    record = kernel.database.fetchone(
        "SELECT id, login, password_hash, role FROM users WHERE login = ?",
        (username,),
    )
    if not record or not hmac.compare_digest(
        record["password_hash"], hash_password(password)
    ):
        raise AccessDenied("Неверный логин или пароль")
    kernel.current_user = {
        "id": record["id"], "login": record["login"], "role": record["role"]
    }
    kernel.cwd = f"/home/{username}"
    return f"Вход выполнен: {username} ({record['role']})"


def logout(kernel):
    """End the active session and reset the current directory."""
    kernel.require_login()
    username = kernel.current_user["login"]
    kernel.current_user = None
    kernel.cwd = "/"
    return f"Выход из учётной записи {username}"
