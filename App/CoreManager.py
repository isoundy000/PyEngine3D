import gc
import os
import platform as platformModule
import sys
import time
import re
import traceback
from functools import partial

import numpy as np

from .GameBackend import PyGlet, PyGame, Keyboard, Event
from Common import logger, log_level, COMMAND
from Utilities import Singleton, GetClassName, Config, Profiler

# Function : IsExtensionSupported
# NeHe Tutorial Lesson: 45 - Vertex Buffer Objects
reCheckGLExtention = re.compile("GL_(.+?)_(.+)")


# ------------------------------#
# CLASS : CoreManager
# ------------------------------#
class CoreManager(Singleton):
    """
    Manager other mangers classes. ex) shader manager, material manager...
    CoreManager usage for debug what are woring manager..
    """

    def __init__(self):
        self.valid = True

        # command
        self.cmdQueue = None
        self.uiCmdQueue = None
        self.cmdPipe = None

        self.need_to_gc_collect = False

        # timer
        self.fps = 0.0
        self.vsync = False
        self.minDelta = 1.0 / 60.0  # 60fps
        self.delta = 0.0
        self.updateTime = 0.0
        self.logicTime = 0.0
        self.gpuTime = 0.0
        self.renderTime = 0.0
        self.presentTime = 0.0
        self.currentTime = 0.0

        self.min_delta = sys.float_info.max
        self.max_delta = sys.float_info.min
        self.curr_min_delta = sys.float_info.max
        self.curr_max_delta = sys.float_info.min
        self.avg_fps = 0.0
        self.avg_ms = 0.0
        self.frame_count = 0
        self.acc_time = 0.0

        self.avg_logicTime = 0.0
        self.avg_gpuTime = 0.0
        self.avg_renderTime = 0.0
        self.avg_presentTime = 0.0

        self.acc_logicTime = 0.0
        self.acc_gpuTime = 0.0
        self.acc_renderTime = 0.0
        self.acc_presentTime = 0.0

        # managers
        self.game_backend = None
        self.resource_manager = None
        self.render_option_manager = None
        self.renderer = None
        self.rendertarget_manager = None
        self.font_manager = None
        self.scene_manager = None
        self.projectManager = None
        self.config = None

        self.last_game_backend = PyGlet.__name__
        self.game_backend_list = [PyGlet.__name__, PyGame.__name__]

        self.commands = []

    def gc_collect(self):
        self.need_to_gc_collect = True

    def initialize(self, cmdQueue, uiCmdQueue, cmdPipe, project_filename=""):
        # process start
        logger.info('Platform : %s' % platformModule.platform())
        logger.info("Process Start : %s" % GetClassName(self))

        self.cmdQueue = cmdQueue
        self.uiCmdQueue = uiCmdQueue
        self.cmdPipe = cmdPipe

        self.config = Config("config.ini", log_level)

        self.registCommand()

        # ready to launch - send message to ui
        if self.cmdPipe:
            self.cmdPipe.SendAndRecv(COMMAND.UI_RUN, None, COMMAND.UI_RUN_OK, None)

        from ResourceManager import ResourceManager
        from Object import RenderTargetManager, Renderer, FontManager, RenderOptionManager
        from .SceneManager import SceneManager
        from .ProjectManager import ProjectManager

        self.resource_manager = ResourceManager.instance()
        self.render_option_manager = RenderOptionManager.instance()
        self.rendertarget_manager = RenderTargetManager.instance()
        self.font_manager = FontManager.instance()
        self.renderer = Renderer.instance()
        self.scene_manager = SceneManager.instance()
        self.projectManager = ProjectManager.instance()

        # check innvalid project
        if not self.projectManager.initialize(self, project_filename):
            self.valid = False
            self.exit()
            return False

        # do First than other manager initalize. Because have to been opengl init from pygame.display.set_mode
        width, height = self.projectManager.config.Screen.size
        full_screen = self.projectManager.config.Screen.full_screen

        if self.config.hasValue('Project', 'game_backend'):
            self.last_game_backend = self.config.getValue('Project', 'game_backend')

        if self.last_game_backend == PyGame.__name__:
            self.game_backend = PyGame(self)
        else:
            self.game_backend = PyGlet(self)
            self.last_game_backend = PyGlet.__name__
        self.game_backend.change_resolution(width, height, full_screen, resize_scene=False)

        self.sendGameBackendList(self.game_backend_list)
        index = self.game_backend_list.index(
            self.last_game_backend) if self.last_game_backend in self.game_backend_list else 0
        self.sendCurrentGameBackendIndex(index)

        if not self.game_backend.valid:
            self.error('game_backend initializing failed')

        # initalize managers
        self.resource_manager.initialize(self, self.projectManager.project_dir)
        self.render_option_manager.initialize(self)
        self.rendertarget_manager.initialize(self)
        self.font_manager.initialize(self)
        self.renderer.initialize(self)
        self.renderer.resizeScene(width, height)
        self.scene_manager.initialize(self)

        self.send(COMMAND.SORT_UI_ITEMS)
        return True

    def set_window_title(self, title):
        self.game_backend.set_window_title(self.last_game_backend + " - " + title)

    def get_next_open_project_filename(self):
        return self.projectManager.next_open_project_filename

    def run(self):
        self.game_backend.run()
        self.exit()

    def exit(self):
        # send a message to close ui
        if self.uiCmdQueue:
            self.uiCmdQueue.put(COMMAND.CLOSE_UI)

        # write config
        if self.valid:
            self.config.setValue("Project", "recent", self.projectManager.project_filename)
            self.config.setValue("Project", "game_backend", self.last_game_backend)
            self.config.save()  # save config

        # save project
        self.projectManager.close_project()

        self.renderer.close()
        self.resource_manager.close()
        self.renderer.destroyScreen()

        self.game_backend.quit()

        logger.info("Process Stop : %s" % GetClassName(self))  # process stop

    def error(self, msg):
        logger.error(msg)
        self.close()

    def close(self):
        self.game_backend.close()

    def change_game_backend(self, game_backend):
        self.last_game_backend = self.game_backend_list[game_backend]
        logger.info("The game backend was chaned to %s. It will be applied at the next run." % self.last_game_backend)

    # Send messages
    def send(self, *args):
        if self.uiCmdQueue:
            self.uiCmdQueue.put(*args)

    def request(self, *args):
        if self.cmdQueue:
            self.cmdQueue.put(*args)

    def sendResourceInfo(self, resource_info):
        self.send(COMMAND.TRANS_RESOURCE_INFO, resource_info)

    def notifyDeleteResource(self, resource_info):
        self.send(COMMAND.DELETE_RESOURCE_INFO, resource_info)

    def sendObjectInfo(self, obj):
        object_name = obj.name if hasattr(obj, 'name') else str(obj)
        object_class_name = GetClassName(obj)
        self.send(COMMAND.TRANS_OBJECT_INFO, (object_name, object_class_name))

    def sendObjectList(self):
        obj_names = self.scene_manager.getObjectNames()
        for obj_name in obj_names:
            obj = self.scene_manager.getObject(obj_name)
            self.sendObjectInfo(obj)

    def notifyChangeResolution(self, screen_info):
        self.send(COMMAND.TRANS_SCREEN_INFO, screen_info)

    def notifyClearScene(self):
        self.send(COMMAND.CLEAR_OBJECT_LIST)

    def notifyDeleteObject(self, obj_name):
        self.send(COMMAND.DELETE_OBJECT_INFO, obj_name)

    def clearRenderTargetList(self):
        self.send(COMMAND.CLEAR_RENDERTARGET_LIST)

    def sendRenderTargetInfo(self, rendertarget_info):
        self.send(COMMAND.TRANS_RENDERTARGET_INFO, rendertarget_info)

    def sendAntiAliasingList(self, antialiasing_list):
        self.send(COMMAND.TRANS_ANTIALIASING_LIST, antialiasing_list)

    def sendRenderingTypeList(self, rendering_type_list):
        self.send(COMMAND.TRANS_RENDERING_TYPE_LIST, rendering_type_list)

    def sendCurrentGameBackendIndex(self, game_backend_index):
        self.send(COMMAND.TRANS_GAME_BACKEND_INDEX, game_backend_index)

    def sendGameBackendList(self, game_backend_list):
        self.send(COMMAND.TRANS_GAME_BACKEND_LIST, game_backend_list)

    def registCommand(self):
        def nothing(cmd_enum, value):
            logger.warn("Nothing to do for %s(%d)" % (str(cmd_enum), cmd_enum.value))

        self.commands = []
        for i in range(COMMAND.COUNT.value):
            self.commands.append(partial(nothing, COMMAND.convert_index_to_enum(i)))

        # exit
        self.commands[COMMAND.CLOSE_APP.value] = lambda value: self.close()
        # project
        self.commands[COMMAND.NEW_PROJECT.value] = lambda value: self.projectManager.new_project(value)
        self.commands[COMMAND.OPEN_PROJECT.value] = lambda value: self.projectManager.open_project_next_time(value)
        self.commands[COMMAND.SAVE_PROJECT.value] = lambda value: self.projectManager.save_project()
        # scene
        self.commands[COMMAND.NEW_SCENE.value] = lambda value: self.scene_manager.new_scene()
        self.commands[COMMAND.SAVE_SCENE.value] = lambda value: self.scene_manager.save_scene()
        # view mode
        self.commands[COMMAND.VIEWMODE_WIREFRAME.value] = lambda value: self.renderer.setViewMode(
            COMMAND.VIEWMODE_WIREFRAME)
        self.commands[COMMAND.VIEWMODE_SHADING.value] = lambda value: self.renderer.setViewMode(
            COMMAND.VIEWMODE_SHADING)

        # screen
        def cmd_change_resolution(value):
            width, height, full_screen = value
            self.game_backend.change_resolution(width, height, full_screen)
        self.commands[COMMAND.CHANGE_RESOLUTION.value] = cmd_change_resolution

        # Resource commands
        def cmd_load_resource(value):
            resName, resTypeName = value
            self.resource_manager.load_resource(resName, resTypeName)
        self.commands[COMMAND.LOAD_RESOURCE.value] = cmd_load_resource

        def cmd_open_resource(value):
            resName, resTypeName = value
            self.resource_manager.open_resource(resName, resTypeName)
        self.commands[COMMAND.OPEN_RESOURCE.value] = cmd_open_resource

        def cmd_duplicate_resource(value):
            resName, resTypeName = value
            self.resource_manager.duplicate_resource(resName, resTypeName)
        self.commands[COMMAND.DUPLICATE_RESOURCE.value] = cmd_duplicate_resource

        def cmd_save_resource(value):
            resName, resTypeName = value
            self.resource_manager.save_resource(resName, resTypeName)
        self.commands[COMMAND.SAVE_RESOURCE.value] = cmd_save_resource

        def cmd_delete_resource(value):
            resName, resTypeName = value
            self.resource_manager.delete_resource(resName, resTypeName)
        self.commands[COMMAND.DELETE_RESOURCE.value] = cmd_delete_resource

        def cmd_request_resource_list(value):
            resourceList = self.resource_manager.getResourceNameAndTypeList()
            self.send(COMMAND.TRANS_RESOURCE_LIST, resourceList)
        self.commands[COMMAND.REQUEST_RESOURCE_LIST.value] = cmd_request_resource_list

        def cmd_request_resource_attribute(value):
            resName, resTypeName = value
            attribute = self.resource_manager.getResourceAttribute(resName, resTypeName)
            if attribute:
                self.send(COMMAND.TRANS_RESOURCE_ATTRIBUTE, attribute)
        self.commands[COMMAND.REQUEST_RESOURCE_ATTRIBUTE.value] = cmd_request_resource_attribute

        def cmd_set_resource_attribute(value):
            resourceName, resourceType, attributeName, attributeValue, attribute_index = value
            self.resource_manager.setResourceAttribute(resourceName, resourceType, attributeName, attributeValue,
                                                      attribute_index)
        self.commands[COMMAND.SET_RESOURCE_ATTRIBUTE.value] = cmd_set_resource_attribute

        # Scene object commands
        self.commands[COMMAND.REQUEST_OBJECT_LIST.value] = lambda value: self.sendObjectList()
        self.commands[COMMAND.DELETE_OBJECT.value] = lambda value: self.scene_manager.deleteObject(value)

        def cmd_request_object_attribute(value):
            objName, objTypeName = value
            attribute = self.scene_manager.getObjectAttribute(objName, objTypeName)
            if attribute:
                self.send(COMMAND.TRANS_OBJECT_ATTRIBUTE, attribute)
        self.commands[COMMAND.REQUEST_OBJECT_ATTRIBUTE.value] = cmd_request_object_attribute

        def cmd_set_object_attribute(value):
            objectName, objectType, attributeName, attributeValue, attribute_index = value
            self.scene_manager.setObjectAttribute(objectName, objectType, attributeName, attributeValue, attribute_index)
        self.commands[COMMAND.SET_OBJECT_ATTRIBUTE.value] = cmd_set_object_attribute

        self.commands[COMMAND.SET_OBJECT_SELECT.value] = lambda value: self.scene_manager.setSelectedObject(value)
        self.commands[COMMAND.SET_OBJECT_FOCUS.value] = lambda value: self.scene_manager.setObjectFocus(value)

        def cmd_set_anti_aliasing(anti_aliasing_index):
            self.renderer.postprocess.set_anti_aliasing(anti_aliasing_index)
        self.commands[COMMAND.SET_ANTIALIASING.value] = cmd_set_anti_aliasing

        def cmd_set_rendering_type(renderering_type):
            self.render_option_manager.set_rendering_type(renderering_type)
        self.commands[COMMAND.SET_RENDERING_TYPE.value] = cmd_set_rendering_type

        # set game backend
        self.commands[COMMAND.CHANGE_GAME_BACKEND.value] = self.change_game_backend

        def cmd_view_rendertarget(value):
            rendertarget_index, rendertarget_name = value
            texture = self.rendertarget_manager.find_rendertarget(rendertarget_index, rendertarget_name)
            self.renderer.set_debug_texture(texture)
            if self.renderer.debug_texture:
                attribute = self.renderer.debug_texture.getAttribute()
                if attribute:
                    self.send(COMMAND.TRANS_OBJECT_ATTRIBUTE, attribute)
        self.commands[COMMAND.VIEW_RENDERTARGET.value] = cmd_view_rendertarget

        def cmd_recreate_render_targets(value):
            self.renderer.rendertarget_manager.create_rendertargets()
        self.commands[COMMAND.RECREATE_RENDER_TARGETS.value] = cmd_recreate_render_targets

    def updateCommand(self):
        if self.uiCmdQueue is None:
            return

        while not self.cmdQueue.empty():
            # receive value must be tuple type
            cmd, value = self.cmdQueue.get()
            self.commands[cmd.value](value)

    def update_event(self, event_type, event_value=None):
        if Event.QUIT == event_type:
            self.close()
        elif Event.VIDEORESIZE == event_type:
            self.notifyChangeResolution(event_value)
        elif Event.KEYDOWN == event_type:
            key_pressed = self.game_backend.get_keyboard_pressed()
            subkey_down = key_pressed[Keyboard.LCTRL] or key_pressed[Keyboard.LSHIFT] or key_pressed[Keyboard.LALT]
            if Keyboard.ESCAPE == event_value:
                if self.game_backend.full_screen:
                    self.game_backend.change_resolution(0, 0, False)
                else:
                    self.close()
            elif Keyboard._1 == event_value:
                object_name_list = self.resource_manager.getModelNameList()
                sphere = self.resource_manager.getModel('sphere')
                if object_name_list:
                    for i in range(20):
                        pos = [np.random.uniform(-10, 10) for x in range(3)]
                        objName = np.random.choice(object_name_list)
                        model = self.resource_manager.getModel(objName)
                        obj_instance = self.scene_manager.addObject(model=sphere, pos=pos)
                        if obj_instance:
                            self.sendObjectInfo(obj_instance)
            elif Keyboard._2 == event_value:
                self.renderer.render_light_probe(force=True)
            elif Keyboard._3 == event_value:
                self.gc_collect()
            elif Keyboard.DELETE == event_value:
                # Test Code
                obj_names = set(self.scene_manager.getObjectNames())
                # clear static mesh
                self.scene_manager.clear_actors()
                current_obj_names = set(self.scene_manager.getObjectNames())
                for obj_name in (obj_names - current_obj_names):
                    self.notifyDeleteObject(obj_name)

    def updateCamera(self):
        keydown = self.game_backend.get_keyboard_pressed()
        mouse_delta = self.game_backend.mouse_delta
        btnL, btnM, btnR = self.game_backend.get_mouse_pressed()

        # get camera
        camera = self.scene_manager.main_camera
        cameraTransform = camera.transform
        move_speed = camera.move_speed * self.delta
        pan_speed = camera.pan_speed * self.delta
        rotation_speed = camera.rotation_speed * self.delta

        if keydown[Keyboard.LSHIFT]:
            move_speed *= 4.0
            pan_speed *= 4.0

        # camera move pan
        if btnL and btnR or btnM:
            cameraTransform.moveToLeft(-mouse_delta[0] * pan_speed)
            cameraTransform.moveToUp(-mouse_delta[1] * pan_speed)

        # camera rotation
        elif btnL or btnR:
            cameraTransform.rotationPitch(mouse_delta[1] * rotation_speed)
            cameraTransform.rotationYaw(-mouse_delta[0] * rotation_speed)

        if keydown[Keyboard.Z]:
            cameraTransform.rotationRoll(-rotation_speed * 10.0)
        elif keydown[Keyboard.C]:
            cameraTransform.rotationRoll(rotation_speed * 10.0)

        # move to view direction ( inverse front of camera matrix )
        if keydown[Keyboard.W] or self.game_backend.wheel_up:
            cameraTransform.moveToFront(-move_speed)
        elif keydown[Keyboard.S] or self.game_backend.wheel_down:
            cameraTransform.moveToFront(move_speed)

        # move to side
        if keydown[Keyboard.A]:
            cameraTransform.moveToLeft(-move_speed)
        elif keydown[Keyboard.D]:
            cameraTransform.moveToLeft(move_speed)

        # move to up
        if keydown[Keyboard.Q]:
            cameraTransform.moveToUp(move_speed)
        elif keydown[Keyboard.E]:
            cameraTransform.moveToUp(-move_speed)

        if keydown[Keyboard.SPACE]:
            cameraTransform.resetTransform()

    def update(self):
        currentTime = time.perf_counter()
        delta = currentTime - self.currentTime

        if self.vsync and delta < self.minDelta or delta == 0.0:
            return

        self.acc_time += delta
        self.frame_count += 1
        self.curr_min_delta = min(delta, self.curr_min_delta)
        self.curr_max_delta = max(delta, self.curr_max_delta)

        # set timer
        self.currentTime = currentTime
        self.delta = delta
        self.fps = 1.0 / delta

        self.updateTime = delta * 1000.0  # millisecond

        startTime = time.perf_counter()
        self.updateCommand()
        self.updateCamera()

        # update actors
        self.scene_manager.update_scene(delta)
        self.logicTime = (time.perf_counter() - startTime) * 1000.0  # millisecond

        # render scene
        startTime = time.perf_counter()
        self.renderer.render_light_probe()
        renderTime, presentTime = self.renderer.renderScene()

        self.renderTime = renderTime * 1000.0  # millisecond
        self.presentTime = presentTime * 1000.0  # millisecond

        self.acc_logicTime += self.logicTime
        self.acc_gpuTime += self.gpuTime
        self.acc_renderTime += self.renderTime
        self.acc_presentTime += self.presentTime

        if 1.0 < self.acc_time:
            self.avg_logicTime = self.acc_logicTime / self.frame_count
            self.avg_gpuTime = self.acc_gpuTime / self.frame_count
            self.avg_renderTime = self.acc_renderTime / self.frame_count
            self.avg_presentTime = self.acc_presentTime / self.frame_count

            self.acc_logicTime = 0.0
            self.acc_gpuTime = 0.0
            self.acc_renderTime = 0.0
            self.acc_presentTime = 0.0

            self.min_delta = self.curr_min_delta * 1000.0
            self.max_delta = self.curr_max_delta * 1000.0
            self.curr_min_delta = sys.float_info.max
            self.curr_max_delta = sys.float_info.min
            self.avg_ms = self.acc_time / self.frame_count * 1000.0
            self.avg_fps = 1000.0 / self.avg_ms
            self.frame_count = 0
            self.acc_time = 0.0

        # debug info
        # print(self.fps, self.updateTime)
        self.font_manager.log("%.2f fps" % self.avg_fps)
        self.font_manager.log("%.2f ms (%.2f ms ~ %.2f ms)" % (self.avg_ms, self.min_delta, self.max_delta))
        self.font_manager.log("CPU : %.2f ms" % self.avg_logicTime)
        self.font_manager.log("GPU : %.2f ms" % self.avg_gpuTime)
        self.font_manager.log("Render : %.2f ms" % self.avg_renderTime)
        self.font_manager.log("Present : %.2f ms" % self.avg_presentTime)

        # selected object transform info
        selected_object = self.scene_manager.getSelectedObject()
        if selected_object:
            self.font_manager.log("Selected Object : %s" % selected_object.name)
            self.font_manager.log(selected_object.transform.getTransformInfos())
        self.gpuTime = (time.perf_counter() - startTime) * 1000.0

        if self.need_to_gc_collect:
            self.need_to_gc_collect = False
            gc.collect()

