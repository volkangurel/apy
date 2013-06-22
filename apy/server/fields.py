import collections


class BaseField(object):
    creation_counter = 0

    def __init__(self,
                 required_fields=None,  # other fields that getting data for this field requires
                 ):
        super(BaseField, self).__init__()
        self.required_fields = required_fields

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


class NestedIdField(BaseNestedField):
    # field that represents a model nested within a wrapping model, linked by an id
    def __init__(self, model_or_name, id_field, **kwargs):
        super(NestedIdField, self).__init__(model_or_name, required_fields=[id_field], **kwargs)
        self.id_field = id_field

    def to_client(self, request, owner, query_field, objects):
        ids = {obj.data[self.id_field] for obj in objects if self.id_field in obj.data}
        nested_objects = {d.get_id(): d for d in self.get_model(owner).find_for_client
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
        related_objects = self.get_model(owner).find_for_client(
            request, condition={self.filter_id_field: {'$in': ids}}, query_fields=query_field.sub_fields)
        data = collections.defaultdict(list)
        for obj in related_objects:
            data[obj[self.filter_id_field]].append(obj)
        for obj in objects:
            obj.client_data[query_field.key] = data[obj.get_id()]


class AssociationField(BaseNestedField):
    # field that represents a model nested within a wrapping model, fetched by a method on the wrapping model
    def __init__(self, model_or_name, method, **kwargs):
        super(AssociationField, self).__init__(model_or_name, **kwargs)
        self.method = method

    def to_client(self, request, owner, query_field, objects):
        method = getattr(self.get_model(owner), self.method)
        ids = {obj.get_id() for obj in objects}
        data = method(request, ids, query_field.sub_fields)
        for obj in objects:
            obj.client_data[query_field.key] = data.get(obj.get_id(), [])
