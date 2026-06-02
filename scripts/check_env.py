import os
import sys
import platform

def main():
    print("====================================================")
    print("         FitCheck AI Environment Diagnostics")
    print("====================================================")
    
    # 1. Python Path
    print(f"Python Executable Path: {sys.executable}")
    
    # 2. Python Version
    print(f"Python Version: {sys.version}")
    
    # 3. Python 64-bit status
    arch = platform.architecture()[0]
    print(f"Platform Architecture: {arch}")
    is_64bit = "64" in arch
    print(f"Is 64-bit Platform: {is_64bit}")
    
    # 4. Current working directory
    print(f"Current Working Directory: {os.getcwd()}")
    
    # 5. MediaPipe installation check
    mp_installed = False
    mp_version = "None"
    mp_file_path = "None"
    mp_path = None
    try:
        import mediapipe as mp
        mp_installed = True
        mp_version = mp.__version__
        mp_file_path = mp.__file__
        mp_path = os.path.dirname(mp_file_path)
        print(f"[SUCCESS] MediaPipe imported successfully.")
        print(f"MediaPipe Version: {mp_version}")
        print(f"MediaPipe File Path: {mp_file_path}")
        print(f"MediaPipe Package Root: {mp_path}")
    except ImportError as e:
        print(f"[ERROR] Failed to import MediaPipe: {e}")
        print("[FAILED] pose_landmark_cpu.binarypb is missing.")
        sys.exit(1)

    # 6. Check modules subfolder structures
    if mp_path:
        modules_dir = os.path.join(mp_path, "modules")
        print(f"\n--- Listing contents of: {modules_dir} ---")
        if os.path.exists(modules_dir):
            try:
                subfolders = [f for f in os.listdir(modules_dir) if os.path.isdir(os.path.join(modules_dir, f))]
                print(f"Subfolders inside mediapipe/modules ({len(subfolders)}):")
                for folder in subfolders:
                    print(f" - {folder}")
            except Exception as e:
                print(f"[ERROR] Failed to list modules directory: {e}")
        else:
            print("[ERROR] mediapipe/modules directory does not exist.")

        # 7. Check pose_landmark folder presence
        pose_landmark_dir = os.path.join(mp_path, "modules", "pose_landmark")
        dir_exists = os.path.exists(pose_landmark_dir)
        print(f"\npose_landmark directory exists: {dir_exists}")
        
        if dir_exists:
            # Check pose_landmark_cpu.binarypb file presence
            binarypb_file = os.path.join(pose_landmark_dir, "pose_landmark_cpu.binarypb")
            binary_exists = os.path.exists(binarypb_file)
            print(f"pose_landmark_cpu.binarypb file exists: {binary_exists}")
            
            # Listing other models (lite/full/heavy .tflite files)
            print("\nListing model files inside pose_landmark folder:")
            try:
                files = os.listdir(pose_landmark_dir)
                for file in files:
                    # Filter for tflite or binarypb files
                    if file.endswith(".tflite") or file.endswith(".binarypb"):
                        print(f" - {file} ({os.path.getsize(os.path.join(pose_landmark_dir, file))} bytes)")
            except Exception as e:
                print(f"[ERROR] Failed to list pose_landmark files: {e}")
            
            if binary_exists:
                print("\n[SUCCESS] pose_landmark_cpu.binarypb exists.")
                sys.exit(0)
            else:
                print("\n[FAILED] pose_landmark_cpu.binarypb is missing.")
                sys.exit(1)
        else:
            print("\n[FAILED] pose_landmark_cpu.binarypb is missing.")
            sys.exit(1)
    else:
        print("\n[FAILED] pose_landmark_cpu.binarypb is missing.")
        sys.exit(1)

if __name__ == "__main__":
    main()
