"""Interactive StudyOS command shell with recoverable input errors."""

import getpass
import os
import posixpath
import shlex

import auth
from cli_format import HELP, format_result
from db import Database
from errors import InvalidOperation, StudyOSError
from kernel import Kernel
from syscalls import SyscallRouter


class Shell:
    """Translate shell commands into audited system calls."""

    def __init__(self, database_path=None):
        """Open the OS state without requiring third-party packages."""
        path = database_path or os.environ.get("STUDYOS_DB", "studyos.db")
        self.database = Database(path)
        self.kernel = Kernel(self.database)
        self.syscalls = SyscallRouter(self.kernel)

    def _path(self, path):
        """Resolve user-friendly relative paths into required absolute paths."""
        if path.startswith("/"):
            return posixpath.normpath(path)
        return posixpath.normpath(posixpath.join(self.kernel.cwd, path))

    @staticmethod
    def _arity(args, minimum, maximum=None):
        """Reject a command with too few or too many arguments."""
        maximum = minimum if maximum is None else maximum
        if not minimum <= len(args) <= maximum:
            raise InvalidOperation("Неверные аргументы. Введите help")

    @staticmethod
    def _secret(confirmation=False):
        """Read a password without echoing it or placing it in command logs."""
        password = getpass.getpass("Пароль: ")
        if confirmation and password != getpass.getpass("Повторите пароль: "):
            raise InvalidOperation("Пароли не совпадают")
        return password

    def setup_admin(self):
        """Initialize the administrator on the first launch only."""
        if auth.has_admin(self.kernel):
            return
        print("Первый запуск StudyOS. Создайте пароль администратора admin.")
        while True:
            try:
                password = self._secret(confirmation=True)
                auth.create_initial_admin(self.kernel, password)
                auth.login(self.kernel, "admin", password)
                print("Администратор создан. Вы вошли как admin.")
                return
            except StudyOSError as error:
                print(f"Ошибка: {error}. Повторите ввод.")

    def execute(self, line):
        """Parse a single shell line and return formatted console output."""
        try:
            words = shlex.split(line)
        except ValueError as error:
            raise InvalidOperation(f"Ошибка кавычек: {error}") from error
        if not words:
            return ""
        command, *args = words
        if command == "help":
            return HELP
        if command == "exit":
            return "__EXIT__"
        if command in ("register", "login"):
            self._arity(args, 1)
            password = self._secret(confirmation=command == "register")
            return self.syscalls.invoke(command, args[0], password)
        if command in ("logout", "whoami", "pwd", "ps", "mem", "report"):
            self._arity(args, 0)
            return format_result(command, self.syscalls.invoke(command))
        if command in ("ls", "tree"):
            self._arity(args, 0, 1)
            path = self._path(args[0]) if args else self.kernel.cwd
            return format_result(command, self.syscalls.invoke(command, path))
        if command == "logs":
            self._arity(args, 0, 1)
            count = self._positive_int(args[0]) if args else 15
            return format_result(command, self.syscalls.invoke(command, count))
        if command in ("cd", "mkdir", "rmdir", "touch", "cat", "rm"):
            self._arity(args, 1)
            return format_result(command, self.syscalls.invoke(command, self._path(args[0])))
        if command in ("rename", "copy", "move"):
            self._arity(args, 2)
            first = self._path(args[0])
            second = args[1] if command == "rename" else self._path(args[1])
            return format_result(command, self.syscalls.invoke(command, first, second))
        if command == "write":
            if len(args) < 2:
                raise InvalidOperation('Использование: write PATH "ТЕКСТ"')
            return format_result(command, self.syscalls.invoke(
                command, self._path(args[0]), " ".join(args[1:])
            ))
        if command == "run":
            self._arity(args, 1, 2)
            memory = self._positive_int(args[1]) if len(args) == 2 else 64
            return format_result(command, self.syscalls.invoke(command, args[0], memory))
        if command == "kill":
            self._arity(args, 1)
            return format_result(command, self.syscalls.invoke(
                command, self._positive_int(args[0])
            ))
        raise InvalidOperation(f"Неизвестная команда: {command}. Введите help")

    @staticmethod
    def _positive_int(value):
        """Parse a positive integer for PID, memory and log count."""
        try:
            result = int(value)
        except ValueError as error:
            raise InvalidOperation("Ожидалось целое положительное число") from error
        if result <= 0:
            raise InvalidOperation("Число должно быть положительным")
        return result

    def run(self):
        """Start an interactive loop that survives malformed user input."""
        print("StudyOS — учебная операционная система. Команда help — справка.")
        try:
            self.setup_admin()
            while True:
                user = self.kernel.current_user
                login = user["login"] if user else "guest"
                try:
                    line = input(f"{login}@studyos:{self.kernel.cwd}$ ")
                    result = self.execute(line)
                    if result == "__EXIT__":
                        break
                    if result:
                        print(result)
                except (StudyOSError, ValueError, TypeError) as error:
                    print(f"Ошибка: {error}")
                except KeyboardInterrupt:
                    print("\nДля выхода используйте exit")
        except (EOFError, KeyboardInterrupt):
            print("\nРабота завершена")
        finally:
            self.database.close()
