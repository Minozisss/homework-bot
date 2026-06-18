"""Телеграм-бот, который следит за статусами домашних работ в Практикуме."""

import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telebot
from dotenv import load_dotenv

from exceptions import (
    APIRequestError,
    InvalidAPIResponseError,
    InvalidHomeworkStatusError,
    MissingTokensError,
)


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def configure_logging():
    """Настраивает логи для запуска бота как отдельной программы."""
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    )
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.propagate = False


def check_tokens():
    """Проверяет, что все нужные переменные окружения вообще есть."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    missing_tokens = []

    for token_name, token_value in tokens.items():
        if not token_value:
            missing_tokens.append(token_name)

    if missing_tokens:
        for token_name in missing_tokens:
            logger.critical(
                'Отсутствует обязательная переменная окружения: %r',
                token_name,
            )
        raise MissingTokensError(
            'Отсутствуют обязательные переменные окружения: '
            f'{", ".join(missing_tokens)}'
        )


def send_message(bot, message):
    """Отправляет сообщение в Телеграм и пишет в лог, как всё прошло."""
    logger.debug('Пробую отправить сообщение в Telegram "%s"', message)
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Бот отправил сообщение "%s"', message)
        return True
    except (
        telebot.apihelper.ApiException,
        requests.RequestException,
    ) as error:
        logger.error('Сбой при отправке сообщения в Telegram: %s', error)
        return False


def get_api_answer(timestamp):
    """Ходит в API Практикума и забирает свежий ответ по домашкам."""
    request_kwargs = {
        'headers': HEADERS,
        'params': {'from_date': timestamp},
    }
    logger.debug(
        'Начинаю запрос к API: url=%s, headers=%s, params=%s',
        ENDPOINT,
        request_kwargs['headers'],
        request_kwargs['params'],
    )

    try:
        response = requests.get(ENDPOINT, **request_kwargs)
    except requests.RequestException as error:
        raise APIRequestError(
            f'Ошибка при запросе к API Практикума: {error}'
        ) from error

    if response.status_code != HTTPStatus.OK:
        raise APIRequestError(
            f'API вернул неожиданный статус-код: {response.status_code}. '
            f'Адрес запроса: {ENDPOINT}'
        )

    return response.json()


def check_response(response):
    """Проверяет ответ API и достает из него список домашних работ."""
    if not isinstance(response, dict):
        raise TypeError('Ответ API должен быть словарем.')

    if 'homeworks' not in response:
        raise InvalidAPIResponseError(
            'В ответе API отсутствует ключ "homeworks".'
        )

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError('Значение ключа "homeworks" должно быть списком.')

    return homeworks


def parse_status(homework):
    """Собирает текст сообщения по статусу одной конкретной домашки."""
    if 'homework_name' not in homework:
        raise InvalidAPIResponseError(
            'В ответе API отсутствует ключ "homework_name".'
        )

    if 'status' not in homework:
        raise InvalidHomeworkStatusError(
            'В ответе API отсутствует статус домашней работы.'
        )

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise InvalidHomeworkStatusError(
            f'Недокументированный статус домашней работы: {homework_status}'
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Запускает основную логику бота в бесконечном цикле."""
    check_tokens()

    # Создаем объект класса бота
    bot = telebot.TeleBot(TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_error_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = response.get('current_date', timestamp)
            else:
                logger.debug('В ответе API нет новых статусов.')
            last_error_message = ''
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != last_error_message:
                send_message(bot, message)
                last_error_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    configure_logging()
    try:
        main()
    except MissingTokensError as error:
        sys.exit(str(error))
