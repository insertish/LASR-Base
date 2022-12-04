#!/usr/bin/env python3
# from genericpath import exists
import rospy
import rospkg

from face_detection.srv import FaceDetectionPCL, FaceDetectionPCLResponse, FaceDetectionPCLRequest
import os
import numpy as np
import cv2
import pickle
import imutils
from cv_bridge3 import CvBridge
from common_math import bb_to_centroid

from lasr_perception_server.msg import DetectionPCL

NET = os.path.join(rospkg.RosPack().get_path('face_detection'), 'nn4', "nn4.small2.v1.t7")
PROTO_PATH = os.path.join(rospkg.RosPack().get_path('face_detection'), 'caffe_model', "deploy.prototxt")
MODEL_PATH = os.path.join(rospkg.RosPack().get_path('face_detection'), 'caffe_model',
                          "res10_300x300_ssd_iter_140000.caffemodel")
OUTPUT_PATH = os.path.join(rospkg.RosPack().get_path('face_detection'), "output")

CONFIDENCE_THRESHOLD = 0.5

# TODO: rfactor -> make common stuff between normal face detection server and pcl face detection server

class FaceDetectionServer:
    """
    A Server for performing face detection and classification with OpenCV.
    """

    def __init__(self):

        # Load network and models.
        self.detector = cv2.dnn.readNetFromCaffe(PROTO_PATH, MODEL_PATH)
        self.embedder = cv2.dnn.readNetFromTorch(NET)

        # Bridge for conversion between cv2 and sensor_msgs/Image, and vice versa.
        self.bridge = CvBridge()
        # delete_model()
        self.recognizer = None
        self.le = None

    def load_model(self):
        if not os.path.exists(os.path.join(OUTPUT_PATH, "recognizer.pickle")):
            self.recognizer = None
        else:
            with open(os.path.join(OUTPUT_PATH, "recognizer.pickle"), "rb") as fp:
                self.recognizer = pickle.loads(fp.read())
        if not os.path.exists(os.path.join(OUTPUT_PATH, "le.pickle")):
            self.le = None
        else:
            with open(os.path.join(OUTPUT_PATH, "le.pickle"), "rb") as fp:
                self.le = pickle.loads(fp.read())
                print(self.le.classes_)

        if self.recognizer and self.le:
            return True

    def __call__(self, req):
        """
        Core method of server.
        """

        if not self.recognizer or not self.le:
            if not self.load_model():
                raise rospy.ServiceException("No model to load from.")

        # Construct empty response.
        if not isinstance(req, FaceDetectionPCLRequest):
            raise rospy.ServiceException("Wrong request type.")

        response = FaceDetectionPCLResponse()

        # Extract rgb image from pointcloud
        cv_image = np.fromstring(req.cloud.data, dtype=np.uint8)
        cv_image = cv_image.reshape(req.cloud.height, req.cloud.width, 32)
        cv_image = cv_image[:, :, 16:19]

        # Ensure array is contiguous
        cv_image = np.ascontiguousarray(cv_image, dtype=np.uint8)

        # Resize for input to the network.
        cv_image = imutils.resize(cv_image, width=600)
        h, w = cv_image.shape[:2]

        # Construct a blob from the image.
        blob = cv2.dnn.blobFromImage(
            cv2.resize(cv_image, (300, 300)),
            1.0, (300, 300),
            (104.0, 177.0, 123.0),
            swapRB=False, crop=False
        )

        # Apply OpenCV's deep learning-based face detector to localize
        # faces in the input image
        self.detector.setInput(blob)
        detections = self.detector.forward()

        print(detections, 'the face detections')

        # Iterate detections
        for detection in detections[0][0]:

            # Extract confidence.
            confidence = detection[2]

            # Ensure confidence of detection is above specified threshold.
            if confidence > CONFIDENCE_THRESHOLD:

                # Compute bounding box coordinates.
                face_bb = detection[3:7] * np.array([w, h, w, h])
                x1, y1, x2, y2 = face_bb.astype("int")

                # Extract face.
                face = cv_image[y1:y2, x1:x2]

                face_width, face_height = face.shape[:2]

                # Ensure face width and height are sufficiently large.
                if face_width < 20 or face_height < 20: continue

                # Construct a blob from the face.
                faceBlob = cv2.dnn.blobFromImage(
                    face, 1.0 / 255, (96, 96),
                    (0, 0, 0),
                    swapRB=True, crop=False
                )

                # Pass blob through face embedding model
                # to obtain the 128-d quantification of the face.
                self.embedder.setInput(faceBlob)
                vec = self.embedder.forward()

                # Perform classification to recognise the face.
                predictions = self.recognizer.predict_proba(vec)[0]
                j = np.argmax(predictions)
                prob = predictions[j]
                name = self.le.classes_[j]
                # Append the detection to the response.

                centroid = bb_to_centroid(req.cloud, x1, y1, x2 - x1, y2 - y1)
                curr_detection = DetectionPCL()
                curr_detection.name = name
                curr_detection.confidence = prob
                curr_detection.bb = [x1, y1, x2, y2]
                curr_detection.centroid = centroid
                response.detections.append(curr_detection)
        return response


if __name__ == "__main__":
    rospy.init_node("pcl_face_detection_server")
    server = FaceDetectionServer()
    service_pcl = rospy.Service('pcl_face_detection_server', FaceDetectionPCL, server)
    rospy.loginfo("Face Detection Service initialised")
    rospy.spin()
