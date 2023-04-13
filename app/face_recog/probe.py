from .message import *
from .data import *

def pgie_sink_pad_buffer_probe(pad,info,u_data):
    """
    Probe to extract facial info from metadata and add them to Face pool. 
    
    Should be after retinaface.
    """
    face_pool, tpool, perf_data = u_data[0], u_data[1], u_data[3]
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.NvDsFrameMeta.cast()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        l_obj=frame_meta.obj_meta_list
        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                #obj_meta=pyds.glist_get_nvds_object_meta(l_obj.data)
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
            except StopIteration:
                break
            
            drop_signal = True
            tmp_face_bbox = [obj_meta.rect_params.width, obj_meta.rect_params.height]
            print(tmp_face_bbox)

            drop_signal = comp_replace(face_pool, tpool, frame_meta, obj_meta, tmp_face_bbox) and\
                            add_new_face(face_pool, tpool, frame_meta, obj_meta, tmp_face_bbox)
                            # DSFaceProbe.update_face(face_pool, tpool, obj_meta, tmp_face_bbox)
            try: 
                l_obj=l_obj.next
                if drop_signal is True:
                    pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
                
            except StopIteration:
                break
        stream_index = "stream{0}".format(frame_meta.pad_index)
        perf_data.update_fps(stream_index)
        # Get frame rate through this probe
        try:
            l_frame=l_frame.next
        except StopIteration:
            break

    return Gst.PadProbeReturn.OK


def sgie_sink_pad_buffer_probe(pad,info,u_data):
    """
    Probe to extract facial feature from user-meta data. 
    
    Should be after arcface.
    """
    face_pool = u_data[0]
    frame_number=0
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))    
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.glist_get_nvds_frame_meta()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        l_obj=frame_meta.obj_meta_list

        while l_obj is not None:
            try:
                # Casting l_obj.data to pyds.NvDsObjectMeta
                obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
                
            except StopIteration:
                break

            get_face_feature(face_pool, obj_meta)
            
            try: 
                l_obj=l_obj.next

            except StopIteration:
                break  
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
            
    return Gst.PadProbeReturn.OK	

def msg_sink_pad_buffer_probe(pad,info,data):
    """
    probe to add info into msg-meta data.
    """
    face_pool, tpool, srcm = data[0], data[1], data[2]
    frame_number=0
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        print("Unable to get GstBuffer ")
        return

    # Retrieve batch metadata from the gst_buffer
    # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
    # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))    
    l_frame = batch_meta.frame_meta_list
    while l_frame is not None:
        try:
            # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
            # The casting is done by pyds.glist_get_nvds_frame_meta()
            # The casting also keeps ownership of the underlying memory
            # in the C code, so the Python garbage collector will leave
            # it alone.
            #frame_meta = pyds.glist_get_nvds_frame_meta(l_frame.data)
            frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        except StopIteration:
            break
        
        frame_number=frame_meta.frame_num
        
        ids = face_pool.get_ids_in_pool()
        for id in ids:
            tmp_face = face_pool.get_face_by_id(id=id)
            if tmp_face.get_state() == FaceState.TOSEND:
                tmp_bbox = tmp_face.get_bbox()
                image_link, ff_link, name, ts, sid = face_pool.check_msg_status(id=id)
                uid = srcm.get_id_by_idx(sid)
                logger.success("Sending message: \n source: {} | track-id: {} \n capture time: {} \n image link: {} \n feature link: {}".format(uid, id, time.strftime("%Y-%m-%d %H:%M:%S",time.localtime(ts)), image_link, ff_link))
                face_pool.pop_face_by_id(id=id)
                # print([id, tmp_bbox])
                tpool.add([id, tmp_bbox])
                gen_msg(batch_meta, frame_meta, frame_number, image_link, ff_link, uid, name, ts)
                
        try:
            l_frame=l_frame.next
        except StopIteration:
            break
            
    return Gst.PadProbeReturn.OK	

def gen_msg(batch_meta, frame_meta, frame_number, image_link, ff_link, uid, name, ts):
    '''
    生成deepstream message_meta结构体用于发送kafka/mqtt消息

    params:
    + batch_meta
    + frame_meta
    + frame_num: 帧序号
    + image_link: fastfdfs返回的图片链接
    + face_feature_link:fastfdfs返回的特征值文件链接
    + uid: 资源任务名
    + name: 
    + ts: 捕获时间戳
    '''
    msg_meta = pyds.alloc_nvds_event_msg_meta()
    msg_meta.bbox.top = 0
    msg_meta.bbox.left = 0
    msg_meta.bbox.width = 0
    msg_meta.bbox.height = 0
    msg_meta.frameId = frame_number
    msg_meta.trackingId = 0
    msg_meta.confidence = 0
    msg_meta = DSFaceMessage.generate_event_msg_meta(msg_meta, image_link, ff_link, uid, name, ts)
    user_event_meta = pyds.nvds_acquire_user_meta_from_pool(batch_meta)

    if user_event_meta:
        user_event_meta.user_meta_data = msg_meta
        user_event_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_EVENT_MSG_META
        # Setting callbacks in the event msg meta. The bindings
        # layer will wrap these callables in C functions.
        # Currently only one set of callbacks is supported.
        pyds.user_copyfunc(user_event_meta, DSFaceMessage.meta_copy_func)
        pyds.user_releasefunc(user_event_meta, DSFaceMessage.meta_free_func)
        pyds.nvds_add_user_meta_to_frame(frame_meta,
                                        user_event_meta)
    else:
        print("Error in attaching event meta to buffer\n")

def comp_replace(face_pool, tpool, frame_meta, obj_meta, tmp_face_bbox):
    '''
    if this face already exist as well as there still space for arcface to infer
    check its states and bbox info
    '''
    
    # print("check replace face - ", obj_meta.object_id)
    if tpool.id_exist(obj_meta.object_id) and face_pool.check_full() is False:
        tmp_data = tpool.get_bbox_by_id(obj_meta.object_id)
        # this face has already sent a message
        # if tmp_face.get_state() == FaceState.FINISH:
        origin_bbox = tmp_data[1]
        if (tmp_face_bbox[0] > origin_bbox[0] * 1.5) or (tmp_face_bbox[1] > origin_bbox[1] * 1.5):
            logger.debug("face-{} get a more clear detection, replace: {} ===> {}".format(obj_meta.object_id, origin_bbox, tmp_face_bbox))
            face = FaceFeature()
            ts = time.time()
            face.set_frame_num(frame_num=frame_meta.frame_num)
            face.set_source_id(source_id=frame_meta.source_id)
            face.set_timestamp(ts=ts)
            face.set_bbox(tmp_face_bbox)
            face.set_state(state=FaceState.TOINFER)
            face_pool.add(id=obj_meta.object_id, face=face)
            tpool.pop(tmp_data)
            logger.debug("face-{} reinit with bbox size ={}. ".format(obj_meta.object_id, tmp_face_bbox))
            face_pool.counter(op='up')
            # tmp_face.set_bbox(tmp_face_bbox)
            # tmp_face.set_state(FaceState.TOINFER)
            # face_pool.counter(op='up')
            return False
    return True

def add_new_face(face_pool, tpool, frame_meta, obj_meta, tmp_face_bbox):
    '''
    check to add a new face to face pool
    '''
    
    if face_pool.id_exist(obj_meta.object_id) == False \
        and tpool.id_exist(obj_meta.object_id) == False \
        and face_pool.check_full() == False \
        and check_bbox_size(obj_meta):
        face = FaceFeature()
        ts = time.time()
        face.set_frame_num(frame_num=frame_meta.frame_num)
        face.set_source_id(source_id=frame_meta.source_id)
        face.set_timestamp(ts=ts)
                                
        face.set_bbox(tmp_face_bbox)
        face.set_state(state=FaceState.TOINFER)
        face_pool.add(id=obj_meta.object_id, face=face)
        logger.debug("face-{} detected, init with bbox size ={}. ".format(obj_meta.object_id, tmp_face_bbox))
        face_pool.counter(op='up')
        return False
    return True

def get_face_feature(face_pool, obj_meta):
    if face_pool.id_exist(obj_meta.object_id):
        temp_face = face_pool.get_face_by_id(obj_meta.object_id)
        print(temp_face.get_state())
        if temp_face.get_state() == FaceState.TOINFER:
            # print("try to get face feature of face-", obj_meta.object_id)
            l_user_meta = obj_meta.obj_user_meta_list
            while l_user_meta:
                try:
                    user_meta = pyds.NvDsUserMeta.cast(l_user_meta.data) 
                except StopIteration:
                    break
                if user_meta and user_meta.base_meta.meta_type==pyds.NvDsMetaType.NVDSINFER_TENSOR_OUTPUT_META: 
                    try:
                        tensor_meta = pyds.NvDsInferTensorMeta.cast(user_meta.user_meta_data)
                    except StopIteration:
                        break
            
                    layer = pyds.get_nvds_LayerInfo(tensor_meta, 0)
                    output = []
                    for i in range(512):
                        output.append(pyds.get_detections(layer.buffer, i))
                    res = np.reshape(output,(512,-1))
                    norm=np.linalg.norm(res)                    
                    normal_array = res / norm
                    temp_face.set_face_feature(normal_array)
                    temp_face.set_state(FaceState.TOSAVE)
                    # print("get face {} feature".format(obj_meta.object_id))
                    try:
                        l_user_meta = l_user_meta.next
                    except StopIteration:
                        break
            face_pool.counter(op='down')

def check_bbox_size(obj_meta):
    bbox = obj_meta.rect_params
    if bbox.width < MIN_FACE_WIDTH or bbox.height < MIN_FACE_HEIGHT:
        return False
    else:
        return True

def update_face(face_pool, tpool, obj_meta, tmp_face_bbox):
    if face_pool.id_exist(obj_meta.object_id) \
        and face_pool.check_full() == False \
        and check_bbox_size(obj_meta):

        tmp_face = face_pool.get_face_by_id(obj_meta.object_id)
        origin_bbox = tmp_face.get_bbox()
        if (tmp_face_bbox[0] - origin_bbox[0]) > 20 or (tmp_face_bbox[1] - origin_bbox[1]) > 20:
            logger.debug("face-{} get a more clear detection, replace: {} ===> {}".format(obj_meta.object_id, origin_bbox, tmp_face_bbox))
            tmp_face.set_bbox(tmp_face_bbox)
            tmp_face.set_state(FaceState.TOINFER)
            face_pool.counter(op='up')
        
        return True
    return False
