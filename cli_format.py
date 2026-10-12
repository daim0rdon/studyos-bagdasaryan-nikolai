"""Human-readable shell help and formatting for system-call results."""

HELP = """Команды StudyOS (пути могут быть абсолютными или относительными):
  help                    справка
  register LOGIN          регистрация нового пользователя
  login LOGIN             вход (пароль запрашивается отдельно)
  logout                  выход из учётной записи
  whoami                  пользователь и роль
  pwd                     текущий каталог
  ls [PATH]               содержимое каталога
  cd PATH                 перейти в каталог
  mkdir PATH              создать каталог
  rmdir PATH              удалить каталог рекурсивно
  touch PATH              создать файл
  cat PATH                прочесть файл
  write PATH TEXT         записать текст (например: write notes.txt "Привет")
  rm PATH                 удалить файл
  rename PATH NEW_NAME    переименовать объект
  copy SRC DST            скопировать файл / каталог
  move SRC DST            переместить файл / каталог
  tree [PATH]             вывести дерево каталогов
  run NAME [MEMORY_KB]    создать процесс (по умолчанию 64 KB)
  ps                      список процессов
  kill PID                завершить процесс
  mem                     состояние памяти
  logs [COUNT]            последние системные вызовы (по умолчанию 15)
  report                  статистика файлов и последних действий
  exit                    выйти из оболочки
"""


def format_result(name, result):
    """Render structured subsystem responses as console-friendly text."""
    if name == "ls":
        return "\n".join(("[DIR] " if x["kind"] == "dir" else "[FILE] ")
                         + x["name"] for x in result) or "(пусто)"
    if name == "ps":
        rows = ["PID  Имя               Статус      KB   Владелец"]
        rows += [f"{x['pid']:<4} {x['name'][:17]:<17} {x['state']:<11} "
                 f"{x['memory_kb']:<4} {x['owner']}" for x in result]
        return "\n".join(rows)
    if name == "mem":
        return (f"Память: занято {result['used_kb']} KB / "
                f"{result['limit_kb']} KB; свободно {result['free_kb']} KB")
    if name == "logs":
        rows = ["ID   Время                Кто       Вызов       Статус   Аргументы"]
        rows += [f"{x['id']:<4} {x['created_at']}  {x['owner']:<9} "
                 f"{x['name']:<11} {x['status']:<8} {x['arguments']}" for x in result]
        return "\n".join(rows)
    if name == "report":
        actions = "\n".join(f"  {x['created_at']} {x['name']}: {x['status']}"
                            for x in result["recent_actions"]) or "  (пока нет)"
        return (f"Файлы: {result['files']}; каталоги: {result['directories']}; "
                f"объём: {result['bytes']} байт\nПоследние действия:\n{actions}")
    return str(result)
