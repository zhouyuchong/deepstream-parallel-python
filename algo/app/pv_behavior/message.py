import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import pyds

import sys
import time
from loguru import logger
from .constant import *

class DSCarPTZMessage(object):

    # Callback function for deep-copying an NvDsEventMsgMeta struct
    def meta_copy_func(data, user_data):
        # Cast data to pyds.NvDsUserMeta
        user_meta = pyds.NvDsUserMeta.cast(data)
        src_meta_data = user_meta.user_meta_data
        # Cast src_meta_data to pyds.NvDsEventMsgMeta
        srcmeta = pyds.NvDsEventMsgMeta.cast(src_meta_data)
        # Duplicate the memory contents of srcmeta to dstmeta
        # First use pyds.get_ptr() to get the C address of srcmeta, then
        # use pyds.memdup() to allocate dstmeta and copy srcmeta into it.
        # pyds.memdup returns C address of the allocated duplicate.
        dstmeta_ptr = pyds.memdup(pyds.get_ptr(srcmeta),
                                  sys.getsizeof(pyds.NvDsEventMsgMeta))
        # Cast the duplicated memory to pyds.NvDsEventMsgMeta
        dstmeta = pyds.NvDsEventMsgMeta.cast(dstmeta_ptr)

        # Duplicate contents of ts field. Note that reading srcmeat.ts
        # returns its C address. This allows to memory operations to be
        # performed on it.
        dstmeta.ts = pyds.memdup(srcmeta.ts, MAX_TIME_STAMP_LEN + 1)

        # Copy the sensorStr. This field is a string property. The getter (read)
        # returns its C address. The setter (write) takes string as input,
        # allocates a string buffer and copies the input string into it.
        # pyds.get_string() takes C address of a string and returns the reference
        # to a string object and the assignment inside the binder copies content.
        dstmeta.sensorStr = pyds.get_string(srcmeta.sensorStr)

        if srcmeta.objSignature.size > 0:
            dstmeta.objSignature.signature = pyds.memdup(
                srcmeta.objSignature.signature, srcmeta.objSignature.size)
            dstmeta.objSignature.size = srcmeta.objSignature.size

        if srcmeta.extMsgSize > 0:
            if srcmeta.objType == pyds.NvDsObjectType.NVDS_OBJECT_TYPE_FACE:
                srcobj = pyds.NvDsFaceObject.cast(srcmeta.extMsg)
                obj = pyds.alloc_nvds_face_object()
                # obj.faceimage = pyds.get_string(srcobj.faceimage)
                # obj.feature = pyds.get_string(srcobj.feature)
                obj.age = srcobj.age
                obj.gender = pyds.get_string(srcobj.gender)
                obj.cap = pyds.get_string(srcobj.cap)
                obj.hair = pyds.get_string(srcobj.hair)
                obj.glasses = pyds.get_string(srcobj.glasses)
                obj.facialhair = pyds.get_string(srcobj.facialhair)
                obj.name = pyds.get_string(srcobj.name)
                obj.eyecolor = pyds.get_string(srcobj.eyecolor)
                dstmeta.extMsg = obj
                dstmeta.extMsgSize = sys.getsizeof(pyds.NvDsFaceObject)

        return dstmeta

    # Callback function for freeing an NvDsEventMsgMeta instance
    def meta_free_func(data, user_data):
        user_meta = pyds.NvDsUserMeta.cast(data)
        srcmeta = pyds.NvDsEventMsgMeta.cast(user_meta.user_meta_data)

        # pyds.free_buffer takes C address of a buffer and frees the memory
        # It's a NOP if the address is NULL
        pyds.free_buffer(srcmeta.ts)
        pyds.free_buffer(srcmeta.sensorStr)

        if srcmeta.objSignature.size > 0:
            pyds.free_buffer(srcmeta.objSignature.signature)
            srcmeta.objSignature.size = 0

        if srcmeta.extMsgSize > 0:
            if srcmeta.objType == pyds.NvDsObjectType.NVDS_OBJECT_TYPE_FACE:
                obj = pyds.NvDsFaceObject.cast(srcmeta.extMsg)
                # pyds.free_buffer(obj.faceimage)
                # pyds.free_buffer(obj.feature)
                pyds.free_buffer(obj.gender)
                pyds.free_buffer(obj.hair)
                pyds.free_buffer(obj.cap)
                pyds.free_buffer(obj.glasses)
                pyds.free_buffer(obj.facialhair)
                pyds.free_buffer(obj.name)
                pyds.free_buffer(obj.eyecolor)

            pyds.free_gbuffer(srcmeta.extMsg)
            srcmeta.extMsgSize = 0

    def generate_event_msg_meta(data, catch_time, uid, ptz_id, event_label, fast_url):
        meta = pyds.NvDsEventMsgMeta.cast(data)
        meta.sensorId = 0
        meta.placeId = 0
        meta.moduleId = 0
        meta.sensorStr = "sensor-0"
        meta.ts = pyds.alloc_buffer(MAX_TIME_STAMP_LEN + 1)
        pyds.generate_ts_rfc3339(meta.ts, MAX_TIME_STAMP_LEN)

        # This demonstrates how to attach custom objects.
        # Any custom object as per requirement can be generated and attached
        # like NvDsVehicleObject / NvDsPersonObject. Then that object should
        # be handled in payload generator library (nvmsgconv.cpp) accordingly.

        meta.type = pyds.NvDsEventType.NVDS_EVENT_ENTRY
        meta.objType = pyds.NvDsObjectType.NVDS_OBJECT_TYPE_FACE
        meta.objClassId = 0

        obj = pyds.alloc_nvds_face_object()
        obj = DSCarPTZMessage.generate_car_meta(
            obj, catch_time, uid, ptz_id, event_label, fast_url)
        meta.extMsg = obj
        meta.extMsgSize = sys.getsizeof(pyds.NvDsFaceObject)
        return meta

    def generate_car_meta(data, catch_time, uid, ptz_id, event_label, fast_url):
        obj = pyds.NvDsFaceObject.cast(data)
        obj.age = 1
        obj.gender = str(uid)
        obj.cap = str(catch_time)
        obj.hair = ''
        obj.glasses = event_label
        obj.facialhair = ''
        obj.name = fast_url
        obj.eyecolor = str(ptz_id)
        return obj

