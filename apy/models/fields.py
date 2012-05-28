import time

class BaseField(object):

    creation_counter = 0
    python_classes = tuple()

    def __init__(self,description=None,is_selectable=True,is_default=False,field_type='f',
                 child_field=None,required_fields=None):
        super(BaseField,self).__init__()

        self.description = description
        self.is_selectable = is_selectable
        self.is_default = is_default
        self.type = field_type
        self.child_field = child_field
        self.required_fields = required_fields

        self.creation_counter = BaseField.creation_counter
        BaseField.creation_counter += 1

    def validate(self,key,value,model):
        if not any(isinstance(value,c) for c in self.python_classes):
            raise ValidationError("invalid type '%s' for field '%s' in model '%s', has to be an instance of %s"%(type(value).__name__,key,model,' or '.join("'%s'"%c.__name__ for c in self.python_classes)))
        if self.child_field:
            self.child_field.validate(value)

    def get_json_value(self,request,value):
        return value

class IntegerField(BaseField):
    json_type = 'integer'

    python_classes = (int,long,)

class LongField(BaseField):
    json_type = 'string'

    python_classes = (int,long,)

    def get_json_value(self,request,value):
        return unicode(value)

class StringField(BaseField):
    json_type = 'string'

    python_classes = (unicode,)

class ArrayField(BaseField):
    json_type = 'array'

    python_classes = (list,tuple,)

    def get_json_value(self,request,value):
        return [self.child_field.get_json_value(request,v) for v in value] if self.child_field else value

class ObjectField(BaseField):
    json_type = 'object'

    python_classes = (dict,)

    def get_json_value(self,request,value):
        if self.child_field:
            return {k:self.child_field[k].get_json_value(request,v) for k,v in value.iteritems()}
        else:
            return value

class TimeField(BaseField):
    json_type = 'string'

    python_classes = (float,)

    def get_json_value(self,request,value):
        return time.strftime("%Y-%m-%d %H:%M:%S",time.gmtime(value))

class LinkField(ArrayField):
    def __init__(self,**kwargs):
        link_method = kwargs.pop('link_method')
        kwargs['field_type'] = 'l'
        super(LinkField,self).__init__(**kwargs)
        self.link_method = link_method

# exceptions
class ValidationError(Exception):
    pass
