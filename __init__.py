
# LOD: be sure all have the same material or a new geometry is created

#
# This script is licensed as public domain.
#

# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_59_0/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_66_4/bpy.props.html
# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.types.Panel.html
# http://www.blender.org/documentation/blender_python_api_2_57_release/bpy.types.PropertyGroup.html
# http://www.blender.org/documentation/blender_python_api_2_66_4/bpy.types.WindowManager.html
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Guidelines/Layouts
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Cookbook/Code_snippets/Properties
# http://wiki.blender.org/index.php/Dev:2.5/Py/Scripts/Cookbook/Code_snippets/Interface
# http://wiki.blender.org/index.php/Dev:IT/2.5/Py/Scripts/Cookbook/Code_snippets/Interface
# http://wiki.blender.org/index.php/Dev:IT/2.5/Py/Scripts/Cookbook/Code_snippets/Multi-File_packages
# http://wiki.blender.org/index.php/Doc:2.6/Manual/Extensions/Python/Properties
# http://www.blender.org/documentation/blender_python_api_2_66_4/info_tutorial_addon.html

DEBUG = 0
if DEBUG: print("Urho export init")

bl_info = {
    "name": "Urho3D export",
    "description": "Urho3D export",
    "author": "reattiva",
    "version": (0, 7),
    "blender": (2, 80, 0),
    "location": "Properties > Render > Urho export",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Import-Export"}

if "decompose" in locals():
    import imp
    imp.reload(decompose)
    imp.reload(export_urho)
    imp.reload(export_scene)
    imp.reload(utils)
    if DEBUG and "testing" in locals(): imp.reload(testing)

from .decompose import TOptions, Scan
from .export_urho import UrhoExportData, UrhoExportOptions, UrhoWriteModel, UrhoWriteAnimation, \
                         UrhoWriteTriggers, UrhoExport
from .export_scene import SOptions, UrhoScene, UrhoExportScene, UrhoWriteMaterialTrees
from .utils import PathType, FOptions, GetFilepath, CheckFilepath, ErrorsMem,IsJsonNodeAddonAvailable,getLodSetWithID,getObjectWithID
if DEBUG: from .testing import PrintUrhoData, PrintAll

import os
import time
import sys
import shutil
import logging
import subprocess

# object-array to keep track of temporary objects created just for the export-process(like for the lodsets)
tempObjects = []

if IsJsonNodeAddonAvailable():
    import JSONNodetreeUtils    

import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.app.handlers import persistent
from mathutils import Quaternion
from math import radians

#--------------------
# Loggers
#--------------------

# A list to save export messages
logList = []

# Create a logger
log = logging.getLogger("ExportLogger")
log.setLevel(logging.DEBUG)

# Formatter for the logger
FORMAT = '%(levelname)s:%(message)s'
formatter = logging.Formatter(FORMAT)

# Console filter: no more than 3 identical messages 
consoleFilterMsg = None
consoleFilterCount = 0
class ConsoleFilter(logging.Filter):
    def filter(self, record):
        global consoleFilterMsg
        global consoleFilterCount
        if consoleFilterMsg == record.msg:
            consoleFilterCount += 1
            if consoleFilterCount > 2:
                return False
        else:
            consoleFilterCount = 0
            consoleFilterMsg = record.msg
        return True
consoleFilter = ConsoleFilter()

# Logger handler which saves unique messages in the list
logMaxCount = 500
class ExportLoggerHandler(logging.StreamHandler):
    def emit(self, record):
        global logList
        try:
            if len(logList) < logMaxCount:
                msg = self.format(record)
                if not msg in logList:
                    logList.append(msg)
            #self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

# Delete old handlers
for handler in reversed(log.handlers):
    log.removeHandler(handler)

# Create a logger handler for the list
listHandler = ExportLoggerHandler()
listHandler.setFormatter(formatter)
log.addHandler(listHandler)
    
# Create a logger handler for the console
consoleHandler = logging.StreamHandler()
consoleHandler.addFilter(consoleFilter)
log.addHandler(consoleHandler)



#--------------------
# Blender UI
#--------------------

# Addon preferences, they are visible in the Users Preferences Addons page,
# under the Urho exporter addon row
class UrhoAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    outputPath : StringProperty(
            name = "Default export path",
            description = "Default path where to export",
            default = "", 
            maxlen = 1024,
            subtype = "DIR_PATH")

    modelsPath : StringProperty(
            name = "Default Models subpath",
            description = "Models subpath (relative to output)",
            default = "Models")
    animationsPath : StringProperty(
            name = "Default Animations subpath",
            description = "Animations subpath (relative to output)",
            default = "Models")
    materialsPath : StringProperty(
            name = "Default Materials subpath",
            description = "Materials subpath (relative to output)",
            default = "Materials")
    techniquesPath : StringProperty(
            name = "Default Techniques subpath",
            description = "Techniques subpath (relative to output)",
            default = "Techniques")
    texturesPath : StringProperty(
            name = "Default Textures subpath",
            description = "Textures subpath (relative to output)",
            default = "Textures")
    objectsPath : StringProperty(
            name = "Default Objects subpath",
            description = "Objects subpath (relative to output)",
            default = "Objects")
    scenesPath : StringProperty(
            name = "Default Scenes subpath",
            description = "Scenes subpath (relative to output)",
            default = "Scenes")

    bonesPerGeometry : IntProperty(
            name = "Per geometry",
            description = "Max numbers of bones per geometry",
            min = 64, max = 2048,
            default = 64)
    bonesPerVertex : IntProperty(
            name = "Per vertex",
            description = "Max numbers of bones per vertex",
            min = 4, max = 256,
            default = 4)

    reportWidth : IntProperty(
            name = "Window width",
            description = "Width of the report window",
            default = 500)

    maxMessagesCount : IntProperty(
            name = "Max number of messages",
            description = "Max number of messages in the report window",
            default = 500)
            
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "outputPath")
        layout.prop(self, "modelsPath")
        layout.prop(self, "animationsPath")
        layout.prop(self, "materialsPath")
        layout.prop(self, "techniquesPath")
        layout.prop(self, "texturesPath")
        layout.prop(self, "objectsPath")
        layout.prop(self, "scenesPath")
        row = layout.row()
        row.label(text="Max number of bones:")
        row.prop(self, "bonesPerGeometry")
        row.prop(self, "bonesPerVertex")
        row = layout.row()
        row.label(text="Report window:")
        row.prop(self, "reportWidth")
        row.prop(self, "maxMessagesCount")


##############################################
##              USER-DATA-LIST
##############################################
class KeyValue(bpy.types.PropertyGroup):
    key : bpy.props.StringProperty(name="key",default="key")
    value : bpy.props.StringProperty(name="value",default="value")

class UL_URHO_LIST_USERDATA(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):

        # We could write some code to decide which icon to use here...
        if item.key.lower()=="tag":
            custom_icon = 'EVENT_T'
        else:
            custom_icon = 'TEXT'

        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
#            layout.label(item.key, icon = custom_icon)
 #           layout.label(item.value)
            layout.prop(item,"key",  icon=custom_icon,text="")
            layout.prop(item,"value",text="")

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


BUTTON_MAPPING={}


class UL_URHO_LIST_CREATE_GENERIC(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_button.generic"
    bl_label = "Add a new item"

    typeName : bpy.props.StringProperty()
    objectName : bpy.props.StringProperty(default="")

    def execute(self, context):
        global BUTTON_MAPPING
        BUTTON_MAPPING[self.typeName](self,context)
        return{'FINISHED'}



class UL_URHO_LIST_ITEM_USERDATA(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_keyvalue.new_item"
    bl_label = "Add a new item"

    def execute(self, context):
        context.active_object.user_data.add()

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_USERDATA(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_keyvalue.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object.user_data

    def execute(self, context):
        kv_list = context.active_object.user_data
        index = context.active_object.list_index_userdata

        kv_list.remove(index)
        context.active_object.list_index_userdata = min(max(0, index - 1), len(kv_list) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_USERDATA(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_keyvalue.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object.user_data

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.list_index_userdata
        list_length = len(bpy.context.active_object.user_data) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.list_index_userdata = max(0, min(new_index, list_length))

    def execute(self, context):
        kv_list = context.active_object.user_data
        index = context.active_object.list_index_userdata

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        kv_list.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}

##############################################
##              LIST - NODETREES
##############################################
##TODO: Try to unify the list handling (userdata,nodetree) 

def poll_component_nodetree(self,object):
    return object.bl_idname=="urho3dcomponents"

def poll_material_nodetree(self,object):
    return object.bl_idname=="urho3dmaterials"


class NodetreeInfo(bpy.types.PropertyGroup):
    nodetreePointer : bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_component_nodetree)

class UL_URHO_LIST_NODETREE(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        custom_icon = 'NODETREE'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.05)
            c = split.column()
            c.label(text="")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            #c.prop_search(item,"nodetreeName",bpy.data,"node_groups",text="")
            c.prop(item,"nodetreePointer")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_NODETREE(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_nodetrees.new_item"
    bl_label = "Add a new item"


    def execute(self, context):
        context.active_object.nodetrees.add()

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_NODETREE(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_nodetrees.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object.nodetrees

    def execute(self, context):
        currentlist = context.active_object.nodetrees
        index = context.active_object.list_index_nodetrees

        currentlist.remove(index)
        context.active_object.list_index_nodetrees = min(max(0, index - 1), len(currentlist) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_NODETREE(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_nodetrees.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object.nodetrees

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.list_index_nodetrees
        list_length = len(bpy.context.active_object.nodetrees) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.list_index_nodetrees = max(0, min(new_index, list_length))

    def execute(self, context):
        currentlist = context.active_object.nodetrees
        index = context.active_object.list_index_nodetrees

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}

##############################################
##              LIST - MATERIAL NODETREES
##############################################
##TODO: Try to unify the list handling (userdata,nodetree) 

class MaterialNodetreeInfo(bpy.types.PropertyGroup):
    nodetreePointer : bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_material_nodetree)

## TODO: this is actually unnecessary (same as for logic nodetrees)
class UL_URHO_LIST_MATERIAL_NODETREE(bpy.types.UIList):
    """KeyValue UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        custom_icon = 'NODETREE'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.05)
            c = split.column()
            c.label(text="")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            #c.prop_search(item,"nodetreeName",bpy.data,"node_groups",text="")
            c.prop(item,"nodetreePointer")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_MATERIAL_NODETREE(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_material_nodetrees.new_item"
    bl_label = "Add a new item"


    def execute(self, context):
        context.active_object.data.materialNodetrees.add()

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_MATERIAL_NODETREE(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_material_nodetrees.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object.data.materialNodetrees

    def execute(self, context):
        currentlist = context.active_object.data.materialNodetrees
        index = context.active_object.data.list_index_nodetrees

        currentlist.remove(index)
        
        context.active_object.data.list_index_nodetrees = min(max(0, index - 1), len(currentlist) - 1)
        bpy.context.active_object.active_material_index = context.active_object.data.list_index_nodetrees
        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_MATERIAL_NODETREE(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_material_nodetrees.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object.data.materialNodetrees

    def move_index(self):
        """ Move  """

        index = bpy.context.active_object.data.list_index_nodetrees
        list_length = len(bpy.context.active_object.data.materialNodetrees) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        bpy.context.active_object.data.list_index_nodetrees = max(0, min(new_index, list_length))
        bpy.context.active_object.active_material_index = bpy.context.active_object.data.list_index_nodetrees        

    def execute(self, context):
        currentlist = context.active_object.data.materialNodetrees
        index = context.active_object.data.list_index_nodetrees

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}



##############################################
##              LIST - LODS
##############################################
##TODO: Try to unify the list handling (userdata,nodetree,lods) 

def nextLodSetIDX():
    new_idx = bpy.data.worlds[0].lodset_counter + 1
    bpy.data.worlds[0].lodset_counter = new_idx
    return new_idx
    
# button-logic used within the generic-button
def OpCreateLodSet(self,context):
    lodset = bpy.data.worlds[0].lodsets.add()
    lodset.lodset_id = nextLodSetIDX()
    lodset.name="new-lodset "+str(lodset.lodset_id)
    bpy.context.active_object.lodsetID=lodset.lodset_id

BUTTON_MAPPING["create_lodset"]=OpCreateLodSet

# button-logic used within the generic-button
def OpDeleteLodSet(self,context):
    idx = getLodSetWithID(bpy.context.active_object.lodsetID,True)
    lodset = bpy.data.worlds[0].lodsets.remove(idx)

BUTTON_MAPPING["delete_lodset"]=OpDeleteLodSet


## make sure to keep the lodsetID to set selected object


def getLodSetName(self):
    # print("get")
    if self.lodsetID == -1:
        return ""

    lodset = getLodSetWithID(self.lodsetID)

    if lodset:
        return lodset.name
    else:
        return ""

def setLodSetName(self,value):
    if value == "":
        #print("RESETID")
        self.lodsetID = -1
    else:
        #print("set %s=%s" % (self.name, str(value) ))
        for lodset in bpy.data.worlds[0].lodsets:
            if lodset.name == value:
                self.lodsetID = lodset.lodset_id
                return

        self.lodsetID = -1
        #print("assigned ID %s" % getID(nodetree))            
            
def updateLodSetName(self,ctx):
    pass
## make sure the actual name of the lodset is unique
def lodsetNameExists(name):
    for lodset in bpy.data.worlds[0].lodsets:
        if lodset.name == name:
            return True
    return False

def getLodSetDataName(self):
    return self.name

def setLodSetDataName(self,value):
    while lodsetNameExists(value):
        value = value + "_"
    self.lodset_name = value

## -- DATA OBJECTS --
class LODData(bpy.types.PropertyGroup):
    #meshName = bpy.props.StringProperty(get=getMeshName,set=setMeshName,update=updateMeshName)
    #meshID = bpy.props.IntProperty()
    meshObj : bpy.props.PointerProperty(type=bpy.types.Mesh)
    distance : bpy.props.IntProperty(name="distance")
    decimate : bpy.props.FloatProperty(name="decimateFactor",default=1.0,precision=3,max=1.0,min=0.0)


def armature_object_poll(self,object):
    return object.type=="ARMATURE"

class LODSet(bpy.types.PropertyGroup):
    lodset_id : bpy.props.IntProperty()
    name : bpy.props.StringProperty(default="lodset")
    lodset_name : bpy.props.StringProperty(default="lodset",get=getLodSetDataName,set=setLodSetDataName)
    lods : bpy.props.CollectionProperty(type=LODData)
    lods_idx : bpy.props.IntProperty()
    armatureObj :  bpy.props.PointerProperty(type=bpy.types.Object,poll=armature_object_poll)
        

## -- VISUALS --
class UL_LODSet(bpy.types.UIList):
    """LODSet List"""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):
        
        custom_icon = 'MESH'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.label(item,"lodset_Name")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(item,"lodset_Name")


class UL_URHO_LIST_LOD(bpy.types.UIList):
    """LOD UIList."""

    def draw_item(self, context, layout, data, item, icon, active_data,active_propname, index):

        # We could write some code to decide which icon to use here...
        #if item.key.lower()=="tag":
        #    custom_icon = 'INLINK'
        #else:
        #    custom_icon = 'TEXT'
        
        custom_icon = 'MESH'
        # Make sure your code supports all 3 layout types
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            #layout.prop_search(item,"meshName",bpy.data,"meshes","Mesh")
            c = layout.column()
            row = c.row()
            split = row.split(factor=0.5)
            c = split.column()
            c.prop(item,"meshObj")

            split = split.split()
            c= split.column()
            #layout.label(item.nodetreeName, icon = custom_icon)
            c.prop(item,"distance")
            c = split.column()
            if (data.armatureObj):
                c.enabled=False
            c.prop(item,"decimate")


          #  layout.prop(item,"meshObj")
          #  layout.prop(item,"distance")
            ## todo: make this smaller
           # layout.prop(item,"decimate",text="")
            if item.meshObj:
                layout.operator("urho.selectmesh",icon="RESTRICT_SELECT_OFF",text="").meshname=item.meshObj.name

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon = custom_icon)


class UL_URHO_LIST_ITEM_LOD(bpy.types.Operator):
    """Add a new item to the list."""

    bl_idname = "urho_lod.new_item"
    bl_label = "Add a new item"

    def execute(self, context):
        lodset = getLodSetWithID(context.active_object.lodsetID)
        
        if lodset:
            lodset.lods.add()
        else:
            pass

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_DEL_LOD(bpy.types.Operator):
    """Delete the selected item from the list."""

    bl_idname = "urho_lod.delete_item"
    bl_label = "Deletes an item"

    @classmethod
    def poll(cls, context):
        return context.active_object.lodsetID

    def execute(self, context):
        lodset = getLodSetWithID(context.active_object.lodsetID)
        currentlist = lodset.lods
        index = lodset.lods_idx

        currentlist.remove(index)
        lodset.lods_idx = min(max(0, index - 1), len(currentlist) - 1)

        return{'FINISHED'}


class UL_URHO_LIST_ITEM_MOVE_LOD(bpy.types.Operator):
    """Move an item in the list."""

    bl_idname = "urho_lod.move_item"
    bl_label = "Move an item in the list"

    direction : bpy.props.EnumProperty(items=(('UP', 'Up', ""),
                                              ('DOWN', 'Down', ""),))

    @classmethod
    def poll(cls, context):
        return context.active_object.lodsetID

    def move_index(self):
        """ Move  """

        lodset = getLodSetWithID(bpy.context.active_object.lodsetID)
        index = lodset.lods_idx
        currentlist = lodset.lods
        list_length = len(currentlist) - 1  # (index starts at 0)
        new_index = index + (-1 if self.direction == 'UP' else 1)

        lodset.lods_idx = max(0, min(new_index, list_length))

    def execute(self, context):
        lodset = getLodSetWithID(bpy.context.active_object.lodsetID)
        currentlist = lodset.lods
        index = lodset.lods_idx

        neighbor = index + (-1 if self.direction == 'UP' else 1)
        currentlist.move(neighbor, index)
        self.move_index()

        return{'FINISHED'}


##################################################
##
##################################################


# Here we define all the UI objects to be added in the export panel
class UrhoExportSettings(bpy.types.PropertyGroup):

    # This is called each time a property (created with the parameter 'update')
    # changes its value
    def update_func(self, context):
        # Avoid infinite recursion
        if self.updatingProperties:
            return
        self.updatingProperties = True

        # Save preferred output path
        addonPrefs = context.preferences.addons[__name__].preferences
        if self.outputPath:
            addonPrefs.outputPath = self.outputPath
        # Skeleton implies weights    
        if self.skeletons:
            self.geometryWei = True
            self.objAnimations = False
        else:
            self.geometryWei = False
            self.animations = False
        # Use Fcurves only for actions
        if not ('ACTION' in self.animationSource):
            self.actionsByFcurves = False
        # Morphs need geometries    
        if not self.geometries:
            self.morphs = False
        # Tangent needs position, normal and UV
        if not self.geometryPos or not self.geometryNor or not self.geometryUV:
            self.geometryTan = False
        # Morph normal needs geometry normal
        if not self.geometryNor:
            self.morphNor = False
        # Morph tangent needs geometry tangent
        if not self.geometryTan:
            self.morphTan = False
        # Morph tangent needs normal
        if not self.morphNor:
            self.morphTan = False
        # Select errors and merge are incompatible
        if self.selectErrors:
            self.merge = False
            
        self.updatingProperties = False

    def update_func2(self, context):
        if self.updatingProperties:
            return
        self.updatingProperties = True
        # Select errors and merge are incompatible
        if self.merge:
            self.selectErrors = False

        self.updatingProperties = False

    def update_subfolders(self, context):
        # Move folders between the output path and the subfolders
        # (this should have been done with operators)
        if self.updatingProperties:
            return
        self.updatingProperties = True
        if self.addDir:
            # Move the last folder from the output path to the subfolders
            self.addDir = False
            last = os.path.basename(os.path.normpath(self.outputPath))
            ilast = self.outputPath.rindex(last)
            if last and ilast >= 0:
                self.outputPath = self.outputPath[:ilast]
                self.modelsPath = os.path.join(last, self.modelsPath)
                self.animationsPath = os.path.join(last, self.animationsPath)
                self.materialsPath = os.path.join(last, self.materialsPath)
                self.techniquesPath = os.path.join(last, self.techniquesPath)
                self.texturesPath = os.path.join(last, self.texturesPath)
                self.objectsPath = os.path.join(last, self.objectsPath)
                self.scenesPath = os.path.join(last, self.scenesPath)
        if self.removeDir:
            # Move the first common folder from the subfolders to the output path
            self.removeDir = False
            ifirst = self.modelsPath.find(os.path.sep) + 1
            first = self.modelsPath[:ifirst]
            if first and \
               self.animationsPath.startswith(first) and \
               self.materialsPath.startswith(first) and \
               self.techniquesPath.startswith(first) and \
               self.texturesPath.startswith(first) and \
               self.objectsPath.startswith(first) and \
               self.scenesPath.startswith(first):
                self.outputPath = os.path.join(self.outputPath, first)
                self.modelsPath = self.modelsPath[ifirst:]
                self.animationsPath = self.animationsPath[ifirst:]
                self.materialsPath = self.materialsPath[ifirst:]
                self.techniquesPath = self.techniquesPath[ifirst:]
                self.texturesPath = self.texturesPath[ifirst:]
                self.objectsPath = self.objectsPath[ifirst:]
                self.scenesPath = self.scenesPath[ifirst:]
        if self.addSceneDir:
            # Append the scene name to the subfolders
            self.addSceneDir = False
            sceneName = context.scene.name
            last = os.path.basename(os.path.normpath(self.modelsPath))
            if sceneName != last:
                self.modelsPath = os.path.join(self.modelsPath, sceneName)
                self.animationsPath = os.path.join(self.animationsPath, sceneName)
                self.materialsPath = os.path.join(self.materialsPath, sceneName)
                self.techniquesPath = os.path.join(self.techniquesPath, sceneName)
                self.texturesPath = os.path.join(self.texturesPath, sceneName)
                self.objectsPath = os.path.join(self.objectsPath, sceneName)
                self.scenesPath = os.path.join(self.scenesPath, sceneName)
        self.updatingProperties = False

    def errors_update_func(self, context):
        if self.updatingProperties:
            return
        self.updatingProperties = True
        errorName = self.errorsEnum
        self.errorsEnum = 'NONE'
        self.updatingProperties = False
        selectErrors(context, self.errorsMem, errorName)
        
    def errors_items_func(self, context):
        items = [('NONE', "", ""),
                 ('ALL',  "all", "")]
        for error in self.errorsMem.Names():
            items.append( (error, error, "") )
        return items

    # Revert all the export settings back to their default values
    def reset(self, context): 
        
        addonPrefs = context.preferences.addons[__name__].preferences

        self.updatingProperties = False

        self.minimize = False
        self.onlyErrors = False
        self.showDirs = False

        self.useSubDirs = True
        self.fileOverwrite = False

        self.source = 'ALL'
        self.scale = 1.0
        self.modifiers = False
        self.modifiersRes = 'PREVIEW'
        self.origin = 'LOCAL'
        self.selectErrors = True
        self.forceElements = False
        self.merge = False
        self.mergeNotMaterials = False
        self.geometrySplit = False
        self.lods = False
        self.strictLods = True
        self.optimizeIndices = False

        self.skeletons = False
        self.onlyKeyedBones = False
        self.onlyDeformBones = False
        self.onlyVisibleBones = False
        self.actionsByFcurves = False
        self.parentBoneSkinning = False
        self.derigify = False
        self.clampBoundingBox = False

        self.animations = False
        self.objAnimations = False
        self.animationSource = 'USED_ACTIONS'
        self.animationExtraFrame = True
        self.animationTriggers = False
        self.animationRatioTriggers = False
        self.animationPos = True
        self.animationRot = True
        self.animationSca = False
        self.filterSingleKeyFrames = False

        self.geometries = True
        self.geometryPos = True
        self.geometryNor = True
        self.geometryCol = False
        self.geometryColAlpha = False
        self.geometryUV = False
        self.geometryUV2 = False
        self.geometryTan = False
        self.geometryWei = False

        self.morphs = False
        self.morphNor = True
        self.morphTan = False

        self.materials = False
        self.materialsList = False
        self.textures = False

        self.prefabs = True
        self.individualPrefab = False
        self.collectivePrefab = False
        self.scenePrefab = False
        self.trasfObjects = False
        self.physics = 'INDIVIDUAL'
        self.shape = 'TRIANGLEMESH'

    # Revert the output paths back to their default values
    def reset_paths(self, context, forced):

        addonPrefs = context.preferences.addons[__name__].preferences

        if forced or (not self.outputPath and addonPrefs.outputPath):
            self.outputPath = addonPrefs.outputPath

        if forced or (not self.modelsPath and addonPrefs.modelsPath):
            self.modelsPath = addonPrefs.modelsPath
            self.animationsPath = addonPrefs.animationsPath
            self.materialsPath = addonPrefs.materialsPath
            self.techniquesPath = addonPrefs.techniquesPath
            self.texturesPath = addonPrefs.texturesPath
            self.objectsPath = addonPrefs.objectsPath
            self.scenesPath = addonPrefs.scenesPath

    # --- Accessory ---

    updatingProperties : BoolProperty(default = False)

    minimize : BoolProperty(
            name = "Minimize",
            description = "Minimize the export panel",
            default = False)

    onlyErrors : BoolProperty(
            name = "Log errors",
            description = "Show only warnings and errors in the log",
            default = False)

    showLog : BoolProperty(
            name = "Show Log after export",
            description = "Show log after export",
            default = True)            

    showDirs : BoolProperty(
            name = "Show dirs",
            description = "Show the dirs list",
            default = False)

    addDir : BoolProperty(
            name = "Output folder to subfolders",
            description = "Move the last output folder to the subfolders",
            default = False,
            update = update_subfolders)

    removeDir : BoolProperty(
            name = "Subfolders to output folder",
            description = "Move a common subfolder to the output folder",
            default = False,
            update = update_subfolders)

    addSceneDir : BoolProperty(
            name = "Scene to subfolders",
            description = "Append the scene name to the subfolders",
            default = False,
            update = update_subfolders)

    # --- RUNTIME SETTINGS ---
    useRuntime : BoolProperty(
            name = "Use Urho3d runtime",
            description = "Start an external urho3d runtime. e.g. your game",
            default = False)

    runtimeBlocking : BoolProperty(
            name = "Block Blender while running",
            description = "Block Blender while running",
            default = False)            

    runtimeFile : bpy.props.StringProperty(
                    name="Runtime",
                    description="Path of the urho3d runtime",
                    maxlen = 512,
                    default = "",
                    subtype='FILE_PATH')
    runtimeWorkingDir : bpy.props.StringProperty(
                    name="Runtime WorkingDir",
                    description="WorkingDir",
                    maxlen = 512,
                    default = "",
                    subtype='FILE_PATH')

    runtimeFlags : bpy.props.StringProperty(
                    name="runtime flags",
                    description="Runtime Flags that get passed to the 'runtimeflags' argument and can be processed in your runtime",
                    maxlen = 512,
                    default = "")

    runtimeExportComponents : bpy.props.StringProperty(
                    name="component export file",
                    description="Override component export-file (default: ./urho3d_components.json)",
                    maxlen = 512,
                    subtype = "FILE_PATH")   


    # --- Output settings ---
    
    outputPath : StringProperty(
            name = "",
            description = "Path where to export",
            default = "", 
            maxlen = 1024,
            subtype = "DIR_PATH",
            update = update_func)   

    useSubDirs : BoolProperty(
            name = "Use sub folders",
            description = "Use sub folders inside the output folder (Materials, Models, Textures ...)",
            default = True)

    modelsPath : StringProperty(
            name = "Models",
            description = "Models subpath (relative to output)")
    animationsPath : StringProperty(
            name = "Animations",
            description = "Animations subpath (relative to output)")
    materialsPath : StringProperty(
            name = "Materials",
            description = "Materials subpath (relative to output)")
    techniquesPath : StringProperty(
            name = "Techniques",
            description = "Techniques subpath (relative to output)")
    texturesPath : StringProperty(
            name = "Textures",
            description = "Textures subpath (relative to output)")
    objectsPath : StringProperty(
            name = "Objects",
            description = "Objects subpath (relative to output)")
    scenesPath : StringProperty(
            name = "Scenes",
            description = "Scenes subpath (relative to output)")

    fileOverwrite : BoolProperty(
            name = "Files overwrite",
            description = "If enabled existing files are overwritten without warnings",
            default = True)

    # --- Source settings ---
            
    source : EnumProperty(
            name = "Source",
            description = "Objects to be exported",
            items=(('ALL', "All", "all the objects in the scene"),
                   ('ONLY_SELECTED', "Only selected", "only the selected objects in visible layers")),
            default='ALL')



    orientation : EnumProperty(
            name = "Front view",
            description = "Front view of the model",
            items = (('X_MINUS', "Left (--X +Z)", ""),
                     ('X_PLUS',  "Right (+X +Z)", ""),
                     ('Y_MINUS', "Front (--Y +Z)", ""),
                     ('Y_PLUS',  "Back (+Y +Z) *", ""),
                     ('Z_MINUS', "Bottom (--Z --Y)", ""),
                     ('Z_PLUS',  "Top (+Z +Y)", "")),
            default = 'X_PLUS')

    scale : FloatProperty(
            name = "Scale", 
            description = "Scale to apply on the exported objects", 
            default = 1.0,
            min = 0.0, 
            max = 1000.0,
            step = 10,
            precision = 1)

    modifiers : BoolProperty(
            name = "Apply modifiers",
            description = "Apply the object modifiers before exporting",
            default = False)

    modifiersRes : EnumProperty(
            name = "Modifiers setting",
            description = "Resolution setting to use while applying modifiers",
            items = (('PREVIEW', "Preview", "use the Preview resolution setting"),
                     ('RENDER', "Render", "use the Render resolution setting")),
            default = 'RENDER')

    origin : EnumProperty(
            name = "Mesh origin",
            description = "Origin for the position of vertices/bones",
            items=(('GLOBAL', "Global", "Blender's global origin"),
                   ('LOCAL', "Local", "object's local origin (orange dot)")),
            default = 'LOCAL')

    selectErrors : BoolProperty(
            name = "Select vertices with errors",
            description = "If a vertex has errors (e.g. invalid UV, missing UV or color or weights) select it",
            default = True,
            update = update_func)

    errorsMem = ErrorsMem()
    errorsEnum : EnumProperty(
            name = "",
            description = "List of errors",
            items = errors_items_func,
            update = errors_update_func)

    forceElements : BoolProperty(
            name = "Force missing elements",
            description = "If a vertex element (UV, color, weights) is missing add it with a zero value",
            default = False)

    ignoreHidden : BoolProperty(
            name = "Ignore hidden objects",
            description = "Ignore hidden objects",
            default = False)  

    wiredAsEmpty : BoolProperty(
            name = "Export wired MeshesNodes as empties",
            description = "MeshesNodes that are set to wired in ObjectPanel are exported as empties",
            default = False)                

    exportOnSave : BoolProperty(
            name = "Export Data on Save",
            description = "Export Data after Saving the blend",
            default = False)    

    exportGroupsAsObject : BoolProperty(
            name = "Export Instanced Collections as PrefabObject",
            description = "Export Collections as PrefabObject and write meta data into the group-instance-empties",
            default = False)   

    exportObjectCollectionAsTag   : BoolProperty(
            name = "add collections as tag",
            description = "Export object's collection containment as tag",
            default = True)                                                  

    merge : BoolProperty(
            name = "Merge objects",
            description = ("Merge all the objects in a single file, one common geometry for each material. "
                           "It uses the current object name."),
            default = False,
            update = update_func2)

    mergeNotMaterials : BoolProperty(
            name = "Don't merge materials",
            description = "Create a different geometry for each material of each object",
            default = False)

    geometrySplit : BoolProperty(
            name = "One vertex buffer per object",
            description = "Split each object into its own vertex buffer",
            default = False)

    lods : BoolProperty(
            name = "Use LODs",
            description = "Search for the LOD distance if the object name, objects with the same name are added as LODs",
            default = False)

    strictLods : BoolProperty(
            name = "Strict LODs",
            description = "Add a new vertex if the LOD0 does not contain a vertex with the exact same position, normal and UV",
            default = True)
            
    optimizeIndices : BoolProperty(
            name = "Optimize indices (slow)",
            description = "Linear-Speed vertex cache optimisation",
            default = True)

    # --- Components settings ---

    skeletons : BoolProperty(
            name = "Skeletons",
            description = "Export model armature bones",
            default = False,
            update = update_func)

    onlyKeyedBones : BoolProperty(
            name = "Only keyed bones",
            description = "In animinations export only bones with keys",
            default = False)

    onlyDeformBones : BoolProperty(
            name = "Only deform bones",
            description = "Don't export bones without Deform and its children",
            default = False,
            update = update_func2)
            
    onlyVisibleBones : BoolProperty(
            name = "Only visible bones",
            description = "Don't export bones not visible and its children",
            default = False,
            update = update_func2)

    actionsByFcurves : BoolProperty(
            name = "Read actions by Fcurves",
            description = "Should be much faster than updating the whole scene, usable only for Actions and for Quaternion rotations",
            default = False)

    derigify : BoolProperty(
            name = "Derigify",
            description = "Remove extra bones from Rigify armature",
            default = False,
            update = update_func)

    clampBoundingBox : BoolProperty(
            name = "Clamp bones bounding box",
            description = "Clamp each bone bounding box between bone head & tail. Use case: ragdoll, IK...",
            default = False)

    parentBoneSkinning : BoolProperty(
            name = "Use skinning for parent bones",
            description = "If an object has a parent of type BONE use a 100% skinning on its vertices "
                          "(use this only for a quick prototype)",
            default = False,
            update = update_func)

    animations : BoolProperty(
            name = "Animations",
            description = "Export bones animations (Skeletons needed)",
            default = False)

    objAnimations : BoolProperty(
            name = "of objects",
            description = "Export objects animations (without Skeletons)",
            default = False)

    animationSource : EnumProperty(
            name = "",
            items = (('ALL_ACTIONS', "All Actions", "Export all the actions in memory"),
                    ('CURRENT_ACTION', "Current Action", "Export the object's current action linked in the Dope Sheet editor"),
                    ('USED_ACTIONS', "Actions used in tracks", "Export only the actions used in NLA tracks"),
                    ('SELECTED_ACTIONS', "Selected Strips' Actions", "Export the actions of the current selected NLA strips"),
                    ('SELECTED_STRIPS', "Selected Strips", "Export the current selected NLA strips"),
                    ('SELECTED_TRACKS', "Selected Tracks", "Export the current selected NLA tracks"),
                    ('ALL_STRIPS', "All Strips", "Export all NLA strips"),
                    ('ALL_TRACKS', "All Tracks (not muted)", "Export all NLA tracks"),
                    ('TIMELINE', "Timelime", "Export the timeline (NLA tracks sum)")),
            default = 'USED_ACTIONS',
            update = update_func)

    animationExtraFrame : BoolProperty(
            name = "Ending extra frame",
            description = "In Blender to avoid pauses in a looping animation you normally want to skip the last frame "
                          "when it is the same as the first one. Urho needs this last frame, use this option to add it. "
                          "It is needed only when using the Timeline or Nla-Tracks.",
            default = True)

    animationTriggers : BoolProperty(
            name = "Export markers as triggers",
            description = "Export action pose markers (for actions, strips and tracks) or scene markers (for timeline) "
                          "as triggers, the time is expressed in seconds",
            default = False)

    animationRatioTriggers : BoolProperty(
            name = "Normalize time",
            description = "Export the time of triggers as a number from 0 (start) to 1 (end)",
            default = False)

    #---------------------------------

    animationPos : BoolProperty(
            name = "Position",
            description = "Within animations export bone positions",
            default = True)

    animationRot : BoolProperty(
            name = "Rotation",
            description = "Within animations export bone rotations",
            default = True)

    animationSca : BoolProperty(
            name = "Scale",
            description = "Within animations export bone scales",
            default = False)

    filterSingleKeyFrames : BoolProperty(
            name = "Remove single tracks",
            description = "Do not export tracks which contain only one keyframe, useful for layered animations",
            default = False)

    geometries : BoolProperty(
            name = "Geometries",
            description = "Export vertex buffers, index buffers, geometries, lods",
            default = True,
            update = update_func)

    geometryPos : BoolProperty(
            name = "Position",
            description = "Within geometry export vertex position",
            default = True,
            update = update_func)

    geometryNor : BoolProperty(
            name = "Normal",
            description = "Within geometry export vertex normal (enable 'Auto Smooth' to export custom normals)",
            default = True,
            update = update_func)

    geometryCol : BoolProperty(
            name = "Color",
            description = "Within geometry export vertex color",
            default = False)

    geometryColAlpha : BoolProperty(
            name = "Alpha",
            description = "Within geometry export vertex alpha (append _ALPHA to the color layer name)",
            default = False)

    geometryUV : BoolProperty(
            name = "UV",
            description = "Within geometry export vertex UV",
            default = False,
            update = update_func)

    geometryUV2 : BoolProperty(
            name = "UV2",
            description = "Within geometry export vertex UV2 (append _UV2 to the texture name)",
            default = False,
            update = update_func)

    geometryTan : BoolProperty(
            name = "Tangent",
            description = "Within geometry export vertex tangent (Position, Normal, UV needed)",
            default = False,
            update = update_func)

    geometryWei : BoolProperty(
            name = "Weights",
            description = "Within geometry export vertex bones weights (Skeletons needed)",
            default = False)

    morphs : BoolProperty(
            name = "Morphs (shape keys)",
            description = "Export vertex morphs (Geometries needed)",
            default = False)

    morphNor : BoolProperty(
            name = "Normal",
            description = "Within morph export vertex normal (Geometry Normal needed)",
            default = True,
            update = update_func)

    morphTan : BoolProperty(
            name = "Tangent",
            description = "Within morph export vertex tangent (Morph Normal, Geometry Tangent needed)",
            default = False,
            update = update_func)

    materials : BoolProperty(
            name = "Export materials",
            description = "Export XML materials",
            default = False,
            update = update_func)

    materialsList : BoolProperty(
            name = "Materials text list",
            description = "Write a txt file with the list of materials filenames",
            default = False)

    textures : BoolProperty(
            name = "Copy textures",
            description = "Copy diffuse textures",
            default = False,
            update = update_func)            

    prefabs : BoolProperty(
            name = "Export Urho Prefabs",
            description = "Export Urho3D XML objects (prefabs)",
            default = False,
            update = update_func)

    individualPrefab : BoolProperty(
            name = "Individual Prefabs",
            description = "Create one prefab per exported object (so if \"Merge objects\" option is checked, export one prefab for the merged object only)",
            default = False,
            update = update_func)

    individualPrefab_onlyRootObject : BoolProperty(
            name = "Only Root-Objects",
            description = "Only export individual ROOT objects and pack children recursively inside",
            default = True)


    collectivePrefab : BoolProperty(
            name = "One Collective",
            description = "Create one unic/global prefab containing every exported objects. An empty root node holds the objects.",
            default = False,
            update = update_func)

    scenePrefab : BoolProperty(
            name = "Scene Prefab",
            description = "Same content as 'Collective', but outputs a Urho3D xml scene (with Octree, PhysicsWorld and DebugRenderer)",
            default = False,
            update = update_func)

    trasfObjects : BoolProperty(
            name = "Transform objects",
            description = "Save objects position/rotation/scale, works only with 'Front View = Back'",
            default = True)

    export_userdata : BoolProperty(
            name = "Export Object Userdata",
            description = "Export the userdata of every object that have any specified in object-tab",
            default = True)

    physics : EnumProperty(
            name = "Physics",
            description = "Generate physics RigidBody(s) & Shape(s)",
            items = (('DISABLE', "No physics", "Do not create physics stuff"),
                        ('GLOBAL', "Global", "Create a unic RigidBody + Shape at the root. Expects a 'Physics.mdl' model as TriangleMesh."),
                        ('INDIVIDUAL', "Individual", "Create individual physics RigidBodies and Shapes")),
            default = 'DISABLE',
            update = update_func2)

    shapeItems = [ ('BOX', "Box", ""), ('CAPSULE', "Capsule", ""), ('CONE', "Cone", ""), \
                ('CONVEXHULL', "ConvexHull", ""), ('CYLINDER', "Cylinder", ""), ('SPHERE', "Sphere", ""), \
                ('STATICPLANE', "StaticPlane", ""), ('TRIANGLEMESH', "TriangleMesh", "") ]
    shape : EnumProperty(
            name = "CollisionShape",
            description = "CollisionShape type. Discarded if 'Collision Bounds' is checked in Physics panel.",
            items = shapeItems,
            default = 'TRIANGLEMESH',
            update = update_func2)

    meshnameDerivedBy : EnumProperty(
        name = "meshnameDerivedBy",
        description = "Meshname derived by",
        items=(('Object', "Object-Name", "The object's mesh gets the name of the node, which can result in duplicated meshes saved as different mesh-files"),
                ('Mesh', "Mesh-Name", "The object's mesh gets its name by the mesh preventing duplicated mesh-files")),
        default='Mesh')
        

    bonesGlobalOrigin : BoolProperty(name = "Bones global origin", default = False)
    actionsGlobalOrigin : BoolProperty(name = "Actions global origin", default = False)
    

# Reset settings button
class UrhoExportResetOperator(bpy.types.Operator):
    """ Reset export settings """

    bl_idname = "urho.exportreset"
    bl_label = "Revert settings to default"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.urho_exportsettings.reset(context)
        return {'FINISHED'}


# Reset output paths button
class UrhoExportResetPathsOperator(bpy.types.Operator):
    """ Reset paths """

    bl_idname = "urho.exportresetpaths"
    bl_label = "Revert paths to default"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_confirm(self, event)

    def execute(self, context):
        context.scene.urho_exportsettings.reset_paths(context, True)
        return {'FINISHED'}


# View log button
class UrhoReportDialog(bpy.types.Operator):
    """ View export log """
    
    bl_idname = "urho.report"
    bl_label = "Urho export report"
 
    def execute(self, context):
        return {'FINISHED'}
 
    def invoke(self, context, event):
        global logMaxCount
        wm = context.window_manager
        addonPrefs = context.preferences.addons[__name__].preferences
        logMaxCount = addonPrefs.maxMessagesCount
        return wm.invoke_props_dialog(self, width = addonPrefs.reportWidth)
        #return wm.invoke_popup(self, width = addonPrefs.reportWidth)
     
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        for line in logList:
            lines = line.split(":", 1)
            if lines[0] == 'CRITICAL':
                lineicon = 'LIGHT'
            elif lines[0] == 'ERROR':
                lineicon = 'CANCEL'
            elif lines[0] == 'WARNING':
                lineicon = 'ERROR'
            elif lines[0] == 'INFO':
                lineicon = 'INFO'
            else:
                lineicon = 'TEXT'
            layout.label(text = lines[1], icon = lineicon)


# Export button
class UrhoExportOperator(bpy.types.Operator):
    """ Start exporting """
    
    bl_idname = "urho.export"
    bl_label = "Export"
  
    def execute(self, context):
        ExecuteAddon(context, not bpy.context.scene.urho_exportsettings.showLog )
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)

# Export without report window
class UrhoExportCommandOperator(bpy.types.Operator):
    """ Start exporting """
    
    bl_idname = "urho.exportcommand"
    bl_label = "Export command"
  
    def execute(self, context):
        ExecuteAddon(context, silent=True)
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)

class UrhoExportSelectLodMesh(bpy.types.Operator):
    """ select mesh """

    bl_idname = "urho.selectmesh"
    bl_label = "Select mesh"
  
    meshname : bpy.props.StringProperty(default="")

    def execute(self, context):
        if self.meshname and self.meshname!="":
            context.object.data=bpy.data.meshes[self.meshname]
        return {'FINISHED'}
 
    def invoke(self, context, event):
        return self.execute(context)    

# Start runtime
class UrhoExportStartRuntime(bpy.types.Operator):
    ''' Start runtime '''
    bl_idname = "urho.start_runtime"
    bl_label = "Start Runtime"
    

    @classmethod
    def poll(self, context):
        return True

    def execute(self, context):
        scene = context.scene
        settings = scene.urho_exportsettings

        execpath = bpy.path.abspath(settings.runtimeFile)
        if execpath[0:2] in { "./", ".\\" }:
            pwd = os.path.dirname(bpy.app.binary_path)
            execpath = pwd + os.sep + execpath

        workingdir = bpy.path.abspath(settings.runtimeWorkingDir)

        processParams = []
        processParams.append(execpath)
        if workingdir != "":
            processParams.append("--workingdir")
            processParams.append(workingdir)

        exportComponentPath = settings.runtimeExportComponents
        if exportComponentPath != "":
            processParams.append("--componentexport")
            processParams.append(exportComponentPath)

        processParams.append("--scenename")
        processParams.append(bpy.context.scene.name+".xml")
        
##        parameters = " --workdir "+workingdir
        print("EXEC-DIR: %s" % execpath)
        print("WORKING-DIR: %s" % workingdir)
        print("PARAMS:%s" % processParams)
        # launch game
        try:
            subp = subprocess.Popen(processParams,  shell=False)
            print("\nLAUNCH RUNTIME: %s\n" % processParams)
            if settings.runtimeBlocking:
                subp.communicate() #like wait() but without the risk of deadlock with verbose output
            returnv = subp.returncode

            if returnv != 0:
                self.report({'ERROR'},"runtime exited anormally.")
                return {'CANCELLED'}

            self.report({'INFO'},"runtime exited normally.")
        except OSError as er:
            self.report({'ERROR'}, "Could not launch: " + execpath + ". In directory:" + workingdir+ ". Error: " + str(er))
            return {'CANCELLED'}

        return {'FINISHED'}

    def invoke(self, context, event):
        return self.execute(context)


# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportObjectPanel(bpy.types.Panel):
    
    bl_idname = "urho.exportobjectpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object


        currentCollection = bpy.context.collection
        if currentCollection:
            box = layout.box()
            box.label(text="Collection '%s'" % currentCollection.name)
            row = box.row()
            row.prop(currentCollection,"urhoExport",text="export as urho object")



        box = layout.box()
        row = box.label(text="Object Userdata")
        row = box.row()
        row.template_list("UL_URHO_LIST_USERDATA", "The_List", obj,
                          "user_data", obj, "list_index_userdata")

        row = box.row()
        row.operator('urho_keyvalue.new_item', text='NEW')
        row.operator('urho_keyvalue.delete_item', text='REMOVE')
        row.operator('urho_keyvalue.move_item', text='UP').direction = 'UP'
        row.operator('urho_keyvalue.move_item', text='DOWN').direction = 'DOWN'

        #row.prop(object,"exportNoMesh",text="NO mesh-export for object")




# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportMeshPanel(bpy.types.Panel):
    
    bl_idname = "urho.exportmeshpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object
        mesh = obj.data


        box = layout.box()
        row = box.row()


        row.prop_search(obj,"lodsetName",bpy.data.worlds[0],"lodsets")
        row = box.row()
        row.operator("urho_button.generic",text="new lodset").typeName="create_lodset"

        lodset = getLodSetWithID(obj.lodsetID)

        if lodset:
            row.operator("urho_button.generic",text="DELETE current").typeName="delete_lodset"
        

        if lodset:
            row = box.row()
            row.prop(lodset,"name")
            row = box.row();
            row = box.label(text="Lods")
            row = box.row()
            row.template_list("UL_URHO_LIST_LOD", "The_List", lodset,
                            "lods", lodset, "lods_idx")

            row = box.row()
            row.prop(lodset,"armatureObj")
            row = box.row()
            row.operator('urho_lod.new_item', text='NEW')
            row.operator('urho_lod.delete_item', text='REMOVE')
            row.operator('urho_lod.move_item', text='UP').direction = 'UP'
            row.operator('urho_lod.move_item', text='DOWN').direction = 'DOWN'
        
# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportScenePanel(bpy.types.Panel):
    
    bl_idname = "urho.exportscenepanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        obj = context.object

        box = layout.box()
        row = box.label(text="Userdata")
        row = box.row()
        row.prop(bpy.context.scene,"nodetree",text="Scene logic")


# The export panel, here we draw the panel using properties we have created earlier
class UrhoExportRenderPanel(bpy.types.Panel):
    
    bl_idname = "urho.exportrenderpanel"
    bl_label = "Urho export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    #bl_options = {'DEFAULT_CLOSED'}
    
    # Draw the export panel
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.urho_exportsettings

        row = layout.row()
        #row=layout.row(align=True)
        minimizeIcon = 'ZOOM_IN' if settings.minimize else 'ZOOM_OUT'
        row.prop(settings, "minimize", text="", icon=minimizeIcon, toggle=False)
        row.operator("urho.export", icon='EXPORT')
        #split = layout.split(percentage=0.1)
        if sys.platform.startswith('win'):
            row.operator("wm.console_toggle", text="", icon='CONSOLE')
        row.prop(settings, "onlyErrors", text="", icon='FORCE_WIND')
        row.operator("urho.report", text="", icon='TEXT')
        if settings.minimize:
            return

        
        row = layout.row()
        row.separator()
        row.separator()
        row.prop(settings,"showLog")    

        row = layout.row()
        row.prop(settings,"useRuntime")
        if (settings.useRuntime):
            box = layout.box()
            row = box.row()
            row.prop(settings,"runtimeFile")
            row = box.row()
            row.prop(settings,"runtimeWorkingDir",text="additional resource-dir")
            row = box.row()
            row.prop(settings,"runtimeFlags")            
            row = box.row()
            row.prop(settings,"runtimeExportComponents")  
            row = box.row()
            row.prop(settings,"runtimeBlocking")
            row = box.row()
            row.operator("urho.start_runtime",icon="GHOST_ENABLED")



        row = layout.row()
        row.label(text="Output:")


        box = layout.box()

        box.label(text="Output folder:")
        box.prop(settings, "outputPath")

        row = box.row()
        row.label(text="Modelname:")
        row.prop(settings, "meshnameDerivedBy", expand=True)

        box.prop(settings, "exportOnSave")
        box.prop(settings, "fileOverwrite")
        row = box.row()
        row.prop(settings, "useSubDirs")
        showDirsIcon = 'ZOOM_OUT' if settings.showDirs else 'ZOOM_IN'
        if settings.showDirs:
            subrow = row.row(align=True)
            subrow.prop(settings, "addDir", text="", icon='TRIA_DOWN_BAR')
            subrow.prop(settings, "removeDir", text="", icon='TRIA_UP_BAR')
            subrow.prop(settings, "addSceneDir", text="", icon='GROUP')
            subrow.operator("urho.exportresetpaths", text="", icon='LIBRARY_DATA_DIRECT')

        row.prop(settings, "showDirs", text="", icon=showDirsIcon, toggle=False)
        if settings.showDirs:
            dbox = box.box()
            dbox.prop(settings, "modelsPath")
            dbox.prop(settings, "animationsPath")
            dbox.prop(settings, "materialsPath")
            dbox.prop(settings, "techniquesPath")
            dbox.prop(settings, "texturesPath")
            dbox.prop(settings, "objectsPath")
            dbox.prop(settings, "scenesPath")

        row = layout.row()
        row.label(text="Settings:")
        row.operator("urho.exportreset", text="", icon='LIBRARY_DATA_DIRECT')
        
        box = layout.box()

        row = box.row()
        row.label(text="Objects:")
        row.prop(settings, "source", expand=True)

        row = box.row()
        row.label(text="Origin:")
        row.prop(settings, "origin", expand=True)

        box.prop(settings, "orientation")
        box.prop(settings, "scale")
        
        box.prop(settings, "modifiers")
        if settings.modifiers:
            row = box.row()
            row.separator()
            row.prop(settings, "modifiersRes", expand=True)

        box.prop(settings, "merge")
        if settings.merge:
            row = box.row()
            row.separator()
            row.prop(settings, "mergeNotMaterials")

        box.prop(settings,"ignoreHidden")
        box.prop(settings, "exportGroupsAsObject")
        box.prop(settings, "exportObjectCollectionAsTag")
        box.prop(settings,"wiredAsEmpty")

        row = box.row()
        row.prop(settings, "selectErrors")
        row.prop(settings, "errorsEnum")
        
        box.prop(settings, "forceElements")

        box.prop(settings, "geometrySplit")
        box.prop(settings, "optimizeIndices")
        box.prop(settings, "lods")
        if settings.lods:
            row = box.row()
            row.separator()
            row.prop(settings, "strictLods")

        box = layout.box()

        row = box.row()
        row.prop(settings, "skeletons")
        row.label(text="", icon='BONE_DATA')
        if settings.skeletons:
            row = box.row()
            row.separator()
            col = row.column()
            col.prop(settings, "derigify")
            #col.prop(settings, "bonesGlobalOrigin")
            #col.prop(settings, "actionsGlobalOrigin")
            col.prop(settings, "onlyDeformBones")
            col.prop(settings, "onlyVisibleBones")
            col.prop(settings, "parentBoneSkinning")
            col.prop(settings, "clampBoundingBox")

        row = box.row()
        column = row.column()
        column.enabled = settings.skeletons
        column.prop(settings, "animations")
        column = row.column()
        column.enabled = not settings.skeletons
        column.prop(settings, "objAnimations")
        row.label(text="", icon='ANIM_DATA')
        if (settings.skeletons and settings.animations) or settings.objAnimations:
            row = box.row()
            row.separator()
            column = row.column()
            column.prop(settings, "animationSource")
            column.prop(settings, "animationExtraFrame")
            column.prop(settings, "animationTriggers")
            if settings.animationTriggers:
                row = column.row()
                row.separator()
                row.prop(settings, "animationRatioTriggers")
            if settings.animations:
                column.prop(settings, "onlyKeyedBones")
            col = column.row()
            col.enabled = 'ACTION' in settings.animationSource
            col.prop(settings, "actionsByFcurves")
            row = column.row()
            row.prop(settings, "animationPos")
            row.prop(settings, "animationRot")
            row.prop(settings, "animationSca")
            column.prop(settings, "filterSingleKeyFrames")
        
        row = box.row()
        row.prop(settings, "geometries")
        row.label(text="", icon='MESH_DATA')
        if settings.geometries:
            row = box.row()
            row.separator()
            row.prop(settings, "geometryPos")
            row.prop(settings, "geometryNor")
            
            row = box.row()
            row.separator()
            row.prop(settings, "geometryUV")
            row.prop(settings, "geometryUV2")

            row = box.row()
            row.separator()
            col = row.column()
            col.enabled = settings.geometryPos and settings.geometryNor and settings.geometryUV
            col.prop(settings, "geometryTan")
            col = row.column()
            col.enabled = settings.skeletons
            col.prop(settings, "geometryWei")
            
            row = box.row()
            row.separator()
            row.prop(settings, "geometryCol")
            row.prop(settings, "geometryColAlpha")
        
        row = box.row()
        row.enabled = settings.geometries
        row.prop(settings, "morphs")
        row.label(text="", icon='SHAPEKEY_DATA')
        if settings.geometries and settings.morphs:
            row = box.row()
            row.separator()
            col = row.column()
            col.enabled = settings.geometryNor
            col.prop(settings, "morphNor")
            col = row.column()
            col.enabled = settings.morphNor and settings.geometryTan
            col.prop(settings, "morphTan")

        row = box.row()
        row.prop(settings, "materials")
        row.label(text="", icon='MATERIAL_DATA')
        if settings.materials:
            row = box.row()
            row.separator()
            row.prop(settings, "materialsList")

        row = box.row()
        row.prop(settings, "textures")
        row.label(text="", icon='TEXTURE_DATA')

        row = box.row()
        row.prop(settings, "prefabs")
        row.label(text="", icon='MOD_OCEAN')

        if settings.prefabs:
            row = box.row()
            row.separator()
            row.prop(settings, "individualPrefab")

            row.label(text="", icon='MOD_BUILD')

            if (settings.individualPrefab):
                row = box.row()
                row.separator()
                row.separator()
                row.prop(settings, "individualPrefab_onlyRootObject")



            if not settings.merge:
                row = box.row()
                row.separator()
                row.prop(settings, "collectivePrefab")
                row.label(text="", icon='URL')

            row = box.row()
            row.separator()
            row.prop(settings, "scenePrefab")
            row.label(text="", icon='WORLD')



            specialBox = box.box()
            row = specialBox.row()
            row.prop(settings, "trasfObjects")

            row = specialBox.row()
            row.prop(settings, "export_userdata")


            # row = specialBox.row()
            # # todo: make it possible to check if physics are used in component-nodes and otherwise take the default settings(!)
            # row.label(text="default physics settings are ignored for objects with component-nodes")

            # row = specialBox.row()
            # row.prop(settings, "physics")
            # row.label(text="", icon='PHYSICS')

            # row = specialBox.row()
            # row.prop(settings, "shape")
            # row.label(text="", icon='GROUP')

class UrhoExportNodetreePanel(bpy.types.Panel):
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_label = "Urho3d-Nodetree"
#    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        if bpy.context.active_object:
            obj = bpy.context.active_object

            layout = self.layout
            box = layout.box()
            row = box.label(text="Nodetrees:")

            innerBox = box.box()
            row = innerBox.row()
            row.prop(bpy.context.scene,"nodetree",text="Scene-Logic")

            ## object's nodetree-managment
            box = box.box()
            row = box.label(text="Component Nodetrees")

            row = layout.row()
            row.prop(bpy.data.worlds[0].jsonNodes,"autoSelectObjectNodetree",text="autoselect object's first nodetree")

            row = box.row()
            row.template_list("UL_URHO_LIST_NODETREE", "The_List", obj,
                            "nodetrees", obj, "list_index_nodetrees")

            row = box.row()
            row.operator('urho_nodetrees.new_item', text='NEW')
            row.operator('urho_nodetrees.delete_item', text='REMOVE')
            row.operator('urho_nodetrees.move_item', text='UP').direction = 'UP'
            row.operator('urho_nodetrees.move_item', text='DOWN').direction = 'DOWN'
            ####


            if bpy.context.active_object.type=="MESH":
                box = box.box()
                row = box.row()
                row.label(text="Material Nodetrees")
                #row.prop(bpy.context.active_object.data,"materialNodetree")
                row = box.row()
                row.template_list("UL_URHO_LIST_MATERIAL_NODETREE", "The_material_List", obj.data,
                "materialNodetrees", obj, "active_material_index")

                row = box.row()
                row.operator('urho_material_nodetrees.new_item', text='NEW')
                row.operator('urho_material_nodetrees.delete_item', text='REMOVE')
                # no movement of the materialtree-slots, as I dont know how to stabely swap the change in the mesh
                # maybe using blender's material operators: 
                #row.operator("object.material_slot_move", icon='TRIA_UP', text="").direction = 'UP'
                #row.operator("object.material_slot_move", icon='TRIA_DOWN', text="").direction = 'DOWN'                


                #row.operator('urho_material_nodetrees.move_item', text='UP').direction = 'UP'
                #row.operator('urho_material_nodetrees.move_item', text='DOWN').direction = 'DOWN'
                
                #bpy.ops.wm.read_homefile('INVOKE_DEFAULT')                

                if obj.mode == 'EDIT':
                    row = box.row(align=True)
                    row.operator("object.material_slot_assign", text="Assign")
                    row.operator("object.material_slot_select", text="Select")
                    row.operator("object.material_slot_deselect", text="Deselect")                



#--------------------
# Handlers
#--------------------

# Called after loading a new blend. Set the default path if the path edit box is empty.        
@persistent
def PostLoad(dummy):
    addonPrefs = bpy.context.preferences.addons[__name__].preferences
    settings = bpy.context.scene.urho_exportsettings
    settings.errorsMem.Clear()
    settings.updatingProperties = False
    settings.reset_paths(bpy.context, False)

@persistent
def PostSave(dummy):
    settings = bpy.context.scene.urho_exportsettings
    if settings.exportOnSave:
        print("AUTO EXPORT on SAVE")
        bpy.ops.urho.export()
    


#--------------------
# Register Unregister
#--------------------

# Called when the addon is enabled. Here we register out UI classes so they can be 
# used by Python scripts.

addon_keymaps = []

def register():
        # property hooks:
    def updateMaterialTreeName(self,ctx):
        if self.materialTreeId!=-1:
            ctx.space_data.node_tree = JSONNodetreeUtils.getNodetreeById(self.materialTreeId)
        else:
            ctx.space_data.node_tree = None

    def getMaterialTreeName(self):
        # print("get")
        if self.materialTreeId == -1:
            #print("No nodetree(%s)" % self.name)
            return ""
        
        nodetree = JSONNodetreeUtils.getNodetreeById(self.materialTreeId)
        if nodetree:
            return nodetree.name
        else:
            return ""

    def setMaterialTreeName(self,value):
        if value == "":
            #print("RESETID")
            self.materialTreeId = -1
        else:
            #print("set %s=%s" % (self.name, str(value) ))
            nodetree = bpy.data.node_groups[value]
            self.materialTreeId = JSONNodetreeUtils.getID(nodetree)
            #print("assigned ID %s" % getID(nodetree))


    ## SCENE-Node-Tree

        # property hooks:
    def updateSceneTreeName(self,ctx):
        if self.sceneTreeId!=-1:
            ctx.space_data.node_tree = JSONNodetreeUtils.getNodetreeById(self.sceneTreeId)
        else:
            ctx.space_data.node_tree = None

    def getSceneTreeName(self):
        # print("get")
        if self.sceneTreeId == -1:
            #print("No nodetree(%s)" % self.name)
            return ""
        
        nodetree = JSONNodetreeUtils.getNodetreeById(self.sceneTreeId)
        if nodetree:
            return nodetree.name
        else:
            return ""

    def setSceneTreeName(self,value):
        if value == "":
            #print("RESETID")
            self.sceneTreeId = -1
        else:
            #print("set %s=%s" % (self.name, str(value) ))
            nodetree = bpy.data.node_groups[value]
            self.sceneTreeId = JSONNodetreeUtils.getID(nodetree)
            #print("assigned ID %s" % getID(nodetree))            
            

    if DEBUG: print("Urho export register")
    
    #bpy.utils.register_module(__name__)
    


    bpy.utils.register_class(UrhoAddonPreferences)
    bpy.utils.register_class(UrhoExportSettings)
    bpy.utils.register_class(UrhoExportOperator)
    bpy.utils.register_class(UrhoExportSelectLodMesh)
    bpy.utils.register_class(UrhoExportCommandOperator)
    bpy.utils.register_class(UrhoExportResetOperator)
    bpy.utils.register_class(UrhoExportResetPathsOperator)
    bpy.utils.register_class(UrhoExportRenderPanel)
    bpy.utils.register_class(UrhoExportObjectPanel)
    bpy.utils.register_class(UrhoExportStartRuntime)
    
    bpy.utils.register_class(UrhoReportDialog)
    bpy.utils.register_class(KeyValue)
    
    bpy.utils.register_class(UL_URHO_LIST_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_USERDATA)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_USERDATA)
    
    
    bpy.utils.register_class(UL_URHO_LIST_CREATE_GENERIC)

    bpy.types.Scene.urho_exportsettings = bpy.props.PointerProperty(type=UrhoExportSettings)
    bpy.types.Scene.nodetree = bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_component_nodetree);

    bpy.types.Object.user_data = bpy.props.CollectionProperty(type=KeyValue)
    bpy.types.Object.list_index_userdata = IntProperty(name = "Index for key value list",default = 0)
    
    bpy.types.Mesh.ID = bpy.props.IntProperty(default=-1)
    #bpy.types.Mesh.IDNAME=bpy.props.StringProperty(get=getMeshName,set=setMeshName,update=updateMeshName)

    # lod
    bpy.utils.register_class(LODData)
    bpy.utils.register_class(LODSet)

    bpy.types.Object.ID = bpy.props.IntProperty(default=-1)
    bpy.types.Object.lodsetID = bpy.props.IntProperty()
    bpy.types.Object.lodsetName = bpy.props.StringProperty(get=getLodSetName,set=setLodSetName,update=updateLodSetName)
    bpy.types.World.lodsets=bpy.props.CollectionProperty(type=LODSet)
    bpy.types.World.lodset_counter=bpy.props.IntProperty()
    bpy.types.World.meshid_counter=bpy.props.IntProperty()
    bpy.types.World.objid_counter=bpy.props.IntProperty()
    bpy.types.Collection.urhoExport = bpy.props.BoolProperty(description="export as urho3d object")

    
    bpy.utils.register_class(UL_URHO_LIST_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_LOD)
    bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_LOD)    
    bpy.utils.register_class(UrhoExportMeshPanel)

    if IsJsonNodeAddonAvailable():
        bpy.utils.register_class(UrhoExportNodetreePanel)
        bpy.utils.register_class(UrhoExportScenePanel)

        bpy.utils.register_class(UL_URHO_LIST_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_NODETREE)
        bpy.utils.register_class(NodetreeInfo)
        bpy.types.Object.nodetrees = bpy.props.CollectionProperty(type=NodetreeInfo)
        bpy.types.Object.list_index_nodetrees = IntProperty(name = "Index for nodetree list",default = 0)


        bpy.utils.register_class(UL_URHO_LIST_MATERIAL_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_MATERIAL_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_DEL_MATERIAL_NODETREE)
        bpy.utils.register_class(UL_URHO_LIST_ITEM_MOVE_MATERIAL_NODETREE)
        bpy.utils.register_class(MaterialNodetreeInfo)
        bpy.types.Mesh.materialNodetrees = bpy.props.CollectionProperty(type=MaterialNodetreeInfo)
        bpy.types.Mesh.list_index_nodetrees = IntProperty(name = "Index for nodetree list",default = 0)

        #bpy.types.Mesh.materialNodetree=bpy.props.PointerProperty(type=bpy.types.NodeTree,poll=poll_material_nodetree)


        try:
            #print("Try to remove the default-nodetree-selector")
            import addon_jsonnodetree
            
            def customAutoSelection(current_obj,current_treetype,current_tree):
                # aprint("CUSTOM CHECK:%s %s %s" % (current_obj.name,current_treetype,current_tree))
                # check if we have at least one nodetree for this object
                if bpy.data.worlds[0].jsonNodes.autoSelectObjectNodetree:
                    if current_treetype=="urho3dcomponents":
                        if current_obj and len(current_obj.nodetrees)>0 and current_obj.nodetrees[0].nodetreePointer:
                            try:
                                autoNodetree = current_obj.nodetrees[0].nodetreePointer
                                return autoNodetree
                            except:
                                pass
                    elif current_treetype=="urho3dmaterials" and len(current_obj.data.materialNodetrees)>0:
                        if current_obj and current_obj.data and len(current_obj.data.materialNodetrees)>0:
                            try:
                                slot = current_obj.data.materialNodetrees[bpy.context.object.active_material_index]                                  
                                if slot.nodetreePointer:
                                    autoNodetree = slot.nodetreePointer
                                return autoNodetree
                            except:
                                pass                            
                    # dont show anything if in auto mode and no nodetree found
                    return "NOTREE"
                return None




            JSONNodetreeUtils.overrideAutoNodetree = customAutoSelection
            
            addon_jsonnodetree.unregisterSelectorPanel()
            bpy.utils.unregister_class(addon_jsonnodetree.NODE_PT_json_nodetree_select)
            print("ok!")
        except:
            print("did not work")


    

    #bpy.context.preferences.filepaths.use_relative_paths = False
    
    if not PostLoad in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(PostLoad)

    if not PostSave in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(PostSave)

    # handle the shortcuts
    wm = bpy.context.window_manager
    
    #km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    kmi = km.keymap_items.new("urho.start_runtime", 'A', 'PRESS', ctrl=True,shift=True)
    addon_keymaps.append(km)

    print("installed addons: %s" % bpy.context.preferences.addons.keys())

# Note: the script __init__.py is executed only the first time the addons is enabled. After that
# disabling or enabling the script will only call unregister() or register(). So in unregister()
# delete only objects created with register(), do not delete global objects as they will not be
# created re-enabling the addon.
# __init__.py is re-executed pressing F8 or randomly(?) enabling the addon.



# Called when the addon is disabled. Here we remove our UI classes.
def unregister():
    if DEBUG: print("Urho export unregister")
    
    #bpy.utils.unregister_module(__name__)

    bpy.utils.unregister_class(UrhoAddonPreferences)
    bpy.utils.unregister_class(UrhoExportSettings)
    bpy.utils.unregister_class(UrhoExportSelectLodMesh)
    bpy.utils.unregister_class(UrhoExportOperator)
    bpy.utils.unregister_class(UrhoExportCommandOperator)
    bpy.utils.unregister_class(UrhoExportResetOperator)
    bpy.utils.unregister_class(UrhoExportResetPathsOperator)  
    bpy.utils.unregister_class(UrhoExportStartRuntime)  
    try:
        bpy.utils.unregister_class(UrhoExportRenderPanel)
    except:
        pass
    try:
        bpy.utils.unregister_class(UrhoExportObjectPanel)
    except:
        pass

    bpy.utils.unregister_class(UL_URHO_LIST_CREATE_GENERIC)
    bpy.utils.unregister_class(UrhoReportDialog)
    bpy.utils.unregister_class(UL_URHO_LIST_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_USERDATA)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_USERDATA)
    

    bpy.utils.unregister_class(LODData)
    bpy.utils.unregister_class(LODSet)
    bpy.utils.unregister_class(UL_URHO_LIST_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_LOD)
    bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_LOD)
    bpy.utils.unregister_class(UrhoExportMeshPanel)

    
    del bpy.types.Scene.urho_exportsettings
    del bpy.types.Object.user_data
    
    if IsJsonNodeAddonAvailable():
        bpy.utils.unregister_class(UL_URHO_LIST_NODETREE)
        bpy.utils.unregister_class(UL_URHO_LIST_ITEM_NODETREE)
        bpy.utils.unregister_class(UL_URHO_LIST_ITEM_DEL_NODETREE)
        bpy.utils.unregister_class(UL_URHO_LIST_ITEM_MOVE_NODETREE)

        bpy.utils.unregister_class(UrhoExportNodetreePanel)
        bpy.utils.unregister_class(UrhoExportScenePanel)
        del bpy.types.Object.materialNodetree
        del bpy.types.Object.materialTreeId
        del bpy.types.Scene.nodetree
        del bpy.types.Scene.sceneTreeId
        del bpy.types.Collection.urhoExport


    if PostLoad in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(PostLoad)
    if PostSave in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(PostSave)

    #unregister keyboard shortcuts
    wm = bpy.context.window_manager
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    # clear the list
    addon_keymaps.clear()

#--------------------
# Blender UI utility
#--------------------

# Select vertices on a object
def selectVertices(context, objectName, indicesList, deselect):

    objects = context.scene.objects
    
    try:
        obj = objects[objectName]
    except KeyError:
        log.error( "Cannot select vertices on not found object {:s}".format(objectName) )
        return

    # Set the object as current
    #objects.active = obj
    context.view_layer.objects.active=obj
    # Enter Edit mode (check poll() to avoid exception)
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    # Deselect all
    if deselect and bpy.ops.mesh.select_all.poll():
        bpy.ops.mesh.select_all(action='DESELECT')
    # Save the current select mode
    sel_mode = bpy.context.tool_settings.mesh_select_mode
    # Set Vertex select mode
    bpy.context.tool_settings.mesh_select_mode = [True, False, False]
    # Exit Edit mode
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT', toggle=False)
    # Select the vertices
    mesh = obj.data
    for index in indicesList:
        try:
            mesh.vertices[index].select = True
        #except KeyError:
        except IndexError:
            pass
    # Back in Edit mode
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)
    # Restore old selection mode
    bpy.context.tool_settings.mesh_select_mode = sel_mode 

from collections import defaultdict

# Select vertices with errors
def selectErrors(context, errorsMem, errorName):
    names = errorsMem.Names()
    if errorName != 'ALL':
        names = [errorName]
    for i, name in enumerate(names):
        errors = errorsMem.Get(name)
        if not errors:
            continue
        indices = defaultdict(set)
        for mi, vi in errors:
            objectName = errorsMem.Second(mi)
            if objectName:
                indices[objectName].add(vi)
        for objectName, indicesSet in indices.items():
            count = len(indicesSet)
            if count:
                log.info( "Selecting {:d} vertices on {:s} with '{:s}' errors".format(count, objectName, name) )
                selectVertices(context, objectName, indicesSet, i == 0)


#-------------------------------------------------------------------------
# Export main
#-------------------------------------------------------------------------
    
def ExecuteUrhoExport(context):
    global logList

    # Check Blender version
    if bpy.app.version < (2, 70, 0):
        log.error( "Blender version 2.70 or later is required" )
        return False

    # Clear log list
    logList[:] = []
    
    # Get exporter UI settings
    settings = context.scene.urho_exportsettings

    # File utils options
    fOptions = FOptions()

    # List where to store tData (decomposed objects)
    tDataList = []
    # Decompose options
    tOptions = TOptions()

    # Scene export data
    uScene = UrhoScene(context.scene)
    # Scene export options
    sOptions = SOptions()
    
    # Addons preferences
    addonPrefs = context.preferences.addons[__name__].preferences
    
    # Copy from exporter UI settings to Decompose options
    tOptions.mergeObjects = settings.merge
    tOptions.mergeNotMaterials = settings.mergeNotMaterials
    tOptions.doForceElements = settings.forceElements
    tOptions.useLods = settings.lods
    tOptions.onlySelected = (settings.source == 'ONLY_SELECTED')
    tOptions.ignoreHidden = settings.ignoreHidden
    tOptions.scale = settings.scale
    tOptions.globalOrigin = (settings.origin == 'GLOBAL')
    tOptions.applyModifiers = settings.modifiers
    tOptions.applySettings = settings.modifiersRes
    tOptions.doBones = settings.skeletons
    tOptions.doOnlyKeyedBones = settings.onlyKeyedBones
    tOptions.doOnlyDeformBones = settings.onlyDeformBones
    tOptions.doOnlyVisibleBones = settings.onlyVisibleBones
    tOptions.actionsByFcurves = settings.actionsByFcurves
    tOptions.skinBoneParent = settings.parentBoneSkinning
    tOptions.derigifyArmature = settings.derigify
    tOptions.doAnimations = settings.animations
    tOptions.doObjAnimations = settings.objAnimations
    tOptions.doAllActions = (settings.animationSource == 'ALL_ACTIONS')
    tOptions.doCurrentAction = (settings.animationSource == 'CURRENT_ACTION')
    tOptions.doUsedActions = (settings.animationSource == 'USED_ACTIONS')
    tOptions.doSelectedActions = (settings.animationSource == 'SELECTED_ACTIONS')
    tOptions.doSelectedStrips = (settings.animationSource == 'SELECTED_STRIPS')
    tOptions.doSelectedTracks = (settings.animationSource == 'SELECTED_TRACKS')
    tOptions.doStrips = (settings.animationSource == 'ALL_STRIPS')
    tOptions.doTracks = (settings.animationSource == 'ALL_TRACKS')
    tOptions.doTimeline = (settings.animationSource == 'TIMELINE')
    tOptions.doTriggers = settings.animationTriggers
    tOptions.doAnimationExtraFrame = settings.animationExtraFrame
    tOptions.doAnimationPos = settings.animationPos
    tOptions.doAnimationRot = settings.animationRot
    tOptions.doAnimationSca = settings.animationSca
    tOptions.filterSingleKeyFrames = settings.filterSingleKeyFrames
    tOptions.doGeometries = settings.geometries
    tOptions.doGeometryPos = settings.geometryPos
    tOptions.doGeometryNor = settings.geometryNor
    tOptions.doGeometryCol = settings.geometryCol
    tOptions.doGeometryColAlpha = settings.geometryColAlpha
    tOptions.doGeometryUV  = settings.geometryUV
    tOptions.doGeometryUV2  = settings.geometryUV2
    tOptions.doGeometryTan = settings.geometryTan
    tOptions.doGeometryWei = settings.geometryWei
    tOptions.doMorphs = settings.morphs
    tOptions.doMorphNor = settings.morphNor
    tOptions.doMorphTan = settings.morphTan
    tOptions.doMorphUV = settings.morphTan
    tOptions.doOptimizeIndices = settings.optimizeIndices
    tOptions.doMaterials = settings.materials or settings.textures
    tOptions.bonesGlobalOrigin = settings.bonesGlobalOrigin
    tOptions.actionsGlobalOrigin = settings.actionsGlobalOrigin

    tOptions.orientation = None # ='Y_PLUS'
    if settings.orientation == 'X_PLUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(90.0))
    elif settings.orientation == 'X_MINUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(-90.0))
    elif settings.orientation == 'Y_MINUS':
        tOptions.orientation = Quaternion((0.0,0.0,1.0), radians(180.0))
    elif settings.orientation == 'Z_PLUS':
        tOptions.orientation = Quaternion((1.0,0.0,0.0), radians(-90.0)) * Quaternion((0.0,0.0,1.0), radians(180.0))
    elif settings.orientation == 'Z_MINUS':
        tOptions.orientation = Quaternion((1.0,0.0,0.0), radians(90.0)) * Quaternion((0.0,0.0,1.0), radians(180.0))

    sOptions.shapeItems = settings.shapeItems
    for shapeItems in settings.shapeItems:
        if shapeItems[0] == settings.shape:
            tOptions.shape = shapeItems[1]
            sOptions.shape = shapeItems[1]
            break
    tOptions.meshNameDerivedBy = settings.meshnameDerivedBy

    sOptions.mergeObjects = settings.merge
    sOptions.doIndividualPrefab = settings.individualPrefab
    sOptions.individualPrefab_onlyRootObject = settings.individualPrefab_onlyRootObject
    sOptions.doCollectivePrefab = settings.collectivePrefab
    sOptions.doScenePrefab = settings.scenePrefab
    sOptions.noPhysics = (settings.physics == 'DISABLE')
    sOptions.individualPhysics = (settings.physics == 'INDIVIDUAL')
    sOptions.wiredAsEmpty = settings.wiredAsEmpty
    sOptions.exportGroupsAsObject = settings.exportGroupsAsObject
    sOptions.exportObjectCollectionAsTag = settings.exportObjectCollectionAsTag
    sOptions.globalPhysics = (settings.physics == 'GLOBAL')
    sOptions.trasfObjects = settings.trasfObjects
    sOptions.exportUserdata = settings.export_userdata
    sOptions.globalOrigin = tOptions.globalOrigin
    sOptions.orientation = tOptions.orientation
    sOptions.objectsPath = settings.objectsPath

    fOptions.useSubDirs = settings.useSubDirs
    fOptions.fileOverwrite = settings.fileOverwrite
    fOptions.paths[PathType.ROOT] = settings.outputPath
    fOptions.paths[PathType.MODELS] = settings.modelsPath
    fOptions.paths[PathType.ANIMATIONS] = settings.animationsPath
    fOptions.paths[PathType.TRIGGERS] = settings.animationsPath
    fOptions.paths[PathType.MATERIALS] = settings.materialsPath
    fOptions.paths[PathType.TECHNIQUES] = settings.techniquesPath
    fOptions.paths[PathType.TEXTURES] = settings.texturesPath
    fOptions.paths[PathType.MATLIST] = settings.modelsPath
    fOptions.paths[PathType.OBJECTS] = settings.objectsPath
    fOptions.paths[PathType.SCENES] = settings.scenesPath

    settings.errorsMem.Clear()

    if settings.onlyErrors:
        log.setLevel(logging.WARNING)
    else:
        log.setLevel(logging.DEBUG)

    if not settings.outputPath:
        log.error( "Output path is not set" )
        return False

    if tOptions.mergeObjects and not tOptions.globalOrigin:
        log.warning("To merge objects you should use Origin = Global")

    # create dummy objects to each lodset
    print("LODSETS:\n");
    for lodset in bpy.data.worlds[0].lodsets:
        firstLOD = True
        for lod in lodset.lods:
            if not lod.meshObj:
                print("NO MESH for %s lod-distance:%s" % (lodset.name,lod.distance) );
                continue
            new_objname = "%s_LOD%s" % (lodset.name,str(lod.distance).zfill(3))
            lodmesh = lod.meshObj
            #new_obj = bpy.data.objects.new(name=new_objname,object_data=lodmesh)
            new_obj = None
            if lodset.armatureObj and lodset.armatureObj.name!="":
                ## todo: make sure this is mesh and make sure to really duplicate everything...!? (sense?)
                armaObj = lodset.armatureObj
                firstChild = armaObj.children[0]
                
                new_obj = firstChild.copy()
                new_obj.name = new_objname 
                new_obj.data = lodmesh
                new_obj.animation_data_clear()
                new_obj.parent = None
                new_obj.location = armaObj.location
                # TODO: Check if you this assuption is true. (Quaternion or else Euler)
                if armaObj.rotation_mode=="QUATERNION":
                    new_obj.rotation_quaternion = armaObj.rotation_quaternion
                else:
                    new_obj.rotation_euler = armaObj.rotation_euler
                new_obj.scale = armaObj.scale                

                #scn.objects.link(new_obj)
            if not new_obj:
                new_obj = bpy.data.objects.new(name=new_objname,object_data=lodmesh)

            ## mark this object to be temporary lodset object (used to assure applyModifier)
            new_obj.lodsetID=-2
            # check if this lodset has an armature set
            if lodset.armatureObj and firstLOD:
                # create an armature-modifier for the lod-export to export this arma as well
                arma_mod = new_obj.modifiers.new(name="__lod_armature", type="ARMATURE")
                
                # set the arma
                arma_mod.object=lodset.armatureObj
            
            # add decimate-modifier if the decimate was < 1.0
            if lod.decimate < 1.0 and not lodset.armatureObj:
                decimate = new_obj.modifiers.new(name="__decimate",type="DECIMATE")
                decimate.ratio = lod.decimate

            firstLOD = False
            tempObjects.append(new_obj)
            bpy.context.scene.collection.objects.link(new_obj)
            print ("LODSET:%s" % lodset.name)

    # Decompose
    if DEBUG: ttt = time.time() #!TIME
    Scan(context, tDataList, settings.errorsMem, tOptions)
    if DEBUG: print("[TIME] Decompose in {:.4f} sec".format(time.time() - ttt) ) #!TIME

    # keep track of all meshes that we processed and avoid multiple handling
    processedMeshes = []

    # Export each decomposed object
    for tData in tDataList:
    
        #PrintAll(tData)
        
        log.info("---- Exporting {:s} ----".format(tData.objectName))

        uExportData = UrhoExportData()
        
        uExportOptions = UrhoExportOptions()
        uExportOptions.splitSubMeshes = settings.geometrySplit
        uExportOptions.useStrictLods = settings.strictLods
        uExportOptions.useRatioTriggers = settings.animationRatioTriggers
        uExportOptions.bonesPerGeometry = addonPrefs.bonesPerGeometry
        uExportOptions.bonesPerVertex = addonPrefs.bonesPerVertex
        uExportOptions.clampBoundingBox = settings.clampBoundingBox

        if DEBUG: ttt = time.time() #!TIME
        UrhoExport(tData, uExportOptions, uExportData, settings.errorsMem)
        if DEBUG: print("[TIME] Export in {:.4f} sec".format(time.time() - ttt) ) #!TIME
        if DEBUG: ttt = time.time() #!TIME

        uScene.Load(uExportData, tData.blenderObjectName, sOptions)
        for uModel in uExportData.models:
            obj = None
            try:
                obj = bpy.data.objects[uModel.name]
                uModel.isEmpty=obj.type=="EMPTY" or (sOptions.wiredAsEmpty and obj.display_type=="WIRE")
                if uModel.isEmpty:
                    uModel.meshName=obj.name
                else:
                    if obj.lodsetID>0:
                        print("0")
                        lodset = getLodSetWithID(obj.lodsetID)
                        uModel.meshName=lodset.name
                    elif tOptions.meshNameDerivedBy == 'Object':
                        print("1")
                        uModel.meshName=uModel.name
                    else:
                        print("2")
                        uModel.meshName=obj.data.name
                    print("SET MESHNAME:%s" % uModel.meshName)
                
            except:
                uModel.meshName=uModel.name
                uModel.isEmpty=False
            #
            ########

            # check if the draw_type is on wire=>skip
            # check if we already exported this mesh. if yes, skip it
            filepath = GetFilepath(PathType.MODELS, uModel.meshName, fOptions)
            uScene.AddFile(PathType.MODELS, uModel.name, filepath[1])

            print("%s: hasLOD:%s\n" % (uModel.meshName, str(tData.hasLODs)))
            # make sure that meshes with LOD gets written also there is a mesh with this name (that was created by a node that is referencing the root-mesh)
            if obj==None or (not uModel.isEmpty and (not uModel.meshName in processedMeshes or tData.hasLODs)):
                # use the name of the mesh to make mesh sharing possible (no need to write one shared mesh multiple times)
                if uModel.geometries:
                    if CheckFilepath(filepath[0], fOptions):
                        log.info( "Creating model {:s}".format(filepath[1]) )
                        UrhoWriteModel(uModel, filepath[0])
                        # mark this mesh to be processed and avoid another export
                        processedMeshes.append(uModel.meshName)
            
        for uAnimation in uExportData.animations:
            filepath = GetFilepath(PathType.ANIMATIONS, uAnimation.name, fOptions)
            uScene.AddFile(PathType.ANIMATIONS, uAnimation.name, filepath[1])
            if CheckFilepath(filepath[0], fOptions):
                log.info( "Creating animation {:s}".format(filepath[1]) )
                UrhoWriteAnimation(uAnimation, filepath[0])

            if uAnimation.triggers:
                filepath = GetFilepath(PathType.TRIGGERS, uAnimation.name, fOptions)
                uScene.AddFile(PathType.TRIGGERS, uAnimation.name, filepath[1])
                if CheckFilepath(filepath[0], fOptions):
                    log.info( "Creating triggers {:s}".format(filepath[1]) )
                    UrhoWriteTriggers(uAnimation.triggers, filepath[0], fOptions)
                
        for uMaterial in uExportData.materials:
            for textureName in uMaterial.getTextures():
                # Check the texture name (it can be a filename)
                if textureName is None:
                    continue
                # Check if the Blender image data exists
                image = bpy.data.images[textureName]
                if image is None:
                    continue
                # Get the texture file full path
                srcFilename = bpy.path.abspath(image.filepath)
                # Get image filename
                filename = os.path.basename(image.filepath)
                if not filename:
                    filename = textureName
                # Get the destination file full path (preserve the extension)
                fOptions.preserveExtTemp = True
                filepath = GetFilepath(PathType.TEXTURES, filename, fOptions)
                # Check if already exported
                if not uScene.AddFile(PathType.TEXTURES, textureName, filepath[1]):
                    continue
                # Copy or unpack the texture
                if settings.textures and CheckFilepath(filepath[0], fOptions):
                    if image.packed_file:
                        format = str(context.scene.render.image_settings.file_format)
                        mode = str(context.scene.render.image_settings.color_mode)
                        log.info( "Unpacking {:s} {:s} texture to {:s}".format(format, mode, filepath[1]) )
                        render_ext = context.scene.render.file_extension
                        file_ext = os.path.splitext(filepath[0])[1].lower()
                        if file_ext and render_ext != file_ext:
                            log.warning( "Saving texture as {:s} but the file has extension {:s}".format(render_ext, file_ext) )
                        image.save_render(filepath[0])
                    elif not os.path.exists(srcFilename):
                        log.error( "Missing source texture {:s}".format(srcFilename) )
                    else:
                        try:
                            log.info( "Copying texture {:s}".format(filepath[1]) )
                            shutil.copyfile(src = srcFilename, dst = filepath[0])
                        except:
                            log.error( "Cannot copy texture to {:s}".format(filepath[0]) )


                    
            # if settings.materialsList:
            #     for uModel in uExportData.models:
            #         filepath = GetFilepath(PathType.MATLIST, uModel.name, fOptions)
            #         uScene.AddFile(PathType.MATLIST, uModel.name, filepath[1])
            #         if CheckFilepath(filepath[0], fOptions):
            #             log.info( "Creating materials list {:s}".format(filepath[1]) )
            #             UrhoWriteMaterialsList(uScene, uModel, filepath[0])

        if DEBUG: print("[TIME] Write in {:.4f} sec".format(time.time() - ttt) ) #!TIME

    settings.errorsMem.Cleanup()
    if settings.selectErrors:
        selectErrors(context, settings.errorsMem, 'ALL')
    
    # Export scene and nodes
    UrhoExportScene(context, uScene, sOptions, fOptions)

    return True


def ExecuteAddon(context, silent=False):

    startTime = time.time()
    print("----------------------Urho export start----------------------")    
    ExecuteUrhoExport(context)
    log.setLevel(logging.DEBUG)

    print ("TRY TO REMOVE TEMPOBJECTS:")
    for tempObj in tempObjects:
        print("REMOVE tempobject:%s" % tempObj.name)
        bpy.data.objects.remove(tempObj, do_unlink=True)
        pass
    tempObjects.clear()


    log.info("Export ended in {:.4f} sec".format(time.time() - startTime) )
    
    if not silent:
        bpy.ops.urho.report('INVOKE_DEFAULT')

            
if __name__ == "__main__":
	register()
