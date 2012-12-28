import collections

from apy.models import fields as apy_fields


def get_declared_fields(bases, attrs):
    model_fields = [(field_name, attrs.pop(field_name)) for field_name, obj in list(attrs.items()) if isinstance(obj, apy_fields.BaseField)]
    model_fields.sort(key=lambda x: x[1].creation_counter)

    for base in bases[::-1]:
        if hasattr(base, 'base_fields'):
            model_fields = list(base.base_fields.items()) + model_fields

    return collections.OrderedDict(model_fields)


class ApiModelMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['base_fields'] = get_declared_fields(bases, attrs)
        attrs['class_creation_counter'] = ApiModelMetaClass.creation_counter
        ApiModelMetaClass.creation_counter += 1
        new_class = super(ApiModelMetaClass, cls).__new__(cls, name, bases, attrs)
        return new_class


class BaseApiModel(object, metaclass=ApiModelMetaClass):
    base_fields = None
    class_creation_counter = None
    is_hidden = False

    def __init__(self, *args, **kwargs):
        super(BaseApiModel, self).__init__(*args, **kwargs)

    @classmethod
    def validate_fields(cls, fields):
        for k, v in list(fields.items()):
            if k not in cls.base_fields:
                raise apy_fields.ValidationError("invalid key '%s' for model '%s'" % (k, cls.__name__))
            cls.base_fields[k].validate(k, v, cls.__name__)

    @classmethod
    def get_selectable_fields(cls):
        return collections.OrderedDict([(k, v) for k, v in cls.base_fields.items() if v.is_selectable])

    @classmethod
    def get_default_fields(cls):
        return [(k, v) for k, v in cls.base_fields.items() if v.is_default]

    @classmethod
    def get_fields(cls, keys):
        return [(k, cls.base_fields[k]) for k in keys]
