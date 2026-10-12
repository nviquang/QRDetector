import cv2
import os
import datetime
import time

# === CẤU HÌNH ===
# Copy file .env.example thành .env và điền thông tin thực
import dotenv  # pip install python-dotenv
dotenv.load_dotenv()
USERNAME = os.getenv("RTSP_USERNAME", "admin")
PASSWORD = os.getenv("RTSP_PASSWORD", "")       # Đặt trong .env, không hardcode
IP       = os.getenv("RTSP_IP", "192.168.1.19")
PORT     = int(os.getenv("RTSP_PORT", "554"))

# Thư mục gốc lưu dữ liệu (đặt cùng cấp với file này)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMAGES_DIR = os.path.join(DATA_DIR, "images")
VIDEOS_DIR = os.path.join(DATA_DIR, "videos")

# === TẠO CÁC THƯ MỤC NẾU CHƯA TỒN TẠI ===
def ensure_data_dirs():
    os.makedirs(IMAGES_DIR, exist_ok=True)
    os.makedirs(VIDEOS_DIR, exist_ok=True)

# === TẠO TÊN FILE DUY NHẤT (tránh trùng trong cùng 1 giây) ===
def unique_path(directory, extension):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = os.path.join(directory, f"{timestamp}.{extension}")
    counter = 2
    while os.path.exists(filepath):
        filepath = os.path.join(directory, f"{timestamp}_{counter}.{extension}")
        counter += 1
    return filepath

ensure_data_dirs()

# Tạo URL RTSP
rtsp_url = f"rtsp://{USERNAME}:{PASSWORD}@{IP}:{PORT}/cam/realmonitor?channel=1&subtype=0"

print(f"Đang kết nối tới: {rtsp_url}")

# === MỞ LUỒNG VIDEO ===
cap = cv2.VideoCapture("./Video_20261009095403726.mp4")

# Kiểm tra kết nối
if not cap.isOpened():
    print("Không thể mở luồng RTSP. Kiểm tra lại URL, mật khẩu và kết nối mạng.")
    exit()

print("Đã kết nối thành công!")
print("Nhấn 'Space' để chụp ảnh | 's' để bắt đầu quay | 'd' để dừng và lưu video | 'q' để thoát.")

# === TRẠNG THÁI GHI HÌNH ===
writer = None          # VideoWriter hiện tại (None nếu không đang ghi)
current_video_file = None  # đường dẫn video đang ghi
recording = False

# Biến hiển thị thông báo trên màn hình
status_message = ""
status_color = (0, 0, 0)
status_until_time = 0  # thời điểm thông báo hết hạn (thời gian thực, giây)

# === VÒNG LẶP ĐỌC VÀ HIỂN THỊ ===
frame_count = 0
while True:
    ret, frame = cap.read()

    if not ret:
        print("Không đọc được frame (có thể mất kết nối).")
        break

    frame_count += 1
    # Bản hiển thị: copy frame gốc rồi vẽ chữ thông báo lên
    display = frame.copy()

    # Vẽ hướng dẫn sử dụng (góc trên cùng)
    overlay_text = "Space: chup anh | s: quay | d: dung & luu | q: thoat"
    cv2.putText(display, overlay_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    # Hiển thị trạng thái đang quay (màu đỏ, chớp nháy)
    if recording:
        rec_color = (0, 0, 255) if (frame_count // 20) % 2 == 0 else (255, 0, 0)
        cv2.putText(display, f"● REC  {os.path.basename(current_video_file)}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, rec_color, 2)

    # Hiển thị thông báo trạng thái tạm thời (2 giây, dòng 60)
    if status_message and time.time() < status_until_time:
        cv2.putText(display, status_message, (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
    else:
        status_message = ""

    # Nếu đang ghi, ghi frame GỐC (không chữ đè) vào video
    if recording:
        writer.write(frame)

    # Hiển thị frame (có chữ)
    cv2.imshow("Dahua Hero A1 - OpenCV", display)

    key = cv2.waitKey(1) & 0xFF

    # === NHẤN SPACE: CHỤP ẢNH (lưu frame gốc) ===
    if key == ord(' '):
        filepath = unique_path(IMAGES_DIR, "png")
        cv2.imwrite(filepath, frame)
        status_message = f"Da luu anh: {os.path.basename(filepath)}"
        status_color = (0, 200, 0)
        status_until_time = time.time() + 2
        print(f"Đã lưu ảnh: {filepath}")

    # === NHẤN 's': BẮT ĐẦU QUAY VIDEO ===
    elif key == ord('s'):
        if not recording:
            current_video_file = unique_path(VIDEOS_DIR, "mp4")
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            writer = cv2.VideoWriter(current_video_file, fourcc, fps, (w, h))
            recording = True
            print(f"Bắt đầu quay: {current_video_file}")

    # === NHẤN 'd': KẾT THÚC VÀ LƯU VIDEO ===
    elif key == ord('d'):
        if recording and writer is not None:
            writer.release()
            writer = None
            filename = os.path.basename(current_video_file)
            current_video_file = None
            recording = False
            status_message = f"Da luu video: {filename}"
            status_color = (0, 200, 0)
            status_until_time = time.time() + 2
            print(f"Đã lưu video: {os.path.join(VIDEOS_DIR, filename)}")
        else:
            status_message = "Chua quay! Nhan 's' de bat dau."
            status_color = (255, 0, 0)
            status_until_time = time.time() + 2

    # === NHẤN 'q': THOÁT ===
    if key == ord('q'):
        break

# === KẾT THÚC: giải phóng video nếu còn đang ghi ===
if recording and writer is not None:
    writer.release()
    print(f"Đã lưu video (tự động): {os.path.join(VIDEOS_DIR, os.path.basename(current_video_file))}")

# === GIẢI PHÓNG TÀI NGUYÊN ===
cap.release()
cv2.destroyAllWindows()
