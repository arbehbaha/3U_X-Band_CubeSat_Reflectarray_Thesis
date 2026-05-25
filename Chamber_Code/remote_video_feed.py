import time
import threading

import cv2
from flask import Flask, Response

app = Flask(__name__)

CAMERA_INDEX = 0
JPEG_QUALITY = 80

latest_frame = None
frame_lock = threading.Lock()
stop_event = threading.Event()


def camera_loop():
    global latest_frame

    # Use DirectShow on Windows; usually more stable than MSMF
    cap = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"ERROR: Could not open camera index {CAMERA_INDEX}")
        return

    while not stop_event.is_set():
        ok, frame = cap.read()
        if not ok:
            print("WARNING: failed to read camera frame")
            time.sleep(0.1)
            continue

        ok, jpg = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY],
        )

        if ok:
            with frame_lock:
                latest_frame = jpg.tobytes()

        time.sleep(0.03)  # about 30 FPS max

    cap.release()


def generate_frames():
    while True:
        with frame_lock:
            frame = latest_frame

        if frame is None:
            time.sleep(0.1)
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            frame +
            b"\r\n"
        )

        time.sleep(0.03)


@app.route("/")
def index():
    return """
    <html>
      <head>
        <title>Chamber Camera</title>
      </head>
      <body>
        <h2>Chamber Live View</h2>
        <img src="/video" style="max-width: 100%; height: auto;">
      </body>
    </html>
    """


@app.route("/video")
def video():
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()

    try:
        app.run(host="0.0.0.0", port=5000, threaded=True)
    finally:
        stop_event.set()