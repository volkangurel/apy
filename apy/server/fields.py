import collections


class BaseField(object):
    creation_counter = 0

    def __init__(self,
                 required_fields=None,  # other fields that getting data for this field requires
                 in_place=False,
                 ):
        super(BaseField, self).__init__()
        self.required_fields = required_fields
        self.in_place = in_place

        self.creation_counter = BaseField.creation_counter
        BaseField.creation_counter += 1

    def to_client(self, request, owner, query_field, objects):
        raise NotImplementedError()

    # @classmethod TODO
    # def to_server(cls, request, objects, key):
    #     # used in modify and create
    #     # take in a client field, convert it to a
    #     raise NotImplementedError()


class BaseNestedField(BaseField):  # pylint: disable=W0223
    def __init__(self, model_or_name, **kwargs):
        super(BaseNestedField, self).__init__(**kwargs)
        self.model_or_name = model_or_name

    def get_model(self, owner):  # pylint: disable=W0613
        # owner is the model that contains this field
        if isinstance(self.model_or_name, str):
            from .models import SERVER_MODELS
            return SERVER_MODELS[self.model_or_name]
        else:
            return self.model_or_name


class NestedField(BaseNestedField):
    # field that represents a model nested within a wrapping model

    def to_client(self, request, owner, query_field, objects):
        for obj in objects:
            obj.client_data[query_field.key] = obj.data[query_field.key].self_to_client(request, query_field.sub_fields)


class NestedIdField(BaseNestedField):
    # field that represents a model nested within a wrapping model, linked by an id
    def __init__(self, model_or_name, id_field, **kwargs):
        super(NestedIdField, self).__init__(model_or_name, required_fields=[id_field], **kwargs)
        self.id_field = id_field

    def to_client(self, request, owner, query_field, objects):
        ids = {obj.data[self.id_field] for obj in objects if obj.data.get(self.id_field)}
        nested_objects = {d.get_id(): d for d in self.get_model(owner).read
                          (request, ids=ids, query_fields=query_field.sub_fields)}
        for obj in objects:
            obj.client_data[query_field.key] = nested_objects.get(obj.data[self.id_field])


class RelationIdField(BaseNestedField):  # pylint: disable=W0223
    # field that represents a relation nested within a wrapping model,
    # fetched by filtering the relation's filter_id_field by the id of the model instance
    def __init__(self, model_or_name, filter_id_field, **kwargs):
        super(RelationIdField, self).__init__(model_or_name, **kwargs)
        self.filter_id_field = filter_id_field

    def to_client(self, request, owner, query_field, objects):
        ids = {obj.get_id() for obj in objects}
        related_objects = self.get_model(owner).read(
            request, condition={self.filter_id_field: {'$in': ids}}, query_fields=query_field.sub_fields)
        data = collections.defaultdict(list)
        for obj in related_objects:
            data[obj[self.filter_id_field]].append(obj)
        for obj in objects:
            obj.client_data[query_field.key] = data[obj.get_id()]


class AssociationField(BaseNestedField):
    # field that represents a model nested within a wrapping model, fetched by a method on the wrapping model
    def __init__(self, model_or_name, method, extra_kwargs=None, **kwargs):
        super(AssociationField, self).__init__(model_or_name, **kwargs)
        self.method = method
        self.extra_kwargs = extra_kwargs or {}

    def to_client(self, request, owner, query_field, objects):
        model = self.get_model(owner)
        method = getattr(model, self.method)
        ids = {obj.get_id() for obj in objects}
        data = method(request, ids,
                      query_field.sub_fields or model.ClientModel.get_default_fields(),
                      **self.extra_kwargs)
        for obj in objects:
            obj.client_data[query_field.key] = data.get(obj.get_id(), [])


class RelationField(AssociationField):
    # field that represents a model nested within a wrapping model, linked by an id
    def __init__(self, relation_model_or_name, filtered_relation_field, **kwargs):
        super(RelationField, self).__init__(
            relation_model_or_name, 'get_related_objects',
            extra_kwargs={'filtered_relation_field': filtered_relation_field},
            **kwargs)

    def to_client(self, request, owner, query_field, objects):
        model = self.get_model(owner)
        ids = {obj.get_id() for obj in objects}
        data = model.get_related_objects(
            request, ids, query_field.sub_fields or model.ClientModel.get_default_fields(),
            **self.extra_kwargs)
        for obj in objects:
            obj.client_data[query_field.key] = data.get(obj.get_id(), [])
