from __future__ import unicode_literals, absolute_import

from django.db import models, connection
from django.utils.translation import ugettext_lazy as _
from django import get_version

from .descriptors import *
from .dict import *
from .virtual import *
from . import forms, utils


class HStoreField(models.Field):
    """ HStore Base Field """
    
    def __init_dict(self, value):
        """
        initializes HStoreDict
        """
        return HStoreDict(value, self)

    def validate(self, value, *args):
        super(HStoreField, self).validate(value, *args)
        forms.validate_hstore(value)

    def contribute_to_class(self, cls, name):
        super(HStoreField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, HStoreDescriptor(self))

    def get_default(self):
        """
        Returns the default value for this field.
        """
        # if default defined
        if self.has_default():
            # if default is callable
            if callable(self.default):
                return self.__init_dict(self.default())
            # if it's a dict
            elif isinstance(self.default, dict):
                return self.__init_dict(self.default)
            # else just return it
            return self.default
        # if allowed to return None
        if (not self.empty_strings_allowed or (self.null and
                   not connection.features.interprets_empty_strings_as_nulls)):
            return None
        # default to empty dict
        return self.__init_dict({})

    def get_prep_value(self, value):
        if isinstance(value, dict) and not isinstance(value, HStoreDict):
            return self.__init_dict(value)
        else:
            return value

    def get_db_prep_value(self, value, connection, prepared=False):
        if not prepared:
            value = self.get_prep_value(value)
        return value

    def value_to_string(self, obj):
        return self._get_val_from_obj(obj)

    def db_type(self, connection=None):
        return 'hstore'

    def south_field_triple(self):
        from south.modelsinspector import introspector
        name = '%s.%s' % (self.__class__.__module__, self.__class__.__name__)
        args, kwargs = introspector(self)
        return name, args, kwargs


if get_version() >= '1.7':
    from .lookups import *

    HStoreField.register_lookup(HStoreGreaterThan)
    HStoreField.register_lookup(HStoreGreaterThanOrEqual)
    HStoreField.register_lookup(HStoreLessThan)
    HStoreField.register_lookup(HStoreLessThanOrEqual)
    HStoreField.register_lookup(HStoreContains)
    HStoreField.register_lookup(HStoreIContains)


class DictionaryField(HStoreField):
    description = _("A python dictionary in a postgresql hstore field.")
    
    def __init__(self, *args, **kwargs):
        self.schema = kwargs.pop('schema', None)
        self.pickle = False
        
        # if schema parameter is supplied the behaviour is slightly different
        if self.schema is not None:
            self._validate_schema(self.schema)
            self.pickle = True
            # DictionaryField with schema is not editable via admin
            kwargs['editable'] = False
            # DictionaryField with schema defaults to empty dict
            kwargs['default'] = {}
        
        super(DictionaryField, self).__init__(*args, **kwargs)
    
    def __init_dict(self, value):
        """
        init HStoreDict
        pass pickle=True if in "schema" mode
        """
        return HStoreDict(value, self, pickle=self.pickle)

    def contribute_to_class(self, cls, name):
        super(DictionaryField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, HStoreDescriptor(self, pickle=self.pickle))
        
        if self.schema:
            self._add_virtual_fields_on_class(cls, name)
    
    def _validate_schema(self, schema):
        if not isinstance(schema, list):
            raise ValueError('schema parameter must be a list')
    
        if len(schema) == 0:
            raise ValueError('schema parameter cannot be an empty list')
        
        for field in schema:
            if not isinstance(field, dict):
                raise ValueError('schema parameter must contain dicts representing fields, read the docs to see the format')
            
            if not field.has_key('name'):
                raise ValueError('schema element %s is missing the name key' % field)
            
            if not field.has_key('class'):
                raise ValueError('schema element %s is missing the class key' % field)

    def _add_virtual_fields_on_class(self, cls, hstore_field_name):
        """
        this methods creates all the virtual fields automatically by reading the schema attribute
        """
        # add hstore_virtual_fields attribute to class
        if not hasattr(cls._meta, 'hstore_virtual_fields'):
            cls._meta.hstore_virtual_fields = []
    
        if not hasattr(cls, '_add_hstore_virtual_fields_to_fields'):
            cls._add_hstore_virtual_fields_to_fields = _add_hstore_virtual_fields_to_fields

        if not hasattr(cls, '_remove_hstore_virtual_fields_from_fields'):
            cls._remove_hstore_virtual_fields_from_fields = _remove_hstore_virtual_fields_from_fields
            
        for field in self.schema:
            # insert the name of the hstore field, which is necessary
            # for the initialization of the virtual field
            field['kwargs']['hstore_field_name'] = hstore_field_name
            # initialize the virtual field by specifying the class and the kwargs
            virtual_field = create_hstore_virtual_field(
                field_cls=field['class'],
                kwargs=field['kwargs']
            )
            # set the name and the attname properties of the field
            virtual_field.name = field['name']
            virtual_field.attname = field['name']
            # add the field on the class
            setattr(cls, field['name'], virtual_field)
            # add the field in the virtual fields
            cls._meta.virtual_fields.append(virtual_field)
            # add this field to hstore_virtual_fields list
            cls._meta.hstore_virtual_fields.append(virtual_field)

    def formfield(self, **kwargs):
        kwargs['form_class'] = forms.DictionaryField
        return super(DictionaryField, self).formfield(**kwargs)

    def _value_to_python(self, value):
        return value


class ReferencesField(HStoreField):
    description = _("A python dictionary of references to model instances in an hstore field.")

    def contribute_to_class(self, cls, name):
        super(ReferencesField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, HStoreReferenceDescriptor(self))

    def formfield(self, **kwargs):
        kwargs['form_class'] = forms.ReferencesField
        return super(ReferencesField, self).formfield(**kwargs)

    def get_prep_lookup(self, lookup, value):
        if isinstance(value, dict):
            return utils.serialize_references(value)
        return value

    def get_prep_value(self, value):
        return utils.serialize_references(value)

    def to_python(self, value):
        return value if isinstance(value, dict) else HStoreReferenceDict({})

    def _value_to_python(self, value):
        return utils.acquire_reference(value)


# south compatibility
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules(rules=[], patterns=['django_hstore\.hstore'])
except ImportError:
    pass
