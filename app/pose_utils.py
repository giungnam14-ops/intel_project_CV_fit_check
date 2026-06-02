import cv2
import mediapipe as mp
import numpy as np

# =================================================================
# 표준 MediaPipe 솔루션 및 드로잉 모듈 바인딩
# =================================================================
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

def init_pose():
    """
    MediaPipe Pose 솔루션을 초기화합니다.
    어떤 특정 경로의 하드코딩된 binarypb 파일 존재 여부도 직접적으로 점검하지 않고,
    MediaPipe 패키지가 내부 휠(wheel) 경로를 직접 해석하여 Pose 모델을 인스턴스화 하도록 위임합니다.
    """
    try:
        pose = mp_pose.Pose(
            static_image_mode=False,        # 비디오 연속 분석에 맞추어 False로 설정
            model_complexity=1,             # 속도와 정합성이 조화로운 1단계 모델
            enable_segmentation=False,      # 세그멘테이션 제외 (연산 성능 향상)
            min_detection_confidence=0.7,    # 검출 최소 신뢰도 (0.5 -> 0.7 상향)
            min_tracking_confidence=0.7     # 추적 최소 신뢰도 (0.5 -> 0.7 상향)
        )
        return pose
    except Exception as e:
        raise RuntimeError(f"Failed to initialize MediaPipe Pose: {e}")

def calculate_angle(a, b, c):
    """
    세 2차원 좌표 a, b, c 사이의 사잇각을 3점 공식을 통해 연산합니다. 꼭짓점은 b입니다.
    """
    a = np.array(a)
    b = np.array(b)
    c = np.array(c)
    
    ba = a - b
    bc = c - b
    
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    angle = np.arccos(cosine_angle)
    return np.degrees(angle)

def calculate_slope(hip, shoulder):
    """
    골반(hip)과 어깨(shoulder) 사이의 선이 가상 수직선([0, -1]) 대비 갖는 숙임도 각도를 구합니다.
    """
    hip = np.array(hip)
    shoulder = np.array(shoulder)
    
    torso_vector = shoulder - hip
    vertical_vector = np.array([0, -1])
    
    cosine_angle = np.dot(torso_vector, vertical_vector) / (np.linalg.norm(torso_vector) * np.linalg.norm(vertical_vector) + 1e-6)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    angle = np.arccos(cosine_angle)
    return np.degrees(angle)

def extract_pose_data(pose, frame):
    """
    비디오 프레임에서 Pose 관절 좌표를 추출하고 무릎 각도 및 상체 기울기 정보를 구합니다.
    랜드마크 검출에 실패하거나 감지 신뢰도가 임계치보다 낮은 경우 안전하게 None을 돌려줍니다.
    """
    try:
        # OpenCV BGR 채널 포맷을 RGB로 변경
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)
        
        if not results.pose_landmarks:
            return None
        
        landmarks = results.pose_landmarks.landmark
        
        # 왼쪽 관절 랜드마크 데이터 바인딩
        left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
        left_hip = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
        left_knee = landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]
        left_ankle = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value]
        
        # 오른쪽 관절 랜드마크 데이터 바인딩
        right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
        right_hip = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
        right_knee = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]
        right_ankle = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]
        
        # 좌/우 신체 중 카메라 구도 상 더 선명하고 뚜렷히 인식된 랜드마크(Visibility가 큰 쪽) 자동 선택
        left_confidence = (left_shoulder.visibility + left_hip.visibility + left_knee.visibility + left_ankle.visibility) / 4.0
        right_confidence = (right_shoulder.visibility + right_hip.visibility + right_knee.visibility + right_ankle.visibility) / 4.0
        
        # 최소 가시성 임계값 (조정 가능)
        min_visibility = 0.5
        
        # 기본값을 False 로 시작
        uncertain_view = False
        
        if left_confidence > right_confidence:
            # 왼쪽 신체 분석
            essential_visibility = left_confidence
            shoulder = [left_shoulder.x, left_shoulder.y]
            hip = [left_hip.x, left_hip.y]
            knee = [left_knee.x, left_knee.y]
            ankle = [left_ankle.x, left_ankle.y]
            side = "left"
            joint_visibilities = [left_shoulder.visibility, left_hip.visibility, left_knee.visibility, left_ankle.visibility]
        else:
            # 오른쪽 신체 분석
            essential_visibility = right_confidence  # 기존에 누락된 essential_visibility 추가
            shoulder = [right_shoulder.x, right_shoulder.y]
            hip = [right_hip.x, right_hip.y]
            knee = [right_knee.x, right_knee.y]
            ankle = [right_ankle.x, right_ankle.y]
            side = "right"
            joint_visibilities = [right_shoulder.visibility, right_hip.visibility, right_knee.visibility, right_ankle.visibility]
        
        # 가시성이 낮은 관절이 있더라도 계산을 진행하고, 상태를 표시하도록 함
        visibility_status = "GOOD"
        for v in joint_visibilities:
            if v < min_visibility:
                # 하나라도 기준 이하이면 LOW_VISIBILITY 로 전환 (하지만 여기서는 ambiguous view 판단에 사용)
                visibility_status = "LOW_VISIBILITY"
                break
        if essential_visibility < min_visibility:
            visibility_status = "LOW_VISIBILITY"
        
        # ----- View quality 판단 로직 -----
        # 1) 양쪽 가시성이 비슷하면(차이가 0.1 미만) 측면 구도가 애매하다고 판단
        if abs(left_confidence - right_confidence) < 0.1:
            uncertain_view = True
        # 2) 선택된 쪽의 핵심 관절 중 하나라도 가시성이 낮으면 uncertain
        if any(v < min_visibility for v in joint_visibilities):
            uncertain_view = True
        # 3) 선택된 쪽의 관절 연결이 비정상적으로 짧거나 겹치는 경우(거리 비율) – 간단히 3개의 관절 간 거리 차이를 확인
        #    여기서는 구현을 간단히 하여, 어깨-골반, 골반-무릎, 무릎-발목 사이 거리 중 하나라도 0.02 이하(정규화 좌표)이면 uncertain 로 케이스 추가
        def norm_dist(p1, p2):
            return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** 0.5
        d1 = norm_dist(shoulder, hip)
        d2 = norm_dist(hip, knee)
        d3 = norm_dist(knee, ankle)
        if min(d1, d2, d3) < 0.02:
            uncertain_view = True
        # ---------------------------------
        
        if visibility_status == "LOW_VISIBILITY":
            # 기존 로직 유지 – 낮은 가시성은 LOW_VISIBILITY 로 표시
            feedback_type = "LOW_VISIBILITY"
        else:
            feedback_type = None  # 나중에 analysis 단계에서 판단
        
        # 주요 신체 기하학 분석
        knee_angle = calculate_angle(hip, knee, ankle)
        torso_slope = calculate_slope(hip, shoulder)
        
        return {
            "knee_angle": knee_angle,
            "torso_slope": torso_slope,
            "side": side,
            "essential_visibility": essential_visibility,
            "visibility_status": visibility_status,
            "uncertain_view": uncertain_view,
            "landmarks": results.pose_landmarks,
            "core_visibility": np.mean(joint_visibilities),
            "shoulder": shoulder,
            "hip": hip,
            "knee": knee,
            "ankle": ankle
        }
    except Exception:
        # 예외 시 에러 누출 없이 안정적으로 None 반환 처리
        return None
