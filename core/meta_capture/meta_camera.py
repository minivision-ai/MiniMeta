import cv2
import math
import time
import asyncio
import socketio
import numpy as np
from .meta_face import MetaFace

from modules.minimeta_kinematics.modules.kinematics.update_skeleton import UpdateSkeleton
from modules.minimeta_pose.modules.pose_estimation_2d.MediaPipeONNX import Holistic
from modules.minimeta_pose.modules.human_3d_position_estimation.Conv import Human3DPositionEstimation
from modules.minimeta_pose.modules.utils.utils import get_upper_body


class MetaCamera:
    def __init__(self, joint_config: dict, only_upper_body: bool, interval_threshold: float, person_shoulder_ratio: float, sio: socketio.AsyncServer):
        self.sio = sio
        self.interval_threshold = interval_threshold   
        self.person_shoulder_ratio = person_shoulder_ratio
        self.only_upper_body = only_upper_body
        self.update_skeleton = UpdateSkeleton(joint_config, only_upper_body=only_upper_body)
        self.update_face = MetaFace(use_iris_tracking=True)
        self.pose_rotations = self.update_skeleton.pose_joint_rotation
        self.holistic = Holistic(
            static_image_mode=False,       # set False to use filter and tracker.
            pose_model_complexity=1,      # set 0, 1 or 2 to choose lite, full or heavy model.
            hand_model_complexity=1,      # set 0 or 1 to choose lite or full model.
            enable_segmentation=False     # set True to return body segmentation mask.
        )
        self.human_3d_position_estimation = Human3DPositionEstimation(focal_x=1., focal_y=1., scale_depth=0.5)

    async def run(self):
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        leave_time = 0    # the time when person leaves
        leave_state = True  # when person leaves, leave_state is True.
        while True:
            loop = asyncio.get_running_loop()
            success, image = await loop.run_in_executor(None, cap.read)

            if not success:
                if cap.get(cv2.CAP_PROP_POS_FRAMES) == cap.get(cv2.CAP_PROP_FRAME_COUNT):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    print("Ignoring empty camera frame.")
                continue

            # process image
            image = cv2.flip(image, 1)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            h, w, _ = image.shape
            image_size_batch = [[w, h]]

            # get detection results
            detection_results = self.holistic(image_rgb)

            body_world_lmks = detection_results[
                'pose_world_landmarks'] if detection_results['pose_world_landmarks'] is not None  else None

            cv2.imshow('MiniMeta', image)
            if cv2.waitKey(1) & 0xFF == 27:
                break

            # judge shoulder width
            if body_world_lmks is not None:
                image_h, image_w, _ = image.shape
                body_local_lmks = detection_results['pose_landmarks']
                shoulder_width = math.sqrt((body_local_lmks[11][0] - body_local_lmks[12][0])**2 +
                                           (body_local_lmks[11][1] - body_local_lmks[12][1])**2 +
                                           (body_local_lmks[11][2] - body_local_lmks[12][2])**2)
                # shoulder_flag False: person is far from the camera, ignore the person.
                shoulder_flag = True if shoulder_width > self.person_shoulder_ratio*image_w else False
            else:
                shoulder_flag = False

            results = {}
            # compute leave interval and recover to the specific pose
            if body_world_lmks is None and not leave_state:
                leave_time = time.time() if leave_time == 0 else leave_time
                current_time = time.time()

                leave_interval = current_time - leave_time
                if leave_interval > self.interval_threshold:
                    results['body_rotation'] = self.pose_rotations
                    results['blendshapes'] = None
                    leave_state = True

            # update rotation and blendshape
            if shoulder_flag:
                body_rotation = self.update_skeleton(detection_results)
                face_blendshape, head_pose = self.update_face(image_rgb, body_rotation)
                if not self.only_upper_body:
                    lmks_pose = detection_results['pose_landmarks'][:, :2]
                    lmks_upper = get_upper_body(lmks_pose)
                    lmks_upper_batch = lmks_upper[np.newaxis, :, :]
                    translation = self.human_3d_position_estimation(lmks_upper_batch, image_size_batch)
                    results['translation'] = [translation[0][0], translation[0][1], translation[0][2]]
                else:
                    translation = None
                    results['translation'] = translation

                body_rotation['neck']['rotation'] = head_pose
                results['body_rotation'] = body_rotation
                results['blendshapes'] = face_blendshape


                leave_time = 0
                leave_state = False

            if results != {}:
                await self.sio.emit('data', results)

        cap.release()
