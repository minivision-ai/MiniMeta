# -*- coding: utf-8 -*-
import sys
import numpy as np
from three.math import Quaternion, Euler

# submodule_dir = "../../"
# sys.path.append(submodule_dir)
from modules.minimeta_face.modules.face_detection.BlazeFace import FaceDetection
from modules.minimeta_face.modules.face_lmks_detection.PFLD import FaceLmksDetection
from modules.minimeta_face.modules.blendshapes_detection.MobileNetV3 import BlendshapesDetection

from modules.minimeta_face.modules.head_pose_estimation.MobileNetV2 import HeadPoseEstimation
from modules.minimeta_face.modules.filters.one_euro_filter import ListFilter
from modules.minimeta_face.modules.utils.rotation import radian2angle, angle2radian
from modules.minimeta_face.modules.utils.utils import landmarks_to_bbox


class MetaFace:
    def __init__(self, use_iris_tracking):
        # initialize detectors
        self.face_detection = FaceDetection(min_detection_confidence=0.5, model_selection=1)
        self.face_lmks_detection = FaceLmksDetection(use_iris_tracking, model_selection=1)
        self.blendshapes_detection = BlendshapesDetection(use_iris_tracking)
        self.blendshape_names = self.blendshapes_detection.blendshapes_names

        self.head_pose_estimation = HeadPoseEstimation(model_selection=1)
        self.filter = ListFilter(3, frequency=30, min_cutoff=0.1, beta=0.1, derivate_cutoff=1.)

    def __call__(self, image, joint_rotation):
        blendshape_dict = None
        head_pose = [0, 0, 0, 1]

        # detect faces
        results = self.face_detection(image)

        if results is not None:
            max_bbox = results[0]['bbox']
            landmarks = self.face_lmks_detection(image, max_bbox)

            blendshape_dict = self.get_blendshapes(image, landmarks)
            head_pose = self.get_head_pose(image, landmarks, joint_rotation)

        return blendshape_dict, head_pose

    def get_blendshapes(self, image, landmarks):
        blendshapes = self.blendshapes_detection(image, landmarks)
        blendshape_dict = {}
        for i in range(len(self.blendshape_names)):
            blendshape_dict[self.blendshape_names[i]] = float(blendshapes[i])
        return blendshape_dict

    def get_head_pose(self, image, landmarks, joint_rotation):
        max_bbox = landmarks_to_bbox(landmarks)
        pose = self.head_pose_estimation(image, max_bbox)*np.array([0.5, 0.5, 0.7])

        pose_angle = [radian2angle(angle) for angle in pose]
        pose_angle = self.filter(pose_angle)
        pose_rad = [angle2radian(angle) for angle in pose_angle]

        head_rotation = Quaternion().setFromEuler(Euler(*pose_rad, order=Euler.RotationOrders.YXZ))
        spine_mid_up_rotation = joint_rotation['spine_mid_up']['rotation']
        spine_mid_up_rotation = Quaternion(*spine_mid_up_rotation)
        head_rotation.multiply(spine_mid_up_rotation.inverse())
        return [head_rotation.x, head_rotation.y, head_rotation.z, head_rotation.w]
