import time
import math

from OpenGL.GL import *
from OpenGL.GL.shaders import *
from OpenGL.GL.shaders import glDeleteShader

import numpy as np

from Common import logger
from App import CoreManager
from OpenGLContext import VertexArrayBuffer

from .constants import *
from .model import *


class Luminance:
    NONE = 0
    APPROXIMATE = 1
    PRECOMPUTED = 2


class Atmosphere:
    def __init__(self):
        self.use_constant_solar_spectrum = False
        self.use_ozone = True
        self.use_combined_textures = True
        self.use_luminance = Luminance.NONE
        self.do_white_balance = False
        self.show_help = True
        self.view_distance_meters = 9000.0
        self.view_zenith_angle_radians = 1.47
        self.view_azimuth_angle_radians = -0.1
        self.sun_zenith_angle_radians = 1.3
        self.sun_azimuth_angle_radians = 2.9
        self.sun_direction = Float3()
        self.exposure = 3.0

        self.white_point = Float3()
        self.earth_center = Float3(0.0, 0.0, -kBottomRadius / kLengthUnitInMeters)
        self.sun_size = Float2(math.tan(kSunAngularRadius), math.cos(kSunAngularRadius))
        self.model_from_view = Matrix4()
        self.view_from_clip = Matrix4()

        self.model = None
        self.atmosphere_material_instance = None

        self.transmittance_texture = None
        self.scattering_texture = None
        self.irradiance_texture = None
        self.optional_single_mie_scattering_texture = None

        positions = np.array([(-1, 1, 0, 1), (-1, -1, 0, 1), (1, -1, 0, 1), (1, 1, 0, 1)], dtype=np.float32)
        indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
        self.quad = VertexArrayBuffer(
            name='atmosphere quad',
            datas=[positions, ],
            index_data=indices,
            dtype=np.float32
        )

        self.initialize()

    def initialize(self):
        resource_manager = CoreManager.instance().resource_manager

        # USE PRECOMPUTED TEXTURE
        use_precomputed_texture = False
        if not use_precomputed_texture:
            self.transmittance_texture = resource_manager.getTexture('precomputed_atmosphere.transmittance')
            self.scattering_texture = resource_manager.getTexture('precomputed_atmosphere.scattering')
            self.irradiance_texture = resource_manager.getTexture('precomputed_atmosphere.irradiance')
            if self.use_combined_textures:
                self.optional_single_mie_scattering_texture = resource_manager.getTexture(
                    'precomputed_atmosphere.optional_single_mie_scattering')
        else:
            max_sun_zenith_angle = 120.0 / 180.0 * kPi

            rayleigh_layer = DensityProfileLayer(0.0, 1.0, -1.0 / kRayleighScaleHeight, 0.0, 0.0)
            mie_layer = DensityProfileLayer(0.0, 1.0, -1.0 / kMieScaleHeight, 0.0, 0.0)

            ozone_density = [DensityProfileLayer(25000.0, 0.0, 0.0, 1.0 / 15000.0, -2.0 / 3.0),
                             DensityProfileLayer(0.0, 0.0, 0.0, -1.0 / 15000.0, 8.0 / 3.0)]

            wavelengths = []
            solar_irradiance = []
            rayleigh_scattering = []
            mie_scattering = []
            mie_extinction = []
            absorption_extinction = []
            ground_albedo = []

            for i in range(kLambdaMin, kLambdaMax + 1, 10):
                L = float(i) * 1e-3  # micro-meters
                mie = kMieAngstromBeta / kMieScaleHeight * math.pow(L, -kMieAngstromAlpha)
                wavelengths.append(i)
                if self.use_constant_solar_spectrum:
                    solar_irradiance.append(kConstantSolarIrradiance)
                else:
                    solar_irradiance.append(kSolarIrradiance[int((i - kLambdaMin) / 10)])
                rayleigh_scattering.append(kRayleigh * math.pow(L, -4))
                mie_scattering.append(mie * kMieSingleScatteringAlbedo)
                mie_extinction.append(mie)
                if self.use_ozone:
                    absorption_extinction.append(
                        kMaxOzoneNumberDensity * kOzoneCrossSection[int((i - kLambdaMin) / 10)])
                else:
                    absorption_extinction.append(0.0)
                ground_albedo.append(kGroundAlbedo)

            rayleigh_density = [rayleigh_layer, ]
            mie_density = [mie_layer, ]
            num_precomputed_wavelengths = 15 if self.use_luminance == Luminance.PRECOMPUTED else 3

            self.model = Model(wavelengths,
                               solar_irradiance,
                               kSunAngularRadius,
                               kBottomRadius,
                               kTopRadius,
                               rayleigh_density,
                               rayleigh_scattering,
                               mie_density,
                               mie_scattering,
                               mie_extinction,
                               kMiePhaseFunctionG,
                               ozone_density,
                               absorption_extinction,
                               ground_albedo,
                               max_sun_zenith_angle,
                               kLengthUnitInMeters,
                               self.use_luminance != Luminance.NONE,
                               num_precomputed_wavelengths,
                               self.use_combined_textures)
            self.model.Init()

            self.transmittance_texture = self.model.transmittance_texture
            self.scattering_texture = self.model.scattering_texture
            self.irradiance_texture = self.model.irradiance_texture
            self.optional_single_mie_scattering_texture = self.model.optional_single_mie_scattering_texture

        # set material instance
        macros = {
            'USE_LUMINANCE': 1 if self.use_luminance else 0,
            'COMBINED_SCATTERING_TEXTURES': 1 if self.use_combined_textures else 0
        }
        self.atmosphere_material_instance = resource_manager.getMaterialInstance(
            'precomputed_atmosphere.atmosphere',
            macros=macros)

    def update(self, main_camera, main_light):
        if Luminance.NONE == self.use_luminance:
            self.exposure = 3.0
        else:
            self.exposure = 0.00001

        dist = main_camera.transform.pos[2]
        l = (self.view_distance_meters + dist) / kLengthUnitInMeters

        self.view_zenith_angle_radians = main_camera.transform.rot[0]
        self.view_azimuth_angle_radians = main_camera.transform.rot[1]

        cos_z = math.cos(self.view_zenith_angle_radians)
        sin_z = math.sin(self.view_zenith_angle_radians)
        cos_a = math.cos(self.view_azimuth_angle_radians)
        sin_a = math.sin(self.view_azimuth_angle_radians)
        ux = [-sin_a, cos_a, 0.0, 0.0]
        uy = [-cos_z * cos_a, -cos_z * sin_a, sin_z, 0.0]
        uz = [sin_z * cos_a, sin_z * sin_a, cos_z, 0.0]
        self.model_from_view[0][...] = ux
        self.model_from_view[1][...] = uy
        self.model_from_view[2][...] = uz
        self.model_from_view[3][0] = self.model_from_view[2][0] * l
        self.model_from_view[3][1] = self.model_from_view[2][1] * l
        self.model_from_view[3][2] = self.model_from_view[2][2] * l

        # view_from_clip
        kFovY = main_camera.fov / 180.0 * kPi
        kTanFovY = math.tan(kFovY / 2.0)
        self.view_from_clip[...] = np.array([[kTanFovY * main_camera.aspect, 0.0, 0.0, 0.0],
                                        [0.0, kTanFovY, 0.0, 0.0],
                                        [0.0, 0.0, 0.0, 1.0],
                                        [0.0, 0.0, -1.0, 1.0]], dtype=np.float32)

        # sun_direction
        # self.sun_direction[0] = cos(self.sun_azimuth_angle_radians) * sin(self.sun_zenith_angle_radians)
        # self.sun_direction[1] = sin(self.sun_azimuth_angle_radians) * sin(self.sun_zenith_angle_radians)
        # self.sun_direction[2] = cos(self.sun_zenith_angle_radians)
        self.sun_direction[...] = main_light.transform.front

    def render_precomputed_atmosphere(self):
        self.quad.bind_vertex_buffer()
        self.atmosphere_material_instance.use_program()

        self.atmosphere_material_instance.bind_uniform_data("transmittance_texture", self.transmittance_texture)
        self.atmosphere_material_instance.bind_uniform_data("scattering_texture", self.scattering_texture)
        self.atmosphere_material_instance.bind_uniform_data("irradiance_texture", self.irradiance_texture)
        if not self.use_combined_textures:
            self.atmosphere_material_instance.bind_uniform_data("single_mie_scattering_texture",
                                                                self.optional_single_mie_scattering_texture)

        self.atmosphere_material_instance.bind_uniform_data("exposure", self.exposure)
        self.atmosphere_material_instance.bind_uniform_data("camera", self.model_from_view[3][0:3])
        self.atmosphere_material_instance.bind_uniform_data("sun_direction", self.sun_direction)
        self.atmosphere_material_instance.bind_uniform_data("earth_center", self.earth_center)
        self.atmosphere_material_instance.bind_uniform_data("sun_size", self.sun_size)
        self.atmosphere_material_instance.bind_uniform_data("model_from_view", self.model_from_view)
        self.atmosphere_material_instance.bind_uniform_data("view_from_clip", self.view_from_clip)

        self.quad.draw_elements()
