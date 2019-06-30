
#
# This script is licensed as public domain.
#

# http://docs.python.org/2/library/struct.html

from xml.etree import ElementTree as ET
from xml.dom import minidom
import os
import struct
import array
import logging
import bpy
import re
import queue
import json,math

# queue actions
execution_queue = queue.Queue()

log = logging.getLogger("ExportLogger")

initialized = False
reloadScreenshotFlag = False

def enum(**enums):
    return type('Enum', (), enums)
PathType = enum(
    ROOT        = "ROOT-",
    MODELS      = "MODE-",
    ANIMATIONS  = "ANIM-",
    TRIGGERS    = "TRIG-",
    MATERIALS   = "MATE-",
    TECHNIQUES  = "TECH-",
    TEXTURES    = "TEXT-",
    MATLIST     = "MATL-",
    OBJECTS     = "OBJE-",
    SCENES      = "SCEN-")

# Options for file utils
class FOptions:
    def __init__(self):
        self.useSubDirs = True
        self.fileOverwrite = False
        self.paths = {}
        self.exts = {
                        PathType.MODELS : "mdl",
                        PathType.ANIMATIONS : "ani",
                        PathType.TRIGGERS : "xml",
                        PathType.MATERIALS : "xml",
                        PathType.TECHNIQUES : "xml",
                        PathType.TEXTURES : "png",
                        PathType.MATLIST : "txt",
                        PathType.OBJECTS : "xml",
                        PathType.SCENES : "xml"
                    }
        self.preserveExtTemp = False


#--------------------
# Errors container
#--------------------

class ErrorsMem:
    def __init__(self):
        self.errors = {}
        self.seconds = []

    def Get(self, name, defaultValue = None):
        try:
            return self.errors[name]
        except KeyError:
            if defaultValue is not None:
                self.errors[name] = defaultValue
            return defaultValue

    def Delete(self, name):
        if name in self.errors:
            del self.errors[name]

    def Cleanup(self):
        emptyList = []
        for name in self.errors.keys():
            try:
                if not self.errors[name]:
                    emptyList.append(name)
            except TypeError:
                pass
        for name in emptyList:
            del self.errors[name]

    def Names(self):
        return self.errors.keys()

    def Second(self, index):
        try:
            return self.seconds[index]
        except IndexError:
            return None

    def SecondIndex(self, second):
        try:
            return self.seconds.index(second)
        except ValueError:
            index = len(self.seconds)
            self.seconds.append(second)
            return index

    def Clear(self):
        self.errors.clear()
        self.seconds.clear()


#--------------------
# File utilities
#--------------------

# Get a file path for the object 'name' in a folder of type 'pathType'
def GetFilepath(pathType, name, fOptions):

    # Get absolute root path
    rootPath = bpy.path.abspath(fOptions.paths[PathType.ROOT])

    # Remove unnecessary separators and up-level references
    rootPath = os.path.normpath(rootPath)

    # Append the relative path to get the full path
    fullPath = rootPath
    if fOptions.useSubDirs:
        fullPath = os.path.join(fullPath, fOptions.paths[pathType])

    # Compose filename, remove invalid characters
    filename = re.sub('[^\w_.)( -]', '_', name)
    if type(filename) is list or type(filename) is tuple:
        filename = os.path.sep.join(filename)

    # Add extension to the filename, if present we can preserve the extension
    ext = fOptions.exts[pathType]
    if ext and (not fOptions.preserveExtTemp or os.path.extsep not in filename):
        filename += os.path.extsep + ext
        #filename = bpy.path.ensure_ext(filename, ".mdl")
    fOptions.preserveExtTemp = False

    # Replace all characters besides A-Z, a-z, 0-9 with '_'
    #filename = bpy.path.clean_name(filename)

    # Compose the full file path
    fileFullPath = os.path.join(fullPath, filename)

    # Get the Urho path (relative to root)
    fileUrhoPath = os.path.relpath(fileFullPath, rootPath)
    fileUrhoPath = fileUrhoPath.replace(os.path.sep, '/')

    # Return full file path and relative file path
    return (fileFullPath, fileUrhoPath)


# Check if 'filepath' is valid
def CheckFilepath(fileFullPaths, fOptions):

    fileFullPath = fileFullPaths
    if type(fileFullPaths) is tuple:
        fileFullPath = fileFullPaths[0]

    # Create the full path if missing
    fullPath = os.path.dirname(fileFullPath)
    if not os.path.isdir(fullPath):
        try:
            os.makedirs(fullPath)
            log.info( "Created path {:s}".format(fullPath) )
        except Exception as e:
            log.error("Cannot create path {:s} {:s}".format(fullPath, e))

    if os.path.exists(fileFullPath) and not fOptions.fileOverwrite:
        log.error( "File already exists {:s}".format(fileFullPath) )
        return False

    return True


#--------------------
# XML formatters
#--------------------

def FloatToString(value):
    return "{:g}".format(value)

def Vector3ToString(vector):
    return "{:g} {:g} {:g}".format(vector[0], vector[1], vector[2])

def Vector4ToString(vector):
    return "{:g} {:g} {:g} {:g}".format(vector[0], vector[1], vector[2], vector[3])

def XmlToPrettyString(elem):
    rough = ET.tostring(elem, 'utf-8')
    reparsed = minidom.parseString(rough)
    pretty = reparsed.toprettyxml(indent="\t")
    i = pretty.rfind("?>")
    if i >= 0:
        pretty = pretty[i+2:]
    return pretty.strip()


#--------------------
# XML writers
#--------------------

def ensure_dir(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

# Write XML to a text file
def WriteXmlFile(xmlContent, filepath, fOptions):
    try:
        ensure_dir(filepath)
        file = open(filepath, "w")
    except Exception as e:
        log.error("Cannot open file {:s} {:s}".format(filepath, e))
        return
    try:
        file.write(XmlToPrettyString(xmlContent))
    except Exception as e:
        log.error("Cannot write to file {:s} {:s}".format(filepath, e))
    file.close()


#--------------------
# Binary writers
#--------------------

class BinaryFileWriter:

    # We try to write the file with a single API call to avoid
    # the Editor crashing while reading a not completed file.
    # We set the buffer to 1Mb (if unspecified is 64Kb, and it is
    # 8Kb with multiple file.write calls)

    # Constructor.
    def __init__(self):
        self.filename = None
        self.buffer = None

    # Open file stream.
    def open(self, filename):
        self.filename = filename
        self.buffer = array.array('B')
        return True

    def close(self):
        try:
            file = open(self.filename, "wb", 1024 * 1024)
        except Exception as e:
            log.error("Cannot open file {:s} {:s}".format(self.filename, e))
            return
        try:
            self.buffer.tofile(file)
        except Exception as e:
            log.error("Cannot write to file {:s} {:s}".format(self.filename, e))
        file.close()

    # Writes an ASCII string without terminator
    def writeAsciiStr(self, v):
        # Non ASCII to '_'
        v = re.sub(r'[^\x00-\x7f]', '_', v)
        self.buffer.extend(bytes(v, "ascii", errors="ignore"))

    # Writes a 32 bits unsigned int
    def writeUInt(self, v):
        self.buffer.extend(struct.pack("<I", v))

    # Writes a 16 bits unsigned int
    def writeUShort(self, v):
        self.buffer.extend(struct.pack("<H", v))

    # Writes one 8 bits unsigned byte
    def writeUByte(self, v):
        self.buffer.extend(struct.pack("<B", v))

    # Writes four 32 bits floats .w .x .y .z
    def writeQuaternion(self, v):
        self.buffer.extend(struct.pack("<4f", v.w, v.x, v.y, v.z))

    # Writes three 32 bits floats .x .y .z
    def writeVector3(self, v):
        self.buffer.extend(struct.pack("<3f", v.x, v.y, v.z))

    # Writes a 32 bits float
    def writeFloat(self, v):
        self.buffer.extend(struct.pack("<f", v))

# --------------------------
# Hash - Function (like StringHash in Urho3D)
# --------------------------
def SDBMHash(key):
    hash = 0
    for i in range(len(key)):
        hash = ord(key[i]) + (hash << 6) + (hash << 16) - hash
    return (hash & 0xFFFFFFFF)

def IsJsonNodeAddonAvailable():
    #jsonNodetreeAvailable = False
    #log = logging.getLogger("ExportLogger")
    jsonNodetreeAvailable = "addon_jsonnodetree" in bpy.context.preferences.addons.keys()
    return jsonNodetreeAvailable

def getLodSetWithID(id,returnIdx=False):
    cnt=0
    for lodset in bpy.data.worlds[0].lodsets:
        if lodset.lodset_id == id: # good that I'm so consistent with my name *#%&
            if returnIdx:
                return cnt
            else:
                return lodset
        cnt=cnt+1
    print("COULD NOT FIND LODSET WITH ID:%s"%id)
    return None

def getObjectWithID(id):
    if id==-1:
        return None
    for obj in bpy.data.objects:
        if obj.ID == id:
            return obj
    return None

# This function can savely be called in another thread.
# The function will be executed when the timer runs the next time.
def run_in_main_thread(function):
    execution_queue.put(function)

requests2Engine = None
requestsFromEngine = {}
runtime2blender = None
blender2runtime = None

# timered function
def execute_queued_functions():
    #print("TIMER")
    while not execution_queue.empty():
        function = execution_queue.get()
        function()

    if requests2Engine:
        sendRequests2Engine()

    if runtime2blender and runtime2blender!="" and os.path.isfile(runtime2blender):
        with open(runtime2blender) as json_file:  
            data = json.load(json_file)
            action = data["action"]
            print("runtime2blender-action:%s" % data["action"])

            if action=="reload_screenshot":
                bpy.data.images["Screenshot.png"].reload()
                os.remove(runtime2blender)
                a3d = getArea3D()
                a3d.tag_redraw()
                print("TAGGED REDRAW")

                

    # amount of time to wait till next call
    return 1


def sendRequests2Engine():
    global requests2Engine
    if not requests2Engine:
        return
    if not blender2runtime:
        return

    if os.path.isfile(blender2runtime):
        return

    j = json.dumps(requests2Engine, indent=4)
    f = open(blender2runtime, 'w')
    f.write(j)
    f.close()
    print("CREATED runtime-request-FILE:%s" %blender2runtime)
    requests2Engine=None

def queueRequestForRuntime(type,requestData):
    global requests2Engine
    if not requests2Engine:
        requests2Engine={}
    requests2Engine[type]=requestData

def vec2dict(vec,convToDeg=False):
    result={}
    try:
        if not convToDeg:
            result["x"]=vec.x
            result["y"]=vec.y
            result["z"]=vec.z
            result["w"]=vec.w
        else:
            result["x"]=math.degrees(vec.x)
            result["y"]=math.degrees(vec.y)
            result["z"]=math.degrees(vec.z)
            result["w"]=math.degrees(vec.w)

    except:
        pass
    return result


def getArea3D():
    for area in bpy.data.window_managers['WinMan'].windows[0].screen.areas:
        if area.type == "VIEW_3D":
            break
    
    if not area or area.type != "VIEW_3D":
        return None
    return area    

def getRegion3D():

    area = getArea3D()
    if area:
        return area.spaces.active.region_3d
    else:
        return None

def sendUpdateView2Runtime():
    region3d = getRegion3D()
    area3d = getArea3D()
    
    view_matrix = region3d.view_matrix
    viewMatrixDect = []
    for vector in view_matrix:
        viewMatrixDect.append(vec2dict(vector))
    queueRequestForRuntime("view_matrix",viewMatrixDect)

    queueRequestForRuntime("view_width",area3d.width)
    queueRequestForRuntime("view_height",area3d.height)

    #print(json.dumps(viewMatrixDect,indent=4))

    matrix = region3d.perspective_matrix 
    #@ area.spaces.active.region_3d.view_matrix.inverted()
    matrixDect = []
    for vector in matrix:
        matrixDect.append(vec2dict(vector))

    queueRequestForRuntime("perspective_matrix",matrixDect)

    
    global blender2runtime
    global runtime2blender
    blender2runtime = bpy.context.scene.urho_exportsettings.screenshotPath
    if blender2runtime!="":
        runtime2blender=blender2runtime+"/runtime2blender.json"
        blender2runtime= blender2runtime+'/req2engine.json'
        print ("SETPATH %s" % blender2runtime)
    
    
