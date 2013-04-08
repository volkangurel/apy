import datetime


class BaseField(object):

    creation_counter = 0
    python_classes = tuple()
    formats = set()

    def __init__(self, description=None, is_selectable=True, is_default=False,
                 child_field=None, required_fields=None):
        super(BaseField, self).__init__()

        self.description = description
        self.is_selectable = is_selectable
        self.is_default = is_default
        self.child_field = child_field
        self.required_fields = required_fields

        self.creation_counter = BaseField.creation_counter
        BaseField.creation_counter += 1

    def validate(self, key, value, model):
        if not any(isinstance(value, c) for c in self.python_classes):
            raise ValidationError("invalid type '%s' for field '%s' in model '%s', has to be an instance of %s" % (type(value).__name__, key, model, ' or '.join("'%s'" % c.__name__ for c in self.python_classes)))
        if self.child_field:
            self.child_field.validate(value)

    def get_json_value(self, request, value, field):  # pylint: disable=W0613
        return value


class BooleanField(BaseField):
    json_type = 'boolean'

    python_classes = (bool,)


class IntegerField(BaseField):
    json_type = 'number'

    python_classes = (int,)


class LongField(BaseField):
    json_type = 'string'

    python_classes = (int,)

    def get_json_value(self, request, value, field):
        if not value: return None
        return str(value)


class FloatField(BaseField):
    json_type = 'number'

    python_classes = (float,)


class StringField(BaseField):
    json_type = 'string'

    python_classes = (str,)


class ArrayField(BaseField):
    json_type = 'array'

    python_classes = (list, tuple,)

    def get_json_value(self, request, value, field):
        if not value: return []
        return [self.child_field.get_json_value(request, v) for v in value] if self.child_field else value


class ObjectField(BaseField):
    json_type = 'object'

    python_classes = (dict,)

    def get_json_value(self, request, value, field):
        if not value: return {}
        if isinstance(self.child_field, dict):
            return {k: self.child_field[k].get_json_value(request, v) for k, v in value.items()}
        elif isinstance(self.child_field, tuple) and len(self.child_field) == 2:
            return {self.child_field[0].get_json_value(request, k): self.child_field[1].get_json_value(request, v)
                    for k, v in value.items()}
        else:
            return value


class DateTimeField(BaseField):
    json_type = 'string'

    python_classes = (datetime.datetime,)

    def get_json_value(self, request, value, field):
        if not value: return None
        return value.strftime('%Y-%m-%dT%H:%M:%S.%f%z')


class NestedField(BaseField):
    def __init__(self, model_or_name, id_field, **kwargs):
        id_fields = id_field.split('.')
        super(NestedField, self).__init__(required_fields=[id_fields[0]], **kwargs)
        self.model_or_name = model_or_name
        self.id_fields = id_fields

    @property
    def model(self):
        if not hasattr(self, '_model'):
            if isinstance(self.model_or_name, str):
                from apy.models import MODELS
                self._model = MODELS[self.model_or_name]
            else:
                self._model = self.model_or_name
        return self._model

    def get_id(self, obj):
        d = obj
        for id_field in self.id_fields:
            if not d: return None
            d = d.get(id_field)
        return d


class AssociationField(BaseField):
    def __init__(self, model_or_name, method, can_multi_get=False, **kwargs):
        super(AssociationField, self).__init__(**kwargs)
        self.model_or_name = model_or_name
        self.method = method
        self.can_multi_get = can_multi_get

    @property
    def model(self):
        if not hasattr(self, '_model'):
            if isinstance(self.model_or_name, str):
                from apy.models import MODELS
                self._model = MODELS[self.model_or_name]
            else:
                self._model = self.model_or_name
        return self._model


# exceptions
class ValidationError(Exception):
    pass
