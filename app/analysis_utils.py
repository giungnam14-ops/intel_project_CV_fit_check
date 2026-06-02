import numpy as np
import cv2
import time
import pandas as pd
from datetime import datetime
from pose_utils import extract_pose_data, mp_pose, mp_drawing
from feedback import FEEDBACK_MESSAGES
import os

# Auto result decision function

def decide_auto_result(feedback_type: str) -> str:
    """Determine auto_result string based on feedback_type.
    Mapping:
    - GOOD -> "통과"
    - NOT_DEEP -> "부분 통과"
    - LEAN_FORWARD -> "부분 통과"
    - TOO_DEEP -> "부분 통과"
    - LOW_VISIBILITY -> "실패"
    - UNCERTAIN_VIEW -> "부분 통과"
    """
    if feedback_type == "GOOD":
        return "통과"
    if feedback_type in ("NOT_DEEP", "LEAN_FORWARD", "TOO_DEEP", "UNCERTAIN_VIEW"):
        return "부분 통과"
    if feedback_type == "LOW_VISIBILITY":
        return "실패"
    # Fallback
    return "실패"



def analyze_video(video_path: str, source_type: str, pose_model) -> dict:
    """Analyze a single video and return summary metrics.

    Args:
        video_path: Absolute path to the video file.
        source_type: Identifier for CSV column (e.g., "test_videos" or "uploaded_file").
        pose_model: Initialized MediaPipe Pose model (already created by init_pose()).

    Returns:
        dict with keys required for the summary table and CSV persistence.
    """
    total_frames = 0
    skeleton_detected_frames = 0
    raw_knee_angles = []
    raw_torso_angles = []
    smoothed_knee_angles = []
    smoothed_torso_angles = []
    squat_count = 0
    error_occurred = False
    error_message = ""
    # State machine constants (same as main flow)
    STANDING_KNEE_ANGLE = 160
    BOTTOM_KNEE_ANGLE = 110
    MIN_ANGLE_CHANGE = 10
    MIN_DETECTED_RATE_FOR_COUNT = 0.5
    current_phase = "UP"
    # Flag to capture if any frame has uncertain view
    uncertain_view_detected = False
    # Start processing video with safe try block
    try:
    
        cap = cv2.VideoCapture(video_path)
        # Initialize aggregates for quality assessment
        core_visibilities = []
        good_quality_frames = 0
        # We'll compute knee angle std and torso angle std after smoothing loop

        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            total_frames += 1
            # Resize for speed
            h, w = frame.shape[:2]
            new_w = 640
            new_h = int(h * (new_w / w))
            frame = cv2.resize(frame, (new_w, new_h))
            analysis_result = extract_pose_data(pose_model, frame)
            if analysis_result is None:
                continue
            skeleton_detected_frames += 1
            # Track core visibility per frame
            if "core_visibility" in analysis_result:
                core_visibilities.append(analysis_result["core_visibility"])
            # Check uncertain view flag
            if analysis_result.get("uncertain_view"):
                uncertain_view_detected = True
            # Evaluate full-body quality for this frame
            essential_vis = analysis_result.get("core_visibility", 0)
            joints = [analysis_result.get("shoulder"), analysis_result.get("hip"),
                      analysis_result.get("knee"), analysis_result.get("ankle")]
            body_in_frame_ok = all(
                joint is not None and 0.03 <= joint[0] <= 0.97 and 0.03 <= joint[1] <= 0.97
                for joint in joints)
            if essential_vis >= 0.6 and body_in_frame_ok:
                good_quality_frames += 1
            raw_knee_angle = analysis_result["knee_angle"]
            raw_torso_slope = analysis_result["torso_slope"]
            raw_knee_angles.append(raw_knee_angle)
            raw_torso_angles.append(raw_torso_slope)
            # smoothing (10‑frame moving average)
            smoothed_knee_angle = sum(raw_knee_angles[-10:]) / len(raw_knee_angles[-10:])
            smoothed_torso_slope = sum(raw_torso_angles[-10:]) / len(raw_torso_angles[-10:])
            smoothed_knee_angles.append(smoothed_knee_angle)
            smoothed_torso_angles.append(smoothed_torso_slope)
            # state machine
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
            # small sleep to avoid tight loop (mirrors UI version)
            time.sleep(0.001)
    except Exception as e:
        error_occurred = True
        error_message = str(e)
    finally:
        if 'cap' in locals() and cap.isOpened():
            cap.release()
    # Quality thresholds
    MIN_VALID_KNEE_ANGLE = 45
    MIN_CORE_VISIBILITY = 0.55
    MAX_KNEE_ANGLE_STD = 45

    # post‑processing statistics
    if total_frames == 0:
        # avoid division errors; return empty dict
        return {}
    skeleton_detected_ratio = skeleton_detected_frames / total_frames
    knee_angle_min = min(smoothed_knee_angles) if smoothed_knee_angles else None
    torso_angle_max = max(smoothed_torso_angles) if smoothed_torso_angles else None
    # compute additional quality metrics
    core_visibility_avg = float(np.mean(core_visibilities)) if core_visibilities else 0.0
    full_body_quality_rate = float(good_quality_frames) / total_frames if total_frames > 0 else 0.0
    knee_angle_std = float(np.std(smoothed_knee_angles)) if smoothed_knee_angles else 0.0
    torso_angle_std = float(np.std(smoothed_torso_angles)) if smoothed_torso_angles else 0.0
    # sanity checks for quality
    quality_flag = None
    if knee_angle_min is not None and knee_angle_min < MIN_VALID_KNEE_ANGLE:
        quality_flag = "LOW_KNEE_ANGLE"
    if knee_angle_std > MAX_KNEE_ANGLE_STD:
        quality_flag = "HIGH_KNEE_STD"
    if core_visibility_avg < MIN_CORE_VISIBILITY:
        quality_flag = "LOW_CORE_VISIBILITY"
    # feedback decision with priority
    if skeleton_detected_ratio < 0.5:
        feedback_type = "LOW_VISIBILITY"
    elif uncertain_view_detected or full_body_quality_rate < 0.65:
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
    # auto judgement (use common function)
    auto_judgement = decide_auto_result(feedback_type)

    # count confidence – ensure low confidence for poor quality
    if feedback_type in ("UNCERTAIN_VIEW", "LOW_VISIBILITY"):
        count_confidence = "LOW"
    elif skeleton_detected_ratio < MIN_DETECTED_RATE_FOR_COUNT:
        count_confidence = "LOW"
    elif squat_count == 0 and feedback_type == "NOT_DEEP":
        count_confidence = "LOW"
    elif squat_count >= 1 and skeleton_detected_ratio >= 0.8:
        count_confidence = "HIGH"
    else:
        count_confidence = "MEDIUM"
    # CSV persistence (same schema as original) – add new columns
    results_dir = os.path.join(os.getcwd(), "results")
    os.makedirs(results_dir, exist_ok=True)
    csv_path = os.path.join(results_dir, "eval_result_v1.csv")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = os.path.basename(video_path)
    data = {
        "timestamp": [timestamp],
        "input_source": [source_type],
        "filename": [filename],
        "total_frames": [total_frames],
        "processed_frames": [total_frames],
        "detected_frames": [skeleton_detected_frames],
        "skeleton_detection_rate": [round(skeleton_detected_ratio, 2)],
        "knee_angle_avg": [round(sum(smoothed_knee_angles) / len(smoothed_knee_angles), 1) if smoothed_knee_angles else "None"],
        "knee_angle_min": [round(knee_angle_min, 1) if knee_angle_min is not None else "None"],
        "torso_angle_avg": [round(sum(smoothed_torso_angles) / len(smoothed_torso_angles), 1) if smoothed_torso_angles else "None"],
        "torso_angle_max": [round(torso_angle_max, 1) if torso_angle_max is not None else "None"],
        "core_visibility_avg": [round(core_visibility_avg, 3)],
        "knee_angle_std": [round(knee_angle_std, 3)],
        "torso_angle_std": [round(torso_angle_std, 3)],
        "quality_flag": [quality_flag if quality_flag is not None else ""],
        "full_body_quality_rate": [round(full_body_quality_rate, 3)],
        "feedback_type": [feedback_type],
        "feedback_message": [main_feedback],
        "auto_judgement": [auto_judgement],
        "memo": [error_message if error_occurred else ""],
        "smoothing_applied": [True],
        "squat_count": [squat_count],
        "final_phase": [current_phase],
        "count_confidence": [count_confidence]
    }
    df_new = pd.DataFrame(data)
    if os.path.isfile(csv_path):
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
    # return summary dict for UI table
    return {
        "filename": filename,
        "auto_result": auto_judgement,
        "skeleton_detection_rate": round(skeleton_detected_ratio, 2),
        "squat_count": squat_count,
        "count_confidence": count_confidence,
        "knee_angle_min": round(knee_angle_min, 1) if knee_angle_min is not None else None,
        "torso_angle_max": round(torso_angle_max, 1) if torso_angle_max is not None else None,
        "feedback_type": feedback_type,
        "feedback_message": main_feedback,
    }
