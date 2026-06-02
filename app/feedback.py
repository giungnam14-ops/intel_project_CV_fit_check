FEEDBACK_MESSAGES = {
    "GOOD": "전체적으로 안정적인 자세예요. 지금처럼 천천히 반복해보세요.",
    "NOT_DEEP": "조금만 더 앉아볼까요? 엉덩이를 뒤로 보내며 의자에 앉는 느낌으로 내려가보세요.",
    "LEAN_FORWARD": "상체가 앞으로 많이 기울어졌어요. 가슴을 살짝 들어 정면을 바라보는 느낌으로 해보세요.",
    "TOO_DEEP": "너무 깊게 앉았어요. 무릎과 허리에 부담이 가지 않도록 적당한 깊이에서 멈춰보세요.",
    "LOW_VISIBILITY": "몸 전체가 화면에 잘 보이지 않아요. 카메라 위치와 조명을 다시 맞춰주세요.",
    "UNCERTAIN_VIEW": "카메라 각도 때문에 자세를 확실히 판단하기 어려워요. 측면에서 전신이 보이도록 다시 촬영해보세요.",
    "READY": "전신이 화면에 들어오면 자세 분석을 시작할게요.",
    "PREP_PHASE": "자세를 인식하는 중이에요. 전신이 화면에 들어오게 서주세요.",
    "CAMERA_ADJUSTMENT": "전신이 화면에 들어오도록 카메라를 조금 뒤로 조정해주세요."
}

def get_feedback(knee_angle, torso_slope):
    """
    관절 연산 수치를 바탕으로 사용자의 스쿼트 자세에 최적화된 초보자용 피드백 유형을 결정하여 메시지를 반환합니다.
    """
    if knee_angle is None or torso_slope is None:
        return FEEDBACK_MESSAGES["READY"]
        
    if torso_slope >= 45:
        return FEEDBACK_MESSAGES["LEAN_FORWARD"]
        
    if knee_angle < 60:
        return FEEDBACK_MESSAGES["TOO_DEEP"]
        
    if knee_angle >= 110:
        return FEEDBACK_MESSAGES["NOT_DEEP"]
        
    return FEEDBACK_MESSAGES["GOOD"]
