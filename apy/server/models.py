import collections

from apy.client.models import MODELS

from . import fields as apy_fields

SERVER_MODELS = {}
CLIENT_TO_SERVER_MODELS = {}


# helpers
def get_model_fields(bases, attrs):
    model_fields = [(name, attrs.pop(name)) for name, obj in list(attrs.items()) if isinstance(obj, apy_fields.BaseField)]
    model_fields.sort(key=lambda x: x[1].creation_counter)

    for base in bases[::-1]:
        if hasattr(base, 'base_fields'):
            model_fields = (list((k, v) for k, v in base.base_fields.items()  # pylint: disable=W0212
                                 if k not in model_fields and k not in attrs)
                            + model_fields)

    return collections.OrderedDict(model_fields)


class BaseServerModelMetaClass(type):
    def __new__(cls, name, bases, attrs):
        attrs['base_fields'] = get_model_fields(bases, attrs)
        if name in MODELS:
            attrs['ClientModel'] = MODELS[name]
        new_class = super(BaseServerModelMetaClass, cls).__new__(cls, name, bases, attrs)
        SERVER_MODELS[name] = new_class
        CLIENT_TO_SERVER_MODELS[new_class.ClientModel] = new_class
        return new_class


class BaseServerModel(object, metaclass=BaseServerModelMetaClass):
    ClientModel = NotImplemented
    base_fields = None

    def __init__(self, **data):
        self.data = data
        self.client_data = None

    def get_id(self):
        return self.data[self.ClientModel.id_field]

    @classmethod
    def to_client(cls, request, objects, query_fields=None):
        query_fields = query_fields or cls.ClientModel.get_default_fields()
        for obj in objects:
            if not isinstance(obj, cls):
                raise Exception('cannot convert "%r" to client model: not an instance of %s' % (obj, cls.__name__))
            if obj.client_data is not None:
                raise Exception('object already converted to client data!!')
            obj.client_data = collections.OrderedDict()

        # takes the values in this instance of the model, and returns them as in an instance of ClientModel
        for query_field in query_fields:
            client_field = cls.ClientModel.base_fields.get(query_field.key)
            if client_field is None:
                raise Exception('invalid query field %r' % query_field)
            server_field = cls.base_fields.get(query_field.key)
            if server_field is not None:
                server_field.to_client(request, cls, query_field, objects)
            else:
                for obj in objects:
                    obj.client_data[query_field.key] = obj.data[query_field.key]
        for obj in objects:
            cls.check_read_permissions(request, obj.client_data)

        return [cls.ClientModel(**obj.client_data) for obj in objects]

    # database operations
    @classmethod
    def find(cls, ids=None, condition=None, fields=None, **kwargs):
        raise NotImplementedError()

    @classmethod
    def find_one(cls, **kwargs):
        rows = cls.find(**kwargs)
        return rows[0] if rows else None

    @classmethod
    def find_for_client(cls, request, query_fields, **kwargs):
        return cls.to_client(request, cls.find(**kwargs), query_fields=query_fields)

    @classmethod
    def insert(cls, **kwargs):
        raise NotImplementedError()

    @classmethod
    def update(cls, **kwargs):
        raise NotImplementedError()

    @classmethod
    def remove(cls, **kwargs):
        raise NotImplementedError()

    #
    @classmethod
    def create(cls, request):
        pass

    # permissions
    @classmethod
    def check_read_permissions(cls, request, client_data):
        raise NotImplementedError()


class BaseServerRelation(object):
    pass
