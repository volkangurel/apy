import collections
import re

from apy.client.models import MODELS, QueryField
from apy.client.fields import NestedField

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

    # parse
    _nested_field_re = re.compile(r'(?P<field>[^(/]+)/(?P<sub_fields>.+)')
    _sub_fields_re = re.compile(r'(?P<field>[^(/]+)\((?P<sub_fields>.+)\)')
    _formatted_field_re = re.compile(r'(?P<field>[^(/]+)\.(?P<format>.+)')
    @classmethod
    def parse_query_fields(cls, query_fields, ignore_invalid_fields=False, use_generic_fields=False):
        # credit for fields format: https://developers.google.com/blogger/docs/2.0/json/performance
        query_fields = query_fields.replace(' ', '').lower()
        split_fields = ['']
        open_brackets = 0
        for c in query_fields:
            if c == ',' and open_brackets == 0:
                split_fields.append('')
            else:
                split_fields[-1] += c
                if c == '(':
                    open_brackets += 1
                elif c == ')':
                    open_brackets -= 1
        fields = []
        invalid_fields = []
        for qf in split_fields:
            if not qf.strip(): continue
            qf = qf.strip().lower()
            m = cls._nested_field_re.match(qf) or cls._sub_fields_re.match(qf) or cls._formatted_field_re.match(qf)
            if m:
                qf = m.group('field')
            if qf not in cls.ClientModel.base_fields:
                if use_generic_fields:
                    sub_fields = (m and cls.parse_query_fields(m.group('sub_fields'), use_generic_fields=True)
                                  or cls.ClientModel.get_default_fields())
                    fields.append(QueryField(qf, None, sub_fields, None))
                else:
                    invalid_fields.append(qf)
                continue
            field = cls.ClientModel.base_fields[qf]
            if not field.is_selectable:
                invalid_fields.append(qf)
                continue
            if isinstance(field, NestedField):
                sub_fields = (m and field.get_model(cls).parse_query_fields(m.group('sub_fields'))
                              or field.get_model(cls).get_default_fields())
                fields.append(QueryField(qf, field, sub_fields, None))
            elif m and m.groupdict().get('format'):
                format_ = m.group('format')
                if format_ not in field.formats:
                    raise ValidationError('invalid format "%s" on field "%s"' % (format_, qf))
                fields.append(QueryField(qf, field, None, format_))
            else:
                fields.append(QueryField(qf, field, None, None))
        if invalid_fields and not ignore_invalid_fields:
            plural = 's' if len(invalid_fields) > 1 else ''
            raise ValidationError('invalid field%s: %s' % (plural, ','.join(invalid_fields)))
        return fields


class BaseServerRelation(object):
    pass


# exceptions
class ValidationError(Exception):
    pass
