import re
import collections
import urllib.request
import urllib.parse
import urllib.error
import http.client
import json
import functools
import datetime
import decimal

from django import http as django_http
from django.conf import settings
from django.utils import importlib

from apy.methods.errors import Errors


class ApiMethodMetaClass(type):
    creation_counter = 0

    def __new__(cls, name, bases, attrs):
        attrs['class_creation_counter'] = ApiMethodMetaClass.creation_counter
        ApiMethodMetaClass.creation_counter += 1
        new_class = super(ApiMethodMetaClass, cls).__new__(cls, name, bases, attrs)
        return new_class


def import_errors(cls_path):
    module_path, cls_name = cls_path.rsplit('.', 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        raise Exception('invalid module: "%s"' % module_path)
    if not hasattr(module, cls_name):
        raise Exception('module "%s" doesn\'t have class "%s"' % (module_path, cls_name))
    return getattr(module, cls_name)


class ApiMethod(object, metaclass=ApiMethodMetaClass):
    """
    View class based off of django.views.generic.View, main difference is dispatch doesn't
    pass request, args and kwargs to methods, since they are already attributes of class instance
    """

    http_method_names = ['POST', 'GET', 'PUT', 'DELETE']
    errors = import_errors(getattr(settings, 'APY_ERRORS')) if hasattr(settings, 'APY_ERRORS') else Errors

    PostForm = None
    GetForm = None
    PutForm = None
    DeleteForm = None

    default_response_format = 'json'

    url_pattern = None
    names = {}

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
            if key in cls.http_method_names:
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
        if self.method not in self.http_method_names:
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

    @classmethod
    def internal_dispatch(cls, request, http_method, dirty_data):
        self = cls()
        self.method = http_method
        self.request = request
        self.dirty_data = dirty_data
        response, _ = self.get_response()
        return response

    def http_method_not_allowed(self):
        message = 'Only %s calls allowed for this url' % (','.join(self.http_method_names))
        response, http_status_code = self.error_response(self.errors.INVALID_HTTP_METHOD, [message])
        return self.return_response(response, http_status_code)

    ######################################
    def ok_response(self, data=None, warnings=None, http_code=http.client.OK):
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

    def get_response(self):
        self.data = self.clean_data(self.dirty_data)
        if 'language' in self.dirty_data:
            self.request.language = self.dirty_data['language']
        if 'timezone' in self.dirty_data:
            self.request.timezone = self.dirty_data['timezone']
        processor = getattr(self, 'process_%s' % self.method.lower())
        try:
            response, http_status_code = processor()
        except Exception as e:  # pylint: disable=W0703
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
            put_querydict = self.request.parse_file_upload(self.request.META, self.request)[0]
            self._add_querydict_to_data(put_querydict, data)
        elif self.method.upper() == 'DELETE':
            delete_querydict = self.request.parse_file_upload(self.request.META, self.request)[0]
            self._add_querydict_to_data(delete_querydict, data)
        # add kwargs from url path
        if self.kwargs:
            data.update(self.kwargs)
        return data

    def _add_querydict_to_data(self, query_dict, data):
        for k, v in query_dict.items():
            if k.endswith('[]'):
                k = k[:-2]
            data[k] = v

    @classmethod
    def get_input_form(cls, method):
        return getattr(cls, '%sForm' % method.capitalize())

    def clean_data(self, dirty_data):
        form = self.get_input_form(self.method)
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

        response_format = self.data and self.data.get('format') or self.default_response_format
        if response_format not in ['json']:
            response_format = 'json'  # TODO add support for xml
        if response_format == 'json':
            formatted_response = json.dumps(response, cls=ApyJSONEncoder)
            mimetype = 'application/json'
            callback = self.data and self.data.get('callback')
            if callback:
                formatted_response = '%s(%s)' % (callback, formatted_response)
                mimetype = 'text/javascript'

        return django_http.HttpResponse(formatted_response, status=http_status_code, mimetype=mimetype)

    ######################################
    # def process(self):
    #     """Overwrite this in subclasses to create the logic for the API method"""
    #     return self.error_response(self.errors.UNKNOWN_API_METHOD)

    ######################################
    @property
    def url_doc(self):
        return url_pattern_re.sub(url_pattern_repl, self.url_pattern)


url_pattern_re = re.compile('\(\?P<([^>]+)>[^()]+\)')


def url_pattern_repl(x):
    return '<i>:%s</i>' % x.group(1)


class ApyJSONEncoder(json.JSONEncoder):
    def default(self, obj):  # pylint: disable=E0202
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        else:
            return super(ApyJSONEncoder, self).default(obj)


class AccessForbiddenError(Exception):
    pass


class InvalidFormError(Exception):
    def __init__(self, form):
        Exception.__init__(self, form.errors.as_text())
        self.form = form
