"""Exception types raised by video2sm."""


class Video2SmError(Exception):
    """Base class for all expected, user-facing failures."""


class MediaError(Video2SmError):
    """ffmpeg/ffprobe failed or the input media is unusable."""


class AnalysisError(Video2SmError):
    """The audio could not be analysed (silence, too short, no beat)."""


class SimfileError(Video2SmError):
    """A simfile is malformed or could not be written/validated."""
