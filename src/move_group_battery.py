#!/usr/bin/env python

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("scenefile")
parser.add_argument("--planner-id", dest="planner_id", default="")
parser.add_argument("--pause_after_response",action="store_true")
parser.add_argument("--max_planning_time", type=int, default=10)
args = parser.parse_args()

import subprocess, os

envfile = "/tmp/%s.xml"%os.path.basename(args.scenefile)
subprocess.check_call("python scene2xml.py %s %s"%(args.scenefile, envfile), shell=True)


import roslib
import sys
sys.path.append("/home/joschu/ros/moveit/devel/lib/python2.7/dist-packages")
sys.path.append("/home/ibrahima/moveit/devel/lib/python2.7/dist-packages")
import rospy

from moveit_msgs.msg import *
from moveit_msgs.srv import *
from geometry_msgs.msg import *
from shape_msgs.msg import *
from trajopt_plugin.srv import *

import trajoptpy.math_utils as mu
import trajoptpy.kin_utils as ku

from check_traj import check_traj

import actionlib

import time
import numpy as np
import json
import openravepy as rave, numpy as np
from visualization_msgs.msg import *

ROS_JOINT_NAMES = ['br_caster_rotation_joint', 'br_caster_l_wheel_joint', 'br_caster_r_wheel_joint', 'torso_lift_joint', 'head_pan_joint', 'head_tilt_joint', 'laser_tilt_mount_joint', 'r_shoulder_pan_joint', 'r_shoulder_lift_joint', 'r_upper_arm_roll_joint', 'r_elbow_flex_joint', 'r_forearm_roll_joint', 'r_wrist_flex_joint', 'r_wrist_roll_joint', 'r_gripper_motor_slider_joint', 'r_gripper_motor_screw_joint', 'r_gripper_l_finger_joint', 'r_gripper_l_finger_tip_joint', 'r_gripper_r_finger_joint', 'r_gripper_r_finger_tip_joint', 'r_gripper_joint', 'l_shoulder_pan_joint', 'l_shoulder_lift_joint', 'l_upper_arm_roll_joint', 'l_elbow_flex_joint', 'l_forearm_roll_joint', 'l_wrist_flex_joint', 'l_wrist_roll_joint', 'l_gripper_motor_slider_joint', 'l_gripper_motor_screw_joint', 'l_gripper_l_finger_joint', 'l_gripper_l_finger_tip_joint', 'l_gripper_r_finger_joint', 'l_gripper_r_finger_tip_joint', 'l_gripper_joint', 'torso_lift_motor_screw_joint', 'fl_caster_rotation_joint', 'fl_caster_l_wheel_joint', 'fl_caster_r_wheel_joint', 'fr_caster_rotation_joint', 'fr_caster_l_wheel_joint', 'fr_caster_r_wheel_joint', 'bl_caster_rotation_joint', 'bl_caster_l_wheel_joint', 'bl_caster_r_wheel_joint']
ROS_DEFAULT_JOINT_VALS = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.657967, 0.888673, -1.4311, -1.073419, -0.705232, -1.107079, 2.806742, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.848628, 0.7797, 1.396294, -0.828274, 0.687905, -1.518703, 0.394348, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

def alter_robot_state(robot_state, joints, values):
    d = dict(zip(robot_state.joint_state.name, robot_state.joint_state.position))
    for joint_name, value in zip(joints, values):
        d[joint_name] = value
    unzipped = zip(*d.items())
    robot_state.joint_state.name = unzipped[0]
    robot_state.joint_state.position = unzipped[1]
    
def build_robot_state(joint_names=ROS_JOINT_NAMES, joint_values=ROS_DEFAULT_JOINT_VALS):
    start_state = RobotState()
    start_state.joint_state.name = joint_names
    start_state.joint_state.position = joint_values
    start_state.multi_dof_joint_state.joint_names =  ['world_joint']
    start_state.multi_dof_joint_state.frame_ids = ['odom_combined']
    start_state.multi_dof_joint_state.child_frame_ids = ['base_footprint']
    base_pose = Pose()
    base_pose.orientation.w = 1
    start_state.multi_dof_joint_state.poses = [ base_pose ]
    return start_state

def build_joint_request(jvals, arm, robot, initial_state=build_robot_state(), planner_id=''):
    m = MotionPlanRequest()
    m.group_name = "%s_arm" % arm
    m.start_state = initial_state
    m.planner_id = planner_id
    c = Constraints()
    joints = robot.GetJoints()
    joint_inds = robot.GetManipulator("%sarm"%arm).GetArmIndices()
    c.joint_constraints = [JointConstraint(joint_name=joints[joint_inds[i]].GetName(), position = jvals[i])
                           for i in xrange(len(jvals))]
    jc = JointConstraint()

    m.goal_constraints = [c]
    m.allowed_planning_time = rospy.Duration(args.max_planning_time)
    base_pose = initial_state.multi_dof_joint_state.poses[0]
    base_q = base_pose.orientation
    base_p = base_pose.position
    t = rave.matrixFromPose([base_q.w, base_q.x, base_q.y, base_q.z, base_p.x, base_p.y, base_p.z])
    robot.SetTransform(t)

    return m
    
def build_constraints_request(arm, constraints, initial_state=build_robot_state(), planner_id=''):
    m = MotionPlanRequest()
    m.group_name = "%s_arm" % arm
    m.start_state = initial_state
    m.planner_id = planner_id
    m.goal_constraints = [constraints]
    return m


def build_cart_request(pos, quat, arm, initial_state = build_robot_state(), planner_id=''):
    m = MotionPlanRequest()
    m.group_name = "%s_arm" % arm
    target_link = "%s_wrist_roll_link" % arm[0]
    m.start_state = initial_state
    m.planner_id = planner_id

    pc = PositionConstraint()
    pc.link_name = target_link
    pc.header.frame_id = 'odom_combined'
    pose = Pose()
    pose.position = pos

    pc.constraint_region.primitive_poses = [pose]
    
    sphere = SolidPrimitive()
    sphere.type = SolidPrimitive.SPHERE
    sphere.dimensions = [.01]
    pc.constraint_region.primitives = [ sphere ]
    
    oc = OrientationConstraint()
    oc.link_name = target_link
    oc.header.frame_id = 'odom_combined'
    oc.orientation = quat
    c = Constraints()
    c.position_constraints = [ pc ]
    c.orientation_constraints = [ oc ]
    m.goal_constraints = [ c ]
    m.allowed_planning_time = rospy.Duration(args.max_planning_time)
    return m
    
def robot_state_from_pose_goal(xyz, xyzw, arm, robot, initial_state = build_robot_state()):
    manip = robot.GetManipulator(arm + "arm")
    joint_solutions = ku.ik_for_link(rave.matrixFromPose(np.r_[xyzw[3], xyzw[:3], xyz]),
                                     manip, "%s_wrist_roll_link"%arm[0], 1, True)

    if len(joint_solutions) == 0:
        return None
    joints = robot.GetJoints()
    joint_inds = robot.GetManipulator("%sarm"%arm).GetArmIndices()
    joint_names = [joints[joint_inds[i]].GetName() for i in xrange(len(joint_solutions[0]))]
    joint_values = [joint_solutions[0][i] for i in xrange(len(joint_solutions[0]))]
    new_state = alter_robot_state(initial_state, joint_names, joint_values)
    return new_state

def test_plan_to_pose(xyz, xyzw, leftright, robot, initial_state = build_robot_state(), planner_id='', target_link="%s_gripper_tool_frame"):
    manip = robot.GetManipulator(leftright + "arm")

    base_pose = initial_state.multi_dof_joint_state.poses[0]
    base_q = base_pose.orientation
    base_p = base_pose.position
    t = rave.matrixFromPose([base_q.w, base_q.x, base_q.y, base_q.z, base_p.x, base_p.y, base_p.z])
    robot.SetTransform(t)

    joint_solutions = ku.ik_for_link(rave.matrixFromPose(np.r_[xyzw[3], xyzw[:3], xyz]), manip, target_link%leftright[0], 
                         1, True)

    if len(joint_solutions) == 0:
        print "pose is not reachable"
        return None

    m = build_joint_request(joint_solutions[0], leftright, robot, initial_state, planner_id=planner_id)

    response = None
    try:
        t1 = time.time()
        response = get_motion_plan(m).motion_plan_response
        t2 = time.time()
    except rospy.service.ServiceException:
        pass
    # assert isinstance(response, MotionPlanResponse)

    if args.pause_after_response:
        raw_input("press enter to continue")

    if response is not None:
        if response.error_code.val != 1:
            print "Planner returned error code", response.error_code.val
        traj =  [list(jtp.positions) for jtp in response.trajectory.joint_trajectory.points]
        return dict(returned = True, safe = not check_traj(traj, manip, 100), traj = traj, planning_time = response.planning_time.to_sec(), error_code = response.error_code.val)
    else:
        return dict(returned = False)
    
def update_rave_from_ros(robot, ros_values, ros_joint_names):
    inds_ros2rave = np.array([robot.GetJointIndex(name) for name in ros_joint_names])
    good_ros_inds = np.flatnonzero(inds_ros2rave != -1) # ros joints inds with matching rave joint
    rave_inds = inds_ros2rave[good_ros_inds] # openrave indices corresponding to those joints
    rave_values = [ros_values[i_ros] for i_ros in good_ros_inds]
    robot.SetJointValues(rave_values[:20],rave_inds[:20])
    robot.SetJointValues(rave_values[20:],rave_inds[20:])
    
get_motion_plan = None
env = None
markerpub = None

def warehouse_test(initial_state_id, goal_constraint_starts_with):
    from warehouse_utils import MoveitWarehouseDatabase
    constraints_db = MoveitWarehouseDatabase('moveit_constraints')
    states_db = MoveitWarehouseDatabase('moveit_robot_states')
    initial_state = states_db.get_message(RobotState, state_id=initial_state_id)
    query = {'constraints_id':{"$regex":"^%s.*" % goal_constraint_starts_with}}
    constraints = constraints_db.get_messages(Constraints, query)
    print initial_state
    print len(constraints)
    for c in constraints:
        print pose_constraints_to_xyzquat(c)

def warehouse_scene_pairwise_test(initial_state_id, goal_constraint_starts_with, robot, arm="right", planner_id=""):
    from warehouse_utils import MoveitWarehouseDatabase
    constraints_db = MoveitWarehouseDatabase('moveit_constraints')
    states_db = MoveitWarehouseDatabase('moveit_robot_states')
    initial_state = states_db.get_message(RobotState, state_id=initial_state_id)
    query = {'constraints_id':{"$regex":"^%s.*" % goal_constraint_starts_with}}
    constraints = constraints_db.get_messages(Constraints, query)
    print "Got", len(constraints), "goal constraints from the warehouse"
    initial_states = [initial_state]
    positions, quats = [], []
    results = []
    base_pose = initial_state.multi_dof_joint_state.poses[0]
    base_q = base_pose.orientation
    base_p = base_pose.position
    t = rave.matrixFromPose([base_q.w, base_q.x, base_q.y, base_q.z, base_p.x, base_p.y, base_p.z])
    robot.SetTransform(t)
    update_rave_from_ros(robot, initial_state.joint_state.position, initial_state.joint_state.name)

    for c in constraints:
        pos, quat = pose_constraints_to_xyzquat(c)
        post = (pos.x, pos.y, pos.z)
        quatt = (quat.x, quat.y, quat.z, quat.w)
        positions.append(post)
        quats.append(quatt)
        state = robot_state_from_pose_goal(post, quatt, arm, robot, initial_state)
        if state:
            initial_states.append(state)
    for start_state in initial_states:
        update_rave_from_ros(robot, start_state.joint_state.position, start_state.joint_state.name)
        for posit, quater in zip(positions, quats):
            result = test_plan_to_pose(posit, quater, arm, robot, start_state, planner_id, "%s_wrist_roll_link")
            if result is not None:
                results.append(result)
    process_results(results)

def pose_constraints_to_xyzquat(constraints):
    """
    Converts a pose goal in constraints form to a position and quaternion
    """
    pos = constraints.position_constraints[0].constraint_region.primitive_poses[0].position
    quat = constraints.orientation_constraints[0].orientation
    return (pos, quat)

def publish_marker(x, y, z):
    global markerpub
    marker = Marker()
    marker.header.frame_id='odom_combined'
    marker.type=1
    marker.pose.position.x=x
    marker.pose.position.y=y
    marker.pose.position.z=z
    marker.pose.orientation.w=1
    marker.scale.x = marker.scale.y = marker.scale.z=0.1
    marker.id = (x,y,z).__hash__()% 100
    markerpub.publish(marker)

def main():
    global get_motion_plan, env, robot, markerpub
    if rospy.get_name() == "/unnamed":
        rospy.init_node("move_group_battery")
    env = rave.Environment()
    env.Load("robot/pr2-beta-static.zae")
    loadsuccess = env.Load(envfile)    
    assert loadsuccess
    markerpub = rospy.Publisher('battery_targets', Marker)
    get_motion_plan = rospy.ServiceProxy('plan_kinematic_path', GetMotionPlan)    
    print "waiting for plan_kinematic_path"
    get_motion_plan.wait_for_service()
    print "ok"
    
    robot = env.GetRobots()[0]
    update_rave_from_ros(robot, ROS_DEFAULT_JOINT_VALS, ROS_JOINT_NAMES)
  
    xs, ys, zs = np.mgrid[.35:.65:.05, 0:.5:.05, .8:.9:.1]

    results = []
    for (x,y,z) in zip(xs.flat, ys.flat, zs.flat):
        result = test_plan_to_pose([x,y,z], [0,0,0,1], "left", robot, planner_id=args.planner_id)
        # publish_marker(x, y, z)
        if result is not None: results.append(result)
    process_results(results)

def process_results(results):
    success_count, fail_count, no_answer_count, timeouts= 0,0,0,0
    for result in results:
        if result["returned"] and result["error_code"] == 1:
            if result["safe"] : success_count += 1
            else: fail_count += 1
        else:
            no_answer_count += 1
    print "success count:", success_count
    print "fail count:", fail_count
    print "no answer count:", no_answer_count

def main_warehouse():
    global get_motion_plan, env, robot, markerpub
    if rospy.get_name() == "/unnamed":
        rospy.init_node("move_group_battery")
    env = rave.Environment()
    env.Load("robots/pr2-beta-static.zae")
    loadsuccess = env.Load(envfile)    
    assert loadsuccess
    markerpub = rospy.Publisher('battery_targets', Marker)
    get_motion_plan = rospy.ServiceProxy('plan_kinematic_path', GetMotionPlan)    
    print "waiting for plan_kinematic_path"
    get_motion_plan.wait_for_service()
    print "ok"
    
    robot = env.GetRobots()[0]
    update_rave_from_ros(robot, ROS_DEFAULT_JOINT_VALS, ROS_JOINT_NAMES)
    warehouse_scene_pairwise_test("pr2.countertop.initial", "countertop", robot, arm="right", planner_id="")


# main()
# warehouse_test('pr2.tunnel.initial', "tunnel")
main_warehouse()
