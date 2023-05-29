from enum import Enum, unique

@unique
class CounterOp(Enum):
    UP = "up"
    DOWN = "down"

@unique
class FaceState(Enum):
    INIT = 0
    TOINFER = 1
    TOSAVE = 2
    TOSEND = 3
    FINISH = 4

MAX_NUM_SOURCES = 16
MUXER_OUTPUT_WIDTH=1920
MUXER_OUTPUT_HEIGHT=1080
MAX_TIME_STAMP_LEN = 32
MIN_FACE_WIDTH = 112
MIN_FACE_HEIGHT = 112

MAX_FACE_IN_POOL = 40