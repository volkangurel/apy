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
                 creatable=False,  # whether this field is optional to create an object
                 modifiable=False,  # whether field is modifiable
                 default_to_none=False,
                 # other
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
        self.creatable = creatable
        self.modifiable = modifiable
        self.default_to_none = default_to_none
        # queries
        self.is_id = is_id
        self.is_query_filter = is_query_filter

        self.creation_counter = BaseField.creation_counter
        BaseField.creation_counter += 1

    # from python
    def to_json(self, request, value):  # pylint: disable=W0613
        return value

    # from json
    def to_python(self, value):
        if value is None:
            return None
        if isinstance(value, self.python_type):
            return value
        return self.python_type(value)  # pylint: disable=E1102

    # from server
    def to_client(self, value):
        return self.to_python(value)

    # to python
    def from_form(self, value):
        return self.to_python(value)


class BooleanField(BaseField):
    json_type = 'boolean'
    python_type = bool


class IntegerField(BaseField):
    json_type = 'number'
    python_type = int

    # from json
    def to_python(self, value):
        if value == '': return None
        return super(IntegerField, self).to_python(value)  # pylint: disable=E1102


class LongField(BaseField):
    json_type = 'string'
    python_type = int

    def to_json(self, request, value):
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
    python_type = list

    def to_json(self, request, value):
        if not value: return []
        return [self.child_field.to_json(request, v) for v in value] if self.child_field else value


class ObjectField(BaseField):
    json_type = 'object'
    python_type = dict

    def to_json(self, request, value):
        if not value: return {}
        if isinstance(self.child_field, dict):
            return {k: self.child_field[k].get_json_value(request, v) for k, v in value.items()}
        elif isinstance(self.child_field, tuple) and len(self.child_field) == 2:
            return {self.child_field[0].get_json_value(request, k): self.child_field[1].get_json_value(request, v)
                    for k, v in value.items()}
        else:
            return value


class DateTimeField(IntegerField):
    python_type = datetime.datetime

    def to_json(self, request, value):
        if not value: return None
        return str(utils.datetime_to_ms(value))

    def to_python(self, value):
        if not value: return None
        return utils.ms_to_datetime(int(value))

    def to_client(self, value):
        return value


class NestedField(BaseField):

    def __init__(self, model_or_name, **kwargs):
        has_method = kwargs.pop('has_method', False)
        super(NestedField, self).__init__(**kwargs)
        self.model_or_name = model_or_name
        self._model = None
        self.has_method = has_method

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
        if val is not None:
            if not isinstance(val, (BaseClientModel, list)):
                # TODO handle case where val is a dict describing the object
                raise Exception('invalid nested value "%r"' % val)
            if isinstance(val, list) and val and not isinstance(val[0], BaseClientModel):
                raise Exception('invalid nested list "%r"' % val)
        return val

    def to_json(self, request, value):  # pylint: disable=W0613
        if value is None:
            return None
        if isinstance(value, list):
            return [v.to_json(request) for v in value]
        else:
            return value.to_json(request)


class RelationField(NestedField):
    def __init__(self, model_or_name, relation_filter_field, **kwargs):
        super(RelationField, self).__init__(model_or_name, **kwargs)
        self.relation_filter_field = relation_filter_field
