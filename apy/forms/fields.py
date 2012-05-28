import re

from django import forms
from django.core import validators

class BaseField(forms.Field):
    json_type = None

class IntegerField(BaseField, forms.IntegerField):
    json_type = 'integer'

    def __init__(self,**kwargs):
        default_value = kwargs.pop('default_value',None)
        if default_value is not None: kwargs['required'] = False
        super(IntegerField,self).__init__(**kwargs)
        self.default_value = default_value

    def clean(self, value):
        value = forms.IntegerField.clean(self, value)
        if not value and self.default_value is not None:
            value = self.default_value
        return value

class LongField(BaseField, forms.CharField):
    json_type = 'string'

    _number_rx = re.compile('^\d+$')

    def __init__(self, max_value=2**63-1, min_value=-2**63, **kwargs):
        self.min_value, self.max_value = min_value, max_value
        super(LongField,self).__init__(**kwargs)

    def clean(self, value):
        value = forms.CharField.clean(self, value)
        if not value: return None
        if not self._number_rx.match(value): raise forms.ValidationError('invalid number')
        value = int(value)
        if self.min_value>value: raise forms.ValidationError('value too small')
        if self.max_value<value: raise forms.ValidationError('value too large')
        return value

class StringField(BaseField, forms.CharField):
    json_type = 'string'

class ArrayField(BaseField):
    json_type = 'array'

    def __init__(self, child_field, max_length=None, min_length=None, **kwargs):
        self.child_field = child_field
        self.min_length, self.max_length = min_length, max_length
        super(ArrayField,self).__init__(**kwargs)
        if min_length is not None:
            self.validators.append(validators.MinLengthValidator(min_length))
        if max_length is not None:
            self.validators.append(validators.MaxLengthValidator(max_length))

    def clean(self, value):
        if not isinstance(value,list): return []
        value = super(ArrayField,self).clean(value)
        value = [self.child_field.clean(v) for v in value]
        return value

# helper fields
class FieldsField(StringField):

    def __init__(self,**kwargs):
        model = kwargs.pop('model',None)
        if not model: raise Exception('need to initialize FieldsField with a model')
        kwargs['required'] = False
        super(FieldsField,self).__init__(**kwargs)
        self.model = model
        self.help_text = 'Fields returned, can be: %s'%(','.join(self.model.get_selectable_fields()))

    def clean(self, value):
        value = forms.CharField.clean(self, value)
        if value:
            value = [v.strip().lower() for v in value.split(',') if v.strip()]
            invalid_values = [v for v in value if v not in self.model.get_selectable_fields()]
            if invalid_values:
                plural = 's' if len(invalid_values)>1 else ''
                raise forms.ValidationError('invalid field%s: %s'%(plural,','.join(invalid_values)))
            value = self.model.get_fields(value)
        else:
            value = self.model.get_default_fields()
        return value
