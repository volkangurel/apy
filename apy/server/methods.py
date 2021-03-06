import collections
import json
import functools
import urllib.parse
import http.client as http_client

from django import http
from django.conf import settings
from django.conf.urls import patterns, url
from django.utils import importlib
from django.http.multipartparser import MultiPartParserError

from apy import utils
from apy.client.methods import METHODS

from .models import CLIENT_TO_SERVER_MODELS
from .errors import Errors


SERVER_METHODS = collections.OrderedDict()
DEFAULT_RESPONSE_FORMAT = 'json'


# helpers
def import_errors(cls_path):
    module_path, cls_name = cls_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        raise Exception('invalid module: "%s"' % module_path)
    if not hasattr(module, cls_name):
        raise Exception('module "%s" doesn\'t have class "%s"' % (module_path, cls_name))
    return getattr(module, cls_name)


class ServerMethodMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['class_creation_counter'] = ServerMethodMetaClass.creation_counter
        ServerMethodMetaClass.creation_counter += 1
        if name in METHODS:
            attrs['ClientMethod'] = METHODS[name]
        new_class = super(ServerMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        client_method = attrs.get('ClientMethod', NotImplemented)
        if client_method is not NotImplemented:
            SERVER_METHODS[client_method] = new_class
        return new_class


class ServerMethod(object, metaclass=ServerMethodMetaClass):
    ClientMethod = NotImplemented
    errors = import_errors(getattr(settings, 'APY_ERRORS')) if hasattr(settings, 'APY_ERRORS') else Errors

    def __init__(self, **kwargs):
        """
        Constructor. Called in the URLconf; can contain helpful extra
        keyword arguments, and other things.
        """
        # Go through keyword arguments, and either save their values to our
        # instance, or raise an error.
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.request = None
        self.method = None
        self.args = None
        self.kwargs = None
        self.dirty_data = None
        self.data = None

    @classmethod
    def as_view(cls, **initkwargs):
        """
        Main entry point for a request-response process.
        """
        # sanitize keyword arguments
        for key in initkwargs:
            if key in cls.ClientMethod.http_method_names:
                raise TypeError("You tried to pass in the %s method name as a "
                                "keyword argument to %s(). Don't do that."
                                % (key, cls.__name__))
            if not hasattr(cls, key):
                raise TypeError("%s() received an invalid keyword %r" % (
                    cls.__name__, key))

        def view(request, *args, **kwargs):
            self = cls(**initkwargs)  # pylint: disable=W0142
            return self.dispatch(request, *args, **kwargs)

        # take name and docstring from class
        functools.update_wrapper(view, cls, updated=())

        # and possible attributes set by decorators
        # like csrf_exempt from dispatch
        functools.update_wrapper(view, cls.dispatch, assigned=())
        return view

    def dispatch(self, request, *args, **kwargs):
        # Try to dispatch to the right method; if a method doesn't exist,
        # defer to the error handler. Also defer to the error handler if the
        # request method isn't on the approved list.
        self.method = request.method.upper()
        if self.method not in self.ClientMethod.http_method_names:
            return self.http_method_not_allowed()
        self.request = request
        self.args = args
        self.kwargs = kwargs
        self.dirty_data = self._get_data_from_request()
        try:
            response, http_status_code = self.get_response()
        except InvalidFormError as e:
            messages = [f + ": " + ". ".join(map(str, v)) for f, v in list(e.form.errors.items())]
            response, http_status_code = self.error_response(self.errors.INVALID_PARAM, messages)
            return self.return_response(response, http_status_code)

        return self.return_response(response, http_status_code)

    def internal_dispatch(self, request, http_method, dirty_data, raise_exception=False):
        self.method = http_method
        self.request = request
        self.args = None
        self.kwargs = None
        self.dirty_data = dirty_data
        response, _ = self.get_response(raise_exception=raise_exception)
        return response

    def http_method_not_allowed(self):
        message = 'Only %s calls allowed for this url' % (','.join(self.ClientMethod.http_method_names))
        response, http_status_code = self.error_response(self.errors.INVALID_HTTP_METHOD, [message])
        return self.return_response(response, http_status_code)

    ######################################
    def ok_response(self, data=None, warnings=None, http_code=http_client.OK):
        response = {}
        response['ok'] = True
        if data is not None:
            response['data'] = data
        if warnings:
            response['warnings'] = warnings
        return response, http_code

    def error_response(self, error, messages=None, details=None):
        d = {'ok': False, 'error': error['name']}
        if messages:
            d['error_messages'] = messages
        if details:
            d['error_details'] = details
        return d, error['http_code']

    def handle_exception(self, exc):
        if not hasattr(self.errors, 'get_error_for_exception'):
            raise exc
        return self.error_response(**self.errors.get_error_for_exception(exc))

    def get_response(self, raise_exception=False):
        self.data = self.clean_data(self.dirty_data)
        if 'language' in self.dirty_data:
            self.request.language = self.dirty_data['language']
        if 'timezone' in self.dirty_data:
            self.request.timezone = self.dirty_data['timezone']
        processor = getattr(self, 'process_%s' % self.method.lower())
        try:
            response, http_status_code = processor()
        except Exception as e:  # pylint: disable=W0703
            if raise_exception:
                raise
            return self.handle_exception(e)
        return response, http_status_code

    ######################################
    def _get_data_from_request(self):
        data = {}
        if self.method.upper() == 'GET':
            self._add_querydict_to_data(self.request.GET, data)
        elif self.method.upper() == 'POST':
            self._add_querydict_to_data(self.request.POST, data)
        elif self.method.upper() == 'PUT':
            self._parse_request_body(data)
        elif self.method.upper() == 'DELETE':
            self._parse_request_body(data)
        # add kwargs from url path
        if self.kwargs:
            data.update(self.kwargs)
        return data

    def _add_querydict_to_data(self, query_dict, data):
        for k, v in query_dict.items():
            if k.endswith('[]'):
                k = k[:-2]
            data[k] = v

    def _parse_request_body(self, data):
        content_type = self.request.META.get('HTTP_CONTENT_TYPE', self.request.META.get('CONTENT_TYPE', ''))
        if not content_type: return
        if content_type.startswith('multipart/'):
            querydict = self.request.parse_file_upload(self.request.META, self.request)[0]
        elif content_type.startswith('application/json'):
            querydict = json.loads(self.request.body.decode('utf-8'))
        else:
            raise Exception('invalid content type: {0}'.format(content_type))
        self._add_querydict_to_data(querydict, data)

    def clean_data(self, dirty_data):
        form = self.ClientMethod.get_input_form(self.method)
        if form:
            if getattr(self.request, 'FILES'):
                f = form(dirty_data, self.request.FILES)
            else:
                f = form(dirty_data)
            if not f.is_valid():
                raise InvalidFormError(f)
            cleaned_data = f.cleaned_data
        else:
            cleaned_data = {}
        if dirty_data.get('callback'):
            cleaned_data['callback'] = str(dirty_data['callback'])
        return cleaned_data

    def return_response(self, response, http_status_code):
        # add pagination to requests with limit and offset
        if self.data and self.data.get('limit') is not None and self.data.get('offset') is not None:
            response['pagination'] = {}
            d = collections.OrderedDict(urllib.parse.parse_qsl(self.request.META['QUERY_STRING']) if self.request.META.get('QUERY_STRING') else [])
            d['offset'] = self.data['offset'] + self.data['limit']
            d['limit'] = self.data['limit']
            response['pagination']['next'] = self.request.build_absolute_uri(self.request.path + '?' + urllib.parse.urlencode(d))
            if self.data['offset'] > 0:
                d['offset'] = max(self.data['offset'] - self.data['limit'], 0)
                d['limit'] = min(self.data['limit'], self.data['offset'] - d['offset'])
                response['pagination']['prev'] = self.request.build_absolute_uri(self.request.path + '?' + urllib.parse.urlencode(d))

        response_format = self.data and self.data.get('format') or DEFAULT_RESPONSE_FORMAT
        if response_format not in ['json']:
            response_format = DEFAULT_RESPONSE_FORMAT  # TODO add support for xml
        if response_format == 'json':
            formatted_response = json_encode(response, self.request)
            # raise Exception(formatted_response)
            mimetype = 'application/json'
            callback = self.data and self.data.get('callback')
            if callback:
                formatted_response = '%s(%s)' % (callback, formatted_response)
                mimetype = 'text/javascript'

        return http.HttpResponse(formatted_response, status=http_status_code, mimetype=mimetype)


def json_encode(response, request):
    data = response.get('data')
    if data is not None:
        if isinstance(data, list):
            response['data'] = [d.to_json(request) for d in data]
        else:
            response['data'] = data.to_json(request)
    return json.dumps(response)


# errors
class AccessForbiddenError(Exception):
    pass


class InvalidFormError(Exception):
    def __init__(self, form):
        Exception.__init__(self, form.errors.as_text())
        self.form = form


# helper classes
class ServerObjectsMethodMetaClass(ServerMethodMetaClass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ServerObjectsMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        if new_class.ClientMethod is not NotImplemented:
            new_class.model = CLIENT_TO_SERVER_MODELS[new_class.ClientMethod.model]
        return new_class


class ServerObjectsMethod(ServerMethod, metaclass=ServerObjectsMethodMetaClass):
    model = NotImplemented

    def process_post(self):
        raise NotImplementedError()

    def process_get(self):
        raise NotImplementedError()

    def process_delete(self):
        raise NotImplementedError()


class ServerObjectMethodMetaClass(ServerMethodMetaClass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ServerObjectMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        if new_class.ClientMethod is not NotImplemented:
            new_class.model = CLIENT_TO_SERVER_MODELS[new_class.ClientMethod.model]
        return new_class


class ServerObjectMethod(ServerMethod, metaclass=ServerObjectMethodMetaClass):
    model = NotImplemented

    def process_get(self):
        raise NotImplementedError()

    def process_put(self):
        raise NotImplementedError()

    def process_delete(self):
        raise NotImplementedError()


class ServerObjectNestedMethodMetaClass(ServerMethodMetaClass):
    def __new__(cls, name, bases, attrs):
        new_class = super(ServerObjectNestedMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        if new_class.ClientMethod is not NotImplemented:
            new_class.model = CLIENT_TO_SERVER_MODELS[new_class.ClientMethod.model]
            new_class.nested_model = CLIENT_TO_SERVER_MODELS[new_class.ClientMethod.nested_model]
        return new_class


class ServerObjectNestedMethod(ServerMethod, metaclass=ServerObjectNestedMethodMetaClass):
    model = NotImplemented
    nested_model = NotImplemented

    def process_post(self):
        raise NotImplementedError()

    def process_get(self):
        raise NotImplementedError()


def add_nested_methods_for_model(lcls, model, base_class):
    for name, field in model.ClientModel.get_nested_method_fields():  # pylint: disable=W0612
        cname = '%s%sNestedMethod' % (model.__name__, utils.snake_case_to_camel_case(name))
        lcls[cname] = type(cname, (base_class,), {})


# way to call the api internally
class InternalDispatch(object):
    def __init__(self, version):
        self.server_methods = {}
        self.urls = []
        self.categories = collections.OrderedDict()
        for client_method, server_method in SERVER_METHODS.items():
            url_pattern = '^/%s$' % (client_method.url_pattern)
            view = server_method.as_view()
            self.server_methods[client_method] = server_method()
            self.urls.append(url(
                    url_pattern, view,
                    name='api-v{version}-{name}'.format(version=version, name=client_method.__name__)))
            category_methods = self.categories.setdefault(client_method.category, [])
            for http_method in client_method.http_method_names:
                if http_method not in client_method.names:
                    raise Exception('cannot create class %s, name for %s not specified' %
                                    (client_method.__name__, http_method))
                category_methods.append(
                    {'method': client_method,
                     'http_method': http_method,
                     'name': client_method.__name__,
                     'display_name': client_method.names[http_method],
                     'form': client_method.get_input_form(http_method)})
        self.urlpatterns = patterns('', *self.urls)

    def internal_call(self, request, http_method, client_method, dirty_data, raise_exception=True):
        dirty_data = dirty_data.copy()
        if isinstance(client_method, str):
            server_method = self.server_methods.get(METHODS[client_method])
        else:
            server_method = self.server_methods.get(client_method)
        if not server_method:
            raise http.Http404('Invalid client method: "%r"' % client_method)
        return server_method.internal_dispatch(request, http_method, dirty_data, raise_exception=raise_exception)

    def internal_post(self, request, client_method, dirty_data, raise_exception=True):
        return self.internal_call(request, 'POST', client_method, dirty_data, raise_exception=raise_exception)

    def internal_get(self, request, client_method, dirty_data, raise_exception=True):
        return self.internal_call(request, 'GET', client_method, dirty_data, raise_exception=raise_exception)

    def internal_put(self, request, client_method, dirty_data, raise_exception=True):
        return self.internal_call(request, 'PUT', client_method, dirty_data, raise_exception=raise_exception)

    def internal_delete(self, request, client_method, dirty_data, raise_exception=True):
        return self.internal_call(request, 'DELETE', client_method, dirty_data, raise_exception=raise_exception)
