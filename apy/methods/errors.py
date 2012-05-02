import httplib

class BaseErrors(object):
    UNKNOWN = (1,'An unknown error occurred',httplib.INTERNAL_SERVER_ERROR)
    API_METHOD = (2,'Unknown API method',httplib.BAD_REQUEST)
    HTTP_METHOD = (3,'Invalid HTTP method',httplib.METHOD_NOT_ALLOWED)

class ParameterErrors(object):
    PARAM = (100,'Invalid parameter',httplib.BAD_REQUEST)

class ResourceErrors(object):
    NOT_FOUND = (200,'Resource not found',httplib.NOT_FOUND)

class Errors(BaseErrors,ParameterErrors,ResourceErrors): pass
