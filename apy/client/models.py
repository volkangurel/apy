import collections
import re

from . import fields as apy_fields, forms

MODELS = {}


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


def split_camel_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1 \2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1 \2', s1)


def camel_case_to_snake_case(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


class BaseClientModelMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['display_name'] = attrs.get('display_name') or split_camel_case(name)
        attrs['plural_display_name'] = attrs.get('plural_display_name') or attrs['display_name'] + 's'
        attrs['lowercase_name'] = attrs.get('lowercase_name') or camel_case_to_snake_case(name)
        attrs['url_name'] = attrs.get('url_name') or attrs['plural_display_name'].lower().replace(' ', '-')
        fields = get_model_fields(bases, attrs)
        attrs['base_fields'] = fields
        attrs['_field_indexes'] = {k: ix for ix, k in enumerate(attrs['base_fields'])}
        attrs['class_creation_counter'] = BaseClientModelMetaClass.creation_counter
        BaseClientModelMetaClass.creation_counter += 1
        new_class = super(BaseClientModelMetaClass, cls).__new__(cls, name, bases, attrs)
        for field in fields.values():
            field.owner = new_class
        MODELS[name] = new_class
        return new_class


QueryField = collections.namedtuple('QueryField', ['key', 'field', 'sub_fields', 'format'])
nested_field_re = re.compile(r'(?P<field>[^(/]+)/(?P<sub_fields>.+)')
sub_fields_re = re.compile(r'(?P<field>[^(/]+)\((?P<sub_fields>.+)\)')
formatted_field_re = re.compile(r'(?P<field>[^(/]+)\.(?P<format>.+)')


class BaseClientModel(tuple, metaclass=BaseClientModelMetaClass):
    class_creation_counter = None
    is_hidden = False
    readonly = False

    display_name = None
    plural_display_name = None
    lowercase_name = None
    url_name = None

    id_field = 'id'
    base_fields = None
    _field_indexes = None

    def __new__(cls, **kwargs):
        vals = []
        for k, f in cls.base_fields.items():
            v = kwargs.pop(k, None)
            if v is None and f.required:
                raise ValueError('need to pass in %s to create a %s' % (k, cls.__name__))
            vals.append(f.to_python(v))
        if kwargs:
            raise ValueError('invalid keys passed in to %s: %s' % (cls.__name__, ', '.join(kwargs)))
        self = tuple.__new__(cls, vals)
        self.changes = None
        return self

    def _field_repr_iter(self):
        for (k, f), v in zip(self.base_fields.items(), self):
            if v is None: continue
            if isinstance(f, apy_fields.NestedField):
                yield k
            elif self.changes and k in self.changes:
                yield '%s*=%r' % (k, self.changes[k])
            else:
                yield '%s=%r' % (k, v)

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, ', '.join(self._field_repr_iter()))

    def __getitem__(self, key):
        ix = self._field_indexes.get(key)
        if ix is None:
            raise KeyError('no such field in %s: %s' % (self.__class__.__name__, key))
        return tuple.__getitem__(self, ix)

    def __setitem__(self, key, value):
        if self.changes is None:
            self.changes = {}
        field = self.base_fields.get(key)
        if field is None:
            raise KeyError('cannot set %s, no such field in %s' % (key, self.__class__.__name__))
        if not field.modifiable:
            raise ValueError('cannot set %s, field not modifiable in %s' % (key, self.__class__.__name__))
        self.changes[key] = field.to_python(value)

    @classmethod
    def get_selectable_fields(cls):
        return [QueryField(k, v, None, None) for k, v in cls.base_fields.items() if v.is_selectable]

    @classmethod
    def get_default_fields(cls):
        return [QueryField(k, v, None, None) for k, v in cls.base_fields.items() if v.is_default]

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
            m = nested_field_re.match(qf) or sub_fields_re.match(qf) or formatted_field_re.match(qf)
            if m:
                qf = m.group('field')
            if qf not in cls.base_fields:
                if use_generic_fields:
                    sub_fields = (m and cls.parse_query_fields(m.group('sub_fields'), use_generic_fields=True)
                                  or cls.get_default_fields())
                    fields.append(QueryField(qf, None, sub_fields, None))
                else:
                    invalid_fields.append(qf)
                continue
            field = cls.base_fields[qf]
            if not field.is_selectable:
                invalid_fields.append(qf)
                continue
            if isinstance(field, apy_fields.NestedField):
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

    # form utils
    @classmethod
    def get_id_form_field(cls):
        if 'id' not in cls.base_fields: raise Exception(cls.base_fields)
        return forms.ModelFieldField(cls.base_fields[cls.id_field])

    @classmethod
    def get_create_form(cls):
        form_fields = {cls.id_field: cls.get_id_form_field()}
        for k, f in cls.base_fields.items():
            if k not in form_fields and (f.required or f.modifiable):
                form_fields[k] = forms.ModelFieldField(f)
        return type('PostForm', (forms.MethodForm,), form_fields)

    @classmethod
    def get_read_form(cls):
        form_fields = {cls.id_field: cls.get_id_form_field(),
                       'fields': forms.FieldsField(cls), }
        return type('GetForm', (forms.MethodForm,), form_fields)

    @classmethod
    def get_read_many_form(cls):
        form_fields = {'%ss' % cls.id_field: forms.ModelFieldListField(cls.base_fields[cls.id_field])}
        for k, f in cls.base_fields.items():
            if f.is_query_filter:
                form_fields[k] = forms.ModelFieldField(f)
        form_fields['fields'] = forms.FieldsField(cls)
        return type('GetForm', (forms.OptionalLimitOffsetForm,), form_fields)

    @classmethod
    def get_nested_read_form(cls, nested_model):
        form_fields = {cls.id_field: cls.get_id_form_field()}
        for k, f in nested_model.base_fields.items():
            if f.is_query_filter:
                form_fields[k] = forms.ModelFieldField(f)
        form_fields['fields'] = forms.FieldsField(nested_model)
        return type('GetForm', (forms.OptionalLimitOffsetForm,), form_fields)

    @classmethod
    def get_modify_form(cls):
        form_fields = {cls.id_field: cls.get_id_form_field()}
        for k, f in cls.base_fields.items():
            if f.modifiable:
                form_fields[k] = forms.ModelFieldField(f)
        return type('PutForm', (forms.ModifyForm,), form_fields)

    @classmethod
    def get_delete_form(cls):
        form_fields = {cls.id_field: cls.get_id_form_field()}
        return type('DeleteForm', (forms.MethodForm,), form_fields)

    @classmethod
    def get_delete_many_form(cls):
        form_fields = {'%ss' % cls.id_field: forms.ModelFieldListField(cls.base_fields[cls.id_field])}
        return type('DeleteForm', (forms.MethodForm,), form_fields)


class BaseClientRelation(tuple):  #TODO
    pass


# exceptions
class ValidationError(Exception):
    pass
