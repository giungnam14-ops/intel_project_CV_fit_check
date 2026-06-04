import streamlit as st

try:
    import cv2
except Exception as e:
    cv2 = None
    CV2_IMPORT_ERROR = e
else:
    CV2_IMPORT_ERROR = None

import tempfile
import os
import numpy as np
import time
import csv
import pandas as pd
from datetime import datetime
from collections import Counter, deque

# pose_utils에서 mp_pose, mp_drawing 도구를 가져옵니다.
try:
    from pose_utils import init_pose, extract_pose_data, mp_pose, mp_drawing
except ImportError as e:
    st.error("❌ 필수 코어 라이브러리(MediaPipe) 패키지를 불러오는 데 실패했습니다.")
    st.exception(e)
    st.stop()
from feedback import get_feedback, FEEDBACK_MESSAGES
from analysis_utils import analyze_video, decide_auto_result


# ---------------------- 실시간 코칭 헬퍼 함수 ----------------------
def get_realtime_coaching(feedback_type: str) -> dict:
    """실시간 피드백 타입에 따라 메시지, 배경색, 스켈레톤 색상을 반환합니다.
    반환값: {"message": str, "bg_color": str, "skeleton_color": (r,g,b)}
    """
    # 메시지와 스켈레톤 색상은 OpenCV BGR 포맷 기준으로 설정합니다.
    mapping = {
        "GOOD": {
            "message": "좋아요! 전체적으로 안정적인 자세예요.",
            "bg_color": "#d4f7dc",
            "skeleton_color": (80, 220, 120)  # BGR
        },
        "NOT_DEEP": {
            "message": "조금만 더 깊게 앉아볼까요? 엉덩이를 뒤로 보내보세요.",
            "bg_color": "#fff4cc",
            "skeleton_color": (0, 180, 255)  # BGR
        },
        "LEAN_FORWARD": {
            "message": "상체가 앞으로 많이 기울었어요. 가슴을 살짝 들어주세요.",
            "bg_color": "#ffd6d6",
            "skeleton_color": (60, 60, 255)  # BGR
        },
        "LOW_VISIBILITY": {
            "message": "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치를 다시 맞춰주세요.",
            "bg_color": "#f0f0f0",
            "skeleton_color": (180, 180, 180)  # BGR
        },
        "UNCERTAIN_VIEW": {
            "message": "카메라 각도 때문에 자세 판단이 어려워요. 측면에서 전신이 보이게 서주세요.",
            "bg_color": "#fff4cc",
            "skeleton_color": (255, 165, 0)
        },
        "READY": {
            "message": FEEDBACK_MESSAGES.get("READY", "전신이 화면에 들어오면 자세 분석을 시작할게요."),
            "bg_color": "#eef3ff",
            "skeleton_color": (255, 255, 255)
        }
    }
    return mapping.get(feedback_type, mapping["READY"])


def update_bad_posture_counter(feedback_type: str, counters: dict, threshold: int = 10) -> tuple:
    """연속적으로 나쁜 자세가 유지되는 프레임을 카운트하고, 임계치 도달 시 경고 메시지를 반환합니다.
    counters는 {'LEAN_FORWARD': int, 'LOW_VISIBILITY': int} 형태를 기대합니다.
    반환값: (updated_counters, warning_message_or_None)
    """
    # reset counters on GOOD or other non-warning
    warning = None
    if feedback_type == "LEAN_FORWARD":
        counters["LEAN_FORWARD"] = counters.get("LEAN_FORWARD", 0) + 1
        counters["LOW_VISIBILITY"] = 0
        if counters["LEAN_FORWARD"] >= threshold:
            warning = "⚠️ 자세가 계속 불안정해요. 잠시 멈추고 자세를 다시 잡아보세요."
    elif feedback_type == "LOW_VISIBILITY":
        counters["LOW_VISIBILITY"] = counters.get("LOW_VISIBILITY", 0) + 1
        counters["LEAN_FORWARD"] = 0
        if counters["LOW_VISIBILITY"] >= threshold:
            warning = "🚨 몸이 화면에서 잘 보이지 않아요. 카메라 위치를 조정해주세요."
    else:
        # reset both counters on GOOD / NOT_DEEP / UNCERTAIN_VIEW / READY
        counters["LEAN_FORWARD"] = 0
        counters["LOW_VISIBILITY"] = 0

    return counters, warning


def get_status_style(feedback_type: str) -> dict:
    """실시간 패널 색상/라벨 스타일을 반환합니다."""
    palette = {
        "GOOD": {"label": "GOOD", "chip": "#e8fff2", "border": "#2ecc71", "text": "#1f7a45", "accent": "#2ecc71"},
        "NOT_DEEP": {"label": "NOT_DEEP", "chip": "#fff7e6", "border": "#f39c12", "text": "#995c00", "accent": "#f39c12"},
        "LEAN_FORWARD": {"label": "LEAN_FORWARD", "chip": "#fff2f2", "border": "#e74c3c", "text": "#b23b2f", "accent": "#e74c3c"},
        "LOW_VISIBILITY": {"label": "LOW_VISIBILITY", "chip": "#f3f4f6", "border": "#9aa0a6", "text": "#4b5563", "accent": "#6b7280"},
        "UNCERTAIN_VIEW": {"label": "UNCERTAIN_VIEW", "chip": "#f5edff", "border": "#9b59b6", "text": "#6a3d8a", "accent": "#9b59b6"},
        "READY": {"label": "READY", "chip": "#edf4ff", "border": "#4a90e2", "text": "#24508b", "accent": "#4a90e2"},
    }
    return palette.get(feedback_type, palette["READY"])


def choose_stable_feedback(history, previous_stable: str) -> str:
    """최근 history 기준으로 가장 안정적인 feedback_type을 선택합니다."""
    if not history:
        return previous_stable or "READY"

    counts = Counter(history)
    top_feedback, top_count = counts.most_common(1)[0]

    # LOW_VISIBILITY 우선순위 부여(안전상)
    if counts.get("LOW_VISIBILITY", 0) >= max(2, top_count - 1):
        return "LOW_VISIBILITY"

    if top_feedback == previous_stable and top_count >= 2:
        return top_feedback

    return top_feedback

# ---------------------- 헬퍼 함수 끝 ----------------------

# 웹페이지 기본 스펙 구성
st.set_page_config(
    page_title="FitCheck AI - 자세 분석 MVP v1",
    page_icon="🤸‍♀️",
    layout="wide"
)

# 브랜딩 스타일 적용
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

st.markdown("<h1 class='main-title'>FitCheck AI 🤸‍♀️</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-title'>Day 5 Build v1: 영상 업로드 기반 스쿼트 자세 분석 MVP</p>", unsafe_allow_html=True)
st.markdown("<div class='status-badge'>💡 현재는 영상 업로드 기반 분석 v1 안정화 단계입니다.</div>", unsafe_allow_html=True)

# ==================== 분석 모드 선택 ====================
st.markdown("---")
analysis_mode = st.radio(
    "🎯 분석 모드 선택",
    ["영상 업로드 분석", "실시간 웹캠 분석"],
    horizontal=False
)
st.markdown("---")

# ==================== 영상 업로드 분석 모드 ====================
if analysis_mode == "영상 업로드 분석":
    # 2열(Grid) 레이아웃 분할
    col1, col2 = st.columns([3, 2])

    with col2:
        st.subheader("📊 자세 분석 제어 패널")
        
        # 실시간 카메라 구현 계획에 대한 안내
        st.info("💡 **알림**: 본 v1 MVP는 복잡한 하드웨어 에러와 권한 문제를 사전에 방지하고자 **'영상 업로드 방식'**을 먼저 검증하도록 설계되었습니다.")
        
        input_method = st.radio("입력 방식 선택", ["1) test_videos 폴더에서 선택", "2) 직접 파일 업로드"])
        
        selected_video_path = None
        uploaded_file = None
        start_analysis = False
        
        if input_method == "1) test_videos 폴더에서 선택":
            # 현재 작업 디렉토리 기준으로 test_videos 폴더 경로 설정
            test_videos_dir = os.path.join(os.getcwd(), "test_videos")
            
            st.info("💡 **안내**: 안정적인 인식을 위해 한글 파일명은 피하고 **영어 파일명**을 권장합니다.")
            
            if os.path.exists(test_videos_dir) and os.path.isdir(test_videos_dir):
                valid_extensions = ('.mp4', '.mov', '.avi')
                video_files = [f for f in os.listdir(test_videos_dir) if f.lower().endswith(valid_extensions)]
                
                if video_files:
                    selected_video = st.selectbox("테스트 영상 선택", video_files)
                    selected_video_path = os.path.join(test_videos_dir, selected_video)
                    st.success(f"✅ 선택된 영상: {selected_video}")
                    start_analysis = st.button("▶️ 분석 시작", type="primary", use_container_width=True)
            
            # 전체 테스트 영상 일괄 분석
            run_all_videos = st.button("📂 전체 테스트 영상 일괄 분석", type="primary", use_container_width=True)

            if run_all_videos:
                pose_model = None
                try:
                    with st.spinner("AI 엔진 활성화 중 (배치 분석)..."):
                        pose_model = init_pose()
                except Exception as e:
                    st.error("❌ MediaPipe 초기화에 실패했습니다.")
                    st.exception(e)
                    st.stop()

                test_videos_dir = os.path.join(os.getcwd(), "test_videos")
                if not os.path.isdir(test_videos_dir):
                    st.warning("📢 test_videos 폴더를 찾을 수 없습니다.")
                else:
                    video_files = [f for f in os.listdir(test_videos_dir) if f.lower().endswith((".mp4", ".mov", ".avi"))]
                    if not video_files:
                        st.warning("📢 test_videos 폴더에 영상 파일이 없습니다.")
                    else:
                        total = len(video_files)
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        summaries = []
                        for idx, filename in enumerate(video_files, start=1):
                            status_text.text(f"현재 분석 중: {idx}/{total} - {filename}")
                            progress_bar.progress(idx / total)
                            video_path = os.path.join(test_videos_dir, filename)
                            summary = analyze_video(video_path, "test_videos", pose_model)
                            if summary:
                                summaries.append(summary)
                        if summaries:
                            df_summary = pd.DataFrame(summaries)
                            display_cols = ["filename", "auto_judgement", "skeleton_detection_rate", "total_frames", "analyzed_frames", "detected_frames", "detection_debug_note", "squat_count", "count_confidence", "knee_angle_min", "torso_angle_max", "feedback_type", "feedback_message"]
                            st.subheader("📊 전체 테스트 영상 일괄 분석 결과")
                            st.dataframe(df_summary[display_cols])
                        else:
                            st.info("⚠️ 분석 결과가 없습니다.")
        else:
            uploaded_file = st.file_uploader("검증용 스쿼트 영상 파일(.MP4, .MOV, .AVI 등)을 선택해 주세요.", type=["mp4", "mov", "avi"])
            if uploaded_file is not None:
                st.success("✅ 영상 파일이 안전하게 업로드되었습니다.")
                start_analysis = st.button("▶️ 분석 시작", type="primary", use_container_width=True)
            else:
                st.warning("📢 스쿼트 영상을 업로드한 뒤 분석 시작 버튼을 눌러주세요.")

        # 실시간 수치 리포트를 띄우기 위한 컨테이너 바인딩
        st.markdown("---")
        st.markdown("### 📈 최종 자세 리포트")
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            knee_metric = st.empty()
        with metric_col2:
            slope_metric = st.empty()
            
        metric_col3, metric_col4 = st.columns(2)
        with metric_col3:
            phase_metric = st.empty()
        with metric_col4:
            count_metric = st.empty()
            
        st.caption("✨ 5프레임 이동평균 적용됨 (관절 인식 튐 현상 보정)")
        feedback_container = st.empty()

    with col1:
        st.subheader("🎥 자세 분석 프리뷰")
        video_placeholder = st.empty()

        has_valid_input = (input_method == "1) test_videos 폴더에서 선택" and selected_video_path is not None) or \
                          (input_method == "2) 직접 파일 업로드" and uploaded_file is not None)

        if has_valid_input:
            if start_analysis:
                if cv2 is None:
                    st.error("OpenCV 로딩 중 오류가 발생했습니다. 배포 환경 설정을 확인해주세요.")
                    st.info("배포 환경에서는 웹캠 기능이 제한될 수 있습니다. 영상 업로드 분석 기능을 사용해주세요.")
                    st.stop()

                pose_model = None
                try:
                    with st.spinner("AI 엔진 활성화 중..."):
                        pose_model = init_pose()
                except Exception as e:
                    st.error("❌ MediaPipe 초기화에 실패했습니다.")
                    st.info("💡 **해결 방법**: `scripts/reinstall_mediapipe.bat` 파일을 더블클릭해 실행하여 MediaPipe를 강제 재설치해 주세요.")
                    st.warning("⚠️ **참고**: 그래도 계속 실패하는 경우, 파이썬 패키지 호환성이 완벽하게 검증된 **Python 3.10 또는 3.11 64-bit** 환경이 필요합니다.")
                    st.exception(e)
                    st.stop()
                
                if pose_model is not None:
                    # 평가 기록용 변수 초기화
                    total_frames = 0
                    skeleton_detected_frames = 0
                    raw_knee_angles = []
                    raw_torso_angles = []
                    smoothed_knee_angles = []
                    smoothed_torso_angles = []
                    feedbacks = []
                    
                    # 스쿼트 카운팅 상태 머신 상수 및 변수 초기화
                    STANDING_KNEE_ANGLE = 160
                    BOTTOM_KNEE_ANGLE = 110
                    MIN_ANGLE_CHANGE = 10
                    MIN_DETECTED_RATE_FOR_COUNT = 0.5
                    
                    current_phase = "UP"
                    squat_count = 0
                    error_occurred = False
                    error_message = ""
                    
                    try:
                        # 입력 방식에 따른 영상 소스 설정
                        if input_method == "1) test_videos 폴더에서 선택":
                            cap = cv2.VideoCapture(selected_video_path)
                        else:
                            # 업로드된 이진 스트림을 임시 파일 공간에 저장
                            tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                            tfile.write(uploaded_file.read())
                            tfile.close()
                            cap = cv2.VideoCapture(tfile.name)
                        
                        # 민트 & 화이트 뼈대 커스텀 드로잉 팩 설정
                        custom_connections_style = mp_drawing.DrawingSpec(color=(72, 201, 176), thickness=4, circle_radius=1)
                        custom_joints_style = mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=1, circle_radius=6)
                        
                        # 비디오 프레임 추출 및 관절 분석 시작
                        while cap.isOpened():
                            ret, frame = cap.read()
                            if not ret:
                                break
                            
                            total_frames += 1
                                
                            # 해상도 크기 조정 (640px 최적화)
                            h, w = frame.shape[:2]
                            new_w = 640
                            new_h = int(h * (new_w / w))
                            frame = cv2.resize(frame, (new_w, new_h))
                            
                            # 로컬 계산식 호출을 통해 주요 랜드마크 분석 데이터 획득
                            analysis_result = extract_pose_data(pose_model, frame)
                            
                            if analysis_result is not None:
                                skeleton_detected_frames += 1
                                # 감지된 뼈대 스켈레톤 라인 오버레이 그리기
                                mp_drawing.draw_landmarks(
                                    frame, 
                                    analysis_result["landmarks"], 
                                    mp_pose.POSE_CONNECTIONS,
                                    landmark_drawing_spec=custom_joints_style,
                                    connection_drawing_spec=custom_connections_style
                                )
                                
                                raw_knee_angle = analysis_result["knee_angle"]
                                raw_torso_slope = analysis_result["torso_slope"]
                                
                                raw_knee_angles.append(raw_knee_angle)
                                raw_torso_angles.append(raw_torso_slope)
                                
                                # 최근 5프레임 이동평균 스무딩 적용
                                smoothed_knee_angle = sum(raw_knee_angles[-5:]) / len(raw_knee_angles[-5:])
                                smoothed_torso_slope = sum(raw_torso_angles[-5:]) / len(raw_torso_angles[-5:])
                                
                                smoothed_knee_angles.append(smoothed_knee_angle)
                                smoothed_torso_angles.append(smoothed_torso_slope)
                                
                                # 스쿼트 카운팅 상태 머신 로직
                                if current_phase == "UP":
                                    if smoothed_knee_angle < STANDING_KNEE_ANGLE - MIN_ANGLE_CHANGE:
                                        current_phase = "DOWN"
                                elif current_phase == "DOWN":
                                    if smoothed_knee_angle <= BOTTOM_KNEE_ANGLE:
                                        current_phase = "BOTTOM"
                                    elif smoothed_knee_angle >= STANDING_KNEE_ANGLE:
                                        current_phase = "UP"
                                elif current_phase == "BOTTOM":
                                    if smoothed_knee_angle > BOTTOM_KNEE_ANGLE + MIN_ANGLE_CHANGE:
                                        current_phase = "RISING"
                                elif current_phase == "RISING":
                                    if smoothed_knee_angle >= STANDING_KNEE_ANGLE:
                                        current_phase = "UP"
                                        squat_count += 1
                                    elif smoothed_knee_angle <= BOTTOM_KNEE_ANGLE:
                                        current_phase = "BOTTOM"
                                
                                coaching_feedback = get_feedback(smoothed_knee_angle, smoothed_torso_slope)
                                feedbacks.append(coaching_feedback)
                                
                                # 실시간 대시보드 리포트 값 갱신
                                knee_metric.metric("현재 무릎 각도 (프레임 참고값)", f"{smoothed_knee_angle:.1f}°")
                                slope_metric.metric("현재 상체 기울기 (프레임 참고값)", f"{smoothed_torso_slope:.1f}°")
                                phase_metric.metric("현재 동작 국면", current_phase)
                                count_metric.metric("누적 스쿼트 횟수", f"{squat_count} 회")
                                feedback_container.info("⏳ 영상을 분석 중입니다...")
                            else:
                                knee_metric.metric("현재 무릎 각도", "N/A")
                                slope_metric.metric("현재 상체 기울기", "N/A")
                                feedback_container.info("👤 화면에 전신 측면이 잘 들어올 수 있도록 영상을 확인해 주세요.")
                            
                            # RGB 변환 후 웹뷰 이미지 객체 전송
                            rgb_preview = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            video_placeholder.image(rgb_preview, channels="RGB", use_container_width=True)
                            
                            time.sleep(0.03)
                            
                    except Exception as e:
                        error_occurred = True
                        error_message = str(e)
                        st.error(f"⚠️ 프레임을 분석하는 도중 예상치 못한 오류가 발생했습니다: {error_message}")
                    finally:
                        if 'cap' in locals() and cap.isOpened():
                            cap.release()
                        if input_method == "2) 직접 파일 업로드" and 'tfile' in locals() and os.path.exists(tfile.name):
                            try:
                                os.unlink(tfile.name)
                            except:
                                pass
                                
                        # 결과 통계 계산 및 CSV 저장
                        if total_frames > 0:
                            skeleton_detected_ratio = skeleton_detected_frames / total_frames
                            knee_angle_avg = sum(smoothed_knee_angles) / len(smoothed_knee_angles) if smoothed_knee_angles else None
                            torso_angle_avg = sum(smoothed_torso_angles) / len(smoothed_torso_angles) if smoothed_torso_angles else None
                            knee_angle_min = min(smoothed_knee_angles) if smoothed_knee_angles else None
                            torso_angle_max = max(smoothed_torso_angles) if smoothed_torso_angles else None
                            
                            # 판정 근거 수치 계산
                            knee_angle_range = max(smoothed_knee_angles) - min(smoothed_knee_angles) if smoothed_knee_angles else None
                            torso_angle_range = max(smoothed_torso_angles) - min(smoothed_torso_angles) if smoothed_torso_angles else None
                            
                            # 피드백 판정 로직
                            if skeleton_detected_ratio < 0.5:
                                feedback_type = "LOW_VISIBILITY"
                            elif torso_angle_max is not None and torso_angle_max >= 45:
                                feedback_type = "LEAN_FORWARD"
                            elif knee_angle_min is not None and knee_angle_min >= 110:
                                feedback_type = "NOT_DEEP"
                            elif skeleton_detected_ratio >= 0.5 and smoothed_knee_angles:
                                if knee_angle_range < 25:
                                    feedback_type = "UNCERTAIN_VIEW"
                                elif squat_count == 0:
                                    feedback_type = "UNCERTAIN_VIEW"
                                else:
                                    feedback_type = "GOOD"
                            else:
                                feedback_type = "GOOD"
                                
                            main_feedback = FEEDBACK_MESSAGES[feedback_type]

                            # 자동 판정 로직
                            auto_judgement = decide_auto_result(feedback_type)
                            
                            # skeleton_detection_rate 변수 확보
                            skeleton_detection_rate = skeleton_detected_ratio
                                
                            # 카운팅 신뢰도 판정 로직
                            if skeleton_detected_ratio < MIN_DETECTED_RATE_FOR_COUNT:
                                count_confidence = "LOW"
                            elif squat_count == 0 and feedback_type in ["NOT_DEEP", "UNCERTAIN_VIEW"]:
                                count_confidence = "LOW"
                            elif squat_count >= 1 and skeleton_detected_ratio >= 0.8:
                                count_confidence = "HIGH"
                            else:
                                count_confidence = "MEDIUM"
                                
                            # CSV 저장 준비
                            results_dir = os.path.join(os.getcwd(), "results")
                            if not os.path.exists(results_dir):
                                os.makedirs(results_dir)
                            csv_path = os.path.join(results_dir, "eval_result_v1.csv")
                            file_exists = os.path.isfile(csv_path)
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                            src_type = "test_videos" if input_method.startswith("1") else "uploaded_file"
                            filename = selected_video if input_method.startswith("1") else uploaded_file.name
                            memo = error_message if error_occurred else ""
                            
                            data = {
                                "timestamp": [timestamp],
                                "input_source": [src_type],
                                "filename": [filename],
                                "total_frames": [total_frames],
                                "analyzed_frames": [total_frames],
                                "detected_frames": [skeleton_detected_frames],
                                "skeleton_detection_rate": [round(skeleton_detected_ratio, 2)],
                                "detection_debug_note": ["" if feedback_type != "LOW_VISIBILITY" else "영상 프레임 중 스켈레톤 인식이 충분히 안정적이지 않아 자세 판단이 어려웠습니다. 카메라 구도·조명·프레임 위치 등을 점검하세요."],
                                "processed_frames": [total_frames],
                                "knee_angle_avg": [round(knee_angle_avg, 1) if knee_angle_avg is not None else "None"],
                                "knee_angle_min": [round(knee_angle_min, 1) if knee_angle_min is not None else "None"],
                                "torso_angle_avg": [round(torso_angle_avg, 1) if torso_angle_avg is not None else "None"],
                                "torso_angle_max": [round(torso_angle_max, 1) if torso_angle_max is not None else "None"],
                                "feedback_type": [feedback_type],
                                "feedback_message": [main_feedback],
                                "auto_judgement": [auto_judgement],
                                "memo": [memo],
                                "smoothing_applied": [True],
                                "squat_count": [squat_count],
                                "final_phase": [current_phase],
                                "count_confidence": [count_confidence],
                            }
                            
                            df_new = pd.DataFrame(data)

                            if file_exists:
                                try:
                                    df_existing = pd.read_csv(csv_path, encoding="utf-8-sig")
                                    if "filename" in df_existing.columns:
                                        df_existing = df_existing[df_existing["filename"] != filename]
                                    df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                                    df_combined.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                                except Exception:
                                    df_new.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                            else:
                                df_new.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                            
                            # CSV 검증
                            with open(csv_path, "r", encoding="utf-8-sig") as f:
                                content = f.read()
                                if "..." in content:
                                    st.error("❌ 저장된 CSV 파일에 '...' 축약 문자열이 감지되었습니다.")
                                    error_occurred = True
                                else:
                                    print("✅ CSV Validation Passed")
                            
                            if not error_occurred:
                                st.success("🎉 분석 검증 작업이 완료되었습니다!")
                            
                            # 오른쪽 최종 리포트 패널 갱신
                            knee_metric.metric("최저점 무릎 각도 (안정선: 110° 이하)", f"{knee_angle_min:.1f}°" if knee_angle_min is not None else "N/A")
                            slope_metric.metric("최대 상체 기울기 (안정선: 45° 이하)", f"{torso_angle_max:.1f}°" if torso_angle_max is not None else "N/A")
                            
                            if feedback_type == "GOOD":
                                feedback_container.success(f"💚 **최종 코치 피드백**: {main_feedback}")
                            else:
                                feedback_container.warning(f"💡 **최종 코치 피드백**: {main_feedback}")
                                
                            # 화면에 왼쪽 결과 통계 표시
                            st.markdown("### 📝 오늘의 자세 코칭 리포트")
                            
                            status_map = {
                                "GOOD": ("💚 안정적인 자세", "전체적으로 안정적인 자세예요. 지금처럼 천천히 반복해보세요.", "success"),
                                "NOT_DEEP": ("⚠️ 조금 더 깊이 앉기", "엉덩이를 뒤로 보내며 조금 더 깊게 앉아보세요.", "warning"),
                                "LEAN_FORWARD": ("⚠️ 상체 세우기", "가슴을 살짝 들어 상체가 앞으로 쏠리지 않게 해보세요.", "warning"),
                                "UNCERTAIN_VIEW": ("❓ 카메라 구도 불확실", "카메라 각도 때문에 자세를 확실히 판단하기 어려워요. 측면에서 전신이 보이도록 다시 촬영해보세요.", "warning"),
                                "LOW_VISIBILITY": ("🚫 카메라/조명 재조정", "전신이 화면에 잘 보이도록 카메라 위치와 조명을 다시 맞춰주세요.", "error")
                            }
                            
                            status_label, advice, alert_type = status_map.get(feedback_type, ("알 수 없음", "", "info"))
                            
                            with st.container():
                                st.markdown(f"#### {status_label}")
                                if alert_type == "success":
                                    st.success(f"**원포인트 어드바이스**: {advice}")
                                elif alert_type == "warning":
                                    st.warning(f"**원포인트 어드바이스**: {advice}")
                                else:
                                    st.error(f"**원포인트 어드바이스**: {advice}")
                                
                                st.info(f"💡 **대표 코칭 피드백**: {main_feedback}")
                                    
                                confidence_msg = {
                                    "HIGH": "운동 흐름이 안정적으로 인식되었어요.",
                                    "MEDIUM": "운동 흐름은 일부 인식되었지만, 자세나 촬영 조건에 따라 차이가 있을 수 있어요.",
                                    "LOW": "카메라 위치나 동작 범위 때문에 횟수 인식 신뢰도가 낮아요."
                                }
                                st.info(f"📊 **카운팅 신뢰도 ({count_confidence})**: {confidence_msg[count_confidence]}")
                                    
                                col_rep1, col_rep2, col_rep3 = st.columns(3)
                                col_rep1.metric("피드백 유형", feedback_type)
                                col_rep2.metric("스쿼트 횟수", f"{squat_count} 회")
                                col_rep3.metric("스켈레톤 인식률", f"{skeleton_detected_ratio:.1%}")
                                
                                col_rep4, col_rep5 = st.columns(2)
                                col_rep4.metric("최저점 무릎 각도", f"{knee_angle_min:.1f}°" if knee_angle_min is not None else "N/A")
                                col_rep5.metric("최대 상체 기울기", f"{torso_angle_max:.1f}°" if torso_angle_max is not None else "N/A")
                                
                                # 판정 근거 디버그 정보 expander
                                with st.expander("🔍 판정 근거 보기"):
                                    debug_col1, debug_col2, debug_col3 = st.columns(3)
                                    with debug_col1:
                                        st.metric("무릎 각도 변화량", f"{knee_angle_range:.1f}°" if knee_angle_range is not None else "N/A")
                                        st.metric("스켈레톤 인식률", f"{skeleton_detection_rate:.1%}")
                                    with debug_col2:
                                        st.metric("상체 각도 변화량", f"{torso_angle_range:.1f}°" if torso_angle_range is not None else "N/A")
                                        st.metric("스쿼트 카운팅", f"{squat_count} 회")
                                    with debug_col3:
                                        st.metric("피드백 유형", feedback_type)
                                        st.metric("카운팅 신뢰도", count_confidence)
            else:
                video_placeholder.info("준비 완료! 우측 제어 패널에서 [분석 시작] 버튼을 눌러 스쿼트 분석을 구동하세요.")
        else:
            video_placeholder.info("입력 방식을 선택하고 테스트 영상을 지정한 뒤 분석 시작 버튼을 눌러주세요.")

# ==================== 실시간 웹캠 분석 모드 ====================
else:
    st.subheader("🎥 실시간 웹캠 자세 분석")
    st.markdown("💡 **안내**: 선택한 시간 동안 웹캠으로 실시간 자세를 분석하고 피드백을 제공합니다. 측면 전신이 보이도록 카메라를 위치시켜 주세요.")
    st.markdown("""
        <style>
        .realtime-shell { padding: 8px 10px; border-radius: 18px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); border: 1px solid #dbe7f3; }
        .realtime-card { border-radius: 18px; border: 2px solid #dbe7f3; padding: 14px 16px; margin-bottom: 10px; background: #ffffff; box-shadow: 0 2px 8px rgba(15,23,42,0.06); }
        .realtime-label { font-size: 14px; text-transform: uppercase; letter-spacing: .08em; color: #4b5563; }
        .realtime-value { font-size: 28px; font-weight: 800; line-height: 1.15; margin-top: 4px; }
        .realtime-note { font-size: 16px; color: #374151; }
        .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .metric-box { border-radius: 14px; padding: 12px; background: #f8fafc; border: 1px solid #e5e7eb; }
        .metric-box strong { font-size: 24px; display: block; margin-top: 4px; }
        </style>
    """, unsafe_allow_html=True)

    # 실시간 UI placeholder는 조건문 내부에서만 정의하지 않고, 여기서 먼저 준비합니다.
    video_box = st.empty()
    status_box = st.empty()
    coaching_box = st.empty()
    count_box = st.empty()
    confidence_box = st.empty()
    visibility_box = st.empty()
    metric_box = st.empty()

    col_cam1, col_cam2 = st.columns([2, 1])

    with col_cam2:
        st.markdown("<div class='realtime-shell'>", unsafe_allow_html=True)
        st.markdown("### 🎛️ 실시간 코칭 패널")
        st.caption("시연용으로 크게 보이도록 정리된 패널입니다.")
        status_box = st.empty()
        coaching_box = st.empty()
        count_box = st.empty()
        confidence_box = st.empty()
        visibility_box = st.empty()
        metric_box = st.empty()
        st.markdown("---")
        st.markdown("#### ⚙️ 카메라 설정")
        if 'realtime_running' not in st.session_state:
            st.session_state['realtime_running'] = False
        camera_index = st.selectbox("카메라 선택", [0, 1, 2], index=0, help="기본값: 0 (내장 카메라)")
        start_webcam_btn = st.button("▶️ 실시간 분석 시작", type="primary", use_container_width=True, key="start_webcam_btn")
        stop_webcam_btn = st.button("■ 실시간 분석 중지", type="secondary", use_container_width=True, key="stop_webcam_btn")
        st.markdown("</div>", unsafe_allow_html=True)
        if start_webcam_btn:
            st.session_state['realtime_running'] = True
        if stop_webcam_btn:
            st.session_state['realtime_running'] = False
        webcam_status = st.empty()
        # 버튼 변수명 오류 방지
        start_webcam = start_webcam_btn
        stop_webcam = stop_webcam_btn

    with col_cam1:
        st.markdown("### 📹 웹캠 프리뷰")
        webcam_placeholder = st.empty()
        st.caption("실시간 분석 결과는 오른쪽 패널에서 크게 표시됩니다.")

    # 실시간 분석 시작 조건: 세션 상태 기반으로 제어
    if st.session_state.get('realtime_running', False):
        # MediaPipe Pose 초기화
        pose_model = None
        try:
            with st.spinner("AI 엔진 활성화 중..."):
                pose_model = init_pose()
        except Exception as e:
            st.error("❌ MediaPipe 초기화에 실패했습니다.")
            st.exception(e)
            st.stop()

        if pose_model is not None:
            # 웹캠 열기 시도 (순차적으로)
            cap = None
            successful_camera = -1
            
            for cam_idx in range(camera_index, min(camera_index + 3, 3)):
                cap = cv2.VideoCapture(cam_idx)
                if cap.isOpened():
                    successful_camera = cam_idx
                    break
            
            if successful_camera >= 0:
                webcam_status.success(f"✅ 카메라 {successful_camera}번으로 연결되었습니다.")
                # 분석 변수 초기화
                start_time = time.time()
                frame_count = 0
                skeleton_detected_count = 0
                raw_knee_angles = []
                raw_torso_angles = []
                smoothed_knee_angles = []
                smoothed_torso_angles = []
                feedbacks = []
                knee_angle_history = deque(maxlen=5)
                torso_angle_history = deque(maxlen=5)
                feedback_history = deque(maxlen=15)
                visibility_fail_history = deque(maxlen=10)
                # 스쿼트 카운팅 상태 머신 상수 및 변수 초기화
                STANDING_KNEE_ANGLE = 160
                BOTTOM_KNEE_ANGLE = 110
                MIN_ANGLE_CHANGE = 10
                MIN_DETECTED_RATE_FOR_COUNT = 0.5
                VISIBILITY_THRESHOLD = 0.7
                PREP_DURATION = 0.0
                PREP_FRAME_COUNT = 5
                # 피드백 타입 안정화: 최근 15프레임 히스토리 + 0.8초 유지시간으로 덜덜거림 방지
                stable_feedback_type = "READY"
                pending_feedback_type = "READY"
                last_feedback_change_time = time.time()
                FEEDBACK_HOLD_SECONDS = 0.8
                current_phase = "READY"
                squat_count = 0
                prep_start_time = time.time()
                analysis_ready = False
                analysis_ready_frame_count = 0
                last_valid_body_state = False
                # 실시간 나쁜 자세 카운터 초기화
                bad_posture_counters = {"LEAN_FORWARD": 0, "LOW_VISIBILITY": 0}
                last_warning = None
                analysis_ongoing = True
                # 문제 부위별 색상 정의
                COLOR_GOOD = (80, 220, 120)
                COLOR_NOT_DEEP = (0, 180, 255)
                COLOR_LEAN_FORWARD = (60, 60, 255)
                COLOR_LOW_VIS = (180, 180, 180)
                COLOR_UNCERTAIN = (255, 255, 255)
                try:
                    while cap.isOpened() and analysis_ongoing:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        # 중지 버튼으로 analysis_ongoing을 제어
                        if not st.session_state.get('realtime_running', True):
                            analysis_ongoing = False
                            break
                        
                        frame_count += 1
                        
                        # 해상도 조정
                        h, w = frame.shape[:2]
                        new_w = 640
                        new_h = int(h * (new_w / w))
                        frame = cv2.resize(frame, (new_w, new_h))
                        
                        # ===== 준비 구간 확인 =====
                        prep_elapsed = time.time() - prep_start_time
                        # 연속 유효 프레임 카운트: body_fully_visible이면 증가, 아니라면 리셋
                        
                        # 관절 인식
                        analysis_result = extract_pose_data(pose_model, frame)
                        
                        # ===== 전신 인식 검증 로직 =====
                        body_fully_visible = False
                        current_feedback_type = stable_feedback_type
                        raw_knee_angle = 0.0
                        raw_torso_slope = 0.0
                        smoothed_knee_angle = 0.0
                        smoothed_torso_slope = 0.0
                        coaching_feedback = FEEDBACK_MESSAGES.get("PREP_PHASE", "자세를 인식하는 중이에요. 전신이 화면에 들어오게 서주세요.")
                        current_confidence = "LOW"
                        
                        if analysis_result is not None:
                            visibility_fail_history.append(False)
                            # 핵심 관절의 visibility 확인 (선택된 쪽)
                            landmark_values = {
                                "shoulder": analysis_result.get("shoulder", [0, 0]),
                                "hip": analysis_result.get("hip", [0, 0]),
                                "knee": analysis_result.get("knee", [0, 0]),
                                "ankle": analysis_result.get("ankle", [0, 0])
                            }
                            
                            # visibility 기반 검증: 모든 핵심 관절이 충분히 보여야 함
                            core_visibility = analysis_result.get("core_visibility", 0)
                            
                            # 추가 조건: hip, knee, ankle 중 하나라도 0.5 미만이면 분석 불가
                            if core_visibility >= VISIBILITY_THRESHOLD:
                                body_fully_visible = True
                                last_valid_body_state = True
                            else:
                                body_fully_visible = False
                                # 갑자기 화면 밖으로 나가거나 얼굴만 보이는 경우
                                if last_valid_body_state:
                                    current_feedback_type = "CAMERA_ADJUSTMENT"
                                    coaching_feedback = FEEDBACK_MESSAGES.get("CAMERA_ADJUSTMENT", "전신이 화면에 들어오도록 카메라를 조금 뒤로 조정해주세요.")
                                else:
                                    current_feedback_type = "LOW_VISIBILITY"
                                    coaching_feedback = FEEDBACK_MESSAGES.get("LOW_VISIBILITY", "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치와 조명을 다시 맞춰주세요.")
                                
                                last_valid_body_state = False
                        else:
                            body_fully_visible = False
                            last_valid_body_state = False
                            visibility_fail_history.append(True)
                            if sum(visibility_fail_history) >= 6:
                                current_feedback_type = "LOW_VISIBILITY"
                            else:
                                current_feedback_type = stable_feedback_type or "READY"
                            coaching_feedback = FEEDBACK_MESSAGES.get("LOW_VISIBILITY", "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치와 조명을 다시 맞춰주세요.")
                        
                        # ===== 실시간 코칭 UI 및 스켈레톤 색상 결정 =====
                        coaching_info = get_realtime_coaching(stable_feedback_type if stable_feedback_type else current_feedback_type)
                        bad_posture_counters, warning_msg = update_bad_posture_counter(stable_feedback_type if stable_feedback_type else current_feedback_type, bad_posture_counters, threshold=10)

                        # 문제 부위별 색상 강조
                        def draw_skeleton_with_highlight(frame, landmarks, feedback_type):
                            # 기본 스타일
                            joint_style = mp_drawing.DrawingSpec(color=(255,255,255), thickness=1, circle_radius=6)
                            # 전체 연결 기본색
                            conn_style = mp_drawing.DrawingSpec(color=COLOR_GOOD, thickness=4, circle_radius=1)
                            # 문제 부위별 강조
                            if feedback_type == "GOOD":
                                conn_style = mp_drawing.DrawingSpec(color=COLOR_GOOD, thickness=4, circle_radius=1)
                                mp_drawing.draw_landmarks(frame, landmarks, mp_pose.POSE_CONNECTIONS, landmark_drawing_spec=joint_style, connection_drawing_spec=conn_style)
                            elif feedback_type == "NOT_DEEP":
                                # 무릎/다리 라인만 노란/주황 강조, 나머지는 흐리게
                                leg_conns = [
                                    (mp_pose.PoseLandmark.LEFT_HIP, mp_pose.PoseLandmark.LEFT_KNEE),
                                    (mp_pose.PoseLandmark.LEFT_KNEE, mp_pose.PoseLandmark.LEFT_ANKLE),
                                    (mp_pose.PoseLandmark.RIGHT_HIP, mp_pose.PoseLandmark.RIGHT_KNEE),
                                    (mp_pose.PoseLandmark.RIGHT_KNEE, mp_pose.PoseLandmark.RIGHT_ANKLE)
                                ]
                                # 전체 흐리게
                                mp_drawing.draw_landmarks(frame, landmarks, mp_pose.POSE_CONNECTIONS, landmark_drawing_spec=joint_style, connection_drawing_spec=mp_drawing.DrawingSpec(color=(200,200,200), thickness=2, circle_radius=1))
                                # 다리만 강조
                                for c in leg_conns:
                                    mp_drawing.draw_landmarks(
                                        frame, landmarks, [ (c[0].value, c[1].value) ],
                                        landmark_drawing_spec=joint_style,
                                        connection_drawing_spec=mp_drawing.DrawingSpec(color=COLOR_NOT_DEEP, thickness=6, circle_radius=2)
                                    )
                            elif feedback_type == "LEAN_FORWARD":
                                # 어깨-엉덩이-상체 라인만 빨간색 강조
                                trunk_conns = [
                                    (mp_pose.PoseLandmark.LEFT_SHOULDER, mp_pose.PoseLandmark.LEFT_HIP),
                                    (mp_pose.PoseLandmark.RIGHT_SHOULDER, mp_pose.PoseLandmark.RIGHT_HIP),
                                    (mp_pose.PoseLandmark.LEFT_SHOULDER, mp_pose.PoseLandmark.RIGHT_SHOULDER),
                                    (mp_pose.PoseLandmark.LEFT_HIP, mp_pose.PoseLandmark.RIGHT_HIP)
                                ]
                                # 전체 흐리게
                                mp_drawing.draw_landmarks(frame, landmarks, mp_pose.POSE_CONNECTIONS, landmark_drawing_spec=joint_style, connection_drawing_spec=mp_drawing.DrawingSpec(color=(200,200,200), thickness=2, circle_radius=1))
                                # 상체만 강조
                                for c in trunk_conns:
                                    mp_drawing.draw_landmarks(
                                        frame, landmarks, [ (c[0].value, c[1].value) ],
                                        landmark_drawing_spec=joint_style,
                                        connection_drawing_spec=mp_drawing.DrawingSpec(color=COLOR_LEAN_FORWARD, thickness=6, circle_radius=2)
                                    )
                            elif feedback_type in ("LOW_VISIBILITY", "UNCERTAIN_VIEW"):
                                # 전체 회색/흰색
                                mp_drawing.draw_landmarks(frame, landmarks, mp_pose.POSE_CONNECTIONS, landmark_drawing_spec=joint_style, connection_drawing_spec=mp_drawing.DrawingSpec(color=COLOR_LOW_VIS, thickness=4, circle_radius=1))
                            else:
                                mp_drawing.draw_landmarks(frame, landmarks, mp_pose.POSE_CONNECTIONS, landmark_drawing_spec=joint_style, connection_drawing_spec=conn_style)

                        # ===== 스켈레톤 그리기 =====
                        if analysis_result is not None and "landmarks" in analysis_result:
                            skeleton_detected_count += 1
                            draw_skeleton_with_highlight(frame, analysis_result["landmarks"], stable_feedback_type if stable_feedback_type else current_feedback_type)

                        # ===== 코칭 메시지 박스 업데이트 (placeholder 사용) =====
                        try:
                            bg = coaching_info.get("bg_color", "#eef3ff")
                            msg = coaching_info.get("message", "")
                            html = f"<div style='background:{bg};padding:10px;border-radius:8px;font-weight:600'>{msg}</div>"
                            if warning_msg:
                                html += f"<div style='margin-top:6px;background:#ffd6d6;padding:8px;border-radius:6px;font-weight:700'>" + warning_msg + "</div>"
                            coaching_box.markdown(html, unsafe_allow_html=True)
                        except Exception:
                            coaching_box.text(coaching_info.get("message", ""))
                        
                        # 연속 유효 프레임 카운트 업데이트 (준비 구간 판단의 핵심)
                        if body_fully_visible:
                            analysis_ready_frame_count += 1
                        else:
                            analysis_ready_frame_count = 0

                        is_in_prep_phase = (prep_elapsed < PREP_DURATION or analysis_ready_frame_count < PREP_FRAME_COUNT)

                        # ===== 분석 로직 (연속 유효 프레임이 쌓인 뒤에만) =====
                        if not is_in_prep_phase:
                            analysis_ready = True
                            
                            if analysis_result is not None:
                                raw_knee_angle = analysis_result["knee_angle"]
                                raw_torso_slope = analysis_result["torso_slope"]

                                raw_knee_angles.append(raw_knee_angle)
                                raw_torso_angles.append(raw_torso_slope)
                                knee_angle_history.append(raw_knee_angle)
                                torso_angle_history.append(raw_torso_slope)

                                # 최근 5프레임 이동평균 스무딩 적용
                                smoothed_knee_angle = float(np.mean(list(knee_angle_history))) if knee_angle_history else float(raw_knee_angle)
                                smoothed_torso_slope = float(np.mean(list(torso_angle_history))) if torso_angle_history else float(raw_torso_slope)
                                
                                smoothed_knee_angles.append(smoothed_knee_angle)
                                smoothed_torso_angles.append(smoothed_torso_slope)
                                
                                # 스쿼트 카운팅 상태 머신 로직 (분석 가능 상태에서만)
                                if current_phase == "READY":
                                    if smoothed_knee_angle < STANDING_KNEE_ANGLE - MIN_ANGLE_CHANGE:
                                        current_phase = "DOWN"
                                elif current_phase == "UP":
                                    if smoothed_knee_angle < STANDING_KNEE_ANGLE - MIN_ANGLE_CHANGE:
                                        current_phase = "DOWN"
                                elif current_phase == "DOWN":
                                    if smoothed_knee_angle <= BOTTOM_KNEE_ANGLE:
                                        current_phase = "BOTTOM"
                                    elif smoothed_knee_angle >= STANDING_KNEE_ANGLE:
                                        current_phase = "UP"
                                elif current_phase == "BOTTOM":
                                    if smoothed_knee_angle > BOTTOM_KNEE_ANGLE + MIN_ANGLE_CHANGE:
                                        current_phase = "RISING"
                                elif current_phase == "RISING":
                                    if smoothed_knee_angle >= STANDING_KNEE_ANGLE:
                                        current_phase = "UP"
                                        squat_count += 1  # 분석 가능 상태에서만 카운트 증가
                                    elif smoothed_knee_angle <= BOTTOM_KNEE_ANGLE:
                                        current_phase = "BOTTOM"
                                
                                # 자세 피드백 결정 (분석 가능 상태에서만)
                                current_feedback_type = "GOOD"
                                if smoothed_torso_slope >= 45:
                                    current_feedback_type = "LEAN_FORWARD"
                                elif smoothed_knee_angle >= 110 and current_phase not in ("UP", "READY"):
                                    current_feedback_type = "NOT_DEEP"
                                
                                coaching_feedback = get_feedback(smoothed_knee_angle, smoothed_torso_slope)
                                feedbacks.append(coaching_feedback)
                        
                        else:
                            # 준비 구간 또는 전신이 보이지 않는 경우
                            if is_in_prep_phase and body_fully_visible:
                                current_feedback_type = "READY"
                                coaching_feedback = FEEDBACK_MESSAGES.get("PREP_PHASE", "자세를 인식하는 중이에요. 전신이 화면에 들어오게 서주세요.")
                            # 이 경우 현재_피드백_타입과 coaching_feedback은 이미 위에서 설정됨
                        
                        # ===== 피드백 안정화: 최근 15프레임 중 가장 많은 피드백을 후보로 선택하고 0.8초 이상 유지 =====
                        raw_feedback_type = current_feedback_type
                        feedback_history.append(raw_feedback_type)
                        candidate_feedback = choose_stable_feedback(feedback_history, stable_feedback_type)

                        if candidate_feedback != pending_feedback_type:
                            pending_feedback_type = candidate_feedback
                            last_feedback_change_time = time.time()

                        if (time.time() - last_feedback_change_time) >= FEEDBACK_HOLD_SECONDS and pending_feedback_type != stable_feedback_type:
                            stable_feedback_type = pending_feedback_type
                        
                        # 카운팅 신뢰도 판정
                        if skeleton_detected_count / max(frame_count, 1) < MIN_DETECTED_RATE_FOR_COUNT:
                            current_confidence = "LOW"
                        elif squat_count >= 1 and skeleton_detected_count / max(frame_count, 1) >= 0.8:
                            current_confidence = "HIGH"
                        else:
                            current_confidence = "MEDIUM"
                        
                        # ===== UI 상태 표시 =====
                        if is_in_prep_phase:
                            status_display = "준비 중"
                        elif body_fully_visible and analysis_ready:
                            status_display = "분석 중"
                        else:
                            status_display = "카메라 조정 필요"
                        
                        # 이미지 표시
                        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        # Streamlit 버전에 따라 use_container_width/use_column_width 호환 처리
                        try:
                            webcam_placeholder.image(rgb_frame, channels="RGB", use_container_width=True)
                        except TypeError:
                            webcam_placeholder.image(rgb_frame, channels="RGB", use_column_width=True)

                        # coaching 메시지 및 경고/성공/에러 표시: 안정화된 피드백 타입 사용
                        display_feedback_type = stable_feedback_type if stable_feedback_type else current_feedback_type
                        style = get_status_style(display_feedback_type)
                        # 실시간 코칭 메시지(요구사항 반영)
                        feedback_msg_map = {
                            "GOOD": "좋아요. 현재 자세가 안정적이에요.",
                            "NOT_DEEP": "조금 더 깊게 앉아보세요.",
                            "LEAN_FORWARD": "상체가 앞으로 많이 기울었어요. 가슴을 살짝 들어보세요.",
                            "LOW_VISIBILITY": "몸 전체가 잘 보이도록 카메라 위치를 조정해주세요.",
                            "UNCERTAIN_VIEW": "카메라 각도 때문에 자세 판단이 불안정해요. 측면에서 전신이 보이게 서주세요."
                        }
                        display_msg = feedback_msg_map.get(display_feedback_type, coaching_feedback)
                        status_box.markdown(
                            f"<div class='realtime-card' style='border-color:{style['border']}; background:{style['chip']}; color:{style['text']};'>"
                            f"<div class='realtime-label'>현재 자세 상태</div>"
                            f"<div class='realtime-value'>{style['label']}</div>"
                            f"<div class='realtime-note'>시연용 상태 카드 · {status_display}</div></div>",
                            unsafe_allow_html=True
                        )
                        coaching_box.markdown(
                            f"<div class='realtime-card' style='border-color:{style['border']}; background:{style['chip']}; color:{style['text']};'>"
                            f"<div class='realtime-label'>대표 코칭 메시지</div>"
                            f"<div class='realtime-value' style='font-size:28px; line-height:1.3;'>{display_msg}</div></div>",
                            unsafe_allow_html=True
                        )
                        count_box.markdown(
                            "<div class='metric-grid'>"
                            f"<div class='metric-box'><span class='realtime-label'>무릎 각도</span><strong>{smoothed_knee_angle:.1f}°</strong></div>"
                            f"<div class='metric-box'><span class='realtime-label'>상체 기울기</span><strong>{smoothed_torso_slope:.1f}°</strong></div>"
                            f"<div class='metric-box'><span class='realtime-label'>스쿼트 카운트</span><strong>{squat_count}회</strong></div>"
                            f"<div class='metric-box'><span class='realtime-label'>카운팅 신뢰도</span><strong>{current_confidence}</strong></div>"
                            "</div>",
                            unsafe_allow_html=True
                        )
                        confidence_box.markdown(
                            f"<div class='realtime-note'>안정화된 피드백: <strong>{display_feedback_type}</strong> · 최근 15프레임 기준, 0.8초 유지</div>",
                            unsafe_allow_html=True
                        )
                        visibility_box.markdown(
                            f"<div class='realtime-card' style='border-color:{style['border']}; background:{style['chip']}; color:{style['text']};'>"
                            f"<div class='realtime-label'>인식 상태</div>"
                            f"<div class='realtime-value' style='font-size:18px; line-height:1.2;'>" + ("전신이 잘 보입니다." if body_fully_visible else "전신이 화면에 잘 보이도록 카메라 위치를 조정해주세요.") + "</div></div>",
                            unsafe_allow_html=True
                        )
                        
                        time.sleep(0.03)
                        
                except Exception as e:
                    st.error(f"⚠️ 웹캠 분석 중 오류: {str(e)}")
                finally:
                    if cap is not None and cap.isOpened():
                        cap.release()
                    
                    # 최종 결과 계산
                    skeleton_detected_ratio = skeleton_detected_count / frame_count if frame_count > 0 else 0
                    
                    knee_angle_avg = sum(smoothed_knee_angles) / len(smoothed_knee_angles) if smoothed_knee_angles else 0
                    torso_angle_avg = sum(smoothed_torso_angles) / len(smoothed_torso_angles) if smoothed_torso_angles else 0
                    knee_angle_min = min(smoothed_knee_angles) if smoothed_knee_angles else 0
                    torso_angle_max = max(smoothed_torso_angles) if smoothed_torso_angles else 0
                    
                    # 최종 피드백 타입 결정
                    # (분석 불가 상태였던 경우는 smoothed_knee_angles가 비어있을 가능성이 높음)
                    if skeleton_detected_ratio < 0.5 or not smoothed_knee_angles:
                        final_feedback_type = "LOW_VISIBILITY"
                    elif torso_angle_max >= 45:
                        final_feedback_type = "LEAN_FORWARD"
                    elif knee_angle_min >= 110:
                        final_feedback_type = "NOT_DEEP"
                    elif squat_count == 0:
                        final_feedback_type = "READY"
                    else:
                        final_feedback_type = "GOOD"
                    
                    final_feedback = FEEDBACK_MESSAGES.get(final_feedback_type, "자세 분석이 완료되었습니다.")
                    
                    # 최종 신뢰도
                    if skeleton_detected_ratio < MIN_DETECTED_RATE_FOR_COUNT:
                        final_confidence = "LOW"
                    elif squat_count >= 1 and skeleton_detected_ratio >= 0.8:
                        final_confidence = "HIGH"
                    else:
                        final_confidence = "MEDIUM"
                    
                    # CSV 저장
                    results_dir = os.path.join(os.getcwd(), "results")
                    if not os.path.exists(results_dir):
                        os.makedirs(results_dir)
                    
                    csv_path = os.path.join(results_dir, "realtime_result_v1.csv")
                    file_exists = os.path.isfile(csv_path)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    duration_sec = int(time.time() - start_time)

                    data = {
                        "timestamp": [timestamp],
                        "duration_sec": [duration_sec],
                        "squat_count": [squat_count],
                        "skeleton_detection_rate": [round(skeleton_detected_ratio, 2)],
                        "knee_angle_avg": [round(knee_angle_avg, 1)],
                        "knee_angle_min": [round(knee_angle_min, 1)],
                        "torso_angle_avg": [round(torso_angle_avg, 1)],
                        "torso_angle_max": [round(torso_angle_max, 1)],
                        "feedback_type": [final_feedback_type],
                        "feedback_message": [final_feedback],
                        "count_confidence": [final_confidence],
                    }
                    
                    df_new = pd.DataFrame(data)
                    
                    if file_exists:
                        try:
                            df_existing = pd.read_csv(csv_path, encoding="utf-8-sig")
                            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                            df_combined.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                        except Exception:
                            df_new.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                    else:
                        df_new.to_csv(csv_path, mode='w', header=True, index=False, encoding="utf-8-sig")
                    
                    # 최종 리포트 표시
                    st.markdown("---")
                    st.markdown("### 🎉 실시간 자세 분석 완료")
                    
                    status_map = {
                        "GOOD": ("💚 안정적인 자세", "전체적으로 안정적인 자세예요. 지금처럼 천천히 반복해보세요.", "success"),
                        "NOT_DEEP": ("⚠️ 조금 더 깊이 앉기", "엉덩이를 뒤로 보내며 조금 더 깊게 앉아보세요.", "warning"),
                        "LEAN_FORWARD": ("⚠️ 상체 세우기", "가슴을 살짝 들어 상체가 앞으로 쏠리지 않게 해보세요.", "warning"),
                        "READY": ("👤 자세 대기", "화면에 측면이 보이도록 정렬한 후 스쿼트를 시작해보세요.", "info"),
                        "LOW_VISIBILITY": ("🚫 카메라 위치 조정", "전신이 화면에 잘 보이도록 카메라 위치와 조명을 다시 맞춰주세요.", "error"),
                        "CAMERA_ADJUSTMENT": ("🚫 카메라 위치 조정", "전신이 화면에 들어오도록 카메라를 조정해주세요.", "error")
                    }
                    
                    status_label, advice, alert_type = status_map.get(final_feedback_type, ("알 수 없음", "", "info"))
                    
                    col_rep1, col_rep2 = st.columns(2)
                    
                    with col_rep1:
                        st.markdown(f"#### {status_label}")
                        if alert_type == "success":
                            st.success(f"**원포인트 어드바이스**: {advice}")
                        elif alert_type == "warning":
                            st.warning(f"**원포인트 어드바이스**: {advice}")
                        else:
                            st.info(f"**원포인트 어드바이스**: {advice}")
                    
                    with col_rep2:
                        st.markdown("#### 📝 분석 요약")
                        rep_col1, rep_col2 = st.columns(2)
                        rep_col1.metric("스쿼트 횟수", f"{squat_count}회")
                        rep_col2.metric("운동 시간", f"{duration_sec}초")
                        rep_col3, rep_col4 = st.columns(2)
                        rep_col3.metric("관절 인식률", f"{skeleton_detected_ratio:.1%}")
                        rep_col4.metric("카운팅 신뢰도", final_confidence)
                    
                    st.markdown("---")
                    st.markdown("#### 📊 상세 분석 결과")
                    
                    if smoothed_knee_angles:  # 분석이 실제로 이루어진 경우에만 표시
                        detail_col1, detail_col2, detail_col3 = st.columns(3)
                        detail_col1.metric("평균 무릎 각도", f"{knee_angle_avg:.1f}°")
                        detail_col2.metric("최저점 무릎 각도", f"{knee_angle_min:.1f}°")
                        detail_col3.metric("자세 안정성 (110° 기준)", "✅ 안정" if knee_angle_min <= 110 else "⚠️ 주의")
                        
                        detail_col4, detail_col5, detail_col6 = st.columns(3)
                        detail_col4.metric("평균 상체 기울기", f"{torso_angle_avg:.1f}°")
                        detail_col5.metric("최대 상체 기울기", f"{torso_angle_max:.1f}°")
                        detail_col6.metric("자세 안정성 (45° 기준)", "✅ 안정" if torso_angle_max <= 45 else "⚠️ 주의")
                    else:
                        st.warning("⚠️ **주의**: 분석 가능한 자세가 충분하지 않아 상세 결과를 표시할 수 없습니다. 카메라 위치를 조정하고 다시 시도해주세요.")
                    
                    st.info(f"💡 **대표 코칭 피드백**: {final_feedback}")
                    st.success(f"✅ **분석 완료**: 결과가 `results/realtime_result_v1.csv` 에 자동으로 저장되었습니다.")
                    
            else:
                st.error("❌ 선택한 카메라에 연결할 수 없습니다. 다른 카메라 번호를 시도해 주세요.")
