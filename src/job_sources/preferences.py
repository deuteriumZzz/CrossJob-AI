def effective_list(preferences: dict, source: str, key: str) -> list:
    """positions/locations площадки, если заданы в её блоке
    (work_preferences.yaml: <source>.positions/.locations) — иначе
    общий список верхнего уровня. Пустой override = не задан,
    падаем на общий (та же конвенция, что уже у top-level positions:
    [] в data_folder_example — "оставить пустым, чтобы вывести из
    резюме/использовать общее")."""
    override = (preferences.get(source) or {}).get(key)
    return override if override else preferences.get(key, [])
