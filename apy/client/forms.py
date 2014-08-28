import collections

from django import forms

from apy import utils


# fields
class BaseField(forms.Field):
    pass


class IntegerField(BaseField, forms.IntegerField):
    def __init__(self, **kwargs):
        default_value = kwargs.pop('default_value', None)
        if default_value is not None:
            kwargs['required'] = False
        super(IntegerField, self).__init__(**kwargs)
        self.default_value = default_value

    def clean(self, value):
        value = forms.IntegerField.clean(self, value)
        if value is None and self.default_value is not None:
            value = self.default_value
        return value


class StringField(BaseField, forms.CharField):
    pass


class DateTimeField(IntegerField):
    def clean(self, value):
        value = super(DateTimeField, self).clean(value)
        if not value: return None
        return utils.ms_to_datetime(value)


class ModelFieldField(StringField):
    def __init__(self, field, **kwargs):
        kwargs.setdefault('help_text', field.description)
        kwargs.setdefault('required', field.required)
        super(ModelFieldField, self).__init__(**kwargs)
        self.field = field

    def clean(self, value):
        value = super(ModelFieldField, self).clean(value)
        return self.field.from_form(value)


class ModelFieldListField(StringField):
    def __init__(self, field, **kwargs):
        kwargs.setdefault('required', field.required)
        super(ModelFieldListField, self).__init__(**kwargs)
        self.field = field

    def clean(self, value):
        if value is None:
            return None
        value = super(ModelFieldListField, self).clean(value)
        if not value:
            return []
        return [self.field.from_form(v.strip()) for v in value.split(',') if v.strip()]


class FieldsField(StringField):
    def __init__(self, model, **kwargs):
        kwargs['required'] = False
        super(FieldsField, self).__init__(**kwargs)
        self.model = model
        self.help_text = 'Fields returned, can be: %s' % (', '.join(f.key for f in self.model.get_selectable_fields()))

    def clean(self, value):
        value = super(FieldsField, self).clean(value)
        return self.model.parse_query_fields(value) if value else None


# forms
class MethodFormMetaclass(type):
    def __new__(cls, name, bases, attrs):
        form_fields = [(field, attrs.pop(field)) for field, obj in list(attrs.items()) if isinstance(obj, BaseField)]
        form_fields.sort(key=lambda x: x[1].creation_counter)
        for base in bases[::-1]:
            if hasattr(base, 'base_fields'):
                if getattr(base, 'append_fields', False):
                    form_fields = form_fields + list(base.base_fields.items())
                else:
                    form_fields = list(base.base_fields.items()) + form_fields
        attrs['base_fields'] = collections.OrderedDict(form_fields)
        new_class = super(MethodFormMetaclass, cls).__new__(cls, name, bases, attrs)
        return new_class


class MethodForm(forms.BaseForm, metaclass=MethodFormMetaclass):
    append_fields = False


class ModifyForm(MethodForm):

    def clean(self):
        self.cleaned_data = super(ModifyForm, self).clean()
        extra_fields = set(self.data.keys()) - set(self.cleaned_data.keys())
        if extra_fields:
            raise forms.ValidationError('unrecognized fields: %s' % ', '.join('"%s"' % f for f in extra_fields))
        for name, field in self.fields.items():
            if name in self.cleaned_data and getattr(field, 'combined_field', None):
                self.cleaned_data.setdefault(field.combined_field, {})
                self.cleaned_data[field.combined_field][name] = self.cleaned_data.pop(name)
        # make sure we don't overwrite fields that are not given in this request
        for k, v in list(self.cleaned_data.items()):
            if v is None and k not in self.data: del self.cleaned_data[k]
        return self.cleaned_data


# helper forms
class SearchForm(MethodForm):
    q = StringField(required=False, help_text='Search query.')


class LimitOffsetForm(MethodForm):
    append_fields = True

    limit = IntegerField(min_value=1, max_value=50, default_value=10, help_text='Limit.')
    offset = IntegerField(min_value=0, max_value=1000, default_value=0, help_text='Offset.')


class OptionalLimitOffsetForm(MethodForm):
    append_fields = True

    limit = IntegerField(required=False, min_value=1, max_value=1000, default_value=None, help_text='Limit.')
    offset = IntegerField(required=False, min_value=0, max_value=1000, default_value=0, help_text='Offset.')


class SearchableLimitOffsetForm(LimitOffsetForm, SearchForm):
    pass


class SearchableOptionalLimitOffsetForm(OptionalLimitOffsetForm, SearchForm):
    pass
