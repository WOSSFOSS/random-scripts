import asyncio
from typing import Annotated

from typer import Argument, Option
from ..app import app
from .find_change_from_start import (
    find_change_from_start_inner,
    find_change_from_first_frame,
)


async def create_offset_mkv_inner(
    bd_path: str,
    target_path: str,
    output_path: str,
    output_offset: bool,
    silent: bool,
    *,
    keep_video: bool = False,
    output_offset_frame_number: bool = False,
):
    bd_offset_frame, bd_fps, first_frame = find_change_from_start_inner(bd_path)
    if bd_offset_frame == -1:
        raise ValueError("No significant change found in BD video.")
    bd_offset_seconds = bd_offset_frame / bd_fps
    target_offset_frame, target_fps = find_change_from_first_frame(
        target_path, first_frame
    )
    if target_offset_frame == -1:
        raise ValueError("No significant change found in target video.")
    target_offset_seconds = target_offset_frame / target_fps
    # Positive if BD starts later, negative if earlier
    offset_seconds = round(bd_offset_seconds - target_offset_seconds, 5)
    if not silent:
        print(
            f"Calculated offset: {offset_seconds} seconds, adjusting all non-video streams accordingly."
        )
    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "quiet",
        "-itsoffset",
        str(offset_seconds),
        "-i",
        target_path,
        "-map",
        "0",
    ]
    if not keep_video:
        ffmpeg_command += [
            "-map",
            "-0:v",  # Exclude original video stream
        ]
    ffmpeg_command += [
        "-map_metadata",
        "0",
        "-c",
        "copy",
        output_path,
    ]
    proc = await asyncio.create_subprocess_exec(
        *ffmpeg_command, stdout=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg command failed with return code {proc.returncode}")
    if output_offset:
        if output_offset_frame_number:
            offset_frames = round(offset_seconds * target_fps)
            print(offset_frames)
        else:
            print(offset_seconds)


@app.command()
def create_offset_mkv(
    bd_path: Annotated[
        str,
        Argument(
            help="Path to the Blu-ray video file to analyze for offset.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    target_path: Annotated[
        str,
        Argument(
            help="Path to the target video file to adjust.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        ),
    ],
    output_path: Annotated[
        str,
        Argument(
            help="Path to save the output MKV file with adjusted timing.",
        ),
    ],
    output_offset: Annotated[
        bool,
        Option(
            help="If true, output the adjusted timing in seconds.",
            is_flag=True,
        ),
    ] = False,
    output_offset_frame_number: Annotated[
        bool,
        Option(
            help="If true, output the adjusted timing in frame numbers instead of seconds.",
            is_flag=True,
        ),
    ] = False,
    silent: Annotated[
        bool,
        Option(
            help="If true, suppress output messages (other than the offset if requested).",
            is_flag=True,
        ),
    ] = False,
    keep_video: Annotated[
        bool,
        Option(
            help="If true, keep the original video stream in the output file.",
            is_flag=True,
        ),
    ] = False,
):
    """Create an MKV file with adjusted timing based on offset from Blu-ray video.

    :param bd_path: Path to the Blu-ray video file to analyze for offset.
    :param target_path: Path to the target video file to adjust.
    :param output_path: Path to save the output MKV file with adjusted timing.
    :param output_offset: If true, output the adjusted timing.
    :param output_offset_frame_number: If true, output the adjusted timing in frame numbers instead of seconds.
    :param silent: If true, suppress output messages (other than the offset if requested).
    :param keep_video: If true, keep the original video stream in the output file.
    """
    asyncio.run(
        create_offset_mkv_inner(
            bd_path=bd_path,
            target_path=target_path,
            output_path=output_path,
            output_offset=output_offset,
            silent=silent,
            keep_video=keep_video,
            output_offset_frame_number=output_offset_frame_number,
        )
    )
