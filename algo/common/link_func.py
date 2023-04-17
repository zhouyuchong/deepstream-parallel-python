import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

import configparser
from loguru import logger


import sys
sys.path.append('../')

def create_parallel_infer_branches(app_list):
    logger.info("Total {} branches.".format(len(app_list)))
    elements = dict()
    for app_index in app_list:
        if app_index == 0:
            pass


def create_element(app_name, element_type, element_name=None):
    if element_name:
        temp_name = element_type + '-' + app_name + '-' + element_name
    else:
        temp_name = element_type + '-' + app_name

    gstreamer_element = Gst.ElementFactory.make(element_type, temp_name)
    if not gstreamer_element:
        logger.error("Unable to create {}.".format(temp_name))
        return False, None, None
    logger.info("Plugin {} created.".format(temp_name))
    
    return True, gstreamer_element

def set_element_property(config_path, element, element_name, addition_path=None):
    config = configparser.ConfigParser()
    config.read(config_path)
    config.sections()

    for key in config[element_name]:
        if 'gie' in element_name:
            if key == "config-file-path":
                element.set_property(key, addition_path)

        elif element_name == 'capsfilter':
            if key == 'caps':
                value = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")
                element.set_property(key, value)

        elif element_name == 'msgbroker':
            if key == 'proto-lib':
                path = config.get(element_name, key)
                element.set_property(key, path)
            if key == 'config':
                element.set_property(key, addition_path)
            if key == 'conn-str':
                path = config.get(element_name, key)
                element.set_property(key, path)

        elif element_name == 'msgconv':
            if key == 'config':
                element.set_property(key, addition_path)
            else:
                temp_property = config.getint(element_name, key)
                element.set_property(key, temp_property)

        elif 'path' in key or 'file' in key:
            path = config.get(element_name, key)
            element.set_property(key, path)
        
        else:
            temp_property = config.getint(element_name, key)
            element.set_property(key, temp_property)

