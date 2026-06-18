"""Кастомные исключения для бота."""


class APIRequestError(Exception):
    """Ошибка, если с запросом к API что-то пошло не так."""


class InvalidAPIResponseError(Exception):
    """Ошибка, если API вернуло ответ не в том формате, который ждем."""


class InvalidHomeworkStatusError(Exception):
    """Ошибка, если у домашки прилетел непонятный статус."""


class MissingTokensError(Exception):
    """Ошибка, если не хватает обязательных переменных окружения."""
