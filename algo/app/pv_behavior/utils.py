import os
import re

import numpy as np

import config 

# print(os.listdir())
# path = '../../configs/lpr/config_nvdsanalytics.txt'
# type: LINE, ROI, DIR
def init_analytics_config_file(max_source_number, types, path):
    '''
    Create an empty analytics config file.
    + Args:
        max_source_number: to write corresponding number of groups.
    '''
    if os.path.exists(path):  # 如果文件存在
        # 删除文件，可使用以下两种方法。
        os.remove(path)
    text_line = []
    text_line.append(
        "[property]\nenable=1\nconfig-width=1920\nconfig-height=1080\nosd-mode=2\ndisplay-font-size=12\n\n")
    file = open(path, 'w')
    if "LINE" in types:
        for i in range(max_source_number + 1):
            text_line.append(
                "[line-crossing-stream-{0}]\nenable=0\nline-crossing-Exit=789;672;1084;900;851;773;1203;732\nextended=0\nmode=balanced\nclass-id=-1\n\n".format(
                    i))
    if "ROI" in types:
        for i in range(max_source_number + 1):
            text_line.append(
                "[roi-filtering-stream-{0}]\nroi-{1}=0;0;0;0;0;0;0;0\nenable=0\ninverse-roi=0\nclass-id=-1\n\n".format(i,
                                                                                                                     i))
    if "DIR" in types:
        for i in range(max_source_number + 1):
            text_line.append(
                "[direction-detection-stream-{0}]\ndirection-{1}=0;0;1;1\nenable=0\nmode=balanced\nclass-id=-1\n\n".format(i,
                                                                                                                     i))

    file.writelines(text_line)
    file.close()


def modify_analytics_crossingline(filepath, max_source_number, index, enable,
                                  extended=0, mode='balanced', class_id=-1, ptz_params=[]):
    if enable == 0:
        return True
    with open(filepath) as lf:
        text_lines = lf.readlines()
    lf.close()

    comp_str = "\[line-crossing-stream-{0}\]".format(index)
    regex = re.compile(comp_str)
    for line_number, line in enumerate(text_lines):
        for match in re.findall(regex, line):
            l = line_number
            break

    if index == max_source_number:
        del text_lines[l + 1:]
    else:
        comp_str_2 = "\[line-crossing-stream-{0}\]".format(index + 1)
        regex_2 = re.compile(comp_str_2)
        for line_number, line in enumerate(text_lines):
            for match in re.findall(regex_2, line):
                l2 = line_number
                break
        del text_lines[l + 1:l2 - 1]
        insert_str = ''
        for param in ptz_params:
            # print("{} = {}".format(key,value))
            ptz_id = param['ptz_id']
            for coor_name, coor_data in param['coordinate'].items():
                coor_data_np = np.array(coor_data.split(';')).astype(np.float64)
                coor_data_np[::2] *= config.MUXER_OUTPUT_WIDTH
                coor_data_np[1::2] *= config.MUXER_OUTPUT_HEIGHT
                coor_data_str = ';'.join([str(int(i)) for i in coor_data_np])
                insert_str = insert_str + 'line-crossing-{0}-{1}={2}\n'.format(ptz_id, coor_name, coor_data_str)
        insert_str = insert_str + 'enable={}\nextended={}\nclass-id={}\n\n'.format(enable, extended, class_id)

        text_lines.insert(l + 1, insert_str)

    with open(filepath, 'w') as file:
        file.writelines(text_lines)

    file.close()
    return True


def modify_analytics_roi(filepath, max_source_number, index, enable, ptz_params, inverse_roi=1, class_id=-1):
    if enable == 0:
        return True
    with open(filepath) as lf:
        text_lines = lf.readlines()
    lf.close()

    comp_str = "\[roi-filtering-stream-{0}\]".format(index)
    regex = re.compile(comp_str)
    for line_number, line in enumerate(text_lines):
        for match in re.findall(regex, line):
            # print('Match found on line %d: %s' % (line_number, match))
            l = line_number
            break

    if index == max_source_number:
        del text_lines[l + 1:]
    else:
        print("****************************************************\n{}".format(ptz_params))
        comp_str_2 = "\[roi-filtering-stream-{0}\]".format(index + 1)
        regex_2 = re.compile(comp_str_2)
        for line_number, line in enumerate(text_lines):
            for match in re.findall(regex_2, line):
                # print('Match found on line %d: %s' % (line_number, match))
                l2 = line_number
                break
        del text_lines[l + 1:l2 - 1]
        insert_str = ''
        for param in ptz_params:
            # print("{} = {}".format(key,value))
            ptz_id = param['ptz_id']
            if 'coordinate' not in param:
                continue

            for coor_name, coor_data in param['coordinate'].items():
                print("name:{} data:{}".format(coor_name, coor_data))
                coor_data_np = np.array(coor_data.split(';')).astype(np.float64)
                coor_data_np[::2] *= config.MUXER_OUTPUT_WIDTH
                coor_data_np[1::2] *= config.MUXER_OUTPUT_HEIGHT
                coor_data_str = ';'.join([str(int(i)) for i in coor_data_np])
                insert_str = insert_str + 'roi-{0}-{1}={2}\n'.format(ptz_id, coor_name, coor_data_str)
        insert_str = insert_str + 'enable={}\ninverse-roi={}\nclass-id={}\n\n'.format(enable, inverse_roi, class_id)

        text_lines.insert(l + 1, insert_str)

    with open(filepath, 'w') as file:
        file.writelines(text_lines)

    file.close()
    return True


def modify_analytics_dir(filepath, max_source_number, index, enable, ptz_params, class_id=-1):
    if enable == 0:
        return True
    with open(filepath) as lf:
        text_lines = lf.readlines()
    lf.close()

    comp_str = "\[direction-detection-stream-{0}\]".format(index)
    regex = re.compile(comp_str)
    for line_number, line in enumerate(text_lines):
        for match in re.findall(regex, line):
            # print('Match found on line %d: %s' % (line_number, match))
            l = line_number
            break

    if index == max_source_number:
        del text_lines[l + 1:]
    else:
        comp_str_2 = "\[direction-detection-stream-{0}\]".format(index + 1)
        regex_2 = re.compile(comp_str_2)
        for line_number, line in enumerate(text_lines):
            for match in re.findall(regex_2, line):
                # print('Match found on line %d: %s' % (line_number, match))
                l2 = line_number
                break
        del text_lines[l + 1:l2 - 1]
        insert_str = ''
        for param in ptz_params:
            # print("{} = {}".format(key,value))
            ptz_id = param['ptz_id']
            if 'direction' not in param:
                continue

            for coor_name, coor_data in param['direction'].items():
                coor_data_np = np.array(coor_data.split(';')).astype(np.float64)
                coor_data_np[::2] *= config.MUXER_OUTPUT_WIDTH
                coor_data_np[1::2] *= config.MUXER_OUTPUT_HEIGHT
                coor_data_inverse = [str(int(i)) for i in coor_data_np]
                coor_data_inverse = ';'.join(coor_data_inverse[2:] + coor_data_inverse[:2])
                insert_str = insert_str + 'direction-{0}-{1}={2}\n'.format(ptz_id, coor_name, coor_data_inverse)
        insert_str = insert_str + 'enable={}\nmode=balanced\nclass-id={}\n\n'.format(enable, class_id)

        text_lines.insert(l + 1, insert_str)

    with open(filepath, 'w') as file:
        file.writelines(text_lines)

    file.close()
    return True


class AnaInfo:
    def __init__(self, roi=None, dir=None):
        self.roi = roi
        self.dir = dir

def long_to_uint64(l):
    value = ctypes.c_uint64(l & 0xffffffffffffffff).value
    return value

if __name__ == "__main__":
    ptz_params = [
        {
            'ptz_id': 'test_mark',
            'ptz': '1.0,0.9,0.8',
            'coordinate': {
                'ptz1': '0;1;2;3;4;5',
                'ptz2': '1;2;3;4;5;6'
            },
            'direction': {
                'ptz1': '0.12;0.12;0.25;0.25',
                'ptz2': '0.25;0.25;0.12;0.12'
            }
        },
    ]
    import os
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    init_analytics_config_file(16, ['ROI', 'DIR'], config.ANALYTICS_CONFIG_FILE)
    modify_analytics_roi(config.ANALYTICS_CONFIG_FILE, config.MAX_NUM_SOURCES, 1, True, ptz_params)
    modify_analytics_roi(config.ANALYTICS_CONFIG_FILE, config.MAX_NUM_SOURCES, 1, True, ptz_params)
