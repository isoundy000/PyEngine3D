import codecs
import math
import copy
import os
import glob
import configparser
import time
import traceback
import datetime
import pprint
import re
import pickle
import gzip
from ctypes import *
from collections import OrderedDict
from distutils.dir_util import copy_tree
import shutil
import uuid

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from numpy import array, float32, uint8
from OpenGL.GL import *

from Common import logger, log_level
from Object import MaterialInstance, Triangle, Quad, Cube, Mesh, Model, Font
from OpenGLContext import CreateTexture, Material, Texture2D, Texture3D, TextureCube
from OpenGLContext import Shader, parsing_macros, parsing_uniforms, parsing_material_components
from Utilities import Attributes, Singleton, Config, Logger
from Utilities import GetClassName, is_gz_compressed_file, check_directory_and_mkdir, get_modify_time_of_file
from . import Collada, OBJ, loadDDS, generate_font_data


# -----------------------#
# CLASS : MetaData
# -----------------------#
class MetaData:
    def __init__(self, resource_version, resource_filepath):
        filepath, ext = os.path.splitext(resource_filepath)
        resource_filepath = filepath.replace(".", os.sep) + ext

        self.filepath = os.path.splitext(resource_filepath)[0] + ".meta"
        self.resource_version = resource_version
        self.old_resource_version = -1
        self.resource_filepath = resource_filepath
        self.resource_modify_time = get_modify_time_of_file(resource_filepath)
        self.source_filepath = ""
        self.source_modify_time = ""
        self.version_updated = False
        self.changed = False

        self.load_meta_file()

    def is_resource_file_changed(self):
        return self.resource_modify_time != get_modify_time_of_file(self.resource_filepath)

    def is_source_file_changed(self):
        return self.source_modify_time != get_modify_time_of_file(self.source_filepath)

    def set_resource_version(self, resource_version, save=True):
        self.changed |= self.resource_version != resource_version
        self.resource_version = resource_version
        if self.changed and save:
            self.save_meta_file()

    def set_resource_meta_data(self, resource_filepath, save=True):
        filepath, ext = os.path.splitext(resource_filepath)
        resource_filepath = filepath.replace(".", os.sep) + ext

        resource_modify_time = get_modify_time_of_file(resource_filepath)
        self.changed |= self.resource_filepath != resource_filepath
        self.changed |= self.resource_modify_time != resource_modify_time
        self.resource_filepath = resource_filepath
        self.resource_modify_time = resource_modify_time

        if self.changed and save:
            self.save_meta_file()

    def set_source_meta_data(self, source_filepath, save=True):
        filepath, ext = os.path.splitext(source_filepath)
        source_filepath = filepath.replace(".", os.sep) + ext

        source_modify_time = get_modify_time_of_file(source_filepath)
        self.changed |= self.source_filepath != source_filepath
        self.changed |= self.source_modify_time != source_modify_time
        self.source_filepath = source_filepath
        self.source_modify_time = source_modify_time

        if self.changed and save:
            self.save_meta_file()

    def load_meta_file(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, 'r') as f:
                load_data = eval(f.read())
                resource_version = load_data.get("resource_version", None)
                resource_filepath = load_data.get("resource_filepath", None)
                resource_modify_time = load_data.get("resource_modify_time", None)
                source_filepath = load_data.get("source_filepath", None)
                source_modify_time = load_data.get("source_modify_time", None)

                self.changed |= self.resource_version != resource_version
                self.changed |= self.resource_filepath != resource_filepath
                self.changed |= self.resource_modify_time != resource_modify_time
                self.changed |= self.source_filepath != source_filepath
                self.changed |= self.source_modify_time != source_modify_time

                if resource_version is not None:
                    self.resource_version = resource_version
                if source_filepath is not None:
                    self.source_filepath = source_filepath
                if source_modify_time is not None:
                    self.source_modify_time = source_modify_time
        else:
            # save meta file
            self.changed = True

        if self.changed:
            self.save_meta_file()

    def save_meta_file(self):
        if (self.changed or not os.path.exists(self.filepath)) and os.path.exists(self.resource_filepath):
            with open(self.filepath, 'w') as f:
                save_data = dict(
                    resource_version=self.resource_version,
                    resource_filepath=self.resource_filepath,
                    resource_modify_time=self.resource_modify_time,
                    source_filepath=self.source_filepath,
                    source_modify_time=self.source_modify_time,
                )
                pprint.pprint(save_data, f)
            self.changed = False

    def delete_meta_file(self):
        if os.path.exists(self.filepath):
            os.remove(self.filepath)


# -----------------------#
# CLASS : Resource
# -----------------------#
class Resource:
    def __init__(self, resource_name, resource_type_name):
        self.name = resource_name
        self.type_name = resource_type_name
        self.data = None
        self.meta_data = None

    def get_resource_info(self):
        return self.name, self.type_name, self.data is not None

    def is_need_to_load(self):
        return self.data is None or self.meta_data.is_resource_file_changed()

    def set_data(self, data):
        if self.data is None:
            self.data = data
        else:
            # copy of data
            if type(data) is dict:
                self.data = data
            else:
                self.data.__dict__ = data.__dict__

        # Notify that data has been loaded.
        ResourceManager.instance().core_manager.sendResourceInfo(self.get_resource_info())

    def clear_data(self):
        self.data = None

    def get_data(self):
        if self.is_need_to_load():
            ResourceManager.instance().load_resource(self.name, self.type_name)
        return self.data

    def getAttribute(self):
        if self.data and hasattr(self.data, 'getAttribute'):
            return self.data.getAttribute()
        return None

    def setAttribute(self, attributeName, attributeValue, attribute_index):
        if self.data and hasattr(self.data, 'setAttribute'):
            self.data.setAttribute(attributeName, attributeValue, attribute_index)


# -----------------------#
# CLASS : ResourceLoader
# -----------------------#
class ResourceLoader(object):
    name = "ResourceLoader"
    resource_dir_name = ''  # example : Fonts, Shaders, Meshes
    resource_version = 0
    resource_type_name = 'None'
    fileExt = '.*'
    external_dir_names = []  # example : Externals/Fonts, Externals/Meshes
    externalFileExt = {}  # example, { 'WaveFront': '.obj' }
    USE_FILE_COMPRESS_TO_SAVE = True

    def __init__(self, core_manager, root_path):
        self.core_manager = core_manager
        self.resource_manager = core_manager.resource_manager
        self.scene_manager = core_manager.scene_manager
        self.resource_path = os.path.join(root_path, self.resource_dir_name)
        check_directory_and_mkdir(self.resource_path)

        self.external_paths = [self.resource_path, ]

        for external_dir_name in self.external_dir_names:
            external_dir_name = os.path.join(root_path, external_dir_name)
            self.external_paths.append(external_dir_name)
            check_directory_and_mkdir(external_dir_name)

        self.externalFileList = []
        self.resources = {}
        self.metaDatas = {}

    @staticmethod
    def getResourceName(resource_path, filepath, make_lower=True):
        resourceName = os.path.splitext(os.path.relpath(filepath, resource_path))[0]
        resourceName = resourceName.replace(os.sep, ".")
        return resourceName if make_lower else resourceName

    def is_new_external_data(self, meta_data, source_filepath):
        if os.path.exists(source_filepath):
            # Refresh the resource from external file.
            source_modify_time = get_modify_time_of_file(source_filepath)
            return meta_data.resource_version != self.resource_version or \
                (meta_data.source_filepath == source_filepath and meta_data.source_modify_time != source_modify_time)
        else:
            return False

    def initialize(self):
        logger.info("initialize " + GetClassName(self))

        # collect resource files
        for dirname, dirnames, filenames in os.walk(self.resource_path):
            for filename in filenames:
                fileExt = os.path.splitext(filename)[1]
                if ".*" == self.fileExt or fileExt == self.fileExt:
                    filepath = os.path.join(dirname, filename)
                    resource_name = self.getResourceName(self.resource_path, filepath)
                    self.create_resource(resource_name=resource_name, resource_data=None, resource_filepath=filepath)

        # If you use external files, will convert the resources.
        if self.externalFileExt:
            # gather external source files
            for external_path in self.external_paths:
                for dirname, dirnames, filenames in os.walk(external_path):
                    for filename in filenames:
                        source_filepath = os.path.join(dirname, filename)
                        self.add_convert_source_file(source_filepath)

                # convert external file to rsource file.
                for source_filepath in self.externalFileList:
                    resource_name = self.getResourceName(external_path, source_filepath)
                    resource = self.getResource(resource_name, noWarn=True)
                    meta_data = self.getMetaData(resource_name, noWarn=True)
                    # Create the new resource from exterial file.
                    if resource is None:
                        logger.info("Create the new resource from %s." % source_filepath)
                        resource = self.create_resource(resource_name)
                        self.convert_resource(resource, source_filepath)
                    elif meta_data and self.is_new_external_data(meta_data, source_filepath):
                        self.convert_resource(resource, source_filepath)
                        logger.info("Refresh the new resource from %s." % source_filepath)
            # clear list
            self.externalFileList = []

        # clear gabage meta file
        for dirname, dirnames, filenames in os.walk(self.resource_path):
            for filename in filenames:
                file_ext = os.path.splitext(filename)[1]
                if file_ext == '.meta':
                    filepath = os.path.join(dirname, filename)
                    resource_name = self.getResourceName(self.resource_path, filepath)
                    resource = self.getResource(resource_name, noWarn=True)
                    meta_data = self.getMetaData(resource_name, noWarn=True)
                    if resource is None:
                        if meta_data:
                            meta_data.delete_meta_file()
                            self.metaDatas.pop(resource_name)
                        else:
                            logger.info("Delete the %s." % filepath)
                            os.remove(filepath)

    def add_convert_source_file(self, source_filepath):
        file_ext = os.path.splitext(source_filepath)[1]
        if file_ext in self.externalFileExt.values() and source_filepath not in self.externalFileList:
            self.externalFileList.append(source_filepath)

    def get_new_resource_name(self, prefix=""):
        if prefix not in self.resources:
            return prefix

        num = 0
        while True:
            new_name = "%s_%d" % (prefix or self.resource_type_name, num)
            if new_name not in self.resources:
                return new_name
            num += 1
        return ''

    def convert_resource(self, resource, source_filepath):
        logger.warn("convert_resource is not implemented in %s." % self.name)

    def getResource(self, resourceName, noWarn=False):
        if resourceName in self.resources:
            return self.resources[resourceName]
        if not noWarn and resourceName:
            logger.error("%s cannot found %s resource." % (self.name, resourceName))
        return None

    def getResourceData(self, resourceName, noWarn=False):
        resource = self.getResource(resourceName, noWarn)
        return resource.get_data() if resource else None

    def getResourceList(self):
        return list(self.resources.values())

    def getResourceNameList(self):
        return list(self.resources.keys())

    def getResourceAttribute(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            return resource.getAttribute()
        return None

    def setResourceAttribute(self, resource_name, attribute_name, attribute_value, attribute_index):
        # rename resource
        if attribute_name == 'name':
            self.rename_resource(resource_name, attribute_value)
        else:
            # set other attributes
            resource = self.getResource(resource_name)
            if resource:
                resource.setAttribute(attribute_name, attribute_value, attribute_index)

    def getMetaData(self, resource_name, noWarn=False):
        if resource_name in self.metaDatas:
            return self.metaDatas[resource_name]
        if not noWarn:
            logger.error("Not found meta data of %s." % resource_name)
        return None

    def create_resource(self, resource_name, resource_data=None, resource_filepath=None):
        if resource_name in self.resources:
            # logger.warn('Resource name is duplicated. %s' % resource_name)
            resource_name = self.get_new_resource_name(resource_name)
        resource = Resource(resource_name, self.resource_type_name)
        if resource_data:
            resource.set_data(resource_data)
        if resource_filepath is None:
            resource_filepath = os.path.join(self.resource_path, resource_name) + self.fileExt
        meta_data = MetaData(self.resource_version, resource_filepath)
        self.regist_resource(resource, meta_data)
        return resource

    def regist_resource(self, resource, meta_data=None):
        logger.info("Regist %s : %s" % (self.resource_type_name, resource.name))
        self.resources[resource.name] = resource
        if meta_data is not None:
            self.metaDatas[resource.name] = meta_data
            resource.meta_data = meta_data
        # The new resource registered.
        if resource:
            self.core_manager.sendResourceInfo(resource.get_resource_info())

    def unregist_resource(self, resource):
        if resource:
            if resource.name in self.metaDatas:
                self.metaDatas.pop(resource.name)
            if resource.name in self.resources:
                self.resources.pop(resource.name)
            self.core_manager.notifyDeleteResource(resource.get_resource_info())

    def rename_resource(self, resource_name, new_name):
        if new_name and resource_name != new_name:
            resource_data = self.getResourceData(resource_name)
            resource = self.create_resource(new_name, resource_data)
            if resource:
                if resource_data and hasattr(resource_data, 'name'):
                    resource_data.name = resource.name
                self.save_resource(resource.name)
                if resource.name != resource_name:
                    self.delete_resource(resource_name)
                logger.info("rename_resource : %s to %s" % (resource_name, new_name))

    def load_resource(self, resource_name):
        logger.warn("load_resource is not implemented in %s." % self.name)

    def open_resource(self, resource_name):
        logger.warn("open_resource is not implemented in %s." % self.name)

    def duplicate_resource(self, resource_name):
        logger.warn("duplicate_resource is not implemented in %s." % self.name)
        # meta_data = self.getMetaData(resource_name)
        # new_resource = self.create_resource(resource_name)
        # new_meta_data = self.getMetaData(new_resource.name)
        #
        # if os.path.exists(meta_data.source_filepath) and not os.path.exists(new_meta_data.source_filepath):
        #     shutil.copy(meta_data.source_filepath, new_meta_data.source_filepath)
        #     self.load_resource(new_resource.name)
        #     logger.info("duplicate_resource : %s to %s" % (resource_name, new_resource_name))

    def save_resource(self, resource_name):
        resource = self.getResource(resource_name)
        resource_data = self.getResourceData(resource_name)
        if resource and resource_data:
            if hasattr(resource_data, 'get_save_data'):
                save_data = resource_data.get_save_data()
                self.save_resource_data(resource, save_data)
                return True
        logger.warn("save_resource is not implemented in %s." % self.name)
        return False

    def load_resource_data(self, resource):
        filePath = ''
        if resource:
            filePath = resource.meta_data.resource_filepath
            try:
                if os.path.exists(filePath):
                    # Load data (deserialize)
                    if is_gz_compressed_file(filePath):
                        with gzip.open(filePath, 'rb') as f:
                            load_data = pickle.load(f)
                    else:
                        # human readable data
                        with open(filePath, 'r') as f:
                            load_data = eval(f.read())
                    return load_data
            except:
                logger.error(traceback.format_exc())
        logger.error("file open error : %s" % filePath)
        return None

    def save_resource_data(self, resource, save_data, source_filepath=""):
        # save_filepath = os.path.join(self.resource_path, resource.name) + self.fileExt
        save_filepath = resource.name.replace('.', os.sep)
        save_filepath = os.path.join(self.resource_path, save_filepath) + self.fileExt
        save_dir = os.path.dirname(save_filepath)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        if self.save_data_to_file(save_filepath, save_data):
            # refresh meta data because resource file saved.
            resource.meta_data.set_resource_meta_data(save_filepath, save=False)
            resource.meta_data.set_source_meta_data(source_filepath, save=False)
            resource.meta_data.set_resource_version(self.resource_version, save=False)
            resource.meta_data.save_meta_file()

    def save_data_to_file(self, save_filepath, save_data):
        logger.info("Save : %s" % save_filepath)
        try:
            # store data, serialize
            if self.USE_FILE_COMPRESS_TO_SAVE:
                with gzip.open(save_filepath, 'wb') as f:
                    pickle.dump(save_data, f, protocol=pickle.HIGHEST_PROTOCOL)
            else:
                # human readable data
                with open(save_filepath, 'w') as f:
                    pprint.pprint(save_data, f, width=128)
            return True
        except:
            logger.error(traceback.format_exc())
        return False

    def delete_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            logger.info("Deleted the %s." % resource.name)
            if resource.name in self.metaDatas:
                resource_filepath = self.metaDatas[resource.name].resource_filepath
            else:
                resource_filepath = ""
            if os.path.exists(resource_filepath):
                os.remove(resource_filepath)
            self.unregist_resource(resource)


# ---------------------------#
# CLASS : ShaderLoader
# ---------------------------#
class ShaderLoader(ResourceLoader):
    name = "ShaderLoader"
    resource_dir_name = 'Shaders'
    resource_type_name = 'Shader'
    resource_version = 0.6
    fileExt = '.glsl'
    shader_version = "#version 430 core"

    def get_shader_version(self):
        return self.shader_version

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            if resource.is_need_to_load():
                file_path = resource.meta_data.resource_filepath
                if os.path.exists(file_path):
                    shader_code = ""
                    try:
                        f = codecs.open(file_path, mode='r', encoding='utf-8')
                        shader_code = f.read()
                        f.close()

                        shader = Shader(resource.name, shader_code)
                        resource.set_data(shader)
                        resource.meta_data.set_resource_meta_data(resource.meta_data.resource_filepath)
                        self.resource_manager.materialLoader.reload_materials(resource.meta_data.resource_filepath)
                        return True
                    except:
                        logger.error(traceback.format_exc())
                        logger.error("Failed %s file open" % file_path)
            else:
                # do not need to load
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def open_resource(self, resource_name):
        shader = self.getResourceData(resource_name)
        if shader:
            self.resource_manager.material_instanceLoader.create_material_instance(resource_name=resource_name,
                                                                                   shader_name=resource_name,
                                                                                   macros={})

    def save_data_to_file(self, save_filepath, save_data):
        logger.info("Save : %s" % save_filepath)
        try:
            # human readable data
            with open(save_filepath, 'w') as f:
                f.write(save_data)
            return True
        except:
            logger.error(traceback.format_exc())
        return False


# -----------------------#
# CLASS : MaterialLoader
# -----------------------#
class MaterialLoader(ResourceLoader):
    name = "MaterialLoader"
    resource_dir_name = 'Materials'
    resource_type_name = 'Material'
    fileExt = '.mat'
    resource_version = 0.6
    USE_FILE_COMPRESS_TO_SAVE = False

    def __init__(self, core_manager, root_path):
        ResourceLoader.__init__(self, core_manager, root_path)
        self.linked_material_map = {}

    def open_resource(self, resource_name):
        material = self.getResourceData(resource_name)
        if material:
            self.resource_manager.material_instanceLoader.create_material_instance(resource_name=material.shader_name,
                                                                                   shader_name=material.shader_name,
                                                                                   macros=material.macros)

    def reload_materials(self, shader_filepath):
        reload_shader_names = []
        resource_names = list(self.resources.keys())
        for resourceName in resource_names:
            reload = False
            meta_data = self.resources[resourceName].meta_data
            if meta_data:
                if shader_filepath == meta_data.source_filepath:
                    reload = True
                elif meta_data and hasattr(meta_data, 'include_files'):
                    for include_file in meta_data.include_files:
                        if shader_filepath == include_file:
                            reload = True
                            break
            if reload:
                self.load_resource(resourceName)
                material = self.getResourceData(resourceName)
                if material and material.shader_name not in reload_shader_names:
                    reload_shader_names.append(material.shader_name)

        for shader_name in reload_shader_names:
            self.resource_manager.material_instanceLoader.reload_material_instances(shader_name)

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            material_datas = self.load_resource_data(resource)
            if material_datas:
                meta_data = resource.meta_data
                generate_new_material = False
                if self.is_new_external_data(meta_data, meta_data.source_filepath):
                    generate_new_material = True

                # set include files meta datas
                meta_data.include_files = material_datas.get('include_files', {})
                for include_file in meta_data.include_files:
                    if get_modify_time_of_file(include_file) != meta_data.include_files[include_file]:
                        generate_new_material = True
                        break

                if generate_new_material:
                    shader_name = material_datas.get('shader_name')
                    macros = material_datas.get('macros', {})
                    self.generate_new_material(resource.name, shader_name, macros)
                else:
                    material = Material(resource.name, material_datas)
                    resource.set_data(material)
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def generate_material_name(self, shader_name, macros=None):
        if macros:
            keys = sorted(macros.keys())
            add_name = [key + "_" + str(macros[key]) for key in keys]
            shader_name = shader_name + "_" + str(uuid.uuid3(uuid.NAMESPACE_DNS, "_".join(add_name))).replace("-", "_")
        return shader_name

    def generate_new_material(self, material_name, shader_name, macros={}):
        logger.info("Generate new material : %s" % material_name)
        shader = self.resource_manager.getShader(shader_name)
        shader_version = self.resource_manager.get_shader_version()
        if shader:
            shader_codes = shader.generate_shader_codes(shader_version, macros)
            if shader_codes is not None:
                shader_code_list = shader_codes.values()
                final_macros = parsing_macros(shader_code_list)
                uniforms = parsing_uniforms(shader_code_list)
                material_components = parsing_material_components(shader_code_list)

                final_material_name = self.generate_material_name(shader_name, final_macros)

                # Check the material_name with final_material_name.
                if material_name != final_material_name:
                    logger.warn("Generated material name is changed. : %s" % final_material_name)
                    self.linked_material_map[material_name] = final_material_name
                    self.delete_resource(material_name)

                include_files = {}
                for include_file in shader.include_files:
                    include_files[include_file] = get_modify_time_of_file(include_file)

                material_datas = dict(
                    shader_name=shader_name,
                    shader_codes=shader_codes,
                    include_files=include_files,
                    uniforms=uniforms,
                    material_components=material_components,
                    binary_data=None,
                    binary_format=None,
                    macros=final_macros
                )
                # create material
                material = Material(final_material_name, material_datas)

                if material and material.valid:
                    resource = self.getResource(final_material_name, noWarn=True)
                    if resource is None:
                        resource = self.create_resource(final_material_name)

                    # set include files meta datas
                    resource.meta_data.include_files = material_datas.get('include_files', {})

                    # write material to file, and regist to resource manager
                    shader_meta_data = self.resource_manager.shader_loader.getMetaData(shader_name)
                    if shader_meta_data:
                        source_filepath = shader_meta_data.resource_filepath
                    else:
                        source_filepath = ""

                    # save binary data of shader.
                    binary_format, binary_data = material.save_to_binary()
                    if binary_format is not None and binary_data is not None:
                        material_datas['binary_format'] = binary_format
                        material_datas['binary_data'] = binary_data

                    # Done : save material data
                    self.save_resource_data(resource, material_datas, source_filepath)
                    resource.set_data(material)
                    return material
        logger.error("Failed to generate_new_material %s." % material_name)
        return None

    def getMaterial(self, shader_name, macros={}):
        if shader_name == '':
            logger.error("Error : Cannot create material. Because material name is empty.")
            return None

        material_name = self.generate_material_name(shader_name, macros)
        # Due to options such as macros, actual material names may differ. That's why we use link maps.
        if material_name in self.linked_material_map:
            material_name = self.linked_material_map[material_name]

        material = self.getResourceData(material_name)
        if material is None:
            material = self.generate_new_material(material_name, shader_name, macros)
        return material


# -----------------------#
# CLASS : MaterialInstanceLoader
# -----------------------#
class MaterialInstanceLoader(ResourceLoader):
    name = "MaterialInstanceLoader"
    resource_dir_name = 'MaterialInstances'
    resource_type_name = 'MaterialInstance'
    fileExt = '.matinst'
    USE_FILE_COMPRESS_TO_SAVE = False

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            material_instance_data = self.load_resource_data(resource)
            if material_instance_data:
                shader_name = material_instance_data.get('shader_name', 'default')
                macros = material_instance_data.get('macros', {})
                material = self.resource_manager.getMaterial(shader_name, macros)
                material_instance_data['material'] = material

                material_instance = MaterialInstance(resource.name, **material_instance_data)
                if material_instance.valid:
                    resource.set_data(material_instance)
                    if material_instance.isNeedToSave:
                        self.save_resource(resource_name)
                        material_instance.isNeedToSave = False
                return material_instance.valid
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def reload_material_instances(self, shader_name):
        for resource_name in self.resources:
            resource = self.resources[resource_name]
            if resource and resource.data:
                material_instance = resource.data
                if material_instance.shader_name == shader_name:
                    old_program = material_instance.material.program
                    self.load_resource(resource_name)

        for resource_name in self.resources:
            resource = self.resources[resource_name]
            if resource and resource.data:
                material_instance = resource.data

    def create_material_instance(self, resource_name, shader_name, macros={}):
        if shader_name == '':
            shader_name = resource_name

        if shader_name:
            resource_name = self.get_new_resource_name(resource_name)
            material = self.resource_manager.getMaterial(shader_name, macros)
            material_instance = MaterialInstance(resource_name, material=material, shader_name=shader_name,
                                                 macros=macros)
            if material_instance.valid:
                resource = self.create_resource(resource_name)
                resource.set_data(material_instance)
                self.save_resource(resource_name)
                return True
        logger.error('Failed to %s material instance.' % resource_name)
        return False

    def getMaterialInstance(self, name, shader_name='', macros={}):
        material_instance = self.getResourceData(name)
        if material_instance is None:
            if self.create_material_instance(resource_name=name,
                                             shader_name=shader_name,
                                             macros=macros):
                material_instance = self.getResourceData(name)
            else:
                material_instance = self.getResourceData('default')
        elif macros:
            material = self.resource_manager.getMaterial(material_instance.shader_name, macros)
            material_instance.set_material(material)
            return material_instance
        return material_instance


# -----------------------#
# CLASS : TextureLoader
# -----------------------#
class TextureLoader(ResourceLoader):
    name = "TextureLoader"
    resource_dir_name = 'Textures'
    resource_type_name = 'Texture'
    resource_version = 2
    USE_FILE_COMPRESS_TO_SAVE = True
    external_dir_names = [os.path.join('Externals', 'Textures'), ]
    fileExt = '.texture'
    externalFileExt = dict(GIF=".gif", JPG=".jpg", JPEG=".jpeg", PNG=".png", BMP=".bmp", TGA=".tga", TIF=".tif",
                           TIFF=".tiff", DXT=".dds", KTX=".ktx")

    def __init__(self, core_manager, root_path):
        ResourceLoader.__init__(self, core_manager, root_path)
        self.new_texture_list = []

    def initialize(self):
        ResourceLoader.initialize(self)
        self.generate_cube_textures()

        # gradient 3d texture
        size = 64
        value = 255.0 / float(size)
        data = array([0, 0, 0, 255] * size * size * size, dtype=uint8)
        for z in range(size):
            for y in range(size):
                for x in range(size):
                    index = (x + y * size + z * size * size) * 4
                    data[index] = x * value
                    data[index+1] = y * value
                    data[index+2] = z * value

        default_3d = CreateTexture(
            name='default_3d',
            texture_type=Texture3D,
            image_mode='RGBA',
            width=size,
            height=size,
            depth=size,
            internal_format=GL_RGBA8,
            texture_format=GL_RGBA,
            min_filter=GL_NEAREST,
            mag_filter=GL_NEAREST,
            data_type=GL_UNSIGNED_BYTE,
            wrap=GL_CLAMP_TO_EDGE,
            data=data,
        )
        self.create_resource("default_3d", default_3d)

    def open_resource(self, resource_name):
        texture = self.getResourceData(resource_name)
        if texture:
            self.core_manager.renderer.set_debug_texture(texture)

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            meta_data = resource.meta_data
            if self.is_new_external_data(meta_data, meta_data.source_filepath):
                self.convert_resource(resource, meta_data.source_filepath)

            texture_datas = self.load_resource_data(resource)
            if texture_datas:
                if texture_datas.get('texture_type') == TextureCube:
                    empty_texture = self.getResourceData('empty')
                    texture_datas['texture_positive_x'] = self.getResourceData(
                        texture_datas['texture_positive_x']) or empty_texture
                    texture_datas['texture_negative_x'] = self.getResourceData(
                        texture_datas['texture_negative_x']) or empty_texture
                    texture_datas['texture_positive_y'] = self.getResourceData(
                        texture_datas['texture_positive_y']) or empty_texture
                    texture_datas['texture_negative_y'] = self.getResourceData(
                        texture_datas['texture_negative_y']) or empty_texture
                    texture_datas['texture_positive_z'] = self.getResourceData(
                        texture_datas['texture_positive_z']) or empty_texture
                    texture_datas['texture_negative_z'] = self.getResourceData(
                        texture_datas['texture_negative_z']) or empty_texture

                texture = CreateTexture(name=resource.name, **texture_datas)
                resource.set_data(texture)
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def generate_cube_textures(self):
        cube_faces = ('right', 'left', 'top', 'bottom', 'back', 'front')
        cube_texutre_map = dict()  # { cube_name : { face : source_filepath } }

        # gather cube texture names
        for resource_name in self.resources:
            if '_' in resource_name:
                index = resource_name.rfind('_')
                texture_name = resource_name[:index]
                texutre_face = resource_name[index + 1:]
                if texutre_face in cube_faces:
                    if texture_name not in cube_texutre_map:
                        cube_texutre_map[texture_name] = dict()
                    cube_texutre_map[texture_name][texutre_face] = self.resources[resource_name]

        for cube_texture_name in cube_texutre_map:
            cube_faces = cube_texutre_map[cube_texture_name]
            if len(cube_faces) == 6:
                isCreateCube = any([cube_face in self.new_texture_list for cube_face in cube_faces])
                cube_resource = self.getResource(cube_texture_name, noWarn=True)
                if cube_resource is None:
                    cube_resource = self.create_resource(cube_texture_name)
                    isCreateCube = True

                if isCreateCube:
                    empty_texture = self.getResourceData('empty')
                    texture_right = cube_faces['right'].get_data() or empty_texture
                    texture_left = cube_faces['left'].get_data() or empty_texture
                    texture_top = cube_faces['top'].get_data() or empty_texture
                    texture_bottom = cube_faces['bottom'].get_data() or empty_texture
                    texture_back = cube_faces['back'].get_data() or empty_texture
                    texture_front = cube_faces['front'].get_data() or empty_texture

                    cube_texture_datas = copy.copy(texture_front.__dict__)
                    cube_texture_datas['name'] = cube_texture_name
                    cube_texture_datas['texture_type'] = TextureCube
                    cube_texture_datas['texture_positive_x'] = texture_right
                    cube_texture_datas['texture_negative_x'] = texture_left
                    cube_texture_datas['texture_positive_y'] = texture_top
                    cube_texture_datas['texture_negative_y'] = texture_bottom
                    cube_texture_datas['texture_positive_z'] = texture_front
                    cube_texture_datas['texture_negative_z'] = texture_back

                    cube_texture = CreateTexture(**cube_texture_datas)
                    cube_resource.set_data(cube_texture)
                    cube_texture_datas = cube_texture.get_save_data()
                    self.save_resource_data(cube_resource, cube_texture_datas, '')
        self.new_texture_list = []

    @staticmethod
    def create_texture_from_file(texture_name, source_filepath):
        if os.path.exists(source_filepath):
            image = Image.open(source_filepath)
            width, height = image.size

            # check size is power of two.
            use_power_of_2 = False
            if use_power_of_2:
                width2 = (2 ** math.ceil(math.log2(width))) if 4 < width else 4
                height2 = (2 ** math.ceil(math.log2(height))) if 4 < width else 4
                if width != width2 or height != height2:
                    logger.info('Image Resized (%s) -> (%s) : %s' % ((width, height), (width2, height2), source_filepath))
                    image = image.resize((width2, height2), Image.ANTIALIAS)
                    width, height = width2, height2

            if image.mode == 'L' or image.mode == 'LA':
                rgbimg = Image.new("RGBA", image.size)
                rgbimg.paste(image)
                image = rgbimg
                logger.info('Convert Grayscale image to RGB : %s' % source_filepath)

            data = image.tobytes("raw", image.mode, 0, -1)

            texture_datas = dict(
                texture_type=Texture2D,
                image_mode=image.mode,
                width=width,
                height=height,
                data=data
            )
            return CreateTexture(name=texture_name, **texture_datas)
        return None

    def convert_resource(self, resource, source_filepath):
        try:
            logger.info("Convert Resource : %s" % source_filepath)
            if resource not in self.new_texture_list:
                self.new_texture_list.append(resource)

            texture = self.create_texture_from_file(resource.name, source_filepath)
            if texture:
                resource.set_data(texture)
                texture_datas = texture.get_save_data()
                self.save_resource_data(resource, texture_datas, source_filepath)
        except:
            logger.error(traceback.format_exc())
        logger.info("Failed to convert resource : %s" % source_filepath)


# -----------------------#
# CLASS : MeshLoader
# -----------------------#
class MeshLoader(ResourceLoader):
    name = "MeshLoader"
    resource_version = 0
    resource_dir_name = 'Meshes'
    resource_type_name = 'Mesh'
    fileExt = '.mesh'
    externalFileExt = dict(WaveFront='.obj', Collada='.dae')
    external_dir_names = [os.path.join('Externals', 'Meshes'), ]
    USE_FILE_COMPRESS_TO_SAVE = True

    def initialize(self):
        # load and regist resource
        super(MeshLoader, self).initialize()

        # Regist basic meshs
        self.create_resource("Triangle", Triangle())
        self.create_resource("Quad", Quad())
        self.create_resource("Cube", Cube())

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            mesh_data = self.load_resource_data(resource)
            if mesh_data:
                mesh = Mesh(resource.name, **mesh_data)
                resource.set_data(mesh)
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def convert_resource(self, resoure, source_filepath):
        logger.info("Convert Resource : %s" % source_filepath)
        file_ext = os.path.splitext(source_filepath)[1]
        if file_ext == self.externalFileExt.get('WaveFront'):
            mesh = OBJ(source_filepath, 1, True)
            mesh_data = mesh.get_mesh_data()
        elif file_ext == self.externalFileExt.get('Collada'):
            mesh = Collada(source_filepath)
            mesh_data = mesh.get_mesh_data()
        else:
            return

        if mesh_data:
            # create mesh
            mesh = Mesh(resoure.name, **mesh_data)
            resoure.set_data(mesh)
            self.save_resource_data(resoure, mesh_data, source_filepath)

    def open_resource(self, resource_name):
        mesh = self.getResourceData(resource_name)
        if mesh:
            self.resource_manager.modelLoader.create_model(mesh)


# -----------------------#
# CLASS : ModelLoader
# -----------------------#
class ModelLoader(ResourceLoader):
    name = "ModelLoader"
    resource_dir_name = 'Models'
    resource_type_name = 'Model'
    fileExt = '.model'
    externalFileExt = dict(Mesh='.mesh')
    USE_FILE_COMPRESS_TO_SAVE = False

    def initialize(self):
        # load and regist resource
        super(ModelLoader, self).initialize()

        # Regist basic meshs
        self.create_resource("Triangle", Model("Triangle", mesh=self.resource_manager.getMesh('Triangle')))
        self.create_resource("Quad", Model("Quad", mesh=self.resource_manager.getMesh('Quad')))

    def create_model(self, mesh):
        resource = self.create_resource(mesh.name)
        model = Model(resource.name, mesh=mesh)
        resource.set_data(model)
        self.save_resource(resource.name)

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            object_data = self.load_resource_data(resource)
            if object_data:
                mesh = self.resource_manager.getMesh(object_data.get('mesh'))
                material_instances = [self.resource_manager.getMaterialInstance(material_instance_name)
                                      for material_instance_name in object_data.get('material_instances', [])]
                obj = Model(resource.name, mesh=mesh, material_instances=material_instances)
                resource.set_data(obj)
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def open_resource(self, resource_name):
        model = self.getResourceData(resource_name)
        if model:
            self.scene_manager.addObjectHere(model)


# -----------------------#
# CLASS : SceneLoader
# -----------------------#
class SceneLoader(ResourceLoader):
    name = "SceneLoader"
    resource_dir_name = 'Scenes'
    resource_type_name = 'Scene'
    fileExt = '.scene'
    USE_FILE_COMPRESS_TO_SAVE = False

    def save_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource and resource_name == self.scene_manager.get_current_scene_name():
            scene_data = self.scene_manager.get_save_data()
            self.save_resource_data(resource, scene_data)

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            meta_data = self.getMetaData(resource_name)
            if resource and meta_data:
                if os.path.exists(meta_data.resource_filepath):
                    scene_datas = self.load_resource_data(resource)
                else:
                    scene_datas = resource.get_data()

                if scene_datas:
                    for object_data in scene_datas.get('static_actors', []):
                        object_data['model'] = self.resource_manager.getModel(object_data.get('model'))

                    for object_data in scene_datas.get('skeleton_actors', []):
                        object_data['model'] = self.resource_manager.getModel(object_data.get('model'))

                    self.scene_manager.open_scene(resource_name, scene_datas)
                    resource.set_data(scene_datas)
                    return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False

    def open_resource(self, resource_name):
        self.load_resource(resource_name)


# -----------------------#
# CLASS : FontLoader
# -----------------------#
class FontLoader(ResourceLoader):
    """
    http://jrgraphix.net/research/unicode.php
    """
    name = "FontLoader"
    resource_dir_name = 'Fonts'
    resource_type_name = 'Font'
    fileExt = '.font'
    external_dir_names = [os.path.join('Externals', 'Fonts'), ]
    externalFileExt = dict(TTF='.ttf', OTF='.otf')

    language_infos = dict(
        ascii=('Basic Latin', 0x20, 0x7F),  # 32 ~ 127
        korean=('Hangul Syllables', 0xAC00, 0xD7AF),  # 44032 ~ 55215
    )

    def check_font_data(self, font_datas, resoure, source_filepath):
        for language in self.language_infos:
            if language not in font_datas:
                unicode_name, range_min, range_max = self.language_infos[language]
                font_data = generate_font_data(
                    resource_name=resoure.name,
                    distance_field_font=False,
                    anti_aliasing=True,
                    font_size=20,
                    padding=1,
                    unicode_name=unicode_name,
                    range_min=range_min,
                    range_max=range_max,
                    source_filepath=source_filepath,
                    preview_path=self.resource_path
                )
                font_datas[language] = font_data

        if font_datas:
            self.save_resource_data(resoure, font_datas, source_filepath)
        return font_datas

    def convert_resource(self, resoure, source_filepath):
        logger.info("Convert Resource : %s" % source_filepath)
        font_datas = {}
        self.check_font_data(font_datas, resoure, source_filepath)

    def load_resource(self, resource_name):
        resource = self.getResource(resource_name)
        if resource:
            meta_data = resource.meta_data
            font_datas = self.load_resource_data(resource)
            if font_datas:
                font_datas = self.check_font_data(font_datas, resource, meta_data.source_filepath)

                for language in font_datas:
                    font_data = font_datas[language]
                    texture = None
                    if font_data:
                        texture_datas = dict(
                            texture_type=Texture2D,
                            image_mode=font_data.get('image_mode'),
                            width=font_data.get('image_width'),
                            height=font_data.get('image_height'),
                            data=font_data.get('image_data'),
                            min_filter=GL_LINEAR,
                            mag_filter=GL_LINEAR,
                        )
                        texture_name = "_".join([resource_name, font_data.get('unicode_name')])
                        if None not in list(texture_datas.values()):
                            texture = CreateTexture(name=texture_name, **texture_datas)
                    font_datas[language]['texture'] = texture
                resource.set_data(font_datas)
                return True
        logger.error('%s failed to load %s' % (self.name, resource_name))
        return False


# -----------------------#
# CLASS : ScriptLoader
# -----------------------#
class ScriptLoader(ResourceLoader):
    name = "ScriptLoader"
    resource_dir_name = 'Scripts'
    fileExt = '.py'


# -----------------------#
# CLASS : ResourceManager
# -----------------------#
class ResourceManager(Singleton):
    name = "ResourceManager"
    PathResources = 'Resource'
    DefaultProjectFile = os.path.join(PathResources, "default.project")

    def __init__(self):
        self.root_path = ""
        self.resource_loaders = []
        self.core_manager = None
        self.scene_manager = None
        self.fontLoader = None
        self.textureLoader = None
        self.shader_loader = None
        self.materialLoader = None
        self.material_instanceLoader = None
        self.meshLoader = None
        self.sceneLoader = None
        self.scriptLoader = None
        self.modelLoader = None

    def regist_loader(self, resource_loader_class):
        resource_loader = resource_loader_class(self.core_manager, self.root_path)
        self.resource_loaders.append(resource_loader)
        return resource_loader

    def initialize(self, core_manager, root_path=""):
        self.core_manager = core_manager
        self.scene_manager = core_manager.scene_manager

        self.root_path = root_path or self.PathResources
        check_directory_and_mkdir(self.root_path)

        # Be careful with the initialization order.
        self.fontLoader = self.regist_loader(FontLoader)
        self.textureLoader = self.regist_loader(TextureLoader)
        self.shader_loader = self.regist_loader(ShaderLoader)
        self.materialLoader = self.regist_loader(MaterialLoader)
        self.material_instanceLoader = self.regist_loader(MaterialInstanceLoader)
        self.meshLoader = self.regist_loader(MeshLoader)
        self.sceneLoader = self.regist_loader(SceneLoader)
        self.scriptLoader = self.regist_loader(ScriptLoader)
        self.modelLoader = self.regist_loader(ModelLoader)

        # initialize
        for resource_loader in self.resource_loaders:
            resource_loader.initialize()

        logger.info("Resource register done.")

    def close(self):
        pass

    def prepare_project_directory(self, new_project_dir):
        check_directory_and_mkdir(new_project_dir)
        copy_tree(self.PathResources, new_project_dir)

    def getResourceNameAndTypeList(self):
        """
        :return [(resource name, resource type)]:
        """
        result = []
        for resource_loader in self.resource_loaders:
            result += [(resName, resource_loader.resource_type_name) for resName in
                       resource_loader.getResourceNameList()]
        return

    def setResourceAttribute(self, resource_name, resource_type_name, attribute_name, attribute_value, attribute_index):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            return resource_loader.setResourceAttribute(resource_name, attribute_name, attribute_value, attribute_index)
        return None

    def getResourceAttribute(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            return resource_loader.getResourceAttribute(resource_name)
        return None

    def getResourceData(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            return resource_loader.getResourceData(resource_name)
        return None

    def getMetaData(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            return resource_loader.getMetaData(resource_name)
        return None

    def load_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.load_resource(resource_name)

    def open_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.open_resource(resource_name)

    def duplicate_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.duplicate_resource(resource_name)

    def save_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.save_resource(resource_name)

    def rename_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.rename_resource(resource_name)

    def delete_resource(self, resource_name, resource_type_name):
        resource_loader = self.find_resource_loader(resource_type_name)
        if resource_loader:
            resource_loader.delete_resource(resource_name)

    def find_resource_loader(self, resource_type_name):
        for resource_loader in self.resource_loaders:
            if resource_loader.resource_type_name == resource_type_name:
                return resource_loader
        logger.error("%s is a unknown resource type." % resource_type_name)
        return None

    # FUNCTIONS : Font

    def getFont(self, fontName):
        return self.fontLoader.getResourceData(fontName)

    def getFontNameList(self):
        return self.fontLoader.getResourceNameList()

    def get_default_font_file(self):
        return os.path.join(self.root_path, 'Externals', 'Fonts', 'NanumGothic_Coding.ttf')

    # FUNCTIONS : Shader
    def get_shader_version(self):
        return self.shader_loader.get_shader_version()

    def getShader(self, shaderName):
        return self.shader_loader.getResourceData(shaderName)

    def getShaderNameList(self):
        return self.shader_loader.getResourceNameList()

    # FUNCTIONS : Material

    def getMaterialNameList(self):
        return self.materialLoader.getResourceNameList()

    def getMaterial(self, shader_name, macros={}):
        return self.materialLoader.getMaterial(shader_name, macros)

    # FUNCTIONS : MaterialInstance

    def getMaterialInstanceNameList(self):
        return self.material_instanceLoader.getResourceNameList()

    def getMaterialInstance(self, name, shader_name='', macros={}):
        return self.material_instanceLoader.getMaterialInstance(name, shader_name=shader_name, macros=macros)

    def getDefaultMaterialInstance(self, skeletal=False):
        if skeletal:
            return self.material_instanceLoader.getMaterialInstance(name='default_skeletal',
                                                                    shader_name='default',
                                                                    macros={'SKELETAL': 1})
        return self.material_instanceLoader.getMaterialInstance('default')

    # FUNCTIONS : Mesh

    def getMeshNameList(self):
        return self.meshLoader.getResourceNameList()

    def getMesh(self, meshName):
        return self.meshLoader.getResourceData(meshName)

    # FUNCTIONS : Texture

    def getTextureNameList(self):
        return self.textureLoader.getResourceNameList()

    def getTexture(self, textureName):
        return self.textureLoader.getResourceData(textureName)

    # FUNCTIONS

    def getModelNameList(self):
        return self.modelLoader.getResourceNameList()

    def getModel(self, modelName):
        return self.modelLoader.getResourceData(modelName)

    # FUNCTIONS : Scene

    def getSceneNameList(self):
        return self.sceneLoader.getResourceNameList()

    def getScene(self, SceneName):
        return self.sceneLoader.getResourceData(SceneName)
