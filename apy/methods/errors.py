import httplib

class ErrorsMetaClass(type):
    def __new__(cls, name, bases, attrs):
        nattrs = {}
        for k,v in attrs.iteritems():
            if type(v)==tuple:
                nattrs[k] = {'name':k.lower(),'desc':v[0],'http_code':v[1]}
            else:
                nattrs[k] = v
        return super(ErrorsMetaClass,cls).__new__(cls, name, bases, nattrs)

class BaseErrors(object):
    __metaclass__ = ErrorsMetaClass

class GeneralErrors(BaseErrors):
    UNKNOWN_ERROR = ('An unknown error occurred',httplib.INTERNAL_SERVER_ERROR)
    UNKNOWN_API_METHOD = ('Unknown API method',httplib.BAD_REQUEST)
    INVALID_HTTP_METHOD = ('Invalid HTTP method',httplib.METHOD_NOT_ALLOWED)

class ParameterErrors(BaseErrors):
    INVALID_PARAM = ('Invalid parameter',httplib.BAD_REQUEST)

class ResourceErrors(BaseErrors):
    NOT_FOUND = ('Resource not found',httplib.NOT_FOUND)

class AuthErrors(BaseErrors):
    FORBIDDEN = ('Forbidden',httplib.FORBIDDEN)

class Errors(GeneralErrors,ParameterErrors,ResourceErrors): pass
