import collections

from django import forms

from apy.forms import fields


class ApiFormMetaclass(type):
    def __new__(cls, name, bases, attrs):
        form_fields = [(field_name, attrs.pop(field_name)) for field_name, obj in list(attrs.items()) if isinstance(obj, fields.BaseField)]
        form_fields.sort(key=lambda x: x[1].creation_counter)
        for base in bases[::-1]:
            if hasattr(base, 'base_fields'):
                if getattr(base, 'append_fields', False):
                    form_fields = form_fields + list(base.base_fields.items())
                else:
                    form_fields = list(base.base_fields.items()) + form_fields
        attrs['base_fields'] = collections.OrderedDict(form_fields)
        new_class = super(ApiFormMetaclass, cls).__new__(cls, name, bases, attrs)
        return new_class


class ApiForm(forms.BaseForm, metaclass=ApiFormMetaclass):
    append_fields = False


# helper forms
class LimitOffsetForm(ApiForm):
    append_fields = True

    limit = fields.IntegerField(min_value=1, max_value=50, default_value=10, help_text='Limit.')
    offset = fields.IntegerField(min_value=0, max_value=1000, default_value=0, help_text='Offset.')


class OptionalLimitOffsetForm(ApiForm):
    append_fields = True

    limit = fields.IntegerField(required=False, min_value=1, max_value=1000, default_value=None, help_text='Limit.')
    offset = fields.IntegerField(required=False, min_value=0, max_value=1000, default_value=0, help_text='Offset.')
