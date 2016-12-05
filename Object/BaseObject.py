import time, math

import numpy as np
from OpenGL.GL import *
from PIL import Image

import Resource
from Resource import *
from Object import TransformObject, Primitive
from Render import Material
from Utilities import Attributes


class BaseObject(TransformObject):
    def __init__(self, name, pos, mesh, material):
        TransformObject.__init__(self, pos)
        self.name = name
        self.selected = False
        self.mesh = mesh
        self.material = material
        self.attributes = Attributes()

        # load texture file
        image = Image.open(os.path.join(PathTextures, 'Wool_carpet_pxr128_bmp.tif'))
        ix, iy = image.size
        image = image.tobytes("raw", "RGBX", 0, -1)

        # binding texture
        self.textureDiffuse = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.textureDiffuse)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, ix, iy, 0, GL_RGBA, GL_UNSIGNED_BYTE, image)
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_MIRRORED_REPEAT)
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_MIRRORED_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)

        # load texture file
        image = Image.open(os.path.join(PathTextures, 'Wool_carpet_pxr128_normal.tif'))
        ix, iy = image.size
        image = image.tobytes("raw", "RGBX", 0, -1)

        # binding texture
        self.textureNormal = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.textureNormal)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, ix, iy, 0, GL_RGBA, GL_UNSIGNED_BYTE, image)
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_MIRRORED_REPEAT)
        # glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_MIRRORED_REPEAT)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glGenerateMipmap(GL_TEXTURE_2D)

    def getAttribute(self):
        self.attributes.setAttribute('name', self.name)
        self.attributes.setAttribute('pos', self.pos)
        self.attributes.setAttribute('rot', self.rot)
        self.attributes.setAttribute('scale', self.scale)
        self.attributes.setAttribute('mesh', self.mesh.name if self.mesh else "", type(Primitive))
        self.attributes.setAttribute('material', self.material.name if self.material else "", type(Material))
        return self.attributes

    def setAttribute(self, attributeName, attributeValue):
        if attributeName == 'pos':
            self.setPos(attributeValue)
        elif attributeName == 'rot':
            self.setRot(attributeValue)
        elif attributeName == 'scale':
            self.setScale(attributeValue)
        elif attributeName == 'mesh':
            self.mesh = Resource.ResourceManager.instance().getMesh(attributeValue)
        elif attributeName == 'material':
            self.material = Resource.ResourceManager.instance().getMaterial(attributeValue)

    def setSelected(self, selected):
        self.selected = selected

    def draw(self, lastProgram, lastMesh, cameraPos, view, perspective, vpMatrix, lightPos, lightColor, selected=False):
        self.setYaw((time.time() * 0.2) % math.pi * 2.0)  # Test Code
        self.updateTransform()

        if self.material is None or self.mesh is None:
            return

        # bind shader program
        if lastProgram != self.material.program:
            glUseProgram(self.material.program)

        loc = glGetUniformLocation(self.material.program, "model")
        glUniformMatrix4fv(loc, 1, GL_FALSE, self.matrix)

        loc = glGetUniformLocation(self.material.program, "view")
        glUniformMatrix4fv(loc, 1, GL_FALSE, view)

        loc = glGetUniformLocation(self.material.program, "perspective")
        glUniformMatrix4fv(loc, 1, GL_FALSE, perspective)

        loc = glGetUniformLocation(self.material.program, "mvp")
        glUniformMatrix4fv(loc, 1, GL_FALSE, np.dot(self.matrix, vpMatrix))

        loc = glGetUniformLocation(self.material.program, "diffuseColor")
        glUniform4fv(loc, 1, (0, 0, 0.5, 1) if selected else (0.3, 0.3, 0.3, 1.0))

        # selected object render color
        loc = glGetUniformLocation(self.material.program, "camera_position")
        glUniform3fv(loc, 1, cameraPos)

        # selected object render color
        loc = glGetUniformLocation(self.material.program, "light_position")
        glUniform3fv(loc, 1, lightPos)

        # selected object render color
        loc = glGetUniformLocation(self.material.program, "light_color")
        glUniform4fv(loc, 1, lightColor)

        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.textureDiffuse)
        glUniform1i(glGetUniformLocation(self.material.program, "textureDiffuse"), 0)

        glActiveTexture(GL_TEXTURE1)
        glBindTexture(GL_TEXTURE_2D, self.textureNormal)
        glUniform1i(glGetUniformLocation(self.material.program, "textureNormal"), 1)

        # At last, bind buffers
        if lastMesh != self.mesh:
            self.mesh.bindBuffers()
        self.mesh.draw()
        # glUseProgram(0)
