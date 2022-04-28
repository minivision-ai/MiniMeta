from aiohttp import web
import socketio
import sys

sys.path.append("./")
from modules.minimeta_kinematics.modules.kinematics.config_skeleton import *
from core.meta_capture.meta_camera import MetaCamera

sio = socketio.AsyncServer(async_mode='aiohttp')
app = web.Application()
sio.attach(app)

joint_config = {
    'joints_visibility_threshold': JOINT_VISIBILITY_THRESHOLD,
    'joints': JOINT_INFOMATION, 'spine_joints': SPINE_JOINTS, 'upper_body_joints': UPPER_BODY_JOINTS,
    'lower_body_joints': LOWER_BODY_JOINTS, 'left_hand_joints': LEFT_HAND_JOINTS, 'right_hand_joints': RIGHT_HAND_JOINTS,
    'limited_fingers': LIMITED_FINGERS, 'limited_first_fingers': LIMITED_FIRST_FINGERS
}
only_upper_body = False   # if True, only update upper body joint rotations, ignore lower body joint rotations.
interval_threshold = 0.5  # if person disappears for more than interval_threshold, vtuber returns to the specific pose.
person_shoulder_ratio = 0.01  # if shoulder_width / image_width < person shoulder ration, ignore the person.
vtuber_cam = MetaCamera(joint_config, only_upper_body, interval_threshold, person_shoulder_ratio, sio)


async def background_task():
    print('background task start')
    await vtuber_cam.run()


@sio.event
async def disconnect_request(sid):
    await sio.disconnect(sid)


@sio.event
async def connect(sid, environ):
    print(f'Client connected: {sid}')


@sio.event
def disconnect(sid):
    print(f'Client disconnected: {sid}')


if __name__ == '__main__':
    sio.start_background_task(background_task)
    app.router.add_static('/', './core/web_visualization')
    web.run_app(
        app, access_log=None, host='127.0.0.1', port=5000, ssl_context=None
    )
