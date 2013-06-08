import datetime

from apy import utils


class BaseField(object):
    creation_counter = 0
    json_type = NotImplemented
    python_type = NotImplemented

    def __init__(self,
                 description=None,
                 is_selectable=True,  # whether it can be specified in a "fields" argument
                 is_default=False,  # whether it gets fetched by default
                 child_field=None,  # for array and object fields
                 # permissions
                 read_access=None,
                 modify_access=None,
                 create_access=None,
                 # updates
                 required=False,  # whether this field is required to create an object
                 modifiable=False,  # whether field is modifiable
                 # id
                 is_id=False,
                 is_query_filter=False,
                 ):
        super(BaseField, self).__init__()

        self.description = description
        self.is_selectable = is_selectable
        self.is_default = is_default
        self.child_field = child_field
        # permissions
        self.create_access = create_access
        self.modify_access = modify_access
        self.read_access = read_access
        # updates
        self.required = required
        self.modifiable = modifiable
        # queries
        self.is_id = is_id
        self.is_query_filter = is_query_filter

        self.creation_counter = BaseField.creation_counter
        BaseField.creation_counter += 1

    def to_python(self, val):
        if val is None:
            return None
        if isinstance(val, self.python_type):
            return val
        return self.python_type(val)  # pylint: disable=E1102

    def to_json(self, request, value, field):  # pylint: disable=W0613
        return value


class BooleanField(BaseField):
    json_type = 'boolean'
    python_type = bool


class IntegerField(BaseField):
    json_type = 'number'
    python_type = int


class LongField(BaseField):
    json_type = 'string'
    python_type = int

    def to_json(self, request, value, field):
        if not value: return None
        return str(value)


class FloatField(BaseField):
    json_type = 'number'
    python_type = float


class StringField(BaseField):
    json_type = 'string'
    python_type = str


class ArrayField(BaseField):
    json_type = 'array'
    python_type = tuple

    def to_json(self, request, value, field):
        if not value: return []
        return [self.child_field.to_json(request, v, field) for v in value] if self.child_field else value


class ObjectField(BaseField):
    json_type = 'object'
    python_type = dict

    def to_json(self, request, value, field):
        if not value: return {}
        if isinstance(self.child_field, dict):
            return {k: self.child_field[k].get_json_value(request, v, field) for k, v in value.items()}
        elif isinstance(self.child_field, tuple) and len(self.child_field) == 2:
            return {self.child_field[0].get_json_value(request, k, field): self.child_field[1].get_json_value(request, v, field)
                    for k, v in value.items()}
        else:
            return value


class DateTimeField(IntegerField):
    python_type = datetime.datetime

    def to_json(self, request, value, field):
        if not value: return None
        return utils.datetime_to_ms(value)

    def to_python(self, value):
        if not value: return None
        return utils.ms_to_datetime(value)


class NestedField(BaseField):

    def __init__(self, model_or_name, **kwargs):
        super(NestedField, self).__init__(**kwargs)
        self.model_or_name = model_or_name
        self._model = None

    def get_model(self, owner):  # pylint: disable=W0613
        if self._model is None:
            if isinstance(self.model_or_name, str):
                from .models import MODELS
                self._model = MODELS[self.model_or_name]
            else:
                self._model = self.model_or_name
        return self._model

    def to_python(self, val):
        from .models import BaseClientModel
        if val is not None and not isinstance(val, BaseClientModel):
            # TODO handle case where val is a dict describing the object
            raise Exception('invalid nested value "%r"' % val)
        return val
