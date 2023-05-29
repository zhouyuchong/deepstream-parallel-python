from enum import Enum, unique


@unique
class AnalyticsValue(Enum):
    LINECROSSING = 1
    ROIREGION = 2


MUXER_OUTPUT_WIDTH=3392
MUXER_OUTPUT_HEIGHT=2000