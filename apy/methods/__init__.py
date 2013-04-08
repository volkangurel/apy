import inspect

from django import http
from django.conf.urls import patterns, url

from . import utils


class ApiCreateMethod(utils.ApiMethod):
    http_method_names = ['POST']


class ApiReadMethod(utils.ApiMethod):
    http_method_names = ['GET']


class ApiUpdateMethod(utils.ApiMethod):
    http_method_names = ['PUT']


class ApiDeleteMethod(utils.ApiMethod):
    http_method_names = ['DELETE']


class ApiDirectory(object):

    def __init__(self, version=None, modules=None):
        if version is None:
            raise Exception('need to call register_version with a version')
        if modules is None:
            raise Exception('need to call register_version with sections')

        self.version = version
        self.methods = {}
        self.sections = []
        self.urls = []
        for module, name in modules:
            module_api_methods = []
            for k in dir(module):
                api_method = getattr(module, k)
                if not inspect.isclass(api_method) or not issubclass(api_method, utils.ApiMethod):
                    continue
                module_api_methods.append(api_method)
            module_api_methods.sort(key=lambda x: x.class_creation_counter)

            section_methods = []
            for api_method in module_api_methods:
                url_pattern = '^/%s$' % (api_method.url_pattern)
                self.urls.append(url(url_pattern, api_method.as_view()))
                for http_method in api_method.http_method_names:
                    if http_method not in api_method.names:
                        raise Exception('cannot create class %s in module %s, name for %s not specified' %
                                        (api_method.__name__, module.__name__, http_method))
                    api_method_name = api_method.names[http_method]
                    self.methods[api_method_name] = (api_method, http_method)
                    section_methods.append(
                        {'method': api_method, 'http_method': http_method,
                         'name': api_method_name, 'form': api_method.get_input_form(http_method)})
            self.sections.append({'name': name, 'methods': section_methods})

    @property
    def urlpatterns(self):
        return patterns('', *self.urls)

    def internal_call(self, request, method_name, dirty_data, raise_exception=True):
        dirty_data = dirty_data.copy()
        method_tuple = self.methods.get(method_name)
        if not method_tuple:
            raise http.Http404('Invalid method name: "%s"' % method_name)
        method, http_method = method_tuple
        return method.internal_dispatch(request, http_method, dirty_data, raise_exception=raise_exception)
