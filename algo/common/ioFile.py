import sys
sys.path.append("../")
import config
import os
SOURCE_MANAGER_FILE = os.path.join(config.__path__[0], "config_other_srcm.txt")
def write_source_to_file(source):
    data = source.get_format_data()
    with open(SOURCE_MANAGER_FILE, 'a+') as f:
        f.write(data+'\n')

    # print(SOURCE_MANAGER_FILE)