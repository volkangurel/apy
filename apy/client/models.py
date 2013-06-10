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
        keys = []
        for k, f in cls.base_fields.items():
            if k in kwargs:
                v = kwargs.pop(k)
                keys.append(k)
            else:
                v = None
            if v is None and f.required:
                raise ValueError('need to pass in %s to create a %s' % (k, cls.__name__))
            vals.append(f.to_python(v))
        if kwargs:
            raise ValueError('invalid keys passed in to %s: %s' % (cls.__name__, ', '.join(kwargs)))
        self = tuple.__new__(cls, vals)
        self.keys = keys
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

    def to_json(self, request):
        d = collections.OrderedDict()
        for key in self.keys:
            d[key] = self.base_fields[key].to_json(request, self[key])
        return d

    @classmethod
    def get_selectable_fields(cls):
        return [QueryField(k, v, None, None) for k, v in cls.base_fields.items() if v.is_selectable]

    @classmethod
    def get_default_fields(cls):
        return [QueryField(k, v, None, None) for k, v in cls.base_fields.items() if v.is_default]

    # form utils
    @classmethod
    def get_id_field_name(cls):
        return '%s_%s' % (cls.lowercase_name, cls.id_field)

    @classmethod
    def get_id_form_field(cls):
        if 'id' not in cls.base_fields: raise Exception(cls.base_fields)
        return forms.ModelFieldField(cls.base_fields[cls.id_field], help_text='ID')

    @classmethod
    def get_create_form(cls):
        form_fields = {cls.get_id_field_name(): cls.get_id_form_field()}
        for k, f in cls.base_fields.items():
            if k not in form_fields and (f.required or f.modifiable):
                form_fields[k] = forms.ModelFieldField(f)
        return type('PostForm', (forms.MethodForm,), form_fields)

    @classmethod
    def get_read_form(cls):
        form_fields = {cls.get_id_field_name(): cls.get_id_form_field(),
                       'fields': forms.FieldsField(cls), }
        return type('GetForm', (forms.MethodForm,), form_fields)

    @classmethod
    def get_read_many_form(cls):
        form_fields = {'%ss' % cls.get_id_field_name(): forms.ModelFieldListField(cls.base_fields[cls.id_field], help_text='IDs')}
        for k, f in cls.base_fields.items():
            if f.is_query_filter:
                form_fields[k] = forms.ModelFieldField(f)
        form_fields['fields'] = forms.FieldsField(cls)
        return type('GetForm', (forms.OptionalLimitOffsetForm,), form_fields)

    @classmethod
    def get_nested_read_form(cls, nested_model):
        form_fields = {cls.get_id_field_name(): cls.get_id_form_field()}
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
        form_fields = {'%ss' % cls.id_field: forms.ModelFieldListField(cls.base_fields[cls.id_field], help_text='IDs')}
        return type('DeleteForm', (forms.MethodForm,), form_fields)


class BaseClientRelation(BaseClientModel):  #TODO
    pass
