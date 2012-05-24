import collections

from apy.models import fields as apy_fields

### model metaclass
def get_declared_fields(bases, attrs):
    model_fields = [(field_name, attrs.pop(field_name)) for field_name, obj in attrs.items() if isinstance(obj, apy_fields.BaseField)]
    model_fields.sort(key=lambda x: x[1].creation_counter)

    for base in bases[::-1]:
        if hasattr(base, 'base_fields'):
            model_fields = base.base_fields.items() + model_fields

    return collections.OrderedDict(model_fields)

def get_permissions(bases, attrs):
    permissions = ApiModelPermissions()

    for base in bases:
        if not hasattr(base,'permissions'): continue
        permissions.update_with_other(base.permissions)

    if 'default_permissions' in attrs:
        permissions.update(**attrs.pop('default_permissions'))

    if 'additional_permissions' in attrs:
        permissions.add(**attrs.pop('additional_permissions'))

    return permissions

class ApiModelMetaClass(type):
    creation_counter = 0
    def __new__(cls, name, bases, attrs):
        attrs['base_fields'] = get_declared_fields(bases, attrs)
        attrs['permissions'] = get_permissions(bases, attrs)
        attrs['class_creation_counter'] = ApiModelMetaClass.creation_counter
        ApiModelMetaClass.creation_counter += 1
        new_class = super(ApiModelMetaClass,cls).__new__(cls, name, bases, attrs)
        return new_class

class ApiModelPermissions(object):

    def __init__(self):
        self.read_permissions = collections.defaultdict(set)
        self.update_permissions = collections.defaultdict(set)
        self.create_permissions = set()
        self.delete_permissions = set()

        self.object = None

    def __repr__(self):
        s = '<ApiModelPermissions:\n'
        s += 'read: ' + str(self.read_permissions) + '\n'
        s += 'update: ' + str(self.update_permissions) + '\n'
        s += 'create: ' + str(self.create_permissions) + '\n'
        s += 'delete: ' + str(self.delete_permissions) + '\n'
        s += '>'
        return s

    def __get__(self,instance,owner):
        if instance is not None:
            instance.update_permissions(self)
            self.object = instance # set the object bound to this permissions object
        return self

    def update_with_other(self,other):
        self.update(other.read_permissions,other.update_permissions,other.create_permissions,other.delete_permissions)

    def update(self,read=None,update=None,create=None,delete=None):
        if read: self.read_permissions.update(read)
        if update: self.update_permissions.update(update)
        if create: self.create_permissions = create
        if delete: self.delete_permissions = delete

    def add(self,read_permissions=None,update_permissions=None,
            create_permissions=None,delete_permissions=None):
        if read_permissions:
            for k,v in read_permissions.iteritems():
                self.read_permissions[k].update(v)
        if update_permissions:
            for k,v in update_permissions.iteritems():
                self.update[k].update(v)
        if create_permissions: self.create_permissions.update(create_permissions)
        if delete_permissions: self.delete_permissions.update(delete_permissions)

    def check_read_fields(self,request,fields):
        p = request.user.get_permissions(request, self.object)
        _fields = []
        user_roles = set(p['roles']) if 'roles' in p else set()
        if 'superuser' in user_roles: return fields # superusers have access to everything
        for k,v in fields:
            valid_roles = self.read_permissions.get(k,set()) | self.read_permissions.get('*',set())
            if 'public' in valid_roles or user_roles&valid_roles: _fields.append((k,v))
        return _fields

    def check_update_fields(self,request,fields):
        return fields

    def check_create_fields(self,request,fields):
        return fields

    @classmethod
    def can_delete(self,request):
        return False


class BaseApiModel(object):
    __metaclass__ = ApiModelMetaClass

    base_fields = None
    class_creation_counter = None
    is_hidden = False

    def __init__(self,*args,**kwargs):
        super(BaseApiModel,self).__init__(*args,**kwargs)

    @classmethod
    def pre_create(cls, request, fields):
        cls.permissions.check_create_fields(request,fields)
        # TODO: validate fields

    @classmethod
    def pre_update(cls, request, fields):
        cls.permissions.check_update_fields(request,fields)
        # TODO: validate fields

    @classmethod
    def pre_delete(cls, request, fields):
        cls.permissions.check_delete_fields(request,fields)

    @classmethod
    def validate_fields(cls,fields):
        for k,v in fields.items():
            if k not in cls.base_fields:
                raise apy_fields.ValidationError("invalid key '%s' for model '%s'"%(k,cls.__name__))
            cls.base_fields[k].validate(k,v,cls.__name__)

    @classmethod
    def get_selectable_fields(cls):
        return {k:v for k,v in cls.base_fields.iteritems() if v.is_selectable}

    @classmethod
    def get_default_fields(cls):
        return [(k,v) for k,v in cls.base_fields.iteritems() if v.is_default]

    @classmethod
    def get_fields(cls,keys):
        return [(k,cls.base_fields[k]) for k in keys]

    # permissions
    permissions = None
    default_permissions = {}

    def update_permissions(self, permissions):
        pass # used to update permissions based on individual object data
