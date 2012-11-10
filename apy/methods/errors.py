import http.client

class ErrorsMetaClass(type):
    def __new__(cls, name, bases, attrs):
        nattrs = {}
        for k,v in attrs.items():
            if isinstance(v,tuple):
                nattrs[k] = {'name':k.lower(),'desc':v[0],'http_code':v[1]}
            else:
                nattrs[k] = v
        return super(ErrorsMetaClass,cls).__new__(cls, name, bases, nattrs)

class BaseErrors(object, metaclass=ErrorsMetaClass):
    pass

class GeneralErrors(BaseErrors):
    UNKNOWN_ERROR = ('An unknown error occurred',http.client.INTERNAL_SERVER_ERROR)
    UNKNOWN_API_METHOD = ('Unknown API method',http.client.BAD_REQUEST)
    INVALID_HTTP_METHOD = ('Invalid HTTP method',http.client.METHOD_NOT_ALLOWED)

class ParameterErrors(BaseErrors):
    INVALID_PARAM = ('Invalid parameter',http.client.BAD_REQUEST)

class ResourceErrors(BaseErrors):
    NOT_FOUND = ('Resource not found',http.client.NOT_FOUND)

class AuthErrors(BaseErrors):
    FORBIDDEN = ('Forbidden',http.client.FORBIDDEN)

class Errors(GeneralErrors,ParameterErrors,ResourceErrors,AuthErrors): pass
