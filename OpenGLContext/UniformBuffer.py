import traceback

import numpy as np
from OpenGL.GL import *

from Common import logger
from App import CoreManager


def CreateUniformBuffer(program, uniform_type, uniform_name):
    """ create uniform buffer from .mat(shader) file """
    uniform_classes = [UniformInt, UniformFloat, UniformVector2, UniformVector3, UniformVector4, UniformMatrix2,
                       UniformMatrix3, UniformMatrix4, UniformTexture2D]
    for uniform_class in uniform_classes:
        if uniform_class.uniform_type == uniform_type:
            uniform_buffer = uniform_class(program, uniform_name)
            return uniform_buffer if uniform_buffer.valid else None
    else:
        logger.error('Cannot matched to %s type of %s.' % (uniform_type, uniform_name))
    return None


def CreateUniformDataFromString(data_type, strValue=None):
    """ return converted data from string or default data """
    try:
        if data_type == 'float':
            # return float(strValue) if strValue else 0.0
            return np.float32(strValue) if strValue else np.float32(0)
        elif data_type == 'int':
            # return int(strValue) if strValue else 0
            return np.int32(strValue) if strValue else np.int32(0)
        elif data_type in ('vec2', 'vec3', 'vec4'):
            componentCount = int(data_type[-1])
            if strValue is not None:
                vecValue = eval(strValue) if type(strValue) is str else strValue
                if len(vecValue) == componentCount:
                    return np.array(vecValue, dtype=np.float32)
                else:
                    logger.error(ValueError("%s need %d float members." % (data_type, componentCount)))
                    raise ValueError
            else:
                return np.array([1.0, ] * componentCount, dtype=np.float32)
        elif data_type in ('mat2', 'mat3', 'mat4'):
            componentCount = int(data_type[-1])
            if strValue is not None:
                vecValue = eval(strValue) if type(strValue) is str else strValue
                if len(vecValue) == componentCount:
                    return np.array(vecValue, dtype=np.float32)
                else:
                    logger.error(ValueError("%s need %d float members." % (data_type, componentCount)))
                    raise ValueError
            else:
                return np.eye(componentCount, dtype=np.float32)
        elif data_type == 'sampler2D':
            texture = CoreManager.instance().resource_manager.getTexture(strValue or 'empty')
            return texture
    except ValueError:
        logger.error(traceback.format_exc())
    return None


class UniformVariable:
    data_type = ""
    uniform_type = ""

    def __init__(self, program, variable_name):
        self.name = variable_name
        self.location = glGetUniformLocation(program, variable_name)
        self.valid = True
        if self.location == -1:
            self.valid = False
            # logger.warn("%s location is -1" % variable_name)

    def bind_uniform(self, value):
        raise BaseException("You must implement bind function.")


class UniformArray(UniformVariable):
    """future work : http://pyopengl.sourceforge.net/context/tutorials/shader_7.html"""
    uniform_type = ""


class UniformInt(UniformVariable):
    uniform_type = "int"

    def bind_uniform(self, value):
        glUniform1i(self.location, value)


class UniformFloat(UniformVariable):
    uniform_type = "float"

    def bind_uniform(self, value):
        glUniform1f(self.location, value)


class UniformVector2(UniformVariable):
    uniform_type = "vec2"

    def bind_uniform(self, value):
        glUniform2fv(self.location, 1, value)


class UniformVector3(UniformVariable):
    uniform_type = "vec3"

    def bind_uniform(self, value):
        glUniform3fv(self.location, 1, value)


class UniformVector4(UniformVariable):
    uniform_type = "vec4"

    def bind_uniform(self, value):
        glUniform4fv(self.location, 1, value)


class UniformMatrix2(UniformVariable):
    uniform_type = "mat2"

    def bind_uniform(self, value):
        glUniformMatrix2fv(self.location, 1, GL_FALSE, value)


class UniformMatrix3(UniformVariable):
    uniform_type = "mat3"

    def bind_uniform(self, value):
        glUniformMatrix3fv(self.location, 1, GL_FALSE, value)


class UniformMatrix4(UniformVariable):
    uniform_type = "mat4"

    def bind_uniform(self, value):
        glUniformMatrix4fv(self.location, 1, GL_FALSE, value)


class UniformTexture2D(UniformVariable):
    uniform_type = "sampler2D"

    def __init__(self, program, variable_name):
        UniformVariable.__init__(self, program, variable_name)
        self.activateTextureIndex = GL_TEXTURE0
        self.textureIndex = 0

    def set_texture_index(self, textureIndex):
        self.activateTextureIndex = eval("GL_TEXTURE%d" % textureIndex)
        self.textureIndex = textureIndex

    def bind_uniform(self, texture):
        glActiveTexture(self.activateTextureIndex)
        texture.bind_texture()  # glBindTexture(texture.target, texture.texture_bind)
        glUniform1i(self.location, self.textureIndex)
