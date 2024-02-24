#!/usr/bin/env python
import rospy
import sys

from sensor_msgs.msg import Image
from lasr_vision_msgs.srv import DeepFaceDetection

if len(sys.argv) < 2:
    print("Usage: rosrun lasr_vision_deepface extract_for_topic.py /image_raw/1")
    exit(0)

rospy.init_node("extract_for_topic", anonymous=True)
msg = rospy.wait_for_message(sys.argv[1], Image)

rospy.wait_for_service("/deepface/detect")

extract = rospy.ServiceProxy("/deepface/detect", DeepFaceDetection)
extract(msg, 'VGG-Face')
