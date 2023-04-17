from .pv_data import EVENT_INFO, EventData, EventFinished, backImages
from .message import *

class PVEventProbe:
    def pgie_src_pad_buffer_probe(pad, info, u_data):
        """
        过滤person、car之外的检测框
        """
        # logger.debug("PVEventProbe | probe triggered.")
        perf_data = u_data[0]
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            logger.error("Unable to get GstBuffer ")
            return

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        # logger.debug("PVEventProbe | l_frame status:{}".format(l_frame is not None))
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration as e:
                logger.error(e)
                break

            l_obj = frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                    # logger.debug("PVEventProbe | class_id:{} confidence:{}".format(obj_meta.class_id, obj_meta.confidence))
                    l_obj = l_obj.next
                    if obj_meta.class_id not in DETECT_OBJECTS or obj_meta.confidence < 0.85:
                        pyds.nvds_remove_obj_meta_from_frame(frame_meta, obj_meta)
                    
                except StopIteration as e:
                    logger.error(e)
                    break

            stream_index = frame_meta.pad_index
            perf_data.update_fps(stream_index)
            try:
                l_frame = l_frame.next
            except StopIteration as e:
                logger.error(e)
                break
        return Gst.PadProbeReturn.OK

    def analytics_src_pad_buffer_probe(pad, info, srcm):
        """
        Probe attached to analytics src pad.

        This probe will extract analytics data from user-meta data.

        """
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            logger.error("Unable to get GstBuffer ")
            return

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration as e:
                logger.error(e)
                break

            source_idx = frame_meta.source_id
            frame_number = frame_meta.frame_num
            l_obj = frame_meta.obj_meta_list
            ret, source = PVEventProbe.get_source_by_index(srcm, source_idx)
            moving_state = "MOVE"
            if ret:
                try:
                    moving_state, ptz_data = source.get_current_state()
                except Exception as e:
                    logger.warning("fail to get ptz state : {}".format(e))
                # print(moving_state, "  ", ptz_data)
            # 以下情况任意一个发生时，跳过，处理batch_meta内下一个数据
            # 1、未找到source_idx源 | 2、当前处于移动状态 | 3、没有检测目标 | 4、检查任务状态
            next_needed = (not ret) or (moving_state == "MOVE") or (not l_obj)
            # logger.debug("PVEventProbe | analytic  [source find:{}, move state:{} obj:{}]".
            #              format(ret, moving_state, bool(l_obj)))
            if next_needed:
                try:
                    l_frame = l_frame.next
                except StopIteration as e:
                    logger.error(e)
                    break
                continue

            time_now = time.time()
            event_data = EventData(time_now, ptz_data.ptz_id, events=[])
            while l_obj:
                try:
                    obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration as e:
                    logger.error(e)
                    break

                l_user_meta = obj_meta.obj_user_meta_list
                # logger.debug("obj_meta: {}".format(obj_meta))
                # logger.debug("obj_meta: idx:{} ptz_id:{} track_id:{} class_id:{} bbox:[{}, {}, {}, {}]".format(
                #    source.idx,
                #    ptz_data.ptz_id, obj_meta.object_id, obj_meta.class_id,
                #    obj_meta.rect_params.left, obj_meta.rect_params.top,
                #    obj_meta.rect_params.left + obj_meta.rect_params.width,
                #    obj_meta.rect_params.top + obj_meta.rect_params.height))
                # logger.debug("l_user_meta status: {}".format(bool(l_user_meta)))
                while l_user_meta:
                    try:
                        user_meta = pyds.NvDsUserMeta.cast(l_user_meta.data)
                    except StopIteration as e:
                        logger.error(e)
                        break

                    if user_meta.base_meta.meta_type == pyds.nvds_get_user_meta_type(
                            "NVIDIA.DSANALYTICSOBJ.USER_META"):
                        try:
                            user_meta_data = pyds.NvDsAnalyticsObjInfo.cast(user_meta.user_meta_data)
                            anainfo = AnaInfo(roi=user_meta_data.roiStatus, dir=user_meta_data.dirStatus)
                            # frame = get_frame(gst_buffer, frame_meta)
                            # logger.debug("----------- 4 ----------{}".format(user_meta_data.roiStatus))
                            event_info = EVENT_INFO(track_id=str(obj_meta.object_id),
                                                    class_id=str(obj_meta.class_id),
                                                    detect_bbox=[
                                                        obj_meta.rect_params.left, obj_meta.rect_params.top,
                                                        obj_meta.rect_params.left + obj_meta.rect_params.width,
                                                        obj_meta.rect_params.top + obj_meta.rect_params.height
                                                    ],
                                                    analytic_info=anainfo,
                                                    frame_num=frame_number)
                            event_data.add_event(event_info)
                            # logger.debug("source_id: {} | track_id:{}, class_id:{}\n bbox:[{},{},{},{}]".format(
                            #     frame_meta.source_id, obj_meta.object_id, obj_meta.class_id,
                            #     obj_meta.rect_params.left, obj_meta.rect_params.top,
                            #     obj_meta.rect_params.width, obj_meta.rect_params.height
                            # ))

                        except StopIteration as e:
                            logger.error(e)
                            break
                    try:
                        l_user_meta = l_user_meta.next
                    except StopIteration as e:
                        logger.error(e)
                        break
                try:
                    l_obj = l_obj.next
                except StopIteration:
                    break

            # logger.debug("events data: {} | {}".format(len(event_data.events), event_data.events))

            source.feed_data(event_data)

            try:
                l_frame = l_frame.next
            except StopIteration as e:
                logger.error(e)
                break

        return Gst.PadProbeReturn.OK

    def msg_sink_pad_buffer_probe(pad,info,srcm):
        """
        probe to add info into msg-meta data.
        """
        global event_finished, bg_images
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
            source_id = frame_meta.source_id
            messages = None
            # print(frame_number, "  ", source_id)

            # 消息处置
            ret, source = PVEventProbe.get_source_by_index(srcm, source_id)
            if not ret:
                logger.warning("get_source_by_index:{} error".format(source_id))
            else:
                try:
                    messages = source.pop_events()
                except Exception as e:
                    logger.warning("source: {} fail to pop events.".format(source_id))
            
            if messages:
                for msg in messages:
                    catch_time, ptz_id, track_id, frame_num, event_label, process_data, process_func = msg
                    # logger.debug("current frame: {}, recorded frame: {}, result of checking: {}".format(frame_number, frame_num, event_finished.check(id=track_id, label=event_label)))
                    logger.debug("current frame: {}, recorded frame: {}".format(
                        frame_number, frame_num))
                    
                    # if bg_images.check_exist(source_id=source_id, frame_num=frame_num) and event_finished.check(id=track_id, label=event_label):
                    if bg_images.check_exist(source_id=source_id, frame_num=frame_num):
                        frame = bg_images.get_frame(source_id=source_id, frame_num=frame_num)

                    # if frame_num >= frame_number - 1 and frame_num <= frame_number + 1 and event_finished.check(id=track_id, label=event_label):
                        # event_finished.add(id=track_id, label=event_label)
                        # frame = get_frame(gst_buffer, frame_meta)
                        # print(frame_number, "----------", process_data)
                        fdfs_url = process_func(frame.copy(), process_data, frame_number)
                        logger.info("  - time:{} | ptz_id:{} | track_id:{} | event_label:{} | img_url:{}".
                                    format(catch_time, ptz_id, track_id, event_label, fdfs_url))

                        uid = srcm.get_id_by_idx(source_id)

                        msg_meta = pyds.alloc_nvds_event_msg_meta()
                        msg_meta.bbox.top = 0
                        msg_meta.bbox.left = 0
                        msg_meta.bbox.width = 0
                        msg_meta.bbox.height = 0
                        msg_meta.frameId = frame_number
                        # print(frame_meta.frame_num)
                        msg_meta.trackingId = long_to_uint64(frame_meta.frame_num)
                        msg_meta.confidence = 0
                        msg_meta = DSCarPTZMessage.generate_event_msg_meta(
                            msg_meta, catch_time, uid, ptz_id, event_label, fdfs_url)
                        user_event_meta = pyds.nvds_acquire_user_meta_from_pool(batch_meta)

                        if user_event_meta:
                            user_event_meta.user_meta_data = msg_meta
                            user_event_meta.base_meta.meta_type = pyds.NvDsMetaType.NVDS_EVENT_MSG_META
                            # Setting callbacks in the event msg meta. The bindings
                            # layer will wrap thframe_numese callables in C functions.
                            # Currently only one set of callbacks is supported.
                            pyds.user_copyfunc(
                                user_event_meta, DSCarPTZMessage.meta_copy_func)
                            pyds.user_releasefunc(
                                user_event_meta, DSCarPTZMessage.meta_free_func)
                            pyds.nvds_add_user_meta_to_frame(frame_meta, user_event_meta)
                        else:
                            print("Error in attaching event meta to buffer\n")


            try:
                l_frame = l_frame.next
            except StopIteration:
                break

        return Gst.PadProbeReturn.OK

    def frame_copy_save_probe(pad, info, u_data):
        """
        过滤person、car之外的检测框
        """
        global bg_images
        # logger.debug("PVEventProbe | probe triggered.")
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            logger.error("Unable to get GstBuffer ")
            return

        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        # logger.debug("PVEventProbe | l_frame status:{}".format(l_frame is not None))
        while l_frame is not None:
            try:
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration as e:
                logger.error(e)
                break

            source_id = frame_meta.source_id
            frame_num = frame_meta.frame_num
            if not bg_images.check_exist(source_id, frame_num):
                frame_copy = get_frame(gst_buffer, frame_meta)
                bg_images.add_image(source_id, frame_num, frame_copy)
        
            try:
                l_frame = l_frame.next
            except StopIteration as e:
                logger.error(e)
                break
        return Gst.PadProbeReturn.OK
    
    @classmethod
    def get_source_by_index(cls, srcm, source_idx):
        is_source_enable = True
        source_id = srcm.get_id_by_idx(source_idx)

        if source_id:
            ret, error_message, source = srcm.get(source_id)
            if ret:
                return True, source
        return False, None

