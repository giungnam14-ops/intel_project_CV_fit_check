import streamlit as st
import cv2
import numpy as np

# MediaPipe import는 나중에 추가합니다 (현재는 웹캠 테스트만 수행)
# from pose_utils import init_pose, extract_pose_data, mp_pose, mp_drawing
# from feedback import get_feedback, FEEDBACK_MESSAGES

# =================================================================
# Streamlit 페이지 설정
# =================================================================
st.set_page_config(
    page_title="FitCheck AI - 웹캠 테스트",
    page_icon="🎥",
    layout="wide"
)

st.markdown("""
    <style>
    .main-title {
        color: #5DADE2;
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-weight: 800;
        margin-bottom: 5px;
    }
    .sub-title {
        color: #777;
        font-size: 16px;
        margin-bottom: 10px;
    }
    .status-badge {
        background-color: #EBF5FB;
        color: #2980B9;
        padding: 8px 15px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 600;
        display: inline-block;
        margin-bottom: 25px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h1 class='main-title'>FitCheck AI 🎥 웹캠 테스트</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>로컬 PC 웹캠 연결 확인</p>", unsafe_allow_html=True)
st.markdown("<div class='status-badge'>💡 이 화면은 로컬 웹캠 연결 확인용입니다.</div>", unsafe_allow_html=True)

st.info("""
**테스트 목적**:
- 로컬 웹캠이 정상 연결되었는지 확인
- OpenCV가 프레임을 정상 읽을 수 있는지 확인
- 카메라 인덱스 탐지 (0, 1, 2 순차 시도)
- MediaPipe 분석은 현재 미포함 (향후 고도화)
""")

# =================================================================
# Session State 초기화
# =================================================================
if "webcam_test_running" not in st.session_state:
    st.session_state.webcam_test_running = False
if "camera_index" not in st.session_state:
    st.session_state.camera_index = -1

# =================================================================
# 카메라 인덱스 자동 탐지 함수
# =================================================================
def find_available_camera():
    """
    cv2.VideoCapture(0), (1), (2)를 순차적으로 시도하여 
    첫 번째 사용 가능한 카메라 인덱스를 반환합니다.
    """
    for idx in range(3):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.release()
            return idx
    return -1

# =================================================================
# 웹캠 테스트 함수
# =================================================================
def run_webcam_test():
    """
    간단한 웹캠 테스트: 100프레임 캡처하여 화면에 표시.
    """
    st.write("**🔍 카메라 탐지 중...**")
    
    # 사용 가능한 카메라 인덱스 찾기
    camera_idx = find_available_camera()
    
    if camera_idx == -1:
        st.error("❌ 사용 가능한 웹캠을 찾을 수 없습니다.")
        st.write("**시도 사항:**")
        st.write("1. 웹캠이 USB로 연결되어 있는지 확인하세요.")
        st.write("2. 다른 프로그램(예: Zoom, Teams)에서 웹캠을 사용 중이면 종료하세요.")
        st.write("3. 웹캠 드라이버를 다시 설치하세요.")
        return
    
    st.success(f"✅ 카메라 인덱스 {camera_idx}에서 웹캠을 감지했습니다.")
    st.session_state.camera_index = camera_idx
    
    # 웹캠 캡처 객체 생성
    cap = cv2.VideoCapture(camera_idx)
    
    if not cap.isOpened():
        st.error(f"❌ 카메라 인덱스 {camera_idx}를 열 수 없습니다.")
        return
    
    # 웹캠 설정
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    
    st.write(f"**📹 카메라 인덱스: {camera_idx}**")
    st.write("**⏳ 100프레임을 캡처하고 있습니다...**")
    
    # 프레임 표시 플레이스홀더
    frame_placeholder = st.empty()
    status_placeholder = st.empty()
    
    frame_count = 0
    max_frames = 100
    
    # 웹캠 루프
    while frame_count < max_frames:
        # 프레임 읽기
        ret, frame = cap.read()
        
        if not ret:
            status_placeholder.error("❌ 웹캠 프레임을 읽지 못했습니다.")
            break
        
        frame_count += 1
        
        # 프레임 반전 (거울 효과)
        frame = cv2.flip(frame, 1)
        
        # BGR에서 RGB로 변환
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # 프레임에 정보 오버레이
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        font_color = (0, 255, 0)  # RGB에서 초록색
        font_thickness = 2
        
        # 프레임 카운트 표시
        cv2.putText(
            frame_rgb,
            f"Frame: {frame_count} / {max_frames}",
            (10, 30),
            font,
            font_scale,
            font_color,
            font_thickness
        )
        
        # 카메라 인덱스 표시
        cv2.putText(
            frame_rgb,
            f"Camera Index: {camera_idx}",
            (10, 70),
            font,
            font_scale,
            font_color,
            font_thickness
        )
        
        # 프레임 크기 표시
        height, width = frame_rgb.shape[:2]
        cv2.putText(
            frame_rgb,
            f"Resolution: {width}x{height}",
            (10, 110),
            font,
            font_scale,
            font_color,
            font_thickness
        )
        
        # Streamlit 화면에 표시
        frame_placeholder.image(frame_rgb, channels="RGB", use_column_width=True)
        
        # 상태 업데이트
        progress = frame_count / max_frames
        status_placeholder.progress(progress, text=f"진행률: {frame_count}/{max_frames}")
    
    # 웹캠 리소스 해제
    cap.release()
    st.session_state.webcam_test_running = False
    
    st.success(f"✅ 웹캠 테스트 완료! ({frame_count}프레임 캡처됨)")
    st.write(f"**사용 중인 카메라:** 인덱스 {camera_idx}")

# =================================================================
# 메인 UI
# =================================================================
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    if st.button("🎬 웹캠 테스트 시작", use_container_width=True, type="primary", key="start_test"):
        st.session_state.webcam_test_running = True

with col2:
    if st.button("⏹️ 테스트 중지", use_container_width=True, key="stop_test"):
        st.session_state.webcam_test_running = False

st.markdown("---")

# 웹캠 테스트 실행
if st.session_state.webcam_test_running:
    run_webcam_test()
else:
    if st.session_state.camera_index >= 0:
        st.info(f"✅ 마지막 인식된 카메라: 인덱스 {st.session_state.camera_index}")
    st.info("📹 **웹캠 테스트 시작** 버튼을 클릭하여 테스트를 시작하세요.")
