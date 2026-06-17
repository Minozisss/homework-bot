"""Телеграм-бот, который следит за статусами домашних работ в Практикуме."""

import logging
import os
import sys
import time

import requests
import telebot
from dotenv import load_dotenv


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


class APIRequestError(Exception):
    """Ошибка, если с запросом к API что-то пошло не так."""


class InvalidAPIResponseError(Exception):
    """Ошибка, если API вернуло ответ не в том формате, который ждем."""


class InvalidHomeworkStatusError(Exception):
    """Ошибка, если у домашки прилетел непонятный статус."""


logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def check_tokens():
    """Проверяет, что все нужные переменные окружения вообще есть."""
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for token_name, token_value in tokens.items():
        if not token_value:
            logger.critical(
                'Отсутствует обязательная переменная окружения: %r',
                token_name,
            )
            return False
    return True


def send_message(bot, message):
    """Отправляет сообщение в Телеграм и пишет в лог, как всё прошло."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug('Бот отправил сообщение "%s"', message)
    except Exception as error:
        logger.error('Сбой при отправке сообщения в Telegram: %s', error)


def get_api_answer(timestamp):
    """Ходит в API Практикума и забирает свежий ответ по домашкам."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp},
        )
    except requests.RequestException as error:
        logger.error('Сбой при запросе к эндпоинту %s: %s', ENDPOINT, error)
        raise APIRequestError(
            f'Ошибка при запросе к API Практикума: {error}'
        ) from error

    if response.status_code != 200:
        logger.error(
            'Эндпоинт %s недоступен. Код ответа API: %s',
            ENDPOINT,
            response.status_code,
        )
        raise APIRequestError(
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )

    return response.json()


def check_response(response):
    """Проверяет ответ API и достает из него список домашних работ."""
    if not isinstance(response, dict):
        logger.error('Ответ API имеет неверный тип: %s', type(response))
        raise TypeError('Ответ API должен быть словарем.')

    if 'homeworks' not in response:
        logger.error('В ответе API отсутствует ключ "homeworks".')
        raise InvalidAPIResponseError(
            'В ответе API отсутствует ключ "homeworks".'
        )

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        logger.error('Ключ "homeworks" содержит данные неверного типа.')
        raise TypeError('Значение ключа "homeworks" должно быть списком.')

    return homeworks


def parse_status(homework):
    """Собирает текст сообщения по статусу одной конкретной домашки."""
    if 'homework_name' not in homework:
        logger.error('В ответе API отсутствует ключ "homework_name".')
        raise InvalidAPIResponseError(
            'В ответе API отсутствует ключ "homework_name".'
        )

    if 'status' not in homework:
        logger.error('В ответе API отсутствует ключ "status".')
        raise InvalidHomeworkStatusError(
            'В ответе API отсутствует статус домашней работы.'
        )

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        logger.error(
            'Обнаружен недокументированный статус: %s',
            homework_status,
        )
        raise InvalidHomeworkStatusError(
            f'Недокументированный статус домашней работы: {homework_status}'
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Запускает основную логику бота в бесконечном цикле."""
    if not check_tokens():
        raise SystemExit('Отсутствуют обязательные переменные окружения.')

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
                send_message(bot, message)
            else:
                logger.debug('В ответе API нет новых статусов.')

            timestamp = response.get('current_date', timestamp)
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
    main()
