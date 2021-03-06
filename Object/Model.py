import time, math

import numpy as np

from Common import logger
from Utilities import GetClassName, Attributes
from App import CoreManager


class Model:
    def __init__(self, name, **data):
        self.name = name
        self.mesh = None
        self.material_instances = []
        self.set_mesh(data.get('mesh'))

        for i, material_instance in enumerate(data.get('material_instances', [])):
            self.set_material_instance(material_instance, i)

        self.attributes = Attributes()

    def set_mesh(self, mesh):
        if mesh:
            self.mesh = mesh
            default_material_instance = CoreManager.instance().resource_manager.getDefaultMaterialInstance(
                skeletal=mesh.has_bone())
            material_instances = [default_material_instance, ] * len(mesh.geometries)
            for i in range(min(len(self.material_instances), len(material_instances))):
                material_instances[i] = self.material_instances[i]
            self.material_instances = material_instances

    def get_save_data(self):
        save_data = dict(
            object_type=GetClassName(self),
            mesh=self.mesh.name if self.mesh is not None else '',
            material_instances=[material_instance.name for material_instance in self.material_instances]
        )
        return save_data

    def get_material_count(self):
        return len(self.material_instances)

    def get_material_instance(self, index):
        return self.material_instances[index]

    def get_material_instance_name(self, index):
        material_instance = self.get_material_instance(index)
        return material_instance.name if material_instance else ''

    def get_material_instance_names(self):
        return [self.get_material_instance_name(i) for i in range(self.get_material_count())]

    def set_material_instance(self, material_instance, attribute_index):
        if attribute_index < len(self.material_instances):
            self.material_instances[attribute_index] = material_instance

    def getAttribute(self):
        self.attributes.setAttribute('name', self.name)
        self.attributes.setAttribute('mesh', self.mesh)
        self.attributes.setAttribute('material_instances', self.get_material_instance_names())
        return self.attributes

    def setAttribute(self, attributeName, attributeValue, attribute_index):
        if attributeName == 'mesh':
            mesh = CoreManager.instance().resource_manager.getMesh(attributeValue)
            if mesh and self.mesh != mesh:
                self.set_mesh(mesh)
        elif attributeName == 'material_instances':
            material_instance = CoreManager.instance().resource_manager.getMaterialInstance(
                attributeValue[attribute_index])
            self.set_material_instance(material_instance, attribute_index)
