import inspect

from django import http
from django.conf.urls.defaults import patterns, url

from . import utils


class ApiReadMethod(utils.ApiMethod):
    http_method_names = ['GET']


class ApiCreateMethod(utils.ApiMethod):
    http_method_names = ['POST']


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
        for module, prefix, name in modules:
            module_methods = []
            for k in dir(module):
                m = getattr(module, k)
                if not inspect.isclass(m) or not issubclass(m, utils.ApiMethod):
                    continue
                self.methods[m.name] = m
                module_methods.append(m)
            module_methods.sort(key=lambda x: x.class_creation_counter)
            self.sections.append({'prefix': prefix, 'name': name, 'methods': module_methods})
            for m in module_methods:
                self.urls.append(url('^/%s/%s$' % (prefix, m.url_pattern), m.as_view(), name='api-v%d-method-%s' % (version, m.name)))

    @property
    def urlpatterns(self):
        return patterns('', *self.urls)

    def internal_call(self, request, method_name, dirty_data):
        dirty_data = dirty_data.copy()
        method = self.methods.get(method_name)
        if not method:
            raise http.Http404('Invalid method name: "%s"' % method_name)
        return method.internal_dispatch(request, dirty_data)
