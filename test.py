from qrdet import QRDetector
import cv2

detector = QRDetector(model_size='s')

# Mở video đầu vào
input_video = './Video_20261009112056799.mp4'
cap = cv2.VideoCapture(input_video)

# Lấy thông số video
fps = cap.get(cv2.CAP_PROP_FPS)
width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Tạo VideoWriter để lưu video đầu ra
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter('./output.mp4', fourcc, fps, (width, height))

while True:
    ret, frame = cap.read()
    if not ret:
        break

    detections = detector.detect(image=frame, is_bgr=True)

    for detection in detections:
        # Ép kiểu sang int
        x1, y1, x2, y2 = map(int, detection['bbox_xyxy'])
        confidence = detection['confidence']

        # Vẽ bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color=(0, 255, 0), thickness=2)

        # Ghi độ tin cậy
        cv2.putText(frame, f'{confidence:.2f}', (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    out.write(frame)

cap.release()
out.release()
print("Đã lưu video kết quả tại: ./output.mp4")
