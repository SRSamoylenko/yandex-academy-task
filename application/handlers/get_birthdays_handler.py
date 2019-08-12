import os
from collections import defaultdict
from typing import List, Tuple

from mongolock import MongoLock
from pymongo.database import Database

from application.handlers import shared


def _get_cached_birthdays(import_id: int, db: Database) -> dict:
    """
    Возвращает закешированные ранее данные о подарках на дни рождения из указанной поставки.

    Если закешированные данные отсутствуют, возвращается None.
    :param int import_id: уникальный идентификатор поставки
    :param Database db: объект базы данных, в которую записываются наборы данных о жителях

    :return: Данные о подарках на дни рождения
    :rtype: dict
    """
    birthdays_data = db['birthdays'].find_one({'import_id': import_id}, {'_id': 0, 'import_id': 0})
    return birthdays_data


def _get_birthdays_data(citizens: List[dict]) -> dict:
    """
    Возвращает жителей и количество подарков по месяцам.

    :param List[dict] citizens: список жителей

    :return: Словарь количества подарков для каждого жителя по месяцам
    :rtype: dict
    """
    birthdays_data = defaultdict(lambda: defaultdict(int))
    for citizen in citizens:
        for relative_id in citizen['relatives']:
            birthdays_data[citizen['birth_date'].month][relative_id] += 1
    return birthdays_data


def _get_birthdays_representation(birthdays_data: dict) -> dict:
    """
    Преобразует данные о подарках в формат для отправки ответа.

    :param dict birthdays_data: данные о подарках

    :return: Данные о подарках в формате для отправки
    :rtype: dict
    """
    months = {str(i): [] for i in range(1, 13)}
    for month in birthdays_data:
        months[str(month)] = [{'citizen_id': key, 'presents': value} for key, value in birthdays_data[month].items()]
    return {'data': months}


def _cache_birthdays_data(import_id: int, birthdays_data: dict, db: Database):
    """
    Сохраняет данные о подарках в указанной поставке в базу данных.

    :param dict birthdays_data: данные о подарках
    :param int import_id: уникальный идентификатор поставки
    :param Database db: объект базы данных, в которую записываются наборы данных о жителях
    """
    data = {'import_id': import_id, 'data': birthdays_data['data']}
    db['birthdays'].insert_one(data)


def get_birthdays(import_id: int, db: Database, lock: MongoLock) -> Tuple[dict, int]:
    """
    Возвращает жителей и количество подарков, которые они будут покупать своим ближайшим родственникам
    (1-го порядка), сгруппированных по месяцам из указанного набора данных.

    :param int import_id: уникальный идентификатор поставки
    :param Database db: объект базы данных, в которую записываются наборы данных о жителях
    :param MongoLock lock: объект для ограничения одновременного доступа к ресурсам из разных процессов

    :return: Данные о подарках и http статус
    :rtype: dict
    """
    with lock(str(import_id), str(os.getpid()), expire=60, timeout=10), \
         lock(f'birthdays_{import_id}', str(os.getpid()), expire=60, timeout=10):
        cached_birthdays_data = _get_cached_birthdays(import_id, db)
        if cached_birthdays_data is not None:
            return cached_birthdays_data, 201
        citizens = shared.get_citizens(import_id, db, {'citizens.birth_date': 1, 'citizens.relatives': 1})
        birthdays_data = _get_birthdays_data(citizens)
        birthdays_data = _get_birthdays_representation(birthdays_data)
        _cache_birthdays_data(import_id, birthdays_data, db)
        return birthdays_data, 201
