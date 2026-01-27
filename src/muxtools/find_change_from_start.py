import cv2

from typing import Annotated

from typer import Argument, Option
from ..app import app


def find_change_from_start_inner(
    video_path, threshold=0, min_changed_pixels=50
) -> tuple[int, float]:
    """
    Consumes video one frame at a time to find where it diverges from Frame 1.

    Args:
        video_path (str): Path to video file.
        threshold (int): Sensitivity (0-255). Lower = detects subtle changes.
                         Higher = ignores compression artifacts.
        min_changed_pixels (int): How many pixels must change to trigger detection.

    Returns:
        tuple[int, float]: Frame number where change is detected and FPS of the video.
                           Returns -1 if no significant change is found.
    """

    # 1. Open the video stream
    cap = cv2.VideoCapture(video_path)

    try:
        if not cap.isOpened():
            raise FileNotFoundError(f"Could not open video file: {video_path}")

        # 2. Read Frame 1 (The Reference)
        ret, frame1 = cap.read()
        if not ret:
            raise ValueError("Video file is empty or unreadable.")

        # Convert to grayscale to reduce complexity and ignore color noise
        frame1_gray = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)

        # Optional: Apply slight blur to reduce compression artifact noise
        frame1_gray = cv2.GaussianBlur(frame1_gray, (21, 21), 0)

        frame_count = 1
        fps = cap.get(cv2.CAP_PROP_FPS)

        # 3. Loop through the stream one frame at a time
        while True:
            # returns (bool, numpy_array)
            ret, current_frame = cap.read()

            # If no frame is returned, we reached the end of the video
            if not ret:
                return -1, fps  # No significant change found

            frame_count += 1

            # Convert current frame to grayscale
            current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
            current_gray = cv2.GaussianBlur(current_gray, (21, 21), 0)

            # 4. Compute Absolute Difference between Frame 1 and Current Frame
            # This creates an image where black pixels means "no change"
            # and white pixels means "change"
            delta = cv2.absdiff(frame1_gray, current_gray)

            # 5. Apply Threshold
            # Any pixel difference < threshold becomes 0 (black).
            # Any pixel difference > threshold becomes 255 (white).
            thresh_img = cv2.threshold(delta, threshold, 255, cv2.THRESH_BINARY)[1]

            # 6. Check if enough pixels have changed
            # We count the white pixels in the threshold image
            changed_pixels = cv2.countNonZero(thresh_img)

            if changed_pixels > min_changed_pixels:
                # Optional: Save the frame to verify
                # cv2.imwrite(f"change_detected_frame_{frame_count}.jpg", current_frame)
                return frame_count, fps

    # 7. Release resources
    finally:
        cap.release()


@app.command()
def find_change_from_start(
    video_path: Annotated[
        str,
        Argument(
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
            help="Path to the video file to analyze.",
        ),
    ],
    threshold: int = Option(
        default=0,
        help="Sensitivity (0-255). Lower = detects subtle changes. Higher = ignores compression artifacts.",
    ),
    min_changed_pixels: int = Option(
        default=50,
        help="How many pixels must change to trigger detection.",
    ),
):
    """Find where a video diverges from its first frame.

    :param video_path: Path to the video file to analyze.
    :param threshold: Sensitivity (0-255). Lower = detects subtle changes. Higher = ignores compression artifacts.
    :param min_changed_pixels: How many pixels must change to trigger detection.
    """
    frame_diff_at, fps = find_change_from_start_inner(
        video_path=video_path,
        threshold=threshold,
        min_changed_pixels=min_changed_pixels,
    )
    frame_diff_at_secs = frame_diff_at / fps if frame_diff_at != -1 else -1
    if frame_diff_at == -1:
        print("No significant change detected in the video.")
    else:
        print(
            f"Significant change detected at frame {frame_diff_at} ({frame_diff_at_secs} seconds)."
        )
