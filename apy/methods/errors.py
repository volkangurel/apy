import http.client

EXCEPTION_MAP = {}


class ApiException(Exception):
    def __init__(self, messages=None, details=None):
        Exception.__init__(self)
        self.messages = messages
        self.details = details


# errors
class ErrorsMetaClass(type):
    def __new__(cls, name, bases, attrs):
        nattrs = {}
        for k, v in attrs.items():
            if isinstance(v, tuple):
                e = {'name': k.lower(), 'desc': v[0], 'http_code': v[1]}
                nattrs[k] = e
                if len(v) > 2:
                    EXCEPTION_MAP[v[2]] = e
            else:
                nattrs[k] = v
        return super(ErrorsMetaClass, cls).__new__(cls, name, bases, nattrs)


class BaseErrors(object, metaclass=ErrorsMetaClass):
    pass


class GeneralErrors(BaseErrors):
    UNKNOWN_ERROR = ('An unknown error occurred', http.client.INTERNAL_SERVER_ERROR)
    UNKNOWN_API_METHOD = ('Unknown API method', http.client.BAD_REQUEST)
    INVALID_HTTP_METHOD = ('Invalid HTTP method', http.client.METHOD_NOT_ALLOWED)


class ParameterErrors(BaseErrors):
    INVALID_PARAM = ('Invalid parameter', http.client.BAD_REQUEST)


class ResourceErrors(BaseErrors):
    NOT_FOUND = ('Resource not found', http.client.NOT_FOUND)


class AuthErrors(BaseErrors):
    FORBIDDEN = ('Forbidden', http.client.FORBIDDEN)


class Errors(GeneralErrors, ParameterErrors, ResourceErrors, AuthErrors):

    @classmethod
    def get_error_for_exception(cls, exc):
        if exc.__class__ not in EXCEPTION_MAP: raise exc
        return {'error': EXCEPTION_MAP[exc.__class__], 'messages': exc.messages, 'details': exc.details}
