import os
import sys
import platform

def main():
    print("====================================================")
    print("         MediaPipe Environment Diagnostics")
    print("====================================================")
    
    # 1. Python version and executable path
    print(f"Python version: {sys.version}")
    print(f"Python executable path: {sys.executable}")
    
    # 2. Platform architecture
    arch = platform.architecture()[0]
    print(f"Platform architecture: {arch}")
    is_64bit = "64" in arch
    print(f"Is 64-bit platform: {is_64bit}")
    
    # 3. MediaPipe import
    mp_imported = False
    mp_path = None
    try:
        import mediapipe as mp
        print("[SUCCESS] MediaPipe imported successfully.")
        print(f"mediapipe.__version__: {mp.__version__}")
        mp_path = os.path.dirname(mp.__file__)
        print(f"mediapipe.__file__: {mp.__file__}")
        print(f"MediaPipe package root: {mp_path}")
        mp_imported = True
    except ImportError as e:
        print(f"[ERROR] Failed to import MediaPipe: {e}")
        print("[FAILED] pose_landmark_cpu.binarypb is missing.")
        sys.exit(1)
        
    # 4. mp.solutions.pose check
    if mp_imported:
        try:
            mp_pose = mp.solutions.pose
            print("[SUCCESS] mp.solutions.pose is accessible.")
        except AttributeError as e:
            print(f"[ERROR] Solutions Pose API Attribute Error: {e}")
            print("[FAILED] pose_landmark_cpu.binarypb is missing.")
            sys.exit(1)
            
    # 5. modules/pose_landmark check
    if mp_path:
        pose_landmark_dir = os.path.join(mp_path, "modules", "pose_landmark")
        dir_exists = os.path.exists(pose_landmark_dir)
        print(f"mediapipe/modules/pose_landmark directory exists: {dir_exists}")
        
        if dir_exists:
            binarypb_file = os.path.join(pose_landmark_dir, "pose_landmark_cpu.binarypb")
            file_exists = os.path.exists(binarypb_file)
            print(f"pose_landmark_cpu.binarypb file exists: {file_exists}")
            
            # Listing other pose landmark files (pose_landmark_full.tflite, etc.)
            try:
                files = os.listdir(pose_landmark_dir)
                print(f"Files inside modules/pose_landmark folder ({len(files)} files):")
                for file in files:
                    print(f" - {file}")
            except Exception as e:
                print(f"[ERROR] Failed to list directory contents: {e}")
                
            if file_exists:
                print("[SUCCESS] pose_landmark_cpu.binarypb exists.")
                sys.exit(0)
            else:
                print("[FAILED] pose_landmark_cpu.binarypb is missing.")
                sys.exit(1)
        else:
            print("[ERROR] mediapipe/modules/pose_landmark directory does not exist.")
            print("[FAILED] pose_landmark_cpu.binarypb is missing.")
            sys.exit(1)
    else:
        print("[FAILED] pose_landmark_cpu.binarypb is missing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
