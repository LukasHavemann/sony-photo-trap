import requests
import cv2
import threading
import time
from collections import deque
from queue import Queue

camaddress = "http://192.168.122.1:8080/sony/camera" #Older models like NEX-5T, a6000, ... (Also make sure that your remote control app on the cam itself is up to date)
#camaddress = "http://192.168.122.1:10000/sony/camera" #Newer models like a6400, a7iii, ... (Note the missing trailing slash)
sharpnessAverageCount = 1000 #Number of frames to average to get the "base sharpness"
relativeTriggerIncrease = 1.25 #Camera is triggered if the sharpness rises by this factor above the base sharpness


def connect_to_camera():
    #Connect to camera
    print("Connecting to camera...")
    payload = {"version": "1.0", "id": 1, "method": "startRecMode", "params": []}
    r = requests.post(camaddress, json=payload)
    if r.status_code != 200:
        print(f"Could not connect to camera. reason={r.status_code} payload={r.text}")
        exit()
    print("Response: " + str(r.json()))

def get_preview_stream():
    print("Requesting medium res preview stream...")
    payload = {"version": "1.0", "id": 1, "method": "startLiveview", "params": []}
    r = requests.post(camaddress, json=payload)
    if r.status_code != 200:
        print(f"Could not retrieve preview stream. reason={r.status_code} payload={r.text}")
        exit()
    response = r.json()
    print("Response: " + str(response))
    url = response["result"][0]
    print("URL: " + str(url))
    return url

def get_all_api():
    print("Get all APIs...")
    payload = {"version": "1.0", "id": 1, "method": "getAvailableApiList", "params": []}
    r = requests.post(camaddress, json=payload)
    if r.status_code != 200:
        print(f"Could not connect to camera. reason={r.status_code} payload={r.text}")
        exit()
    print("Response: " + str(r.json()))


def analyzeStream(triggerCameraEvent):
    i = 0
    t = time.time()
    focusQueue = deque([])

    print("Start analyzing current sharpness...")
    while running:
        frame = frameQueue.get()
        i += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        mean, std = cv2.meanStdDev(laplacian)
        focus = std[0][0]*std[0][0]
        focusQueue.append(focus)
        if len(focusQueue) > sharpnessAverageCount:
            focusQueue.popleft()
            focusavg = sum(focusQueue)/len(focusQueue)
            if focus/focusavg > relativeTriggerIncrease:
                #This is it, there is something here. Take a pic!
                if not triggerCameraEvent.isSet():
                    triggerCameraEvent.set()
                    print("Trigger!!")
            else:
                if triggerCameraEvent.isSet():
                    triggerCameraEvent.clear()
                    print("Stop triggering")
            if i % 25 == 0:
                print("---")
                tnow = time.time()
                print("Analyzing at " + str(25/(tnow-t)) + " fps")
                print("Base sharpness: " + str(focusavg))
                print("Current sharpness: " + str(focus))
                t = tnow
        else:
            if i % 25 == 0:
                print("Collecting sample frames: " + str(len(focusQueue)) + "/" + str(sharpnessAverageCount))


def take_picture(triggerCameraEvent): 
    while running: 
        if triggerCameraEvent.wait(): 
            print("Request camera to take a picture.")
            time.sleep(3)
            payload = {"version": "1.0", "id": 1, "method": "actTakePicture", "params": []}
            r = requests.post(camaddress, json=payload)
            response = r.json()
            print("Response: " + str(response))
            url = response["result"][0][0]
            print("Downloading from URL: " + str(url))
            r = requests.get(url)
            open("pictures/" + time.strftime("%Y%m%d_%H%M%S") + ".jpg", "wb").write(r.content)
            print("Done.")


running = True
frameQueue = Queue()
triggerCameraEvent = threading.Event()

triggerCameraThread = threading.Thread(target=take_picture, args=[triggerCameraEvent])
triggerCameraThread.start()
analyzeThread = threading.Thread(target=analyzeStream, args=[triggerCameraEvent])
analyzeThread.start()

connect_to_camera()
url = get_preview_stream()

print("Opening video stream...")
cap = cv2.VideoCapture(url)

try:
    while running:
        success, frame = cap.read()
        if success:
            frameQueue.put(frame)
            cv2.imshow('show', frame)
            k = cv2.waitKey(1)
            if k == ord('q'):
                break
        else:
            print(f"reading frame failed {success}")

except KeyboardInterrupt:
    running = False
    
print("waiting for thread shutdown")
#Clean up
cap.release()
cv2.destroyAllWindows()
analyzeThread.join()
triggerCameraThread.join()
