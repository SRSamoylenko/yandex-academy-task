import logging
import os

from flask import Flask, request
from mongolock import MongoLock
from pymongo.database import Database
from pymongo.errors import PyMongoError
from werkzeug.exceptions import BadRequest

from application.data_validator import DataValidator
from application.exception_handler import handle_exceptions
from application.handlers.patch_citizen.patch_citizen_handler import patch_citizen
from application.handlers.post_import_handler import post_import

logger = logging.getLogger(__name__)


def make_app(db: Database, data_validator: DataValidator) -> Flask:
    app = Flask(__name__)

    lock = MongoLock(client=db.client, db=db.name)

    @app.route('/imports', methods=['POST'])
    @handle_exceptions(logger)
    def imports():
        """
        Принимает на вход набор с данными о жителях в формате json
        и сохраняет его с уникальным идентификатором import_id.

        :raises: :class:`BadRequest`: Content-Type в заголовке запроса не равен application/json
        :raises: :class:`PyMongoError`: Операция записи в базу данных не была разрешена

        :returns: В случае успеха возвращается ответ с идентификатором импорта
        :rtype: flask.Response
        """
        if not request.is_json:
            raise BadRequest('Content-Type must be application/json')

        import_data = request.get_json()
        data_validator.validate_import(import_data)
        return post_import(import_data, lock, db)

    @app.route('/imports/<int:import_id>/citizens/<int:citizen_id>', methods=['PATCH'])
    @handle_exceptions(logger)
    def citizen(import_id: int, citizen_id: int):
        """
        Изменяет информацию о жителе в указанном наборе данных.
        На вход подается JSON в котором можно указать любые данные о жителе.

        :param int import_id: Уникальный идентификатор поставки, в которой изменяется информация о жителе
        :param int citizen_id: Уникальный индентификатор жителя в поставке
        :raises: :class:`BadRequest`: Content-Type в заголовке запроса не равен application/json
        :raises: :class:`PyMongoError`: Объект с указанным уникальным идентификатором не был найден в базе данных

        :return: Актуальная информация об указанном жителе
        :rtype: flask.Response
        """

        if not request.is_json:
            raise BadRequest('Content-Type must be application/json')

        patch_data = request.get_json()
        data_validator.validate_citizen_patch(citizen_id, patch_data)
        return patch_citizen(import_id, citizen_id, patch_data, lock, db)

    @app.route('/imports/<int:import_id>/citizens', methods=['GET'])
    @handle_exceptions(logger)
    def citizens(import_id: int):
        """
        Возвращает список всех жителей для указанного набора данных.

        :param int import_id: Уникальный идентификатор поставки
        :raises: :class:`PyMongoError`: Объект с указанным уникальным идентификатором не был найден в базе данных

        :return: Список жителей в указанной поставке
        :rtype: flask.Response
        """
        with lock(str(import_id), str(os.getpid()), expire=60, timeout=10):
            import_data = db['imports'].find_one({'import_id': import_id}, {'_id': 0, 'import_id': 0})
            if import_data is None:
                raise PyMongoError('Import with specified id not found')
            for citizen in import_data['citizens']:
                citizen['birth_date'] = citizen['birth_date'].strftime('%d.%m.%Y')
            return {'data': import_data['citizens']}, 201

    return app