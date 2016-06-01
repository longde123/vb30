#
# V-Ray For Blender
#
# http://chaosgroup.com
#
# Author: Andrei Izrantcev
# E-Mail: andrei.izrantcev@chaosgroup.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# All Rights Reserved. V-Ray(R) is a registered trademark of Chaos Software.
#

import os
import sys
import subprocess
import ipaddress

import bpy
import _vray_for_blender

_has_rt = True
try:
    import _vray_for_blender_rt
except:
    _has_rt = False

from vb30.lib import SysUtils
from vb30 import export, debug

from vb30.lib.VRayStream import VRayExportFiles
from vb30.lib.VRayStream import VRayFilePaths


# This will hold handle to subprocess.Popen to the zmq server if
# it is started in local mode, and it should be terminated on Shutdown()
#
class ZMQProcess:
    log_lvl_translate = {
        'ERROR': '4',
        'WARNING': '3',
        'DEBUG': '2',
        'INFO': '1',
    }
    _zmq_process = None
    _heartbeat_running = False

    def _get_settings(self):
        settings = bpy.context.scene.vray.Exporter
        return settings.zmq_address, str(settings.zmq_port), settings.zmq_log_level

    def start_heartbeat(self):
        addr, port, _ = self._get_settings()
        ip = 'localhost'
        try:
            ip = str(ipaddress.ip_address(str(addr)))
        except:
            debug.PrintError("Failed parsing ip addr from [%s], falling back to %s" % (addr, ip))

        self._heartbeat_running = _vray_for_blender_rt.zmq_heartbeat_start("tcp://%s:%s" % (ip, port))
        debug.Debug('ZMQ starting heartbeat = %s' % self._heartbeat_running)

    def stop_heartbeat(self):
        _vray_for_blender_rt.zmq_heartbeat_stop()
        self._heartbeat_running = False
        debug.Debug('ZMQ stopping heartbeat')

    def is_use_zmq(self):
        return bpy.context.scene.vray.Exporter.backend in {'ZMQ'}

    def is_local(self):
        return bpy.context.scene.vray.Exporter.backend_worker == 'LOCAL'

    def should_start(self):
        should_start = self.is_use_zmq() and self.is_local()
        debug.Debug('ZMQ should start %s' % should_start)
        return should_start

    def check_heartbeat(self):
        if self.is_use_zmq():
            if not self._heartbeat_running:
                self.start_heartbeat()

    def check_start(self):
        if self.is_use_zmq():
            if self.is_local():
                self.start()
            self.check_heartbeat()

    def is_running(self):
        running = False
        if self._zmq_process is not None:
            self._zmq_process.poll()

        if self._zmq_process is not None\
            and self._zmq_process.returncode is None:
            running = True

        if self._heartbeat_running:
            running = _vray_for_blender_rt.zmq_heartbeat_check()
            if not running:
                self.stop_heartbeat()

        return running

    def start(self):
        if not self.is_running():
            self._check_process()

    def stop(self):
        if self.is_running():
            try:
                debug.Debug('Zmq stopped - stopping all viewports')
                self.stop_heartbeat()

                if self._zmq_process:
                    debug.Debug('Zmq terminating process')
                    self._zmq_process.terminate()

                for area in bpy.context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D' and space.viewport_shade == 'RENDERED':
                                space.viewport_shade = 'SOLID'
            except Exception as e:
                debug.PrintError(e)
        else:
            debug.Debug("Not running - cant stop")

    def restart(self):
        self.stop()
        self.check_start()

    def _check_process(self):
        _, port, log_lvl = self._get_settings()

        if self._zmq_process is not None:
            self._zmq_process.poll()
            debug.Debug("ZMQ: %s -> code[%s]" % (self._zmq_process, self._zmq_process.returncode))

        if self._zmq_process is None or self._zmq_process.returncode is not None:
            executable_path = SysUtils.GetZmqPath()

            if not executable_path or not os.path.exists(executable_path):
                debug.PrintError("Can't find V-Ray ZMQ Server!")
            else:
                try:
                    env = os.environ.copy()
                    if sys.platform == "win32":
                        if 'VRAY_ZMQSERVER_APPSDK_PATH' not in env:
                            debug.PrintError('Environment variable VRAY_ZMQSERVER_APPSDK_PATH is missing!')
                        else:
                            appsdk = os.path.dirname(env['VRAY_ZMQSERVER_APPSDK_PATH'])
                            env['PATH'] = '%s;%s' % (env['PATH'], appsdk)
                            env['VRAY_PATH'] = appsdk

                    cmd = [
                        executable_path,
                        "-p", port,
                        "-log", self.log_lvl_translate[log_lvl]
                    ]
                    debug.Debug(' '.join(cmd))

                    self.start_heartbeat()
                    self._zmq_process = subprocess.Popen(cmd, env=env)
                except Exception as e:
                    debug.PrintError(e)


ZMQ = ZMQProcess()


def init():
    jsonDirpath = os.path.join(SysUtils.GetExporterPath(), "plugins_desc")
    _vray_for_blender.start(jsonDirpath)
    if _has_rt:
        _vray_for_blender_rt.load(jsonDirpath)


def shutdown():
    _vray_for_blender.free()
    if _has_rt:
        _vray_for_blender_rt.unload()
        ZMQ.stop();


def get_file_manager(exporter, engine, scene):
    debug.Debug('Creating files for export')

    try:
        pm = VRayFilePaths()

        # Setting user defined value here
        # It could be overriden in 'initFromScene'
        # depending on VRayDR settings
        pm.setSeparateFiles(exporter.useSeparateFiles)

        pm.initFromScene(engine, scene)
        pm.printInfo()

        fm = VRayExportFiles(pm)
        fm.setOverwriteGeometry(exporter.auto_meshes)

        fm.init()
    except Exception as e:
        debug.PrintError(e)
        return "Error initing files!"

    return fm


class VRayRendererBase(bpy.types.RenderEngine):
    def render(self, scene):
        if self.is_preview:
            if scene.render.resolution_x < 64: # Don't render icons
                return

        err = export.RenderScene(self, scene)
        if err is not None:
            self.report({'ERROR'}, err)


class VRayRendererPreview(VRayRendererBase):
    bl_idname = 'VRAY_RENDER_PREVIEW'
    bl_label  = "V-Ray (With Material Preview)"

    bl_use_preview      =  True
    bl_preview_filepath = SysUtils.GetPreviewBlend()


class VRayRenderer(VRayRendererBase):
    bl_idname      = 'VRAY_RENDER'
    bl_label       = "V-Ray"
    bl_use_preview =  False


class VRayRendererRT(bpy.types.RenderEngine):
    bl_idname = 'VRAY_RENDER_RT'
    bl_label  = "V-Ray (NEW)"
    bl_use_preview = True
    bl_preview_filepath = SysUtils.GetPreviewBlend()
    bl_use_shading_nodes = True

    def _get_settings(self):
        # In case of preview "scene" argument will point
        # to the preview scene, but we need to use settings
        # from the actual scene
        #
        return bpy.context.scene.vray.Exporter

    def __init__(self):
        debug.Debug("__init__()")
        self.renderer = None
        self.file_manager = None

    def __del__(self):
        debug.Debug("__del__()")

        if hasattr(self, 'renderer') and self.renderer is not None:
            _vray_for_blender_rt.free(self.renderer)

        if hasattr(self, 'file_manager') and  self.file_manager:
            self.file_manager.writeIncludes()
            self.file_manager.closeFiles()

    # Production rendering
    #
    def update(self, data, scene):
        debug.Debug("update()")

        ZMQ.check_start()

        vrayExporter = self._get_settings()
        if not self.renderer:
            arguments = {
                'context': bpy.context.as_pointer(),
                'engine': self.as_pointer(),
                'data': data.as_pointer(),
                'scene': scene.as_pointer(),
            }

            if vrayExporter.backend == 'STD':
                self.file_manager = get_file_manager(vrayExporter, self, scene)

                arguments['mainFile']     = self.file_manager.getFileByPluginType('MAIN')
                arguments['objectFile']   = self.file_manager.getFileByPluginType('OBJECT')
                arguments['envFile']      = self.file_manager.getFileByPluginType('WORLD')
                arguments['geometryFile'] = self.file_manager.getFileByPluginType('GEOMETRY')
                arguments['lightsFile']   = self.file_manager.getFileByPluginType('LIGHT')
                arguments['materialFile'] = self.file_manager.getFileByPluginType('MATERIAL')
                arguments['textureFile']  = self.file_manager.getFileByPluginType('TEXTURE')
                arguments['cameraFile']   = self.file_manager.getFileByPluginType('CAMERA')

            self.renderer = _vray_for_blender_rt.init(**arguments)

        if vrayExporter.animation_mode == 'NONE':
            _vray_for_blender_rt.update(self.renderer)

    def render(self, scene):
        debug.Debug("render()")

        vrayExporter = self._get_settings()

        if self.renderer:
            if vrayExporter.animation_mode == 'NONE':
                _vray_for_blender_rt.render(self.renderer)
            else:
                _vray_for_blender_rt.update(self.renderer)


    # Interactive rendering
    #
    def view_update(self, context):
        debug.Debug("view_update()")

        ZMQ.check_start()

        if not self.renderer:
            self.renderer = _vray_for_blender_rt.init_rt(
                context=context.as_pointer(),
                engine=self.as_pointer(),
                data=bpy.data.as_pointer(),
                scene=bpy.context.scene.as_pointer(),
            )

        if self.renderer:
            _vray_for_blender_rt.view_update(self.renderer)

    def view_draw(self, context):
        if self.renderer:
            _vray_for_blender_rt.view_draw(self.renderer)


def GetRegClasses():
    reg_classes = [
        VRayRenderer,
        VRayRendererPreview,
    ]
    if _has_rt:
        reg_classes.append(VRayRendererRT)
    return reg_classes


def register():
    for regClass in GetRegClasses():
        bpy.utils.register_class(regClass)

    if _has_rt:
        bpy.app.handlers.load_post.append(lambda: ZMQ.check_heartbeat())


def unregister():
    for regClass in GetRegClasses():
        bpy.utils.unregister_class(regClass)
