import re

from . import forms

METHODS = {}


class ClientMethodMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['class_creation_counter'] = ClientMethodMetaClass.creation_counter
        ClientMethodMetaClass.creation_counter += 1
        new_class = super(ClientMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        return new_class


class ClientMethod(object, metaclass=ClientMethodMetaClass):
    """
    View class based off of django.views.generic.View, main difference is dispatch doesn't
    pass request, args and kwargs to methods, since they are already attributes of class instance
    """

    http_method_names = ['POST', 'GET', 'PUT', 'DELETE']
    category = None

    PostForm = None
    GetForm = None
    PutForm = None
    DeleteForm = None

    url_pattern = None
    names = {}

    url_pattern_re = re.compile('\(\?P<([^>]+)>[^()]+\)')

    @staticmethod
    def url_pattern_repl(x):
        return '<i>:%s</i>' % x.group(1)

    @property
    def url_doc(self):
        return self.url_pattern_re.sub(self.url_pattern_repl, self.url_pattern)

    @classmethod
    def _call(cls, http_method, data):
        # TODO use the right form to check data before sending
        # send data
        # parse response with the right models
        pass

    @classmethod
    def get(cls, data):
        return cls._call('GET', data)

    @classmethod
    def post(cls, data):
        return cls._call('POST', data)

    @classmethod
    def put(cls, data):
        return cls._call('PUT', data)

    @classmethod
    def delete(cls, data):
        return cls._call('DELETE', data)


# helper classes
class ClientCreateMethod(ClientMethod):
    http_method_names = ['POST']


class ClientReadMethod(ClientMethod):
    http_method_names = ['GET']


class ClientUpdateMethod(ClientMethod):
    http_method_names = ['PUT']


class ClientDeleteMethod(ClientMethod):
    http_method_names = ['DELETE']


class ClientObjectsMethodMetaClass(ClientMethodMetaClass):
    def __new__(cls, name, bases, attrs):
        if attrs.get('model') is not None:
            model = attrs['model']
            attrs['url_pattern'] = model.url_name
            names = attrs.setdefault('names', {})
            names.setdefault('POST', 'Create %s' % model.display_name)
            names.setdefault('GET', 'Get %s' % model.plural_display_name)
            names.setdefault('DELETE', 'Delete %s' % model.plural_display_name)
            attrs.setdefault('PostForm', model.get_create_form())
            attrs.setdefault('GetForm', model.get_read_many_form())
            attrs.setdefault('DeleteForm', model.get_delete_many_form())
        return super(ClientObjectsMethodMetaClass, cls).__new__(cls, name, bases, attrs)


class ClientObjectsMethod(ClientMethod, metaclass=ClientObjectsMethodMetaClass):
    http_method_names = ['POST', 'GET', 'DELETE']
    model = None


class ClientObjectMethodMetaClass(ClientMethodMetaClass):

    def __new__(cls, name, bases, attrs):
        if attrs.get('model') is not None:
            model = attrs['model']
            attrs.setdefault('id_field', '%s_id' % model.lowercase_name)
            attrs['url_pattern'] = r'%s/(?P<%s>[^/])' % (model.url_name, model.id_field)
            names = attrs.setdefault('names', {})
            names.setdefault('GET', 'Get %s' % model.display_name)
            names.setdefault('PUT', 'Modify %s' % model.display_name)
            names.setdefault('DELETE', 'Delete %s' % model.display_name)
            attrs.setdefault('GetForm', model.get_read_form())
            attrs.setdefault('PutForm', model.get_modify_form())
            attrs.setdefault('DeleteForm', model.get_delete_form())
        return super(ClientObjectMethodMetaClass, cls).__new__(cls, name, bases, attrs)


class ClientObjectMethod(ClientMethod, metaclass=ClientObjectMethodMetaClass):
    http_method_names = ['GET', 'PUT', 'DELETE']  # read, update or delete an object

    model = None
    id_field = None


class ClientObjectNestedMethodMetaClass(ClientMethodMetaClass):

    def __new__(cls, name, bases, attrs):
        if attrs.get('model') is not None and attrs.get('nested_field') is not None:
            model = attrs['model']
            nested_field = attrs['nested_field']
            field = model._fields[nested_field]  # pylint: disable=W0212
            attrs['nested_model'] = nested_model = field.get_model(model)
            attrs.setdefault('id_field', '%s_id' % model.lowercase_name)
            attrs['url_pattern'] = r'%s/(?P<%s>[^/])/%s' % (model.url_name, attrs['id_field'], nested_field)
            names = attrs.setdefault('names', {})
            readonly = attrs.get('readonly', False)
            attrs.setdefault('http_method_names', ['GET'] if readonly else ['GET', 'POST'])
            names.setdefault('GET', 'Get %s %s' % (model.display_name, nested_model.plural_display_name))
            attrs.setdefault('GetForm', nested_model.get_nested_read_form())
            if not readonly:
                names.setdefault('POST', 'Create %s in %s' % (nested_model.display_name, model.display_name))
                attrs.setdefault('PostForm', nested_model.get_create_form())
        return super(ClientObjectNestedMethodMetaClass, cls).__new__(cls, name, bases, attrs)


class ClientObjectNestedMethod(ClientMethod, metaclass=ClientObjectNestedMethodMetaClass):
    http_method_names = []

    model = None
    id_field = None
    nested_field = None

    nested_model = None


def add_nested_methods_for_model(lcls, model, fields):
    for field in fields:
        cname = '%s%sAssociationMethod' % (model.__name__, field.capitalize())
        lcls[cname] = type(cname, (ClientObjectNestedMethod,), {'model': model, 'nested_field': field, })
