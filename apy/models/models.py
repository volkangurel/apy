import collections
import re

from apy.models import fields as apy_fields
from django import forms


def get_declared_fields(bases, attrs):
    model_fields = [(field_name, attrs.pop(field_name)) for field_name, obj in list(attrs.items()) if isinstance(obj, apy_fields.BaseField)]
    model_fields.sort(key=lambda x: x[1].creation_counter)

    for base in bases[::-1]:
        if hasattr(base, 'base_fields'):
            model_fields = list((k, v) for k, v in base.base_fields.items()
                                if k not in model_fields and k not in attrs) + model_fields

    return collections.OrderedDict(model_fields)


class ApiModelMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['base_fields'] = get_declared_fields(bases, attrs)
        attrs['class_creation_counter'] = ApiModelMetaClass.creation_counter
        ApiModelMetaClass.creation_counter += 1
        new_class = super(ApiModelMetaClass, cls).__new__(cls, name, bases, attrs)
        return new_class


QueryField = collections.namedtuple('QueryField', ['key', 'field', 'sub_fields'])
nested_field_re = re.compile(r'(?P<field>[^(/]+)/(?P<sub_fields>.+)')
sub_fields_re = re.compile(r'(?P<field>[^(/]+)\((?P<sub_fields>.+)\)')


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
        return [QueryField(k, v, None) for k, v in cls.base_fields.items() if v.is_default]

    @classmethod
    def parse_query_fields(cls, query_fields):
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
            m = nested_field_re.match(qf) or sub_fields_re.match(qf)
            if m:
                qf = m.group('field')
            if qf not in cls.base_fields:
                invalid_fields.append(qf)
                continue
            field = cls.base_fields[qf]
            if not field.is_selectable:
                invalid_fields.append(qf)
                continue
            if isinstance(field, apy_fields.NestedField):
                sub_fields = m and field.model.parse_query_fields(m.group('sub_fields'))
                fields.append(QueryField(qf, field, sub_fields))
            else:
                fields.append(QueryField(qf, field, None))
        if invalid_fields:
            plural = 's' if len(invalid_fields) > 1 else ''
            raise forms.ValidationError('invalid field%s: %s' % (plural, ','.join(invalid_fields)))
        return fields
