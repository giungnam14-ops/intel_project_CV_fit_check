import streamlit as st
import cv2
import tempfile
import os
import numpy as np
import time
import csv
import pandas as pd
from datetime import datetime
from collections import Counter, deque
import threading

import queue

# ====================== TTS 음성 피드백 ======================
try:
    import pyttsx3
    _tts_available = True
except ImportError:
    _tts_available = False

_tts_queue = queue.Queue()

def _tts_worker():
    if not _tts_available: return
    try:
        import pythoncom
        pythoncom.CoInitialize()
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
    except Exception:
        return
    while True:
        text = _tts_queue.get()
        if text is None: break
        try:
            engine.say(text)
            engine.runAndWait()
        except Exception:
            pass
        _tts_queue.task_done()

if _tts_available:
    threading.Thread(target=_tts_worker, daemon=True).start()

def speak_async(text):
    if not _tts_available:
        return
    # 기존에 대기중인 메시지가 있다면 비워주어 밀림 현상 방지 (최신 상태 우선)
    while not _tts_queue.empty():
        try:
            _tts_queue.get_nowait()
            _tts_queue.task_done()
        except Exception:
            pass
    _tts_queue.put(text)
# ==========================================================

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
            "skeleton_color": (0, 255, 0)  # BGR 초록색
        },
        "NOT_DEEP": {
            "message": "조금만 더 깊게 앉아볼까요? 엉덩이를 뒤로 보내보세요.",
            "bg_color": "#fff4cc",
            "skeleton_color": (0, 0, 255)  # BGR 빨간색
        },
        "LEAN_FORWARD": {
            "message": "상체가 앞으로 많이 기울었어요. 가슴을 살짝 들어주세요.",
            "bg_color": "#ffd6d6",
            "skeleton_color": (0, 0, 255)  # BGR 빨간색
        },
        "TOO_DEEP": {
            "message": "너무 깊게 앉았어요. 무릎과 허리에 부담이 가지 않도록 적당한 깊이에서 멈춰보세요.",
            "bg_color": "#ffebe6",
            "skeleton_color": (0, 165, 255)  # BGR 주황색
        },
        "LOW_VISIBILITY": {
            "message": "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치를 다시 맞춰주세요.",
            "bg_color": "#f0f0f0",
            "skeleton_color": (160, 160, 160)  # BGR 회색
        },
        "UNCERTAIN_VIEW": {
            "message": "카메라 각도 때문에 자세 판단이 어려워요. 측면에서 전신이 보이게 서주세요.",
            "bg_color": "#fff4cc",
            "skeleton_color": (160, 160, 160)  # BGR 회색
        },
        "READY": {
            "message": FEEDBACK_MESSAGES.get("READY", "전신이 화면에 들어오면 자세 분석을 시작할게요."),
            "bg_color": "#eef3ff",
            "skeleton_color": (160, 160, 160)  # BGR 회색
        }
    }
    return mapping.get(feedback_type, mapping["READY"])


def draw_skeleton_with_highlight(image, landmarks, feedback_type):
    """자세 분석 결과(feedback_type)에 따라 스켈레톤의 색상을 변경하여 그립니다.
    - GOOD: 초록색 (0, 255, 0)
    - NOT_DEEP, LEAN_FORWARD: 빨간색 (0, 0, 255)
    - TOO_DEEP: 주황색 (0, 165, 255)
    - LOW_VISIBILITY, UNCERTAIN_VIEW, READY, NO_PERSON: 회색 (160, 160, 160)
    Landmark와 Connection 모두 동일한 색상으로 표시합니다.
    """
    if feedback_type == "GOOD":
        color = (0, 255, 0)  # BGR 초록색
    elif feedback_type in ("NOT_DEEP", "LEAN_FORWARD"):
        color = (0, 0, 255)  # BGR 빨간색
    elif feedback_type == "TOO_DEEP":
        color = (0, 165, 255)  # BGR 주황색
    else:  # LOW_VISIBILITY, UNCERTAIN_VIEW, READY, NO_PERSON 등
        color = (160, 160, 160)  # BGR 회색
        
    joint_style = mp_drawing.DrawingSpec(color=color, thickness=1, circle_radius=6)
    conn_style = mp_drawing.DrawingSpec(color=color, thickness=4, circle_radius=1)
    
    mp_drawing.draw_landmarks(
        image, 
        landmarks, 
        mp_pose.POSE_CONNECTIONS,
        landmark_drawing_spec=joint_style,
        connection_drawing_spec=conn_style
    )


def determine_frame_feedback_type(analysis_result, smoothed_knee_angle, smoothed_torso_slope, current_phase="READY"):
    """각 프레임별로 현재 랜드마크 분석 결과 및 부가 정보(각도, 국면 등)를 바탕으로 피드백 타입을 반환합니다.
    """
    if analysis_result is None:
        return "NO_PERSON"
    
    # 1순위: LOW_VISIBILITY 또는 UNCERTAIN_VIEW
    if analysis_result.get("visibility_status") == "LOW_VISIBILITY":
        return "LOW_VISIBILITY"
    if analysis_result.get("uncertain_view", False):
        return "UNCERTAIN_VIEW"
        
    # 2순위: LEAN_FORWARD
    if smoothed_torso_slope is not None and smoothed_torso_slope >= 45:
        return "LEAN_FORWARD"
        
    # 3순위: TOO_DEEP
    if smoothed_knee_angle is not None and smoothed_knee_angle < 60:
        return "TOO_DEEP"
        
    # 4순위: NOT_DEEP
    if smoothed_knee_angle is not None and smoothed_knee_angle >= 110:
        if current_phase not in ["UP", "READY"]:
            return "NOT_DEEP"
        else:
            return "GOOD"
            
    # 5순위: GOOD
    return "GOOD"


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
        "TOO_DEEP": {"label": "TOO_DEEP", "chip": "#ffebe6", "border": "#ff5722", "text": "#d03b0d", "accent": "#ff5722"},
        "LOW_VISIBILITY": {"label": "LOW_VISIBILITY", "chip": "#f3f4f6", "border": "#9aa0a6", "text": "#4b5563", "accent": "#6b7280"},
        "UNCERTAIN_VIEW": {"label": "UNCERTAIN_VIEW", "chip": "#f5edff", "border": "#9b59b6", "text": "#6a3d8a", "accent": "#9b59b6"},
        "READY": {"label": "READY", "chip": "#edf4ff", "border": "#4a90e2", "text": "#24508b", "accent": "#4a90e2"},
    }
    return palette.get(feedback_type, palette["READY"])


def build_final_report(raw_results):
    EXCLUDE_FIRST_FRAMES = 30
    EXCLUDE_LAST_FRAMES = 30
    if not raw_results:
        return None

    if len(raw_results) > EXCLUDE_FIRST_FRAMES + EXCLUDE_LAST_FRAMES + 10:
        valid_results = raw_results[EXCLUDE_FIRST_FRAMES:-EXCLUDE_LAST_FRAMES]
    else:
        valid_results = raw_results

    if not valid_results:
        return None

    counts = Counter(valid_results)
    score_table = {
        "GOOD": 100,
        "NOT_DEEP": 70,
        "LEAN_FORWARD": 65,
        "TOO_DEEP": 75,
        "LOW_VISIBILITY": 50,
        "UNCERTAIN_VIEW": 50,
    }
    valid_scores = [score_table.get(state, 0) for state in valid_results]
    avg_score = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 0.0

    good_count = counts.get("GOOD", 0)
    not_deep_count = counts.get("NOT_DEEP", 0)
    lean_forward_count = counts.get("LEAN_FORWARD", 0)
    too_deep_count = counts.get("TOO_DEEP", 0)
    low_visibility_count = counts.get("LOW_VISIBILITY", 0) + counts.get("UNCERTAIN_VIEW", 0)

    error_counts = {
        "NOT_DEEP": not_deep_count,
        "LEAN_FORWARD": lean_forward_count,
        "TOO_DEEP": too_deep_count,
    }
    main_issue = "없음"
    if any(error_counts.values()):
        main_issue = max(error_counts, key=error_counts.get)

    if main_issue == "없음":
        if good_count / len(valid_results) >= 0.8:
            summary = "전체적으로 안정적인 자세입니다. 현재 자세를 유지하면서 반복 횟수를 조금씩 늘려보세요."
        else:
            summary = "전체적으로 안정적인 폼입니다. 무릎 각도나 가슴 세우기가 무난합니다. 조금만 더 집중하여 100점 스쿼트에 도전해보세요."
    elif main_issue == "NOT_DEEP":
        summary = "스쿼트 깊이가 다소 부족합니다. 무릎 각도를 조금 더 낮추며 앉는 연습을 해보세요."
    elif main_issue == "LEAN_FORWARD":
        summary = "상체가 앞으로 숙여지는 경향이 있습니다. 시선을 정면에 두고 가슴을 세워보세요."
    elif main_issue == "TOO_DEEP":
        summary = "너무 깊게 앉는 동작이 반복되었습니다. 무릎과 허리에 부담이 가지 않도록 적당한 깊이에서 멈춰보세요."
    else:
        summary = "전반적으로 흐름이 좋습니다. 자세 정렬을 의식하면서 차분히 운동을 이어나가 보세요."

    return {
        "total_count": len(valid_results),
        "avg_score": avg_score,
        "good_count": good_count,
        "not_deep_count": not_deep_count,
        "lean_forward_count": lean_forward_count,
        "too_deep_count": too_deep_count,
        "low_visibility_count": low_visibility_count,
        "main_issue": main_issue,
        "summary": summary,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "exercise": "스쿼트"
    }


def save_analysis_result(final_report):
    data_dir = os.path.join(os.getcwd(), "data")
    os.makedirs(data_dir, exist_ok=True)
    history_csv = os.path.join(data_dir, "analysis_history.csv")

    history_row = {
        "date": [final_report["date"]],
        "exercise": [final_report["exercise"]],
        "total_count": [final_report["total_count"]],
        "avg_score": [final_report["avg_score"]],
        "good_count": [final_report["good_count"]],
        "not_deep_count": [final_report["not_deep_count"]],
        "lean_forward_count": [final_report["lean_forward_count"]],
        "too_deep_count": [final_report["too_deep_count"]],
        "low_visibility_count": [final_report["low_visibility_count"]],
        "main_issue": [final_report["main_issue"]],
        "summary": [final_report["summary"]]
    }
    df_row = pd.DataFrame(history_row)

    try:
        if os.path.isfile(history_csv):
            df_hist = pd.read_csv(history_csv, encoding="utf-8-sig")
            df_combined = pd.concat([df_hist, df_row], ignore_index=True)
            df_combined.to_csv(history_csv, mode='w', header=True, index=False, encoding="utf-8-sig")
        else:
            df_row.to_csv(history_csv, mode='w', header=True, index=False, encoding="utf-8-sig")
        return True, f"분석 결과가 저장되었습니다: {history_csv}"
    except Exception as e:
        return False, str(e)


def choose_stable_feedback(history, previous_stable: str) -> str:
    """최근 history 기준으로 가장 안정적인 feedback_type을 선택합니다.
    
    ★ 핵심 규칙: history 의 '과반수(majority)' 를 차지한 상태만 반환합니다.
       과반수가 없으면 이전 상태(previous_stable)를 그대로 유지합니다.
       이 규칙 하나로 경계선 근처의 모든 덜덜거림이 차단됩니다.
    """
    if not history:
        return previous_stable or "READY"

    counts = Counter(history)
    majority = len(history) / 2  # 과반수 기준

    top_feedback, top_count = counts.most_common(1)[0]

    # 과반수를 차지한 상태가 있을 때만 상태 전환 허용
    if top_count > majority:
        return top_feedback

    # 과반수 없음 → 이전 상태 유지 (변화 없음)
    return previous_stable or top_feedback

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
    ["영상 업로드 분석", "실시간 웹캠 분석", "분석 기록 보기"],
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
                                
                                raw_knee_angle = analysis_result["knee_angle"]
                                raw_torso_slope = analysis_result["torso_slope"]
                                
                                raw_knee_angles.append(raw_knee_angle)
                                raw_torso_angles.append(raw_torso_slope)
                                
                                # 최근 10프레임 이동평균 스무딩 적용 (갑작스러운 튐 제거)
                                smoothed_knee_angle = sum(raw_knee_angles[-10:]) / len(raw_knee_angles[-10:])
                                smoothed_torso_slope = sum(raw_torso_angles[-10:]) / len(raw_torso_angles[-10:])
                                
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
                                
                                # 1단계: 자세 판정 수행
                                frame_feedback_type = determine_frame_feedback_type(
                                    analysis_result,
                                    smoothed_knee_angle,
                                    smoothed_torso_slope,
                                    current_phase
                                )
                                
                                # 2단계: 자세 판정 결과를 바탕으로 스켈레톤 하이라이트 그리기 (순서 이동 완료)
                                draw_skeleton_with_highlight(frame, analysis_result["landmarks"], frame_feedback_type)
                                
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
                            
                            # 피드백 판정 로직 (우선순위 1~5 완벽 구현)
                            if skeleton_detected_ratio < 0.5:
                                feedback_type = "LOW_VISIBILITY"
                            elif skeleton_detected_ratio >= 0.5 and smoothed_knee_angles and (knee_angle_range < 25 or squat_count == 0):
                                feedback_type = "UNCERTAIN_VIEW"
                            elif torso_angle_max is not None and torso_angle_max >= 45:
                                feedback_type = "LEAN_FORWARD"
                            elif knee_angle_min is not None and knee_angle_min < 60:
                                feedback_type = "TOO_DEEP"
                            elif knee_angle_min is not None and knee_angle_min >= 110:
                                feedback_type = "NOT_DEEP"
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
                                    print("[OK] CSV Validation Passed")
                            
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
elif analysis_mode == "실시간 웹캠 분석":
    st.subheader("🎥 실시간 웹캠 자세 분석")
    st.markdown("💡 **안내**: 선택한 시간 동안 웹캠으로 실시간 자세를 분석하고 피드백을 제공합니다. 측면 전신이 보이도록 카메라를 위치시켜 주세요.")
    st.markdown("""
        <style>
        .realtime-shell { padding: 8px 10px; border-radius: 18px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); border: 1px solid #dbe7f3; }
        .realtime-card { border-radius: 18px; border: 2px solid #dbe7f3; padding: 14px 16px; margin-bottom: 10px; background: #ffffff; box-shadow: 0 2px 8px rgba(15,23,42,0.06); }
        .realtime-label { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: #4b5563; }
        .realtime-value { font-size: 26px; font-weight: 800; line-height: 1.15; margin-top: 4px; }
        .realtime-note { font-size: 15px; color: #374151; }
        .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        .metric-box { border-radius: 14px; padding: 10px; background: #f8fafc; border: 1px solid #e5e7eb; }
        .metric-box strong { font-size: 22px; display: block; margin-top: 4px; }
        </style>
    """, unsafe_allow_html=True)

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
        st.markdown("---")
        st.markdown("#### ⚙️ 카메라 설정")
        st.warning("🤸‍♀️ **운동이 끝나면 분석 중지 버튼을 눌러주세요. 종료 직전 움직임은 결과에서 제외되어 더 정확한 리포트를 제공합니다.**")
        st.markdown("#### 🧪 디버그 상태")
        st.write("분석 버퍼 길이:", len(st.session_state.get('analysis_buffer', [])))
        st.write("마지막 자세 상태:", st.session_state.get('debug_last_state', "NONE"))
        st.write("분석 중지 플래그:", st.session_state.get('analysis_stopped', False))
        if 'realtime_running' not in st.session_state:
            st.session_state['realtime_running'] = False
        if 'is_camera_running' not in st.session_state:
            st.session_state['is_camera_running'] = False
        if 'is_recording_analysis' not in st.session_state:
            st.session_state['is_recording_analysis'] = False
        if 'analysis_buffer' not in st.session_state:
            st.session_state['analysis_buffer'] = []
        if 'final_report' not in st.session_state:
            st.session_state['final_report'] = None
        if 'report_saved' not in st.session_state:
            st.session_state['report_saved'] = False
        if 'debug_last_state' not in st.session_state:
            st.session_state['debug_last_state'] = "NONE"
        if 'analysis_stopped' not in st.session_state:
            st.session_state['analysis_stopped'] = False

        camera_index = st.selectbox("카메라 선택", [0, 1, 2], index=0, help="기본값: 0 (내장 카메라)")
        start_webcam_btn = st.button("▶️ 실시간 분석 시작", type="primary", use_container_width=True, key="start_webcam_btn")
        stop_webcam_btn = st.button("■ 실시간 분석 중지", type="secondary", use_container_width=True, key="stop_webcam_btn")
        st.markdown("</div>", unsafe_allow_html=True)
        if start_webcam_btn:
            st.session_state['realtime_running'] = True
            st.session_state['is_camera_running'] = True
            st.session_state['is_recording_analysis'] = True
            st.session_state['analysis_buffer'] = []
            st.session_state['final_report'] = None
            st.session_state['report_saved'] = False
            st.session_state['debug_last_state'] = "NONE"
            st.session_state['analysis_stopped'] = False
            st.session_state['webcam_session_saved'] = False
            st.session_state['last_realtime_report'] = None
        if stop_webcam_btn:
            st.session_state['realtime_running'] = False
            st.session_state['is_camera_running'] = False
            st.session_state['is_recording_analysis'] = False
            st.session_state['analysis_stopped'] = True
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
                frame_feedbacks = []  # 실시간 프레임 자세 결과 누적용
                # 스쿼트 카운팅 상태 머신 상수 및 변수 초기화
                STANDING_KNEE_ANGLE = 160
                BOTTOM_KNEE_ANGLE = 110
                MIN_ANGLE_CHANGE = 10
                MIN_DETECTED_RATE_FOR_COUNT = 0.5
                VISIBILITY_THRESHOLD = 0.7
                PREP_DURATION = 0.0
                PREP_FRAME_COUNT = 5
                # 피드백 타입 안정화: 최근 10프레임 히스토리 + 1초 유지시간으로 덜덜거림 방지
                feedback_history = deque(maxlen=10)
                stable_feedback_type = "READY"
                pending_feedback_type = "READY"
                pending_feedback_since = time.time()
                current_phase = "READY"
                squat_count = 0
                prep_start_time = time.time()
                analysis_ready = False
                analysis_ready_frame_count = 0
                
                # 음성 피드백 및 상태 유지(Hysteresis) 변수
                last_spoken_message = ""
                last_spoken_time = 0.0
                posture_state = "GOOD"
                torso_state = "GOOD"
                visibility_state = "GOOD"
                last_valid_body_state = False
                # 실시간 나쁜 자세 카운터 초기화
                bad_posture_counters = {"LEAN_FORWARD": 0, "LOW_VISIBILITY": 0}
                last_warning = None
                analysis_ongoing = True
                # ===== UI 덜덜거림 방지: 이전 UI 상태 추적 변수 =====
                # 내용이 바뀔 때만 마크다운 업데이트 전송 (매 프레임 전송 금지)
                _prev_display_feedback_type = ""
                _prev_display_msg = ""
                _prev_knee_angle_str = ""
                _prev_torso_slope_str = ""
                _prev_squat_count = -1
                _prev_confidence = ""
                _prev_status_display = ""
                _prev_body_visible = None
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
                        current_feedback_type = "READY"
                        smoothed_knee_angle = 0
                        smoothed_torso_slope = 0
                        coaching_feedback = FEEDBACK_MESSAGES.get("PREP_PHASE", "자세를 인식하는 중이에요. 전신이 화면에 들어오게 서주세요.")
                        current_confidence = "LOW"
                        
                        if analysis_result is not None:
                            # 핵심 관절의 visibility 확인 (선택된 쪽)
                            landmark_values = {
                                "shoulder": analysis_result.get("shoulder", [0, 0]),
                                "hip": analysis_result.get("hip", [0, 0]),
                                "knee": analysis_result.get("knee", [0, 0]),
                                "ankle": analysis_result.get("ankle", [0, 0])
                            }
                            
                            # visibility 기반 검증: 모든 핵심 관절이 충분히 보여야 함
                            core_visibility = analysis_result.get("core_visibility", 0)
                            
                            # 가시성 Hysteresis 로직
                            if visibility_state == "GOOD":
                                if core_visibility < 0.6:
                                    visibility_state = "LOW_VISIBILITY"
                            else:
                                if core_visibility >= 0.7:
                                    visibility_state = "GOOD"
                                    
                            if visibility_state == "GOOD":
                                body_fully_visible = True
                                last_valid_body_state = True
                            else:
                                body_fully_visible = False
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
                            current_feedback_type = "LOW_VISIBILITY"
                            coaching_feedback = FEEDBACK_MESSAGES.get("LOW_VISIBILITY", "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치와 조명을 다시 맞춰주세요.")
                        
                        # ===== 실시간 코칭 UI 및 스켈레톤 색상 결정 =====
                        coaching_info = get_realtime_coaching(stable_feedback_type)
                        # ★ 안정화된 stable_feedback_type 기준으로 카운터 업데이트 (raw 값 사용 금지)
                        bad_posture_counters, warning_msg = update_bad_posture_counter(stable_feedback_type, bad_posture_counters, threshold=30)

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
                                
                                # 최근 10프레임 이동평균 스무딩 적용 (갑작스러운 튐 제거)
                                smoothed_knee_angle = sum(raw_knee_angles[-10:]) / len(raw_knee_angles[-10:])
                                smoothed_torso_slope = sum(raw_torso_angles[-10:]) / len(raw_torso_angles[-10:])
                                
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
                                
                                # 자세 피드백 결정 (분석 가능 상태에서만) - 모든 판정에 Hysteresis 적용
                                if torso_state == "GOOD":
                                    if smoothed_torso_slope >= 45:
                                        torso_state = "LEAN_FORWARD"
                                elif torso_state == "LEAN_FORWARD":
                                    if smoothed_torso_slope < 40:
                                        torso_state = "GOOD"
                                        
                                # TOO_DEEP, GOOD, NOT_DEEP 상태 머신 (3가지 상태)
                                if posture_state == "TOO_DEEP":
                                    if smoothed_knee_angle >= 70:
                                        posture_state = "GOOD"
                                elif posture_state == "GOOD":
                                    if smoothed_knee_angle < 60:
                                        posture_state = "TOO_DEEP"
                                    elif smoothed_knee_angle > 110:
                                        posture_state = "NOT_DEEP"
                                elif posture_state == "NOT_DEEP":
                                    if smoothed_knee_angle < 100:
                                        posture_state = "GOOD"
                                
                                # 피드백 타입 우선순위: LEAN_FORWARD > TOO_DEEP > NOT_DEEP > GOOD
                                if torso_state == "LEAN_FORWARD":
                                    current_feedback_type = "LEAN_FORWARD"
                                elif posture_state == "TOO_DEEP":
                                    current_feedback_type = "TOO_DEEP"
                                elif posture_state == "NOT_DEEP" and current_phase not in ["UP", "READY"]:
                                    # 스쿼트 하강/상승 구간에서만 NOT_DEEP 피드백 활성화
                                    current_feedback_type = "NOT_DEEP"
                                else:
                                    current_feedback_type = "GOOD"
                                
                                coaching_feedback = FEEDBACK_MESSAGES.get(current_feedback_type, FEEDBACK_MESSAGES["GOOD"])
                                feedbacks.append(coaching_feedback)
                        
                        else:
                            # 준비 구간 또는 전신이 보이지 않는 경우
                            if is_in_prep_phase and body_fully_visible:
                                current_feedback_type = "READY"
                                coaching_feedback = FEEDBACK_MESSAGES.get("PREP_PHASE", "자세를 인식하는 중이에요. 전신이 화면에 들어오게 서주세요.")
                            # 이 경우 현재_피드백_타입과 coaching_feedback은 이미 위에서 설정됨
                        
                        # ===== 피드백 안정화: 최근 10프레임 중 가장 많은 피드백을 후보로 선택 =====
                        raw_feedback_type = current_feedback_type
                        feedback_history.append(raw_feedback_type)
                        candidate_feedback = choose_stable_feedback(feedback_history, stable_feedback_type)

                        # Hysteresis 로직과 10프레임 이동평균이 이미 노이즈를 강력히 차단하므로,
                        # 1초 딜레이를 제거하여 사용자의 실제 동작과 피드백의 싱크를 즉각적으로 맞춥니다. (피드백 밀림 현상 방지)
                        stable_feedback_type = candidate_feedback
                        frame_feedbacks.append(stable_feedback_type)
                        if st.session_state.get('is_recording_analysis', False) and stable_feedback_type in ("GOOD", "NOT_DEEP", "LEAN_FORWARD", "TOO_DEEP", "LOW_VISIBILITY", "UNCERTAIN_VIEW"):
                            st.session_state['analysis_buffer'].append(stable_feedback_type)
                            st.session_state['debug_last_state'] = stable_feedback_type
                        
                        # ===== 스켈레톤 그리기 (자세 판정 및 피드백 안정화 이후에 실행) =====
                        if analysis_result is not None and "landmarks" in analysis_result:
                            skeleton_detected_count += 1
                            draw_skeleton_with_highlight(frame, analysis_result["landmarks"], stable_feedback_type)
                        
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
                        display_feedback_type = stable_feedback_type
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
                        
                        # ===== 상태 변경 시 음성 출력 로직 (동일 멘트 방지 및 쿨타임 3초) =====
                        current_time = time.time()
                        if display_feedback_type not in ("READY", "LOW_VISIBILITY") and display_msg != last_spoken_message:
                            if (current_time - last_spoken_time) >= 3.0:
                                speak_async(display_msg)
                                last_spoken_message = display_msg
                                last_spoken_time = current_time
                        # ===== UI 업데이트: 내용이 바뀐 항목만 전송 (덜덜거림 완전 차단) =====
                        # 각도값 문자열화 (소수점 1자리 반올림)
                        _knee_str = f"{smoothed_knee_angle:.1f}"
                        _torso_str = f"{smoothed_torso_slope:.1f}"

                        # [상태 카드 + 코칭 메시지] 피드백 타입이나 메시지가 바뀔 때만 업데이트
                        if display_feedback_type != _prev_display_feedback_type or display_msg != _prev_display_msg or status_display != _prev_status_display:
                            _prev_display_feedback_type = display_feedback_type
                            _prev_display_msg = display_msg
                            _prev_status_display = status_display
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
                                f"<div class='realtime-value' style='font-size:22px; line-height:1.3;'>{display_msg}</div></div>",
                                unsafe_allow_html=True
                            )
                            confidence_box.markdown(
                                f"<div class='realtime-note'>안정화된 피드백: <strong>{display_feedback_type}</strong></div>",
                                unsafe_allow_html=True
                            )

                        # [수치 박스] 각도/카운트/신뢰도가 바뀔 때만 업데이트
                        if _knee_str != _prev_knee_angle_str or _torso_str != _prev_torso_slope_str or squat_count != _prev_squat_count or current_confidence != _prev_confidence:
                            _prev_knee_angle_str = _knee_str
                            _prev_torso_slope_str = _torso_str
                            _prev_squat_count = squat_count
                            _prev_confidence = current_confidence
                            count_box.markdown(
                                "<div class='metric-grid'>"
                                f"<div class='metric-box'><span class='realtime-label'>무릎 각도</span><strong>{_knee_str}°</strong></div>"
                                f"<div class='metric-box'><span class='realtime-label'>상체 기울기</span><strong>{_torso_str}°</strong></div>"
                                f"<div class='metric-box'><span class='realtime-label'>스쿼트 카운트</span><strong>{squat_count}회</strong></div>"
                                f"<div class='metric-box'><span class='realtime-label'>카운팅 신뢰도</span><strong>{current_confidence}</strong></div>"
                                "</div>",
                                unsafe_allow_html=True
                            )

                        # [인식 상태 박스] body_fully_visible 이 바뀔 때만 업데이트
                        if body_fully_visible != _prev_body_visible:
                            _prev_body_visible = body_fully_visible
                            visibility_box.markdown(
                                f"<div class='realtime-card' style='border-color:{style['border']}; background:{style['chip']}; color:{style['text']};'>"
                                f"<div class='realtime-label'>인식 상태</div>"
                                "<div class='realtime-value' style='font-size:18px; line-height:1.2;'>" + ("전신이 잘 보입니다." if body_fully_visible else "전신이 화면에 잘 보이도록 카메라 위치를 조정해주세요.") + "</div></div>",
                                unsafe_allow_html=True
                            )

                        time.sleep(0.03)
                        
                except Exception as e:
                    st.error(f"⚠️ 웹캠 분석 중 오류: {str(e)}")
                finally:
                    if cap is not None and cap.isOpened():
                        cap.release()
                    
                    # 최종 결과 계산 (마지막 30프레임 제외 연산 적용)
                    EXCLUDE_LAST_FRAMES = 30
                    total_analyzed = len(frame_feedbacks)
                    if total_analyzed > EXCLUDE_LAST_FRAMES:
                        valid_feedbacks = frame_feedbacks[:-EXCLUDE_LAST_FRAMES]
                    else:
                        valid_feedbacks = frame_feedbacks
                    
                    good_cnt = valid_feedbacks.count("GOOD")
                    not_deep_cnt = valid_feedbacks.count("NOT_DEEP")
                    lean_forward_cnt = valid_feedbacks.count("LEAN_FORWARD")
                    too_deep_cnt = valid_feedbacks.count("TOO_DEEP")
                    low_visibility_cnt = valid_feedbacks.count("LOW_VISIBILITY") + valid_feedbacks.count("UNCERTAIN_VIEW")
                    
                    # 자세 상태별 점수를 바탕으로 평균 점수 계산
                    posture_scores = {
                        "GOOD": 100,
                        "NOT_DEEP": 70,
                        "LEAN_FORWARD": 65,
                        "TOO_DEEP": 75,
                        "LOW_VISIBILITY": 50,
                        "UNCERTAIN_VIEW": 50,
                        "READY": 50
                    }
                    valid_scores = [posture_scores.get(f, 0) for f in valid_feedbacks if f not in ("NO_PERSON", "READY", "PREP_PHASE")]
                    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
                    
                    # 주요 오류 자세 산출
                    error_counts = {
                        "NOT_DEEP": not_deep_cnt,
                        "LEAN_FORWARD": lean_forward_cnt,
                        "TOO_DEEP": too_deep_cnt
                    }
                    primary_error = "없음"
                    if any(error_counts.values()):
                        primary_error = max(error_counts, key=error_counts.get)
                        
                    # AI 코칭 피드백 총평
                    if primary_error == "없음":
                        if avg_score >= 90:
                            coaching_summary = "대단히 훌륭합니다! 완벽한 깊이와 각도를 유지하며 아주 훌륭한 자세로 스쿼트를 수행하셨습니다. 지금 자세 그대로 루틴을 유지하세요."
                        else:
                            coaching_summary = "전체적으로 안정적인 폼입니다. 무릎 각도나 가슴 세우기가 무난합니다. 조금만 더 집중하여 100점 스쿼트에 도전해보세요."
                    elif primary_error == "NOT_DEEP":
                        coaching_summary = "스쿼트 깊이가 전반적으로 부족한 편입니다(NOT_DEEP). 엉덩이를 의자에 앉는다는 느낌으로 조금 더 깊게 내려앉아야 충분한 둔근 및 대퇴사두근 자극이 발생합니다."
                    elif primary_error == "LEAN_FORWARD":
                        coaching_summary = "상체가 앞으로 쏠리는 경향이 강합니다(LEAN_FORWARD). 가슴을 살짝 들어 앞을 바라보고, 체중을 발뒤꿈치에 실어서 척추 각도를 올바르게 유지해 주세요."
                    elif primary_error == "TOO_DEEP":
                        coaching_summary = "엉덩이가 지나치게 깊이 주저앉는 경향이 있습니다(TOO_DEEP). 완전히 주저앉아 쪼그려 앉을 경우 무릎 인대와 허리에 무리가 갈 수 있으니 허벅지가 바닥과 평행을 이루는 90도 부근에서 멈춰보세요."
                    else:
                        coaching_summary = "전반적으로 흐름이 좋습니다. 자세 정렬을 의식하면서 차분히 운동을 이어나가 보세요."
                        
                    # 리포트 데이터 Session State 저장 (Rerun으로 인한 화면 증발 방지)
                    report_data = {
                        "squat_count": squat_count,
                        "avg_score": round(avg_score, 1),
                        "good_cnt": good_cnt,
                        "not_deep_cnt": not_deep_cnt,
                        "lean_forward_cnt": lean_forward_cnt,
                        "too_deep_cnt": too_deep_cnt,
                        "low_visibility_cnt": low_visibility_cnt,
                        "primary_error": primary_error,
                        "coaching_summary": coaching_summary,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    st.session_state['last_realtime_report'] = report_data
                    
                    # CSV 저장 (Session State 활용 중복 저장 방지)
                    if not st.session_state.get('webcam_session_saved', False):
                        st.session_state['webcam_session_saved'] = True
                        
                        data_dir = os.path.join(os.getcwd(), "data")
                        os.makedirs(data_dir, exist_ok=True)
                        history_csv = os.path.join(data_dir, "analysis_history.csv")
                        
                        history_row = {
                            "timestamp": [report_data["timestamp"]],
                            "squat_count": [report_data["squat_count"]],
                            "avg_score": [report_data["avg_score"]],
                            "good_count": [report_data["good_cnt"]],
                            "not_deep_count": [report_data["not_deep_cnt"]],
                            "lean_forward_count": [report_data["lean_forward_cnt"]],
                            "too_deep_count": [report_data["too_deep_cnt"]],
                            "low_visibility_count": [report_data["low_visibility_cnt"]],
                            "primary_error": [report_data["primary_error"]],
                            "coaching_summary": [report_data["coaching_summary"]]
                        }
                        df_row = pd.DataFrame(history_row)
                        
                        if os.path.isfile(history_csv):
                            try:
                                df_hist = pd.read_csv(history_csv, encoding="utf-8-sig")
                                df_combined = pd.concat([df_hist, df_row], ignore_index=True)
                                df_combined.to_csv(history_csv, mode='w', header=True, index=False, encoding="utf-8-sig")
                            except:
                                df_row.to_csv(history_csv, mode='w', header=True, index=False, encoding="utf-8-sig")
                        else:
                            df_row.to_csv(history_csv, mode='w', header=True, index=False, encoding="utf-8-sig")
                    
            else:
                st.error("❌ 선택한 카메라에 연결할 수 없습니다. 다른 카메라 번호를 시도해 주세요.")

    # 실시간 분석이 종료되었을 때, 세션 버퍼를 기반으로 리포트를 생성하고 저장합니다.
    if not st.session_state.get('realtime_running', False) and st.session_state.get('analysis_stopped', False):
        if st.session_state.get('final_report') is None and st.session_state.get('analysis_buffer'):
            st.session_state['final_report'] = build_final_report(st.session_state['analysis_buffer'])

        final_report = st.session_state.get('final_report')
        if final_report is not None:
            if not (st.session_state.get('report_saved', False) or st.session_state.get('webcam_session_saved', False)):
                save_analysis_result(final_report)
                st.session_state['report_saved'] = True
                st.session_state['webcam_session_saved'] = True
                st.success("분석 결과가 저장되었습니다. 분석 기록 보기 탭에서 확인할 수 있습니다.")

            st.markdown("---")
            st.markdown("### 🏆 오늘의 스쿼트 리포트")
            st.info("💡 **안내**: 분석 종료 버튼을 클릭하여 측정이 완료되었습니다. 종료 직전 움직임은 결과에서 제외하고 더 정확한 리포트를 제공합니다.")
            r_col1, r_col2, r_col3 = st.columns(3)
            r_col1.metric("총 스쿼트 횟수", f"{final_report['total_count']}회")
            r_col2.metric("평균 자세 점수", f"{final_report['avg_score']}점")
            r_col3.metric("주요 오류 자세", final_report['main_issue'])

            st.markdown("#### 📊 자세 상태별 프레임 카운트")
            sc_col1, sc_col2, sc_col3, sc_col4, sc_col5 = st.columns(5)
            sc_col1.markdown(f"<div style='padding:10px; background:#e8fff2; border-radius:8px; text-align:center;'><strong>GOOD</strong><br><span style='font-size:20px; font-weight:700; color:#1f7a45;'>{final_report['good_count']}프레임</span></div>", unsafe_allow_html=True)
            sc_col2.markdown(f"<div style='padding:10px; background:#fff7e6; border-radius:8px; text-align:center;'><strong>NOT_DEEP</strong><br><span style='font-size:20px; font-weight:700; color:#995c00;'>{final_report['not_deep_count']}프레임</span></div>", unsafe_allow_html=True)
            sc_col3.markdown(f"<div style='padding:10px; background:#fff2f2; border-radius:8px; text-align:center;'><strong>LEAN_FORWARD</strong><br><span style='font-size:20px; font-weight:700; color:#b23b2f;'>{final_report['lean_forward_count']}프레임</span></div>", unsafe_allow_html=True)
            sc_col4.markdown(f"<div style='padding:10px; background:#ffebe6; border-radius:8px; text-align:center;'><strong>TOO_DEEP</strong><br><span style='font-size:20px; font-weight:700; color:#d03b0d;'>{final_report['too_deep_count']}프레임</span></div>", unsafe_allow_html=True)
            sc_col5.markdown(f"<div style='padding:10px; background:#f3f4f6; border-radius:8px; text-align:center;'><strong>LOW_VISIBILITY</strong><br><span style='font-size:20px; font-weight:700; color:#4b5563;'>{final_report['low_visibility_count']}프레임</span></div>", unsafe_allow_html=True)

            st.markdown("#### 🤖 AI 코치 총평")
            st.success(final_report['summary'])
        else:
            if st.session_state.get('analysis_buffer'):
                st.warning("분석된 자세 데이터가 부족합니다. 분석 시작 후 몇 초 이상 운동을 진행한 뒤 다시 중지해주세요.")

# ==================== 분석 기록 보기 모드 ====================
elif analysis_mode == "분석 기록 보기":
    st.subheader("📋 실시간 웹캠 분석 기록 목록")
    st.caption("실시간 웹캠 분석 세션을 중지한 기록들이 누적되어 저장되는 공간입니다.")
    
    csv_path = "data/analysis_history.csv"
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig")
            # 컬럼 한글화하여 보기 좋게 렌더링
            df_rename = df.rename(columns={
                "date": "측정 일시",
                "timestamp": "측정 일시",
                "exercise": "운동 유형",
                "squat_count": "총 스쿼트 횟수",
                "avg_score": "평균 자세 점수",
                "good_count": "GOOD 프레임",
                "not_deep_count": "NOT_DEEP 프레임",
                "lean_forward_count": "LEAN_FORWARD 프레임",
                "too_deep_count": "TOO_DEEP 프레임",
                "low_visibility_count": "인식 오류 프레임",
                "primary_error": "주요 오류 자세",
                "coaching_summary": "AI 코치 총평"
            })
            st.dataframe(df_rename, use_container_width=True)
            
            # CSV 다운로드 버튼 제공
            csv_data = df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(
                label="📥 분석 기록 CSV 다운로드",
                data=csv_data,
                file_name="fitcheck_webcam_history.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"기록 파일을 읽는 중 오류가 발생했습니다: {str(e)}")
    else:
        st.info("아직 실시간 웹캠 분석 기록이 없습니다. 웹캠 분석을 진행해 주세요.")
