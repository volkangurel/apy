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

    def __init__(self, *args, **kwargs):
        self.data = dict(*args, **kwargs)
        self.updated_data = {}
        self.client_data = None

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, ', '.join(self.data.keys()))

    def get_id(self):
        return self.data[self.ClientModel.id_field]

    # crud
    @classmethod
    def create(cls, request, **row):
        cls.check_create_permissions(request, row)
        data = cls.db_insert(request, row)
        return cls(data) if data else None

    @classmethod
    def read(cls, request, query_fields, **kwargs):
        return cls.to_client(request, cls.db_find(**kwargs), query_fields=query_fields)

    @classmethod
    def read_one(cls, request, query_fields, **kwargs):
        rows = cls.read(request, query_fields, **kwargs)
        return rows[0] if rows else None

    def update(self, request, updated_fields):
        self.check_update_permissions(request)
        return self.db_update(request, updated_fields)

    def save(self, request, **kwargs):
        val = self.update(request, self.updated_data, **kwargs)
        self.data.update(self.updated_data)
        self.updated_data.clear()
        return val

    def delete(self, request):
        self.check_delete_permissions(request)
        return self.db_remove(request)

    # conversion to client model
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
                    if query_field.key not in obj.data:
                        if client_field.default_to_none:
                            obj.client_data[query_field.key] = None
                        else:
                            raise KeyError("'%s' not in %r" % (query_field.key, obj.data))
                    else:
                        obj.client_data[query_field.key] = obj.data[query_field.key]

        return [cls.ClientModel(**obj.check_read_permissions(request)) for obj in objects]

    def self_to_client(self, request, query_fields=None):
        return self.to_client(request, [self], query_fields=query_fields)[0]

    # database operations
    @classmethod
    def db_find(cls, ids=None, condition=None, fields=None, **kwargs):
        raise NotImplementedError()

    @classmethod
    def db_find_one(cls, **kwargs):
        rows = cls.db_find(**kwargs)
        return rows[0] if rows else None

    @classmethod
    def db_insert(cls, request, row):
        raise NotImplementedError()

    def db_update(self, request, updated_fields):
        raise NotImplementedError()

    def db_remove(self, request):
        raise NotImplementedError()

    # permissions
    @classmethod
    def check_create_permissions(cls, request, row):
        # raise PermissionDeniedError if this request is not allowed to create an object of this class
        raise NotImplementedError()

    def check_read_permissions(self, request):
        # implement a method that uses the request and self.client_data and
        # returns a dictionary of client data that this request has permission to access
        raise NotImplementedError()

    def check_update_permissions(self, request):
        # raise PermissionDeniedError if this request is not allowed to update this object
        raise NotImplementedError()

    def check_delete_permissions(self, request):
        # raise PermissionDeniedError if this request is not allowed to delete this object
        raise NotImplementedError()


# # exceptions
# class ValidationError(Exception):
#     pass


# class PermissionDeniedError(Exception):
#     pass
