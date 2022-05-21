import cv2
import numpy as np
from PIL import Image


def find_faces(bytes_image: bytes) -> str or bytes:
    """
    The find_faces function accepts an image in the form of a bytes object, finds all faces in the image,
    and returns either 'Too many faces' or 'Face not found' if more than one face is detected or if no face is found
    respectively. If exactly one face is found then it will return the cropped version of that single face.

    :param bytes_image :bytes: Pass the image as bytes to the function
    :return: A string if there is more than one or zero faces in the image, a bytes object otherwise
    """
    image_as_np = np.frombuffer(bytes_image, dtype=np.uint8)

    cv2_image = cv2.imdecode(image_as_np, flags=1)
    gray = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.3,
        minNeighbors=3,
        minSize=(30, 30)
    )

    if len(faces) > 1:
        return 'Too many faces'
    elif len(faces) == 0:
        return 'Face not found'
    else:
        for (x, y, w, h) in faces:
            face = cv2_image[y:y + h + 5, x:x + w + 5]
            output_bytes = cv2.imencode('.jpg', face)[1].tobytes()
            return output_bytes


with open("img.jpg", "rb") as image:
    image_bytes = image.read()

image = Image.open((find_faces(image_bytes)))
image.show()
