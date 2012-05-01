import re
import collections
import urllib
import urlparse
import httplib
import json
import functools

from django import http
from django.conf import settings

from . import errors

class ApiMethodMetaClass(type):
    creation_counter = 0
    def __new__(cls, name, bases, attrs):
        if name!='ApiMethod':
            if not attrs['name']: raise Exception('subclass needs a "name" field')
            if not attrs['url_pattern']: raise Exception('subclass needs a "url_pattern" field')
        attrs['class_creation_counter'] = ApiMethodMetaClass.creation_counter
        ApiMethodMetaClass.creation_counter += 1
        new_class = super(ApiMethodMetaClass,cls).__new__(cls, name, bases, attrs)
        return new_class

class ApiMethod(object):
    """
    View class based off of django.views.generic.View, main difference is dispatch doesn't
    pass request, args and kwargs to methods, since they are already attributes of class instance
    """
    #pylint: disable=E1102,W0141
    __metaclass__ = ApiMethodMetaClass

    http_method_names = ['get','post','patch','delete']

    InputForm = None

    default_response_format = 'json'

    url_pattern = None
    name = None

    def __init__(self, **kwargs):
        """
        Constructor. Called in the URLconf; can contain helpful extra
        keyword arguments, and other things.
        """
        # Go through keyword arguments, and either save their values to our
        # instance, or raise an error.
        for key, value in kwargs.iteritems():
            setattr(self, key, value)
        self.request = None
        self.args = None
        self.kwargs = None
        self.data = None
        self.errors = getattr(settings,'apy_errors',errors.Errors)

    @classmethod
    def as_view(cls, **initkwargs):
        """
        Main entry point for a request-response process.
        """
        # sanitize keyword arguments
        for key in initkwargs:
            if key in cls.http_method_names:
                raise TypeError(u"You tried to pass in the %s method name as a "
                                u"keyword argument to %s(). Don't do that."
                                % (key, cls.__name__))
            if not hasattr(cls, key):
                raise TypeError(u"%s() received an invalid keyword %r" % (
                    cls.__name__, key))

        def view(request, *args, **kwargs):
            self = cls(**initkwargs) #pylint: disable=W0142
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
        method = request.method.lower()
        if method not in self.http_method_names or not hasattr(self, method):
            return self.http_method_not_allowed()
        self.request = request
        self.args = args
        self.kwargs = kwargs
        try:
            self.data = self.clean_data(self.get_data_from_request())
        except InvalidFormError, e:
            messages = [f + ": " + ". ".join(map(unicode,v)) for f, v in e.form.errors.items()]
            response, http_status_code = self.error_response(self.errors.PARAM,messages)
            return self.return_response(response, http_status_code)

        response, http_status_code = self.get_response()
        return self.return_response(response, http_status_code)

    def internal_dispatch(self, request, dirty_data):
        self.request = request
        self.data = self.clean_data(dirty_data)
        response, _ = self.get_response()
        return response

    def http_method_not_allowed(self):
        allowed_methods = [m for m in self.http_method_names if hasattr(self, m)]
        message = 'Only %s allowed for this API method'%','.join(allowed_methods)
        response, http_status_code = self.error_response(self.errors.HTTP_METHOD,[message])
        return self.return_response(response, http_status_code)

    ######################################
    def ok_response(self, response=None, warnings=None, http_code=httplib.OK):
        if not response: response = {}
        response['ok'] = True
        if warnings: response['warnings'] = warnings
        return response, http_code

    def error_response(self, error, messages=None):
        d = {'ok': False, 'error_code': error[0], 'error_name': error[1]}
        if messages: d['error_messages'] = messages
        return d, error[2]

    def get_response(self):
        try:
            response, http_status_code = self.process()
        except AccessForbiddenError:
            response, http_status_code = self.error_response(self.errors.FORBIDDEN)
        return response, http_status_code

    ######################################
    def get_data_from_request(self):
        data = {}
        for k,v in self.request.REQUEST.iteritems():
            if k.endswith('[]'): k = k[:-2]
            data[k] = v
        if self.kwargs: data.update(self.kwargs)
        return data

    def clean_data(self,dirty_data):
        if self.InputForm:
            if getattr(self.request,'FILES',False): f = self.InputForm(dirty_data, self.request.FILES)
            else: f = self.InputForm(dirty_data)
            if not f.is_valid(): raise InvalidFormError(f)
            cleaned_data = f.cleaned_data
        else:
            cleaned_data = {}
        return cleaned_data

    def return_response(self, response, http_status_code):
        # add pagination to requests with limit and offset
        if self.data and self.data.get('limit') is not None and self.data.get('offset') is not None:
            response['pagination'] = {}
            d = collections.OrderedDict(urlparse.parse_qsl(self.request.META['QUERY_STRING']) if self.request.META.get('QUERY_STRING') else [])
            d['offset'] = self.data['offset']+self.data['limit']
            d['limit'] = self.data['limit']
            response['pagination']['next'] = self.request.build_absolute_uri(self.request.path+'?'+urllib.urlencode(d))
            if self.data['offset']>0:
                d['offset'] = max(self.data['offset']-self.data['limit'],0)
                d['limit'] = min(self.data['limit'],self.data['offset']-d['offset'])
                response['pagination']['prev'] = self.request.build_absolute_uri(self.request.path+'?'+urllib.urlencode(d))

        response_as_string = json.dumps(response)

        callback = self.data.get('callback')
        if callback:
            return http.HttpResponse('%s(%s)'%(callback,response_as_string), status=http_status_code, mimetype='text/javascript')
        else:
            return http.HttpResponse(response_as_string, status=http_status_code, mimetype='application/json')

    ######################################
    def process(self):
        """Overwrite this in subclasses to create the logic for the API method"""
        return self.error_response(self.errors.API_METHOD)

    ######################################
    @property
    def url_doc(self):
        return url_pattern_re.sub(url_pattern_repl,self.url_pattern)

url_pattern_re = re.compile('\(\?P<([^>]+)>[^()]+\)')
def url_pattern_repl(x):
    return '<i>:%s</i>'%x.group(1)



class ApiReadMethod(ApiMethod):
    http_method_names = ['get']

class ApiCreateMethod(ApiMethod):
    http_method_names = ['post']

class ApiUpdateMethod(ApiMethod):
    http_method_names = ['patch']

class ApiDeleteMethod(ApiMethod):
    http_method_names = ['delete']


class AccessForbiddenError(Exception):
    pass

class InvalidFormError(Exception):
    def __init__(self,form):
        super(InvalidFormError,self).__init__(self)
        self.form = form
