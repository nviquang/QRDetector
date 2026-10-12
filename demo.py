# -*- coding: utf-8 -*-
"""Web Streamlit: Giải mã mã QR từ Ảnh và Video bằng OpenCV & Pyzbar.

Chạy:  streamlit run demo.py
"""

import io
import os
import tempfile
import time

# --- Fix pyzbar thiếu DLL trên Windows ---
# pyzbar tìm ZBar DLL theo vị trí gói; khai báo thư mục gói làm DLL directory
# trước khi gọi decode() để không gặp lỗi "unable to find the specified file".
try:
    import pyzbar  # noqa: F401  (import gói KHÔNG nạp DLL, chỉ khi decode mới nạp)
    os.add_dll_directory(os.path.dirname(pyzbar.__file__))
except Exception:
    pass

import cv2
import csv
import numpy as np
from PIL import Image
from pyzbar import pyzbar
import streamlit as st


# ==============================================================================
# CÁC HÀM XỬ LÝ LÕI (CORE FUNCTIONS)
# ==============================================================================

def decode_qrs_from_frame(frame_bgr):
    """Giải mã tất cả QR trong một frame BGR.

    Trả về danh sách dict:
    [
        {
            "data": str,
            "type": str,
            "rect": (x, y, w, h),
            "polygon": [(x1, y1), ...]
        }, ...
    ]
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    raw_decoded = pyzbar.decode(gray)

    results = []

    # Nếu phát hiện trực tiếp
    if raw_decoded:
        for obj in raw_decoded:
            x, y, w, h = obj.rect
            text = obj.data.decode("utf-8", errors="replace")
            poly = [(p.x, p.y) for p in obj.polygon] if obj.polygon else []
            results.append({
                "data": text,
                "type": obj.type,
                "rect": (int(x), int(y), int(w), int(h)),
                "polygon": poly,
            })
        return results

    # Fallback: Thử xoay ảnh 90 độ theo chiều kim đồng hồ khi chưa tìm thấy QR
    h_orig, w_orig = frame_bgr.shape[:2]
    rot_bgr = cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
    rot_gray = cv2.cvtColor(rot_bgr, cv2.COLOR_BGR2GRAY)
    raw_rot = pyzbar.decode(rot_gray)

    if raw_rot:
        for obj in raw_rot:
            xr, yr, wr, hr = obj.rect
            text = obj.data.decode("utf-8", errors="replace")

            # Ánh xạ tọa độ từ ảnh xoay 90 độ CW về ảnh gốc:
            # Điểm (xr, yr) trong ảnh xoay (kích thước w_rot x h_rot = h_orig x w_orig)
            # tương ứng: x_orig = yr, y_orig = h_orig - 1 - (xr + wr)
            orig_x = int(yr)
            orig_y = int(h_orig - 1 - (xr + wr))
            orig_w = int(hr)
            orig_h = int(wr)

            poly_orig = []
            if obj.polygon:
                for p in obj.polygon:
                    px = int(p.y)
                    py = int(h_orig - 1 - p.x)
                    poly_orig.append((px, py))

            results.append({
                "data": text,
                "type": obj.type,
                "rect": (max(0, orig_x), max(0, orig_y), orig_w, orig_h),
                "polygon": poly_orig,
            })

    return results


def annotate_frame(frame_bgr, qr_results):
    """Vẽ bounding box và nhãn nội dung QR lên frame."""
    annotated = frame_bgr.copy()
    h_img, w_img = annotated.shape[:2]

    for item in qr_results:
        x, y, w, h = item["rect"]
        text = item["data"]

        # Khoanh vùng QR
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 230, 0), thickness=3)

        # Rút gọn nhãn hiển thị trên frame nếu quá dài
        display_label = text if len(text) <= 35 else text[:32] + "..."

        # Tính kích thước text để vẽ nền tương phản
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        font_thickness = 2
        (text_w, text_h), baseline = cv2.getTextSize(display_label, font, font_scale, font_thickness)

        # Tọa độ hộp nền text
        box_y1 = max(0, y - text_h - 10)
        box_y2 = y
        box_x1 = x
        box_x2 = min(w_img, x + text_w + 10)

        # Vẽ nền đen bán trong suốt cho nhãn
        cv2.rectangle(annotated, (box_x1, box_y1), (box_x2, box_y2), (0, 0, 0), cv2.FILLED)
        # Vẽ chữ màu xanh lá tươi
        cv2.putText(
            annotated,
            display_label,
            (box_x1 + 5, box_y2 - 5),
            font,
            font_scale,
            (0, 255, 0),
            font_thickness,
            lineType=cv2.LINE_AA,
        )

    return annotated


def format_timestamp(seconds):
    """Định dạng số giây thành chuỗi MM:SS.ss."""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"


def render_markdown_table(headers, rows):
    """Tạo bảng Markdown chuẩn hiển thị trong Streamlit mà không phụ thuộc pandas."""
    if not rows:
        return ""
    header_line = "| " + " | ".join(str(h) for h in headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    row_lines = [
        "| " + " | ".join(str(cell).replace("|", "\\|") for cell in r) + " |"
        for r in rows
    ]
    return "\n".join([header_line, separator_line] + row_lines)


# ==============================================================================
# GIAO DIỆN CHÍNH STREAMLIT
# ==============================================================================

st.set_page_config(page_title="Hệ thống Giải mã QR", page_icon="🔳", layout="wide")

st.title("🔳 Hệ thống Phát hiện & Giải mã QR Code")
st.caption(
    "Ứng dụng hỗ trợ trích xuất, giải mã và khoanh vùng vị trí mã QR từ ảnh chụp tĩnh hoặc video."
)

tab_image, tab_video = st.tabs(["📷 Xử lý ảnh", "🎥 Xử lý video"])


# ------------------------------------------------------------------------------
# TAB 1: XỬ LÝ ẢNH
# ------------------------------------------------------------------------------
with tab_image:
    st.subheader("Giải mã QR từ tệp ảnh")
    uploaded_image = st.file_uploader(
        "Chọn ảnh (PNG, JPG, JPEG, BMP, WEBP)",
        type=["png", "jpg", "jpeg", "bmp", "webp"],
        key="image_uploader",
    )

    if uploaded_image is not None:
        pil_img = Image.open(io.BytesIO(uploaded_image.read())).convert("RGB")
        rgb = np.array(pil_img)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        # Giải mã và khoanh vùng
        qr_results = decode_qrs_from_frame(bgr)
        annotated_bgr = annotate_frame(bgr, qr_results)
        annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)

        col_img, col_info = st.columns([3, 2])
        with col_img:
            st.image(annotated_rgb, caption="Ảnh đã khoanh vùng các mã QR", use_container_width=True)

        with col_info:
            if qr_results:
                st.success(f"🎉 Đã phát hiện và giải mã thành công {len(qr_results)} mã QR.")
                st.markdown("### 📋 Danh sách mã QR:")
                for i, qr in enumerate(qr_results, start=1):
                    x, y, w, h = qr["rect"]
                    st.markdown(
                        f"**{i}. Mã QR tại `({x}, {y})` (Kích thước: {w}×{h}):**\n"
                        f"- **Loại:** `{qr['type']}`\n"
                        f"- **Nội dung:**\n"
                        f"```text\n{qr['data']}\n```"
                    )
            else:
                st.warning("⚠️ Không tìm thấy mã QR nào trong ảnh đã chọn.")


# ------------------------------------------------------------------------------
# TAB 2: XỬ LÝ VIDEO
# ------------------------------------------------------------------------------
with tab_video:
    st.subheader("Giải mã QR từ tệp video")
    uploaded_video = st.file_uploader(
        "Chọn file video (MP4, AVI, MOV, MKV)",
        type=["mp4", "avi", "mov", "mkv"],
        key="video_uploader",
    )

    if uploaded_video is not None:
        # Lưu video tải lên vào file tạm để OpenCV đọc
        temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_input.write(uploaded_video.read())
        temp_input_path = temp_input.name
        temp_input.close()

        # Đọc thông số kỹ thuật của video
        cap = cv2.VideoCapture(temp_input_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0
        cap.release()

        # Hiển thị thông số video
        st.info(
            f"ℹ️ **Thông tin video:** Độ phân giải: **{width}×{height}** | "
            f"FPS: **{fps:.1f}** | Tổng số khung hình: **{total_frames}** | "
            f"Thời lượng: **{duration:.1f}s**"
        )

        col_opt1, col_opt2 = st.columns(2)
        with col_opt1:
            frame_step = st.slider(
                "Tần suất xử lý khung hình (Frame step):",
                min_value=1,
                max_value=10,
                value=1,
                help="1 = Xử lý tất cả các frame; 2 = Xử lý mỗi 2 frame (tăng tốc độ 2x).",
            )
        with col_opt2:
            max_frames_to_process = st.number_input(
                "Giới hạn số frame xử lý tối đa (0 = Xử lý toàn bộ video):",
                min_value=0,
                max_value=max(1, total_frames),
                value=0,
                step=50,
            )

        start_btn = st.button("🚀 Bắt đầu xử lý video", type="primary")

        if start_btn:
            cap = cv2.VideoCapture(temp_input_path)

            # Tạo file tạm cho video xuất
            temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_output_path = temp_output.name
            temp_output.close()

            # Thiết lập VideoWriter (sử dụng codec mp4v)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(temp_output_path, fourcc, fps, (width, height))

            # Khu vực cập nhật trạng thái thời gian thực
            progress_bar = st.progress(0)
            status_text = st.empty()

            col_preview, col_table_realtime = st.columns([3, 2])
            with col_preview:
                preview_placeholder = st.empty()
            with col_table_realtime:
                stats_placeholder = st.empty()

            unique_qrs = {}  # key: payload text -> dict thông tin
            frame_idx = 0
            processed_count = 0
            start_time = time.time()
            max_frames = total_frames if max_frames_to_process <= 0 else min(total_frames, int(max_frames_to_process))

            with st.spinner("Đang phân tích khung hình video..."):
                while cap.isOpened() and frame_idx < max_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    # Kiểm tra xem frame này có nằm trong chu kỳ xử lý không
                    should_detect = (frame_idx % frame_step == 0)

                    if should_detect:
                        qr_results = decode_qrs_from_frame(frame)
                        timestamp_sec = frame_idx / fps if fps > 0 else 0

                        # Cập nhật bảng tổng hợp các mã QR duy nhất
                        for qr in qr_results:
                            payload = qr["data"]
                            if payload not in unique_qrs:
                                unique_qrs[payload] = {
                                    "payload": payload,
                                    "type": qr["type"],
                                    "first_frame": frame_idx,
                                    "first_time_sec": timestamp_sec,
                                    "first_time_str": format_timestamp(timestamp_sec),
                                    "detections_count": 1,
                                }
                            else:
                                unique_qrs[payload]["detections_count"] += 1

                        annotated = annotate_frame(frame, qr_results)
                    else:
                        # Với các frame bỏ qua, giữ nguyên
                        annotated = frame

                    writer.write(annotated)
                    processed_count += 1
                    frame_idx += 1

                    # Cập nhật giao diện mỗi 5 frame hoặc ở frame cuối để mượt mà
                    if frame_idx % 5 == 0 or frame_idx == max_frames:
                        percent = min(1.0, frame_idx / max_frames)
                        progress_bar.progress(percent)

                        elapsed = time.time() - start_time
                        proc_fps = frame_idx / elapsed if elapsed > 0 else 0
                        status_text.markdown(
                            f"**Tiến độ:** Khung hình `{frame_idx}/{max_frames}` (`{percent * 100:.1f}%`) | "
                            f"**Tốc độ xử lý:** `{proc_fps:.1f} FPS` | "
                            f"**Số mã QR duy nhất phát hiện được:** `{len(unique_qrs)}`"
                        )

                        # Hiển thị preview khung hình gần nhất
                        if should_detect:
                            preview_rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
                            preview_placeholder.image(
                                preview_rgb,
                                caption=f"Khung hình {frame_idx} ({format_timestamp(frame_idx / fps if fps > 0 else 0)})",
                                use_container_width=True,
                            )

                        # Bảng thống kê sơ bộ bên cạnh
                        if unique_qrs:
                            temp_headers = ["Mã QR", "Lần đầu", "Số frame"]
                            temp_rows = [
                                [
                                    v["payload"] if len(v["payload"]) <= 22 else v["payload"][:19] + "...",
                                    v["first_time_str"],
                                    str(v["detections_count"]),
                                ]
                                for v in unique_qrs.values()
                            ]
                            stats_placeholder.markdown(
                                "**Danh sách QR vừa phát hiện:**\n\n" + render_markdown_table(temp_headers, temp_rows)
                            )

            cap.release()
            writer.release()
            progress_bar.progress(1.0)

            total_elapsed = time.time() - start_time
            avg_fps = processed_count / total_elapsed if total_elapsed > 0 else 0

            st.success(
                f"✅ Hoàn tất xử lý video trong **{total_elapsed:.1f} giây** "
                f"(Tốc độ trung bình: **{avg_fps:.1f} FPS**). "
                f"Tổng cộng phát hiện **{len(unique_qrs)}** mã QR duy nhất."
            )

            # ==================================================================
            # XUẤT KẾT QUẢ: BẢNG CSV & TẢI VIDEO MP4
            # ==================================================================
            st.divider()
            st.subheader("📊 Kết quả chi tiết")

            col_down_vid, col_down_csv = st.columns(2)

            # 1. Tải video kết quả MP4
            if os.path.exists(temp_output_path) and os.path.getsize(temp_output_path) > 0:
                with open(temp_output_path, "rb") as vf:
                    video_bytes = vf.read()

                with col_down_vid:
                    st.download_button(
                        label="📥 Tải video kết quả đã khoanh vùng (MP4)",
                        data=video_bytes,
                        file_name="qr_detected_output.mp4",
                        mime="video/mp4",
                        use_container_width=True,
                    )

            # 2. Bảng tổng hợp & Xuất CSV
            if unique_qrs:
                results_rows = [
                    {
                        "STT": idx,
                        "Nội dung QR": v["payload"],
                        "Loại mã": v["type"],
                        "Khung hình đầu tiên": v["first_frame"],
                        "Thời điểm xuất hiện": v["first_time_str"],
                        "Tổng số frame xuất hiện": v["detections_count"],
                    }
                    for idx, v in enumerate(unique_qrs.values(), start=1)
                ]

                # Xuất CSV chuẩn utf-8-sig để Excel mở không lỗi font tiếng Việt
                csv_buffer = io.StringIO()
                fieldnames = [
                    "STT",
                    "Nội dung QR",
                    "Loại mã",
                    "Khung hình đầu tiên",
                    "Thời điểm xuất hiện",
                    "Tổng số frame xuất hiện",
                ]
                csv_writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
                csv_writer.writeheader()
                for row in results_rows:
                    csv_writer.writerow(row)

                csv_data = csv_buffer.getvalue().encode("utf-8-sig")

                with col_down_csv:
                    st.download_button(
                        label="📥 Xuất danh sách QR ra file CSV",
                        data=csv_data,
                        file_name="danh_sach_qr.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )

                st.markdown("#### Bảng danh sách các mã QR phát hiện được:")
                final_headers = [
                    "STT",
                    "Nội dung QR",
                    "Loại mã",
                    "Khung hình đầu",
                    "Thời điểm xuất hiện",
                    "Tổng số frame",
                ]
                final_table_rows = [
                    [
                        str(r["STT"]),
                        f"`{r['Nội dung QR']}`",
                        r["Loại mã"],
                        str(r["Khung hình đầu tiên"]),
                        r["Thời điểm xuất hiện"],
                        str(r["Tổng số frame xuất hiện"]),
                    ]
                    for r in results_rows
                ]
                st.markdown(render_markdown_table(final_headers, final_table_rows))
            else:
                st.warning("Không tìm thấy mã QR nào trong video.")

            # Dọn dẹp file tạm đầu vào
            try:
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
            except Exception:
                pass
