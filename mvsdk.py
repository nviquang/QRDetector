#coding=utf-8
import platform
from ctypes import *
from threading import local

# Callback function type
CALLBACK_FUNC_TYPE = None

# SDK dynamic library
_sdk = None

def _Init():
    global _sdk
    global CALLBACK_FUNC_TYPE

    is_win = (platform.system() == "Windows")
    is_x86 = (platform.architecture()[0] == '32bit')

    global AVAILABLE, LOAD_ERROR
    CALLBACK_FUNC_TYPE = WINFUNCTYPE if is_win else CFUNCTYPE
    try:
        if is_win:
            _sdk = windll.MVCAMSDK if is_x86 else windll.MVCAMSDK_X64
        else:
            _sdk = cdll.LoadLibrary("libMVSDK.so")
    except OSError as e:
        # QRDetector: máy chỉ dùng camera Basler (Jetson Nano) không cài MindVision SDK. Vẫn import được module;
        # gọi hàm SDK nào cũng báo OSError rõ ràng thay vì làm cả app không mở.
        AVAILABLE, LOAD_ERROR = False, e
        _sdk = _MissingSdk(e)

class _MissingSdk(object):
    def __init__(self, error):
        self._error = error
    def __getattr__(self, name):
        raise OSError("Chưa cài MindVision SDK (MVCAMSDK_X64.dll / libMVSDK.so), không gọi được %s: %s"
                      % (name, self._error))

AVAILABLE = True     # False khi không nạp được thư viện SDK
LOAD_ERROR = None
_Init()

#-------------------------------------------Type Definitions--------------------------------------------------

# Status code definitions
CAMERA_STATUS_SUCCESS = 0   # Operation successful
CAMERA_STATUS_FAILED = -1   # Operation failed
CAMERA_STATUS_INTERNAL_ERROR = -2   # Internal error
CAMERA_STATUS_UNKNOW = -3   # Unknown error
CAMERA_STATUS_NOT_SUPPORTED = -4   # Feature not supported
CAMERA_STATUS_NOT_INITIALIZED = -5   # Initialization not completed
CAMERA_STATUS_PARAMETER_INVALID = -6   # Invalid parameter
CAMERA_STATUS_PARAMETER_OUT_OF_BOUND = -7   # Parameter out of bounds
CAMERA_STATUS_UNENABLED = -8   # Not enabled
CAMERA_STATUS_USER_CANCEL = -9   # User manually cancelled, e.g., clicking cancel on ROI panel
CAMERA_STATUS_PATH_NOT_FOUND = -10  # Path not found in registry
CAMERA_STATUS_SIZE_DISMATCH = -11  # Image data length does not match defined size
CAMERA_STATUS_TIME_OUT = -12  # Timeout error
CAMERA_STATUS_IO_ERROR = -13  # Hardware IO error
CAMERA_STATUS_COMM_ERROR = -14  # Communication error
CAMERA_STATUS_BUS_ERROR = -15  # Bus error
CAMERA_STATUS_NO_DEVICE_FOUND = -16  # No device found
CAMERA_STATUS_NO_LOGIC_DEVICE_FOUND = -17  # No logic device found
CAMERA_STATUS_DEVICE_IS_OPENED = -18  # Device already opened
CAMERA_STATUS_DEVICE_IS_CLOSED = -19  # Device already closed
CAMERA_STATUS_DEVICE_VEDIO_CLOSED = -20  # Device video not opened. Returns this error when calling recording functions if camera video is not opened.
CAMERA_STATUS_NO_MEMORY = -21  # Insufficient system memory
CAMERA_STATUS_FILE_CREATE_FAILED = -22  # Failed to create file
CAMERA_STATUS_FILE_INVALID = -23  # Invalid file format
CAMERA_STATUS_WRITE_PROTECTED = -24  # Write protected
CAMERA_STATUS_GRAB_FAILED = -25  # Data capture failed
CAMERA_STATUS_LOST_DATA = -26  # Data lost, incomplete
CAMERA_STATUS_EOF_ERROR = -27  # Frame end marker not received
CAMERA_STATUS_BUSY = -28  # Busy (previous operation still in progress), current operation cannot proceed
CAMERA_STATUS_WAIT = -29  # Need to wait (operation conditions not met), can try again
CAMERA_STATUS_IN_PROCESS = -30  # In progress, already operated
CAMERA_STATUS_IIC_ERROR = -31  # IIC transmission error
CAMERA_STATUS_SPI_ERROR = -32  # SPI transmission error
CAMERA_STATUS_USB_CONTROL_ERROR = -33  # USB control transmission error
CAMERA_STATUS_USB_BULK_ERROR = -34  # USB BULK transmission error
CAMERA_STATUS_SOCKET_INIT_ERROR = -35  # Network transmission suite initialization failed
CAMERA_STATUS_GIGE_FILTER_INIT_ERROR = -36  # Network camera kernel filter driver initialization failed, please check if driver is installed correctly or reinstall.
CAMERA_STATUS_NET_SEND_ERROR = -37  # Network data send error
CAMERA_STATUS_DEVICE_LOST = -38  # Lost connection with network camera, heartbeat detection timeout
CAMERA_STATUS_DATA_RECV_LESS = -39  # Received fewer bytes than requested
CAMERA_STATUS_FUNCTION_LOAD_FAILED = -40  # Failed to load program from file
CAMERA_STATUS_CRITICAL_FILE_LOST = -41  # Critical file for program execution is missing.
CAMERA_STATUS_SENSOR_ID_DISMATCH = -42  # Firmware and program mismatch, caused by downloading wrong firmware.
CAMERA_STATUS_OUT_OF_RANGE = -43  # Parameter exceeds valid range.
CAMERA_STATUS_REGISTRY_ERROR = -44  # Installation program registration error. Please reinstall the program, or run Setup/Installer.exe in installation directory
CAMERA_STATUS_ACCESS_DENY = -45  # Access denied. Returns this status when requesting access to a camera already occupied by another program. (A camera cannot be accessed by multiple programs simultaneously)
#AIA standard compatible error codes
CAMERA_AIA_PACKET_RESEND = 0x0100 #Frame needs retransmission
CAMERA_AIA_NOT_IMPLEMENTED = 0x8001 #Command not supported by device
CAMERA_AIA_INVALID_PARAMETER = 0x8002 #Invalid command parameter
CAMERA_AIA_INVALID_ADDRESS = 0x8003 #Inaccessible address
CAMERA_AIA_WRITE_PROTECT = 0x8004 #Object not writable
CAMERA_AIA_BAD_ALIGNMENT = 0x8005 #Address not aligned as required
CAMERA_AIA_ACCESS_DENIED = 0x8006 #No access permission
CAMERA_AIA_BUSY = 0x8007 #Command is being processed
CAMERA_AIA_DEPRECATED = 0x8008 #0x8008-0x0800B  0x800F  This command is deprecated
CAMERA_AIA_PACKET_UNAVAILABLE = 0x800C #Invalid packet
CAMERA_AIA_DATA_OVERRUN = 0x800D #Data overflow, usually received more data than needed
CAMERA_AIA_INVALID_HEADER = 0x800E #Some areas in packet header do not match protocol
CAMERA_AIA_PACKET_NOT_YET_AVAILABLE = 0x8010 #Image packet data not ready, mostly used in trigger mode, application access timeout
CAMERA_AIA_PACKET_AND_PREV_REMOVED_FROM_MEMORY = 0x8011 #Requested packet no longer exists. Mostly used when data is no longer in buffer during retransmission
CAMERA_AIA_PACKET_REMOVED_FROM_MEMORY = 0x8012 #CAMERA_AIA_PACKET_AND_PREV_REMOVED_FROM_MEMORY
CAMERA_AIA_NO_REF_TIME = 0x0813 #No reference clock source. Mostly used when executing time synchronization commands
CAMERA_AIA_PACKET_TEMPORARILY_UNAVAILABLE = 0x0814 #Current packet temporarily unavailable due to channel bandwidth issues, please access later
CAMERA_AIA_OVERFLOW = 0x0815 #Device data overflow, usually queue is full
CAMERA_AIA_ACTION_LATE = 0x0816 #Command execution has exceeded the valid specified time
CAMERA_AIA_ERROR = 0x8FFF   #Error

# Image format definitions
CAMERA_MEDIA_TYPE_MONO = 0x01000000
CAMERA_MEDIA_TYPE_RGB = 0x02000000
CAMERA_MEDIA_TYPE_COLOR = 0x02000000
CAMERA_MEDIA_TYPE_OCCUPY1BIT = 0x00010000
CAMERA_MEDIA_TYPE_OCCUPY2BIT = 0x00020000
CAMERA_MEDIA_TYPE_OCCUPY4BIT = 0x00040000
CAMERA_MEDIA_TYPE_OCCUPY8BIT = 0x00080000
CAMERA_MEDIA_TYPE_OCCUPY10BIT = 0x000A0000
CAMERA_MEDIA_TYPE_OCCUPY12BIT = 0x000C0000
CAMERA_MEDIA_TYPE_OCCUPY16BIT = 0x00100000
CAMERA_MEDIA_TYPE_OCCUPY24BIT = 0x00180000
CAMERA_MEDIA_TYPE_OCCUPY32BIT = 0x00200000
CAMERA_MEDIA_TYPE_OCCUPY36BIT = 0x00240000
CAMERA_MEDIA_TYPE_OCCUPY48BIT = 0x00300000
CAMERA_MEDIA_TYPE_EFFECTIVE_PIXEL_SIZE_MASK = 0x00FF0000
CAMERA_MEDIA_TYPE_EFFECTIVE_PIXEL_SIZE_SHIFT = 16
CAMERA_MEDIA_TYPE_ID_MASK = 0x0000FFFF
CAMERA_MEDIA_TYPE_COUNT = 0x46

#mono
CAMERA_MEDIA_TYPE_MONO1P = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY1BIT | 0x0037)
CAMERA_MEDIA_TYPE_MONO2P = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY2BIT | 0x0038)
CAMERA_MEDIA_TYPE_MONO4P = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY4BIT | 0x0039)
CAMERA_MEDIA_TYPE_MONO8 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x0001)
CAMERA_MEDIA_TYPE_MONO8S = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x0002)
CAMERA_MEDIA_TYPE_MONO10 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0003)
CAMERA_MEDIA_TYPE_MONO10_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0004)
CAMERA_MEDIA_TYPE_MONO12 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0005)
CAMERA_MEDIA_TYPE_MONO12_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0006)
CAMERA_MEDIA_TYPE_MONO14 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0025)
CAMERA_MEDIA_TYPE_MONO16 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0007)

# Bayer
CAMERA_MEDIA_TYPE_BAYGR8 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x0008)
CAMERA_MEDIA_TYPE_BAYRG8 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x0009)
CAMERA_MEDIA_TYPE_BAYGB8 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x000A)
CAMERA_MEDIA_TYPE_BAYBG8 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY8BIT | 0x000B)

CAMERA_MEDIA_TYPE_BAYGR10_MIPI = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY10BIT | 0x0026)
CAMERA_MEDIA_TYPE_BAYRG10_MIPI = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY10BIT | 0x0027)
CAMERA_MEDIA_TYPE_BAYGB10_MIPI = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY10BIT | 0x0028)
CAMERA_MEDIA_TYPE_BAYBG10_MIPI = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY10BIT | 0x0029)

CAMERA_MEDIA_TYPE_BAYGR10 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x000C)
CAMERA_MEDIA_TYPE_BAYRG10 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x000D)
CAMERA_MEDIA_TYPE_BAYGB10 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x000E)
CAMERA_MEDIA_TYPE_BAYBG10 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x000F)

CAMERA_MEDIA_TYPE_BAYGR12 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0010)
CAMERA_MEDIA_TYPE_BAYRG12 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0011)
CAMERA_MEDIA_TYPE_BAYGB12 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0012)
CAMERA_MEDIA_TYPE_BAYBG12 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0013)

CAMERA_MEDIA_TYPE_BAYGR10_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0026)
CAMERA_MEDIA_TYPE_BAYRG10_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0027)
CAMERA_MEDIA_TYPE_BAYGB10_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0028)
CAMERA_MEDIA_TYPE_BAYBG10_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0029)

CAMERA_MEDIA_TYPE_BAYGR12_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x002A)
CAMERA_MEDIA_TYPE_BAYRG12_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x002B)
CAMERA_MEDIA_TYPE_BAYGB12_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x002C)
CAMERA_MEDIA_TYPE_BAYBG12_PACKED = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x002D)

CAMERA_MEDIA_TYPE_BAYGR16 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x002E)
CAMERA_MEDIA_TYPE_BAYRG16 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x002F)
CAMERA_MEDIA_TYPE_BAYGB16 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0030)
CAMERA_MEDIA_TYPE_BAYBG16 = (CAMERA_MEDIA_TYPE_MONO | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0031)

# RGB
CAMERA_MEDIA_TYPE_RGB8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x0014)
CAMERA_MEDIA_TYPE_BGR8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x0015)
CAMERA_MEDIA_TYPE_RGBA8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY32BIT | 0x0016)
CAMERA_MEDIA_TYPE_BGRA8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY32BIT | 0x0017)
CAMERA_MEDIA_TYPE_RGB10 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0018)
CAMERA_MEDIA_TYPE_BGR10 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0019)
CAMERA_MEDIA_TYPE_RGB12 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x001A)
CAMERA_MEDIA_TYPE_BGR12 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x001B)
CAMERA_MEDIA_TYPE_RGB16 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0033)
CAMERA_MEDIA_TYPE_RGB10V1_PACKED = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY32BIT | 0x001C)
CAMERA_MEDIA_TYPE_RGB10P32 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY32BIT | 0x001D)
CAMERA_MEDIA_TYPE_RGB12V1_PACKED = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY36BIT | 0X0034)
CAMERA_MEDIA_TYPE_RGB565P = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0035)
CAMERA_MEDIA_TYPE_BGR565P = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0X0036)

# YUV and YCbCr
CAMERA_MEDIA_TYPE_YUV411_8_UYYVYY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x001E)
CAMERA_MEDIA_TYPE_YUV422_8_UYVY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x001F)
CAMERA_MEDIA_TYPE_YUV422_8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0032)
CAMERA_MEDIA_TYPE_YUV8_UYV = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x0020)
CAMERA_MEDIA_TYPE_YCBCR8_CBYCR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x003A)
#CAMERA_MEDIA_TYPE_YCBCR422_8 : YYYYCbCrCbCr
CAMERA_MEDIA_TYPE_YCBCR422_8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x003B)
CAMERA_MEDIA_TYPE_YCBCR422_8_CBYCRY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0043)
CAMERA_MEDIA_TYPE_YCBCR411_8_CBYYCRYY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x003C)
CAMERA_MEDIA_TYPE_YCBCR601_8_CBYCR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x003D)
CAMERA_MEDIA_TYPE_YCBCR601_422_8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x003E)
CAMERA_MEDIA_TYPE_YCBCR601_422_8_CBYCRY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0044)
CAMERA_MEDIA_TYPE_YCBCR601_411_8_CBYYCRYY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x003F)
CAMERA_MEDIA_TYPE_YCBCR709_8_CBYCR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x0040)
CAMERA_MEDIA_TYPE_YCBCR709_422_8 = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0041)
CAMERA_MEDIA_TYPE_YCBCR709_422_8_CBYCRY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY16BIT | 0x0045)
CAMERA_MEDIA_TYPE_YCBCR709_411_8_CBYYCRYY = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY12BIT | 0x0042)

# RGB Planar
CAMERA_MEDIA_TYPE_RGB8_PLANAR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY24BIT | 0x0021)
CAMERA_MEDIA_TYPE_RGB10_PLANAR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0022)
CAMERA_MEDIA_TYPE_RGB12_PLANAR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0023)
CAMERA_MEDIA_TYPE_RGB16_PLANAR = (CAMERA_MEDIA_TYPE_COLOR | CAMERA_MEDIA_TYPE_OCCUPY48BIT | 0x0024)

# Save format
FILE_JPG = 1
FILE_BMP = 2
FILE_RAW = 4
FILE_PNG = 8
FILE_BMP_8BIT = 16
FILE_PNG_8BIT = 32
FILE_RAW_16BIT = 64

# Trigger signal
EXT_TRIG_LEADING_EDGE = 0
EXT_TRIG_TRAILING_EDGE = 1
EXT_TRIG_HIGH_LEVEL = 2
EXT_TRIG_LOW_LEVEL = 3
EXT_TRIG_DOUBLE_EDGE = 4

# IO mode
IOMODE_TRIG_INPUT = 0
IOMODE_STROBE_OUTPUT = 1
IOMODE_GP_INPUT = 2
IOMODE_GP_OUTPUT = 3
IOMODE_PWM_OUTPUT = 4


# Camera operation exception information
class CameraException(Exception):
    """docstring for CameraException"""
    def __init__(self, error_code):
        super(CameraException, self).__init__()
        self.error_code = error_code
        self.message = CameraGetErrorString(error_code)

    def __str__(self):
        return 'error_code:{} message:{}'.format(self.error_code, self.message)

class MvStructure(Structure):
    def __str__(self):
        strs = []
        for field in self._fields_:
            name = field[0]
            value = getattr(self, name)
            if isinstance(value, type(b'')):
                value = _string_buffer_to_str(value)
            strs.append("{}:{}".format(name, value))
        return '\n'.join(strs)

    def __repr__(self):
        return self.__str__()

    def clone(self):
        obj = type(self)()
        memmove(byref(obj), byref(self), sizeof(self))
        return obj

# Camera device information, read-only information, do not modify
class tSdkCameraDevInfo(MvStructure):
    _fields_ = [("acProductSeries", c_char * 32), #Product series
                ("acProductName", c_char * 32), #Product name
                ("acFriendlyName", c_char * 32), #Product nickname
                ("acLinkName", c_char * 32), #Kernel symbolic link name, for internal use
                ("acDriverVersion", c_char * 32), #Driver version
                ("acSensorType", c_char * 32), #Sensor type
                ("acPortType", c_char * 32), #Interface type
                ("acSn", c_char * 32), #Product unique serial number
                ("uInstance", c_uint)] #Instance index of this camera model on this computer, used to distinguish multiple cameras of the same model

    def GetProductSeries(self):
        return _string_buffer_to_str(self.acProductSeries)
    def GetProductName(self):
        return _string_buffer_to_str(self.acProductName)
    def GetFriendlyName(self):
        return _string_buffer_to_str(self.acFriendlyName)
    def GetLinkName(self):
        return _string_buffer_to_str(self.acLinkName)
    def GetDriverVersion(self):
        return _string_buffer_to_str(self.acDriverVersion)
    def GetSensorType(self):
        return _string_buffer_to_str(self.acSensorType)
    def GetPortType(self):
        return _string_buffer_to_str(self.acPortType)
    def GetSn(self):
        return _string_buffer_to_str(self.acSn)

# Camera resolution setting range
class tSdkResolutionRange(MvStructure):
    _fields_ = [("iHeightMax", c_int),     #Maximum image height
                ("iHeightMin", c_int),     #Minimum image height
                ("iWidthMax", c_int),     #Maximum image width
                ("iWidthMin", c_int),     #Minimum image width
                ("uSkipModeMask", c_uint),         #SKIP mode mask, 0 means SKIP not supported. Bit 0 is 1 means SKIP 2x2 supported, bit 1 is 1 means SKIP 3x3 supported....
                ("uBinSumModeMask", c_uint),   #BIN (sum) mode mask, 0 means BIN not supported. Bit 0 is 1 means BIN 2x2 supported, bit 1 is 1 means BIN 3x3 supported....
                ("uBinAverageModeMask", c_uint),#BIN (average) mode mask, 0 means BIN not supported. Bit 0 is 1 means BIN 2x2 supported, bit 1 is 1 means BIN 3x3 supported....
                ("uResampleMask", c_uint)]      #Hardware resampling mask

#Camera resolution description
class tSdkImageResolution(MvStructure):
    _fields_ = [
        ("iIndex", c_int),                # Index number, [0,N] indicates preset resolution (N is the maximum number of preset resolutions, generally no more than 20), 0xFF indicates custom resolution (ROI)
        ("acDescription", c_char * 32),   # Description information for this resolution. Only valid for preset resolutions. Custom resolutions can ignore this information
        ("uBinSumMode", c_uint),          # BIN (sum) mode, range cannot exceed uBinSumModeMask in tSdkResolutionRange
        ("uBinAverageMode", c_uint),      # BIN (average) mode, range cannot exceed uBinAverageModeMask in tSdkResolutionRange
        ("uSkipMode", c_uint),            # SKIP size mode, 0 means SKIP mode disabled, range cannot exceed uSkipModeMask in tSdkResolutionRange
        ("uResampleMask", c_uint),        # Hardware resampling mask
        ("iHOffsetFOV", c_int),        # Vertical offset of capture FOV relative to Sensor maximum FOV top-left corner
        ("iVOffsetFOV", c_int),        # Horizontal offset of capture FOV relative to Sensor maximum FOV top-left corner
        ("iWidthFOV", c_int),          # Width of capture FOV
        ("iHeightFOV", c_int),         # Height of capture FOV
        ("iWidth", c_int),             # Width of final output image from camera
        ("iHeight", c_int),            # Height of final output image from camera
        ("iWidthZoomHd", c_int),       # Hardware zoom width, set to 0 for resolutions that do not require this operation
        ("iHeightZoomHd", c_int),      # Hardware zoom height, set to 0 for resolutions that do not require this operation
        ("iWidthZoomSw", c_int),       # Software zoom width, set to 0 for resolutions that do not require this operation
        ("iHeightZoomSw", c_int),      # Software zoom height, set to 0 for resolutions that do not require this operation
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Camera white balance mode description information
class tSdkColorTemperatureDes(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Mode index number
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Camera frame rate description information
class tSdkFrameSpeed(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Frame rate index number, generally 0 corresponds to low speed mode, 1 corresponds to normal mode, 2 corresponds to high speed mode
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Camera exposure function range definition
class tSdkExpose(MvStructure):
    _fields_ = [
        ("uiTargetMin", c_uint),       #Minimum value for auto exposure brightness target
        ("uiTargetMax", c_uint),       #Maximum value for auto exposure brightness target
        ("uiAnalogGainMin", c_uint),   #Minimum analog gain value, unit defined in fAnalogGainStep
        ("uiAnalogGainMax", c_uint),   #Maximum analog gain value, unit defined in fAnalogGainStep
        ("fAnalogGainStep", c_float),  #Amplification factor increase per 1 increment of analog gain. For example, uiAnalogGainMin is usually 16, fAnalogGainStep is usually 0.125, so minimum amplification is 16*0.125 = 2x
        ("uiExposeTimeMin", c_uint),   #Minimum exposure time in manual mode, unit: lines. CameraGetExposureLineTime can get the time per line (microseconds), thus obtaining full frame exposure time
        ("uiExposeTimeMax", c_uint),   #Maximum exposure time in manual mode, unit: lines
    ]

#Trigger mode description
class tSdkTrigger(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Mode index number
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Transmission packet size description (mainly effective for network cameras)
class tSdkPackLength(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Mode index number
        ("acDescription", c_char * 32), # Description information
        ("iPackSize", c_uint),
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Preset LUT table description
class tSdkPresetLut(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Number
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#AE algorithm description
class tSdkAeAlgorithm(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Number
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#RAW to RGB algorithm description
class tSdkBayerDecodeAlgorithm(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Number
        ("acDescription", c_char * 32), # Description information
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Frame statistics information
class tSdkFrameStatistic(MvStructure):
    _fields_ = [
        ("iTotal", c_int),        #Total frames captured (including error frames)
        ("iCapture", c_int),      #Number of valid frames captured
        ("iLost", c_int),         #Number of lost frames
    ]

#Camera output image data format
class tSdkMediaType(MvStructure):
    _fields_ = [
        ("iIndex", c_int),              # Format type number
        ("acDescription", c_char * 32), # Description information
        ("iMediaType", c_uint),         # Corresponding image format code, such as CAMERA_MEDIA_TYPE_BAYGR8
    ]

    def GetDescription(self):
        return _string_buffer_to_str(self.acDescription)

#Gamma setting range
class tGammaRange(MvStructure):
    _fields_ = [
        ("iMin", c_int),       #Minimum value
        ("iMax", c_int),       #Maximum value
    ]

#Contrast setting range
class tContrastRange(MvStructure):
    _fields_ = [
        ("iMin", c_int),       #Minimum value
        ("iMax", c_int),       #Maximum value
    ]

#RGB three-channel digital gain setting range
class tRgbGainRange(MvStructure):
    _fields_ = [
        ("iRGainMin", c_int),   #Minimum red gain
        ("iRGainMax", c_int),   #Maximum red gain
        ("iGGainMin", c_int),   #Minimum green gain
        ("iGGainMax", c_int),   #Maximum green gain
        ("iBGainMin", c_int),   #Minimum blue gain
        ("iBGainMax", c_int),   #Maximum blue gain
    ]

#Saturation setting range
class tSaturationRange(MvStructure):
    _fields_ = [
        ("iMin", c_int),       #Minimum value
        ("iMax", c_int),       #Maximum value
    ]

#Sharpness setting range
class tSharpnessRange(MvStructure):
    _fields_ = [
        ("iMin", c_int),       #Minimum value
        ("iMax", c_int),       #Maximum value
    ]

#ISP module enable information
class tSdkIspCapacity(MvStructure):
    _fields_ = [
        ("bMonoSensor", c_int),        #Indicates whether this camera model is a monochrome camera. If it is a monochrome camera, all color-related functions cannot be adjusted
        ("bWbOnce", c_int),            #Indicates whether this camera model supports manual white balance function
        ("bAutoWb", c_int),            #Indicates whether this camera model supports auto white balance function
        ("bAutoExposure", c_int),      #Indicates whether this camera model supports auto exposure function
        ("bManualExposure", c_int),    #Indicates whether this camera model supports manual exposure function
        ("bAntiFlick", c_int),         #Indicates whether this camera model supports anti-flicker function
        ("bDeviceIsp", c_int),         #Indicates whether this camera model supports hardware ISP function
        ("bForceUseDeviceIsp", c_int), #When both bDeviceIsp and bForceUseDeviceIsp are TRUE, it means forced use of hardware ISP only, cannot be cancelled
        ("bZoomHD", c_int),            #Whether camera hardware supports image zoom output (can only zoom out)
    ]

# Define integrated device description information, this information can be used to dynamically build UI
class tSdkCameraCapbility(MvStructure):
    _fields_ = [
        ("pTriggerDesc", POINTER(tSdkTrigger)),
        ("iTriggerDesc", c_int),   #Number of trigger modes, i.e., size of pTriggerDesc array
        ("pImageSizeDesc", POINTER(tSdkImageResolution)),
        ("iImageSizeDesc", c_int), #Number of preset resolutions, i.e., size of pImageSizeDesc array
        ("pClrTempDesc", POINTER(tSdkColorTemperatureDes)),
        ("iClrTempDesc", c_int),   #Number of preset color temperatures
        ("pMediaTypeDesc", POINTER(tSdkMediaType)),
        ("iMediaTypeDesc", c_int), #Number of camera output image format types, i.e., size of pMediaTypeDesc array
        ("pFrameSpeedDesc", POINTER(tSdkFrameSpeed)), #Adjustable frame speed types, corresponding to normal, high speed and super speed settings on the interface
        ("iFrameSpeedDesc", c_int), #Number of adjustable frame speed types, i.e., size of pFrameSpeedDesc array
        ("pPackLenDesc", POINTER(tSdkPackLength)), #Transmission packet length, generally used for network devices
        ("iPackLenDesc", c_int), #Number of selectable transmission packet lengths, i.e., size of pPackLenDesc array
        ("iOutputIoCounts", c_int),        #Number of programmable output IOs
        ("iInputIoCounts", c_int),         #Number of programmable input IOs
        ("pPresetLutDesc", POINTER(tSdkPresetLut)), #Preset LUT tables in camera
        ("iPresetLut", c_int),             #Number of preset LUT tables in camera, i.e., size of pPresetLutDesc array
        ("iUserDataMaxLen", c_int),        #Indicates the maximum length of user data area in this camera. 0 means none
        ("bParamInDevice", c_int),         #Indicates whether this device supports reading/writing parameter groups from device. 1 means supported, 0 means not supported
        ("pAeAlmSwDesc", POINTER(tSdkAeAlgorithm)),#Software auto exposure algorithm description
        ("iAeAlmSwDesc", c_int),           #Number of software auto exposure algorithms
        ("pAeAlmHdDesc", POINTER(tSdkAeAlgorithm)),#Hardware auto exposure algorithm description, NULL means hardware auto exposure not supported
        ("iAeAlmHdDesc", c_int),           #Number of hardware auto exposure algorithms, 0 means hardware auto exposure not supported
        ("pBayerDecAlmSwDesc", POINTER(tSdkBayerDecodeAlgorithm)),#Software Bayer to RGB conversion algorithm description
        ("iBayerDecAlmSwDesc", c_int),     #Number of software Bayer to RGB conversion algorithms
        ("pBayerDecAlmHdDesc", POINTER(tSdkBayerDecodeAlgorithm)),#Hardware Bayer to RGB conversion algorithm description, NULL means not supported
        ("iBayerDecAlmHdDesc", c_int),     #Number of hardware Bayer to RGB conversion algorithms, 0 means not supported

        # Image parameter adjustment range definition, used for dynamically building UI
        ("sExposeDesc", tSdkExpose),      #Exposure range values
        ("sResolutionRange", tSdkResolutionRange), #Resolution range description
        ("sRgbGainRange", tRgbGainRange),    #Image digital gain range description
        ("sSaturationRange", tSaturationRange), #Saturation range description
        ("sGammaRange", tGammaRange),      #Gamma range description
        ("sContrastRange", tContrastRange),   #Contrast range description
        ("sSharpnessRange", tSharpnessRange),  #Sharpness range description
        ("sIspCapacity", tSdkIspCapacity),     #ISP capability description
    ]

#Image frame header information
class tSdkFrameHead(MvStructure):
    _fields_ = [
        ("uiMediaType", c_uint),      # Image format, Image Format
        ("uBytes", c_uint),           # Image data bytes, Total bytes
        ("iWidth", c_int),            # Width, Image height
        ("iHeight", c_int),           # Height, Image width
        ("iWidthZoomSw", c_int),      # Software zoom width, set to 0 for images that do not require software cropping
        ("iHeightZoomSw", c_int),     # Software zoom height, set to 0 for images that do not require software cropping
        ("bIsTrigger", c_int),        # Indicates whether it is a trigger frame, is trigger
        ("uiTimeStamp", c_uint),      # Capture time of this frame, unit 0.1 millisecond
        ("uiExpTime", c_uint),        # Exposure value of current image, unit microsecond us
        ("fAnalogGain", c_float),     # Analog gain multiplier of current image
        ("iGamma", c_int),            # Gamma setting value for this frame image, only valid when LUT mode is dynamic parameter generation, otherwise -1
        ("iContrast", c_int),         # Contrast setting value for this frame image, only valid when LUT mode is dynamic parameter generation, otherwise -1
        ("iSaturation", c_int),       # Saturation setting value for this frame image, meaningless for monochrome cameras, value is 0
        ("fRgain", c_float),          # Red digital gain multiplier for this frame image processing, meaningless for monochrome cameras, value is 1
        ("fGgain", c_float),          # Green digital gain multiplier for this frame image processing, meaningless for monochrome cameras, value is 1
        ("fBgain", c_float),          # Blue digital gain multiplier for this frame image processing, meaningless for monochrome cameras, value is 1
    ]

# Frame event
class tSdkFrameEvent(MvStructure):
    _fields_ = [
        ("uType", c_uint),          # Event type (1:frame start   2:frame end)
        ("uStatus", c_uint),        # Status (0:success, non-zero:error)
        ("uFrameID", c_uint),       # Frame ID
        ("uWidth", c_uint),         # Width
        ("uHeight", c_uint),        # Height
        ("uPixelFormat", c_uint),   # Image Format
        ("TimeStampL", c_uint),     # Lower 32 bits of timestamp
        ("TimeStampH", c_uint),     # High 32 bits of timestamp
    ]

# Grabber statistics information
class tSdkGrabberStat(MvStructure):
    _fields_ = [
        ("Width", c_int),           # Frame image size
        ("Height", c_int),          # Frame image size
        ("Disp", c_int),            # Display frame count
        ("Capture", c_int),         # Number of valid frames captured
        ("Lost", c_int),            # Number of lost frames
        ("Error", c_int),           # Number of error frames
        ("DispFps", c_float),       # Display frame rate
        ("CapFps", c_float),        # Capture frame rate
    ]

# Method callback helper class
class method(object):
    def __init__(self, FuncType):
        super(method, self).__init__()
        self.FuncType = FuncType
        self.cache = {}

    def __call__(self, cb):
        self.cb = cb
        return self

    def __get__(self, obj, objtype):
        try:
            return self.cache[obj]
        except KeyError as e:
            def cl(*args):
                return self.cb(obj, *args)
            r = self.cache[obj] = self.FuncType(cl)
            return r

# Image capture callback function definition
CAMERA_SNAP_PROC = CALLBACK_FUNC_TYPE(None, c_int, c_void_p, POINTER(tSdkFrameHead), c_void_p)

# Camera connection status callback
CAMERA_CONNECTION_STATUS_CALLBACK = CALLBACK_FUNC_TYPE(None, c_int, c_uint, c_uint, c_void_p)

# Frame event callback
CAMERA_FRAME_EVENT_CALLBACK = CALLBACK_FUNC_TYPE(None, c_int, POINTER(tSdkFrameEvent), c_void_p)

# Async image capture complete callback
pfnCameraGrabberSaveImageComplete = CALLBACK_FUNC_TYPE(None, c_void_p, c_void_p, c_int, c_void_p)

# Frame listener callback
pfnCameraGrabberFrameListener = CALLBACK_FUNC_TYPE(c_int, c_void_p, c_int, c_void_p, POINTER(tSdkFrameHead), c_void_p)

# Grabber image capture callback
pfnCameraGrabberFrameCallback = CALLBACK_FUNC_TYPE(None, c_void_p, c_void_p, POINTER(tSdkFrameHead), c_void_p)

#-----------------------------------Function Interfaces------------------------------------------

# Thread local storage
_tls = local()

# Store the error code returned by the last SDK call
def GetLastError():
    try:
        return _tls.last_error
    except AttributeError as e:
        _tls.last_error = 0
        return 0

def SetLastError(err_code):
    _tls.last_error = err_code

def _string_buffer_to_str(buf):
    s = buf if isinstance(buf, type(b'')) else buf.value

    for codec in ('gbk', 'utf-8'):
        try:
            s = s.decode(codec)
            break
        except UnicodeDecodeError as e:
            continue

    if isinstance(s, str):
        return s
    else:
        return s.encode('utf-8')

def _str_to_string_buffer(str):
    if type(str) is type(u''):
        s = str.encode('gbk')
    else:
        s = str.decode('utf-8').encode('gbk')
    return create_string_buffer(s)

def CameraSdkInit(iLanguageSel):
    err_code = _sdk.CameraSdkInit(iLanguageSel)
    SetLastError(err_code)
    return err_code

def CameraSetDataDirectory(dirname):
    err_code = _sdk.CameraSetDataDirectory(_str_to_string_buffer(dirname))
    SetLastError(err_code)
    return err_code

def CameraSetSysOption(optionName, value):
    err_code = _sdk.CameraSetSysOption(_str_to_string_buffer(optionName), _str_to_string_buffer(str(value)))
    SetLastError(err_code)
    return err_code

def CameraEnumerateDevice(MaxCount = 32):
    Nums = c_int(MaxCount)
    pCameraList = (tSdkCameraDevInfo * Nums.value)()
    err_code = _sdk.CameraEnumerateDevice(pCameraList, byref(Nums))
    SetLastError(err_code)
    return pCameraList[0:Nums.value]

def CameraEnumerateDeviceEx():
    return _sdk.CameraEnumerateDeviceEx()

def CameraIsOpened(pCameraInfo):
    pOpened = c_int()
    err_code = _sdk.CameraIsOpened(byref(pCameraInfo), byref(pOpened) )
    SetLastError(err_code)
    return pOpened.value != 0

def CameraInit(pCameraInfo, emParamLoadMode = -1, emTeam = -1):
    pCameraHandle = c_int()
    err_code = _sdk.CameraInit(byref(pCameraInfo), emParamLoadMode, emTeam, byref(pCameraHandle))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return pCameraHandle.value

def CameraInitEx(iDeviceIndex, emParamLoadMode = -1, emTeam = -1):
    pCameraHandle = c_int()
    err_code = _sdk.CameraInitEx(iDeviceIndex, emParamLoadMode, emTeam, byref(pCameraHandle))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return pCameraHandle.value

def CameraInitEx2(CameraName):
    pCameraHandle = c_int()
    err_code = _sdk.CameraInitEx2(_str_to_string_buffer(CameraName), byref(pCameraHandle))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return pCameraHandle.value

def CameraSetCallbackFunction(hCamera, pCallBack, pContext = 0):
    err_code = _sdk.CameraSetCallbackFunction(hCamera, pCallBack, c_void_p(pContext), None)
    SetLastError(err_code)
    return err_code

def CameraUnInit(hCamera):
    err_code = _sdk.CameraUnInit(hCamera)
    SetLastError(err_code)
    return err_code

def CameraGetInformation(hCamera):
    pbuffer = c_char_p()
    err_code = _sdk.CameraGetInformation(hCamera, byref(pbuffer) )
    SetLastError(err_code)
    if err_code == 0 and pbuffer.value is not None:
        return _string_buffer_to_str(pbuffer)
    return ''

def CameraImageProcess(hCamera, pbyIn, pbyOut, pFrInfo):
    err_code = _sdk.CameraImageProcess(hCamera, c_void_p(pbyIn), c_void_p(pbyOut), byref(pFrInfo))
    SetLastError(err_code)
    return err_code

def CameraImageProcessEx(hCamera, pbyIn, pbyOut, pFrInfo, uOutFormat, uReserved):
    err_code = _sdk.CameraImageProcessEx(hCamera, c_void_p(pbyIn), c_void_p(pbyOut), byref(pFrInfo), uOutFormat, uReserved)
    SetLastError(err_code)
    return err_code

def CameraDisplayInit(hCamera, hWndDisplay):
    err_code = _sdk.CameraDisplayInit(hCamera, hWndDisplay)
    SetLastError(err_code)
    return err_code

def CameraDisplayRGB24(hCamera, pFrameBuffer, pFrInfo):
    err_code = _sdk.CameraDisplayRGB24(hCamera, c_void_p(pFrameBuffer), byref(pFrInfo) )
    SetLastError(err_code)
    return err_code

def CameraSetDisplayMode(hCamera, iMode):
    err_code = _sdk.CameraSetDisplayMode(hCamera, iMode)
    SetLastError(err_code)
    return err_code

def CameraSetDisplayOffset(hCamera, iOffsetX, iOffsetY):
    err_code = _sdk.CameraSetDisplayOffset(hCamera, iOffsetX, iOffsetY)
    SetLastError(err_code)
    return err_code

def CameraSetDisplaySize(hCamera, iWidth, iHeight):
    err_code = _sdk.CameraSetDisplaySize(hCamera, iWidth, iHeight)
    SetLastError(err_code)
    return err_code

def CameraGetImageBuffer(hCamera, wTimes):
    pbyBuffer = c_void_p()
    pFrameInfo = tSdkFrameHead()
    err_code = _sdk.CameraGetImageBuffer(hCamera, byref(pFrameInfo), byref(pbyBuffer), wTimes)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (pbyBuffer.value, pFrameInfo)

def CameraGetImageBufferEx(hCamera, wTimes):
    _sdk.CameraGetImageBufferEx.restype = c_void_p
    piWidth = c_int()
    piHeight = c_int()
    pFrameBuffer = _sdk.CameraGetImageBufferEx(hCamera, byref(piWidth), byref(piHeight), wTimes)
    err_code = CAMERA_STATUS_SUCCESS if pFrameBuffer else CAMERA_STATUS_TIME_OUT
    SetLastError(err_code)
    if pFrameBuffer:
        return (pFrameBuffer, piWidth.value, piHeight.value)
    else:
        raise CameraException(err_code)

def CameraSnapToBuffer(hCamera, wTimes):
    pbyBuffer = c_void_p()
    pFrameInfo = tSdkFrameHead()
    err_code = _sdk.CameraSnapToBuffer(hCamera, byref(pFrameInfo), byref(pbyBuffer), wTimes)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (pbyBuffer.value, pFrameInfo)

def CameraReleaseImageBuffer(hCamera, pbyBuffer):
    err_code = _sdk.CameraReleaseImageBuffer(hCamera, c_void_p(pbyBuffer) )
    SetLastError(err_code)
    return err_code

def CameraPlay(hCamera):
    err_code = _sdk.CameraPlay(hCamera)
    SetLastError(err_code)
    return err_code

def CameraPause(hCamera):
    err_code = _sdk.CameraPause(hCamera)
    SetLastError(err_code)
    return err_code

def CameraStop(hCamera):
    err_code = _sdk.CameraStop(hCamera)
    SetLastError(err_code)
    return err_code

def CameraInitRecord(hCamera, iFormat, pcSavePath, b2GLimit, dwQuality, iFrameRate):
    err_code = _sdk.CameraInitRecord(hCamera, iFormat, _str_to_string_buffer(pcSavePath), b2GLimit, dwQuality, iFrameRate)
    SetLastError(err_code)
    return err_code

def CameraStopRecord(hCamera):
    err_code = _sdk.CameraStopRecord(hCamera)
    SetLastError(err_code)
    return err_code

def CameraPushFrame(hCamera, pbyImageBuffer, pFrInfo):
    err_code = _sdk.CameraPushFrame(hCamera, c_void_p(pbyImageBuffer), byref(pFrInfo) )
    SetLastError(err_code)
    return err_code

def CameraSaveImage(hCamera, lpszFileName, pbyImageBuffer, pFrInfo, byFileType, byQuality):
    err_code = _sdk.CameraSaveImage(hCamera, _str_to_string_buffer(lpszFileName), c_void_p(pbyImageBuffer), byref(pFrInfo), byFileType, byQuality)
    SetLastError(err_code)
    return err_code

def CameraSaveImageEx(hCamera, lpszFileName, pbyImageBuffer, uImageFormat, iWidth, iHeight, byFileType, byQuality):
    err_code = _sdk.CameraSaveImageEx(hCamera, _str_to_string_buffer(lpszFileName), c_void_p(pbyImageBuffer), uImageFormat, iWidth, iHeight, byFileType, byQuality)
    SetLastError(err_code)
    return err_code

def CameraGetImageResolution(hCamera):
    psCurVideoSize = tSdkImageResolution()
    err_code = _sdk.CameraGetImageResolution(hCamera, byref(psCurVideoSize) )
    SetLastError(err_code)
    return psCurVideoSize

def CameraSetImageResolution(hCamera, pImageResolution):
    err_code = _sdk.CameraSetImageResolution(hCamera, byref(pImageResolution) )
    SetLastError(err_code)
    return err_code

def CameraSetImageResolutionEx(hCamera, iIndex, Mode, ModeSize, x, y, width, height, ZoomWidth, ZoomHeight):
    err_code = _sdk.CameraSetImageResolutionEx(hCamera, iIndex, Mode, ModeSize, x, y, width, height, ZoomWidth, ZoomHeight)
    SetLastError(err_code)
    return err_code

def CameraGetMediaType(hCamera):
    piMediaType = c_int()
    err_code = _sdk.CameraGetMediaType(hCamera, byref(piMediaType) )
    SetLastError(err_code)
    return piMediaType.value

def CameraSetMediaType(hCamera, iMediaType):
    err_code = _sdk.CameraSetMediaType(hCamera, iMediaType)
    SetLastError(err_code)
    return err_code

def CameraSetAeState(hCamera, bAeState):
    err_code = _sdk.CameraSetAeState(hCamera, bAeState)
    SetLastError(err_code)
    return err_code

def CameraGetAeState(hCamera):
    pAeState = c_int()
    err_code = _sdk.CameraGetAeState(hCamera, byref(pAeState) )
    SetLastError(err_code)
    return pAeState.value

def CameraSetSharpness(hCamera, iSharpness):
    err_code = _sdk.CameraSetSharpness(hCamera, iSharpness)
    SetLastError(err_code)
    return err_code

def CameraGetSharpness(hCamera):
    piSharpness = c_int()
    err_code = _sdk.CameraGetSharpness(hCamera, byref(piSharpness) )
    SetLastError(err_code)
    return piSharpness.value

def CameraSetLutMode(hCamera, emLutMode):
    err_code = _sdk.CameraSetLutMode(hCamera, emLutMode)
    SetLastError(err_code)
    return err_code

def CameraGetLutMode(hCamera):
    pemLutMode = c_int()
    err_code = _sdk.CameraGetLutMode(hCamera, byref(pemLutMode) )
    SetLastError(err_code)
    return pemLutMode.value

def CameraSelectLutPreset(hCamera, iSel):
    err_code = _sdk.CameraSelectLutPreset(hCamera, iSel)
    SetLastError(err_code)
    return err_code

def CameraGetLutPresetSel(hCamera):
    piSel = c_int()
    err_code = _sdk.CameraGetLutPresetSel(hCamera, byref(piSel) )
    SetLastError(err_code)
    return piSel.value

def CameraSetCustomLut(hCamera, iChannel, pLut):
    pLutNative = (c_ushort * 4096)(*pLut)
    err_code = _sdk.CameraSetCustomLut(hCamera, iChannel, pLutNative)
    SetLastError(err_code)
    return err_code

def CameraGetCustomLut(hCamera, iChannel):
    pLutNative = (c_ushort * 4096)()
    err_code = _sdk.CameraGetCustomLut(hCamera, iChannel, pLutNative)
    SetLastError(err_code)
    return pLutNative[:]

def CameraGetCurrentLut(hCamera, iChannel):
    pLutNative = (c_ushort * 4096)()
    err_code = _sdk.CameraGetCurrentLut(hCamera, iChannel, pLutNative)
    SetLastError(err_code)
    return pLutNative[:]

def CameraSetWbMode(hCamera, bAuto):
    err_code = _sdk.CameraSetWbMode(hCamera, bAuto)
    SetLastError(err_code)
    return err_code

def CameraGetWbMode(hCamera):
    pbAuto = c_int()
    err_code = _sdk.CameraGetWbMode(hCamera, byref(pbAuto) )
    SetLastError(err_code)
    return pbAuto.value

def CameraSetPresetClrTemp(hCamera, iSel):
    err_code = _sdk.CameraSetPresetClrTemp(hCamera, iSel)
    SetLastError(err_code)
    return err_code

def CameraGetPresetClrTemp(hCamera):
    piSel = c_int()
    err_code = _sdk.CameraGetPresetClrTemp(hCamera, byref(piSel) )
    SetLastError(err_code)
    return piSel.value

def CameraSetUserClrTempGain(hCamera, iRgain, iGgain, iBgain):
    err_code = _sdk.CameraSetUserClrTempGain(hCamera, iRgain, iGgain, iBgain)
    SetLastError(err_code)
    return err_code

def CameraGetUserClrTempGain(hCamera):
    piRgain = c_int()
    piGgain = c_int()
    piBgain = c_int()
    err_code = _sdk.CameraGetUserClrTempGain(hCamera, byref(piRgain), byref(piGgain), byref(piBgain) )
    SetLastError(err_code)
    return (piRgain.value, piGgain.value, piBgain.value)

def CameraSetUserClrTempMatrix(hCamera, pMatrix):
    pMatrixNative = (c_float * 9)(*pMatrix)
    err_code = _sdk.CameraSetUserClrTempMatrix(hCamera, pMatrixNative)
    SetLastError(err_code)
    return err_code

def CameraGetUserClrTempMatrix(hCamera):
    pMatrixNative = (c_float * 9)()
    err_code = _sdk.CameraGetUserClrTempMatrix(hCamera, pMatrixNative)
    SetLastError(err_code)
    return pMatrixNative[:]

def CameraSetClrTempMode(hCamera, iMode):
    err_code = _sdk.CameraSetClrTempMode(hCamera, iMode)
    SetLastError(err_code)
    return err_code

def CameraGetClrTempMode(hCamera):
    piMode = c_int()
    err_code = _sdk.CameraGetClrTempMode(hCamera, byref(piMode) )
    SetLastError(err_code)
    return piMode.value

def CameraSetOnceWB(hCamera):
    err_code = _sdk.CameraSetOnceWB(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetOnceBB(hCamera):
    err_code = _sdk.CameraSetOnceBB(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetAeTarget(hCamera, iAeTarget):
    err_code = _sdk.CameraSetAeTarget(hCamera, iAeTarget)
    SetLastError(err_code)
    return err_code

def CameraGetAeTarget(hCamera):
    piAeTarget = c_int()
    err_code = _sdk.CameraGetAeTarget(hCamera, byref(piAeTarget) )
    SetLastError(err_code)
    return piAeTarget.value

def CameraSetAeExposureRange(hCamera, fMinExposureTime, fMaxExposureTime):
    err_code = _sdk.CameraSetAeExposureRange(hCamera, c_double(fMinExposureTime), c_double(fMaxExposureTime) )
    SetLastError(err_code)
    return err_code

def CameraGetAeExposureRange(hCamera):
    fMinExposureTime = c_double()
    fMaxExposureTime = c_double()
    err_code = _sdk.CameraGetAeExposureRange(hCamera, byref(fMinExposureTime), byref(fMaxExposureTime) )
    SetLastError(err_code)
    return (fMinExposureTime.value, fMaxExposureTime.value)

def CameraSetAeAnalogGainRange(hCamera, iMinAnalogGain, iMaxAnalogGain):
    err_code = _sdk.CameraSetAeAnalogGainRange(hCamera, iMinAnalogGain, iMaxAnalogGain)
    SetLastError(err_code)
    return err_code

def CameraGetAeAnalogGainRange(hCamera):
    iMinAnalogGain = c_int()
    iMaxAnalogGain = c_int()
    err_code = _sdk.CameraGetAeAnalogGainRange(hCamera, byref(iMinAnalogGain), byref(iMaxAnalogGain) )
    SetLastError(err_code)
    return (iMinAnalogGain.value, iMaxAnalogGain.value)

def CameraSetAeThreshold(hCamera, iThreshold):
    err_code = _sdk.CameraSetAeThreshold(hCamera, iThreshold)
    SetLastError(err_code)
    return err_code

def CameraGetAeThreshold(hCamera):
    iThreshold = c_int()
    err_code = _sdk.CameraGetAeThreshold(hCamera, byref(iThreshold))
    SetLastError(err_code)
    return iThreshold.value

def CameraSetExposureTime(hCamera, fExposureTime):
    err_code = _sdk.CameraSetExposureTime(hCamera, c_double(fExposureTime) )
    SetLastError(err_code)
    return err_code

def CameraGetExposureLineTime(hCamera):
    pfLineTime = c_double()
    err_code = _sdk.CameraGetExposureLineTime(hCamera, byref(pfLineTime))
    SetLastError(err_code)
    return pfLineTime.value

def CameraGetExposureTime(hCamera):
    pfExposureTime = c_double()
    err_code = _sdk.CameraGetExposureTime(hCamera, byref(pfExposureTime))
    SetLastError(err_code)
    return pfExposureTime.value

def CameraGetExposureTimeRange(hCamera):
    pfMin = c_double()
    pfMax = c_double()
    pfStep = c_double()
    err_code = _sdk.CameraGetExposureTimeRange(hCamera, byref(pfMin), byref(pfMax), byref(pfStep))
    SetLastError(err_code)
    return (pfMin.value, pfMax.value, pfStep.value)

def CameraSetAnalogGain(hCamera, iAnalogGain):
    err_code = _sdk.CameraSetAnalogGain(hCamera, iAnalogGain)
    SetLastError(err_code)
    return err_code

def CameraGetAnalogGain(hCamera):
    piAnalogGain = c_int()
    err_code = _sdk.CameraGetAnalogGain(hCamera, byref(piAnalogGain))
    SetLastError(err_code)
    return piAnalogGain.value

def CameraSetAnalogGainX(hCamera, fGain):
    err_code = _sdk.CameraSetAnalogGainX(hCamera, c_float(fGain) )
    SetLastError(err_code)
    return err_code

def CameraGetAnalogGainX(hCamera):
    fGain = c_float()
    err_code = _sdk.CameraGetAnalogGainX(hCamera, byref(fGain))
    SetLastError(err_code)
    return fGain.value

def CameraGetAnalogGainXRange(hCamera):
    pfMin = c_float()
    pfMax = c_float()
    pfStep = c_float()
    err_code = _sdk.CameraGetAnalogGainXRange(hCamera, byref(pfMin), byref(pfMax), byref(pfStep))
    SetLastError(err_code)
    return (pfMin.value, pfMax.value, pfStep.value)

def CameraSetGain(hCamera, iRGain, iGGain, iBGain):
    err_code = _sdk.CameraSetGain(hCamera, iRGain, iGGain, iBGain)
    SetLastError(err_code)
    return err_code

def CameraGetGain(hCamera):
    piRGain = c_int()
    piGGain = c_int()
    piBGain = c_int()
    err_code = _sdk.CameraGetGain(hCamera, byref(piRGain), byref(piGGain), byref(piBGain))
    SetLastError(err_code)
    return (piRGain.value, piGGain.value, piBGain.value)

def CameraSetGamma(hCamera, iGamma):
    err_code = _sdk.CameraSetGamma(hCamera, iGamma)
    SetLastError(err_code)
    return err_code

def CameraGetGamma(hCamera):
    piGamma = c_int()
    err_code = _sdk.CameraGetGamma(hCamera, byref(piGamma))
    SetLastError(err_code)
    return piGamma.value

def CameraSetContrast(hCamera, iContrast):
    err_code = _sdk.CameraSetContrast(hCamera, iContrast)
    SetLastError(err_code)
    return err_code

def CameraGetContrast(hCamera):
    piContrast = c_int()
    err_code = _sdk.CameraGetContrast(hCamera, byref(piContrast))
    SetLastError(err_code)
    return piContrast.value

def CameraSetSaturation(hCamera, iSaturation):
    err_code = _sdk.CameraSetSaturation(hCamera, iSaturation)
    SetLastError(err_code)
    return err_code

def CameraGetSaturation(hCamera):
    piSaturation = c_int()
    err_code = _sdk.CameraGetSaturation(hCamera, byref(piSaturation))
    SetLastError(err_code)
    return piSaturation.value

def CameraSetMonochrome(hCamera, bEnable):
    err_code = _sdk.CameraSetMonochrome(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetMonochrome(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetMonochrome(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraSetInverse(hCamera, bEnable):
    err_code = _sdk.CameraSetInverse(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetInverse(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetInverse(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraSetAntiFlick(hCamera, bEnable):
    err_code = _sdk.CameraSetAntiFlick(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetAntiFlick(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetAntiFlick(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraGetLightFrequency(hCamera):
    piFrequencySel = c_int()
    err_code = _sdk.CameraGetLightFrequency(hCamera, byref(piFrequencySel))
    SetLastError(err_code)
    return piFrequencySel.value

def CameraSetLightFrequency(hCamera, iFrequencySel):
    err_code = _sdk.CameraSetLightFrequency(hCamera, iFrequencySel)
    SetLastError(err_code)
    return err_code

def CameraSetFrameSpeed(hCamera, iFrameSpeed):
    err_code = _sdk.CameraSetFrameSpeed(hCamera, iFrameSpeed)
    SetLastError(err_code)
    return err_code

def CameraGetFrameSpeed(hCamera):
    piFrameSpeed = c_int()
    err_code = _sdk.CameraGetFrameSpeed(hCamera, byref(piFrameSpeed))
    SetLastError(err_code)
    return piFrameSpeed.value

def CameraSetParameterMode(hCamera, iMode):
    err_code = _sdk.CameraSetParameterMode(hCamera, iMode)
    SetLastError(err_code)
    return err_code

def CameraGetParameterMode(hCamera):
    piTarget = c_int()
    err_code = _sdk.CameraGetParameterMode(hCamera, byref(piTarget))
    SetLastError(err_code)
    return piTarget.value

def CameraSetParameterMask(hCamera, uMask):
    err_code = _sdk.CameraSetParameterMask(hCamera, uMask)
    SetLastError(err_code)
    return err_code

def CameraSaveParameter(hCamera, iTeam):
    err_code = _sdk.CameraSaveParameter(hCamera, iTeam)
    SetLastError(err_code)
    return err_code

def CameraSaveParameterToFile(hCamera, sFileName):
    err_code = _sdk.CameraSaveParameterToFile(hCamera, _str_to_string_buffer(sFileName))
    SetLastError(err_code)
    return err_code

def CameraReadParameterFromFile(hCamera, sFileName):
    err_code = _sdk.CameraReadParameterFromFile(hCamera, _str_to_string_buffer(sFileName))
    SetLastError(err_code)
    return err_code

def CameraLoadParameter(hCamera, iTeam):
    err_code = _sdk.CameraLoadParameter(hCamera, iTeam)
    SetLastError(err_code)
    return err_code

def CameraGetCurrentParameterGroup(hCamera):
    piTeam = c_int()
    err_code = _sdk.CameraGetCurrentParameterGroup(hCamera, byref(piTeam))
    SetLastError(err_code)
    return piTeam.value

def CameraSetTransPackLen(hCamera, iPackSel):
    err_code = _sdk.CameraSetTransPackLen(hCamera, iPackSel)
    SetLastError(err_code)
    return err_code

def CameraGetTransPackLen(hCamera):
    piPackSel = c_int()
    err_code = _sdk.CameraGetTransPackLen(hCamera, byref(piPackSel))
    SetLastError(err_code)
    return piPackSel.value

def CameraIsAeWinVisible(hCamera):
    pbIsVisible = c_int()
    err_code = _sdk.CameraIsAeWinVisible(hCamera, byref(pbIsVisible))
    SetLastError(err_code)
    return pbIsVisible.value

def CameraSetAeWinVisible(hCamera, bIsVisible):
    err_code = _sdk.CameraSetAeWinVisible(hCamera, bIsVisible)
    SetLastError(err_code)
    return err_code

def CameraGetAeWindow(hCamera):
    piHOff = c_int()
    piVOff = c_int()
    piWidth = c_int()
    piHeight = c_int()
    err_code = _sdk.CameraGetAeWindow(hCamera, byref(piHOff), byref(piVOff), byref(piWidth), byref(piHeight))
    SetLastError(err_code)
    return (piHOff.value, piVOff.value, piWidth.value, piHeight.value)

def CameraSetAeWindow(hCamera, iHOff, iVOff, iWidth, iHeight):
    err_code = _sdk.CameraSetAeWindow(hCamera, iHOff, iVOff, iWidth, iHeight)
    SetLastError(err_code)
    return err_code

def CameraSetMirror(hCamera, iDir, bEnable):
    err_code = _sdk.CameraSetMirror(hCamera, iDir, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetMirror(hCamera, iDir):
    pbEnable = c_int()
    err_code = _sdk.CameraGetMirror(hCamera, iDir, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraSetRotate(hCamera, iRot):
    err_code = _sdk.CameraSetRotate(hCamera, iRot)
    SetLastError(err_code)
    return err_code

def CameraGetRotate(hCamera):
    iRot = c_int()
    err_code = _sdk.CameraGetRotate(hCamera, byref(iRot))
    SetLastError(err_code)
    return iRot.value

def CameraGetWbWindow(hCamera):
    PiHOff = c_int()
    PiVOff = c_int()
    PiWidth = c_int()
    PiHeight = c_int()
    err_code = _sdk.CameraGetWbWindow(hCamera, byref(PiHOff), byref(PiVOff), byref(PiWidth), byref(PiHeight))
    SetLastError(err_code)
    return (PiHOff.value, PiVOff.value, PiWidth.value, PiHeight.value)

def CameraSetWbWindow(hCamera, iHOff, iVOff, iWidth, iHeight):
    err_code = _sdk.CameraSetWbWindow(hCamera, iHOff, iVOff, iWidth, iHeight)
    SetLastError(err_code)
    return err_code

def CameraIsWbWinVisible(hCamera):
    pbShow = c_int()
    err_code = _sdk.CameraIsWbWinVisible(hCamera, byref(pbShow))
    SetLastError(err_code)
    return pbShow.value

def CameraSetWbWinVisible(hCamera, bShow):
    err_code = _sdk.CameraSetWbWinVisible(hCamera, bShow)
    SetLastError(err_code)
    return err_code

def CameraImageOverlay(hCamera, pRgbBuffer, pFrInfo):
    err_code = _sdk.CameraImageOverlay(hCamera, c_void_p(pRgbBuffer), byref(pFrInfo))
    SetLastError(err_code)
    return err_code

def CameraSetCrossLine(hCamera, iLine, x, y, uColor, bVisible):
    err_code = _sdk.CameraSetCrossLine(hCamera, iLine, x, y, uColor, bVisible)
    SetLastError(err_code)
    return err_code

def CameraGetCrossLine(hCamera, iLine):
    px = c_int()
    py = c_int()
    pcolor = c_uint()
    pbVisible = c_int()
    err_code = _sdk.CameraGetCrossLine(hCamera, iLine, byref(px), byref(py), byref(pcolor), byref(pbVisible))
    SetLastError(err_code)
    return (px.value, py.value, pcolor.value, pbVisible.value)

def CameraGetCapability(hCamera):
    pCameraInfo = tSdkCameraCapbility()
    err_code = _sdk.CameraGetCapability(hCamera, byref(pCameraInfo))
    SetLastError(err_code)
    return pCameraInfo

def CameraWriteSN(hCamera, pbySN, iLevel):
    err_code = _sdk.CameraWriteSN(hCamera, _str_to_string_buffer(pbySN), iLevel)
    SetLastError(err_code)
    return err_code

def CameraReadSN(hCamera, iLevel):
    pbySN = create_string_buffer(64)
    err_code = _sdk.CameraReadSN(hCamera, pbySN, iLevel)
    SetLastError(err_code)
    return _string_buffer_to_str(pbySN)

def CameraSetTriggerDelayTime(hCamera, uDelayTimeUs):
    err_code = _sdk.CameraSetTriggerDelayTime(hCamera, uDelayTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetTriggerDelayTime(hCamera):
    puDelayTimeUs = c_uint()
    err_code = _sdk.CameraGetTriggerDelayTime(hCamera, byref(puDelayTimeUs))
    SetLastError(err_code)
    return puDelayTimeUs.value

def CameraSetTriggerCount(hCamera, iCount):
    err_code = _sdk.CameraSetTriggerCount(hCamera, iCount)
    SetLastError(err_code)
    return err_code

def CameraGetTriggerCount(hCamera):
    piCount = c_int()
    err_code = _sdk.CameraGetTriggerCount(hCamera, byref(piCount))
    SetLastError(err_code)
    return piCount.value

def CameraSoftTrigger(hCamera):
    err_code = _sdk.CameraSoftTrigger(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetTriggerMode(hCamera, iModeSel):
    err_code = _sdk.CameraSetTriggerMode(hCamera, iModeSel)
    SetLastError(err_code)
    return err_code

def CameraGetTriggerMode(hCamera):
    piModeSel = c_int()
    err_code = _sdk.CameraGetTriggerMode(hCamera, byref(piModeSel))
    SetLastError(err_code)
    return piModeSel.value

def CameraSetStrobeMode(hCamera, iMode):
    err_code = _sdk.CameraSetStrobeMode(hCamera, iMode)
    SetLastError(err_code)
    return err_code

def CameraGetStrobeMode(hCamera):
    piMode = c_int()
    err_code = _sdk.CameraGetStrobeMode(hCamera, byref(piMode))
    SetLastError(err_code)
    return piMode.value

def CameraSetStrobeDelayTime(hCamera, uDelayTimeUs):
    err_code = _sdk.CameraSetStrobeDelayTime(hCamera, uDelayTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetStrobeDelayTime(hCamera):
    upDelayTimeUs = c_uint()
    err_code = _sdk.CameraGetStrobeDelayTime(hCamera, byref(upDelayTimeUs))
    SetLastError(err_code)
    return upDelayTimeUs.value

def CameraSetStrobePulseWidth(hCamera, uTimeUs):
    err_code = _sdk.CameraSetStrobePulseWidth(hCamera, uTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetStrobePulseWidth(hCamera):
    upTimeUs = c_uint()
    err_code = _sdk.CameraGetStrobePulseWidth(hCamera, byref(upTimeUs))
    SetLastError(err_code)
    return upTimeUs.value

def CameraSetStrobePolarity(hCamera, uPolarity):
    err_code = _sdk.CameraSetStrobePolarity(hCamera, uPolarity)
    SetLastError(err_code)
    return err_code

def CameraGetStrobePolarity(hCamera):
    upPolarity = c_uint()
    err_code = _sdk.CameraGetStrobePolarity(hCamera, byref(upPolarity))
    SetLastError(err_code)
    return upPolarity.value

def CameraSetExtTrigSignalType(hCamera, iType):
    err_code = _sdk.CameraSetExtTrigSignalType(hCamera, iType)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigSignalType(hCamera):
    ipType = c_int()
    err_code = _sdk.CameraGetExtTrigSignalType(hCamera, byref(ipType))
    SetLastError(err_code)
    return ipType.value

def CameraSetExtTrigShutterType(hCamera, iType):
    err_code = _sdk.CameraSetExtTrigShutterType(hCamera, iType)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigShutterType(hCamera):
    ipType = c_int()
    err_code = _sdk.CameraGetExtTrigShutterType(hCamera, byref(ipType))
    SetLastError(err_code)
    return ipType.value

def CameraSetExtTrigDelayTime(hCamera, uDelayTimeUs):
    err_code = _sdk.CameraSetExtTrigDelayTime(hCamera, uDelayTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigDelayTime(hCamera):
    upDelayTimeUs = c_uint()
    err_code = _sdk.CameraGetExtTrigDelayTime(hCamera, byref(upDelayTimeUs))
    SetLastError(err_code)
    return upDelayTimeUs.value

def CameraSetExtTrigJitterTime(hCamera, uTimeUs):
    err_code = _sdk.CameraSetExtTrigJitterTime(hCamera, uTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigJitterTime(hCamera):
    upTimeUs = c_uint()
    err_code = _sdk.CameraGetExtTrigJitterTime(hCamera, byref(upTimeUs))
    SetLastError(err_code)
    return upTimeUs.value

def CameraSetExtTrigIntervalTime(hCamera, uTimeUs):
    err_code = _sdk.CameraSetExtTrigIntervalTime(hCamera, uTimeUs)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigIntervalTime(hCamera):
    upTimeUs = c_uint()
    err_code = _sdk.CameraGetExtTrigIntervalTime(hCamera, byref(upTimeUs))
    SetLastError(err_code)
    return upTimeUs.value

def CameraGetExtTrigCapability(hCamera):
    puCapabilityMask = c_uint()
    err_code = _sdk.CameraGetExtTrigCapability(hCamera, byref(puCapabilityMask))
    SetLastError(err_code)
    return puCapabilityMask.value

def CameraPauseLevelTrigger(hCamera):
    err_code = _sdk.CameraPauseLevelTrigger(hCamera)
    SetLastError(err_code)
    return err_code

def CameraGetResolutionForSnap(hCamera):
    pImageResolution = tSdkImageResolution()
    err_code = _sdk.CameraGetResolutionForSnap(hCamera, byref(pImageResolution))
    SetLastError(err_code)
    return pImageResolution

def CameraSetResolutionForSnap(hCamera, pImageResolution):
    err_code = _sdk.CameraSetResolutionForSnap(hCamera, byref(pImageResolution))
    SetLastError(err_code)
    return err_code

def CameraCustomizeResolution(hCamera):
    pImageCustom = tSdkImageResolution()
    err_code = _sdk.CameraCustomizeResolution(hCamera, byref(pImageCustom))
    SetLastError(err_code)
    return pImageCustom

def CameraCustomizeReferWin(hCamera, iWinType, hParent):
    piHOff = c_int()
    piVOff = c_int()
    piWidth = c_int()
    piHeight = c_int()
    err_code = _sdk.CameraCustomizeReferWin(hCamera, iWinType, hParent, byref(piHOff), byref(piVOff), byref(piWidth), byref(piHeight))
    SetLastError(err_code)
    return (piHOff.value, piVOff.value, piWidth.value, piHeight.value)

def CameraShowSettingPage(hCamera, bShow):
    err_code = _sdk.CameraShowSettingPage(hCamera, bShow)
    SetLastError(err_code)
    return err_code

def CameraCreateSettingPage(hCamera, hParent, pWinText, pCallbackFunc = None, pCallbackCtx = 0, uReserved = 0):
    err_code = _sdk.CameraCreateSettingPage(hCamera, hParent, _str_to_string_buffer(pWinText), pCallbackFunc, c_void_p(pCallbackCtx), uReserved)
    SetLastError(err_code)
    return err_code

def CameraCreateSettingPageEx(hCamera):
    err_code = _sdk.CameraCreateSettingPageEx(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetActiveSettingSubPage(hCamera, index):
    err_code = _sdk.CameraSetActiveSettingSubPage(hCamera, index)
    SetLastError(err_code)
    return err_code

def CameraSetSettingPageParent(hCamera, hParentWnd, Flags):
    err_code = _sdk.CameraSetSettingPageParent(hCamera, hParentWnd, Flags)
    SetLastError(err_code)
    return err_code

def CameraGetSettingPageHWnd(hCamera):
    hWnd = c_void_p()
    err_code = _sdk.CameraGetSettingPageHWnd(hCamera, byref(hWnd))
    SetLastError(err_code)
    return hWnd.value

def CameraSpecialControl(hCamera, dwCtrlCode, dwParam, lpData):
    err_code = _sdk.CameraSpecialControl(hCamera, dwCtrlCode, dwParam, c_void_p(lpData) )
    SetLastError(err_code)
    return err_code

def CameraGetFrameStatistic(hCamera):
    psFrameStatistic = tSdkFrameStatistic()
    err_code = _sdk.CameraGetFrameStatistic(hCamera, byref(psFrameStatistic))
    SetLastError(err_code)
    return psFrameStatistic

def CameraSetNoiseFilter(hCamera, bEnable):
    err_code = _sdk.CameraSetNoiseFilter(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetNoiseFilterState(hCamera):
    pEnable = c_int()
    err_code = _sdk.CameraGetNoiseFilterState(hCamera, byref(pEnable))
    SetLastError(err_code)
    return pEnable.value

def CameraRstTimeStamp(hCamera):
    err_code = _sdk.CameraRstTimeStamp(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSaveUserData(hCamera, uStartAddr, pbData):
    err_code = _sdk.CameraSaveUserData(hCamera, uStartAddr, pbData, len(pbData))
    SetLastError(err_code)
    return err_code

def CameraLoadUserData(hCamera, uStartAddr, ilen):
    pbData = create_string_buffer(ilen)
    err_code = _sdk.CameraLoadUserData(hCamera, uStartAddr, pbData, ilen)
    SetLastError(err_code)
    return pbData[:]

def CameraGetFriendlyName(hCamera):
    pName = create_string_buffer(64)
    err_code = _sdk.CameraGetFriendlyName(hCamera, pName)
    SetLastError(err_code)
    return _string_buffer_to_str(pName)

def CameraSetFriendlyName(hCamera, pName):
    pNameBuf = _str_to_string_buffer(pName)
    resize(pNameBuf, 64)
    err_code = _sdk.CameraSetFriendlyName(hCamera, pNameBuf)
    SetLastError(err_code)
    return err_code

def CameraSdkGetVersionString():
    pVersionString = create_string_buffer(64)
    err_code = _sdk.CameraSdkGetVersionString(pVersionString)
    SetLastError(err_code)
    return _string_buffer_to_str(pVersionString)

def CameraCheckFwUpdate(hCamera):
    pNeedUpdate = c_int()
    err_code = _sdk.CameraCheckFwUpdate(hCamera, byref(pNeedUpdate))
    SetLastError(err_code)
    return pNeedUpdate.value

def CameraGetFirmwareVersion(hCamera):
    pVersion = create_string_buffer(64)
    err_code = _sdk.CameraGetFirmwareVersion(hCamera, pVersion)
    SetLastError(err_code)
    return _string_buffer_to_str(pVersion)

def CameraGetEnumInfo(hCamera):
    pCameraInfo = tSdkCameraDevInfo()
    err_code = _sdk.CameraGetEnumInfo(hCamera, byref(pCameraInfo))
    SetLastError(err_code)
    return pCameraInfo

def CameraGetInerfaceVersion(hCamera):
    pVersion = create_string_buffer(64)
    err_code = _sdk.CameraGetInerfaceVersion(hCamera, pVersion)
    SetLastError(err_code)
    return _string_buffer_to_str(pVersion)

def CameraSetIOState(hCamera, iOutputIOIndex, uState):
    err_code = _sdk.CameraSetIOState(hCamera, iOutputIOIndex, uState)
    SetLastError(err_code)
    return err_code

def CameraSetIOStateEx(hCamera, iOutputIOIndex, uState):
    err_code = _sdk.CameraSetIOStateEx(hCamera, iOutputIOIndex, uState)
    SetLastError(err_code)
    return err_code

def CameraGetOutPutIOState(hCamera, iOutputIOIndex):
    puState = c_int()
    err_code = _sdk.CameraGetOutPutIOState(hCamera, iOutputIOIndex, byref(puState))
    SetLastError(err_code)
    return puState.value

def CameraGetOutPutIOStateEx(hCamera, iOutputIOIndex):
    puState = c_int()
    err_code = _sdk.CameraGetOutPutIOStateEx(hCamera, iOutputIOIndex, byref(puState))
    SetLastError(err_code)
    return puState.value

def CameraGetIOState(hCamera, iInputIOIndex):
    puState = c_int()
    err_code = _sdk.CameraGetIOState(hCamera, iInputIOIndex, byref(puState))
    SetLastError(err_code)
    return puState.value

def CameraGetIOStateEx(hCamera, iInputIOIndex):
    puState = c_int()
    err_code = _sdk.CameraGetIOStateEx(hCamera, iInputIOIndex, byref(puState))
    SetLastError(err_code)
    return puState.value

def CameraSetInPutIOMode(hCamera, iInputIOIndex, iMode):
    err_code = _sdk.CameraSetInPutIOMode(hCamera, iInputIOIndex, iMode)
    SetLastError(err_code)
    return err_code

def CameraSetOutPutIOMode(hCamera, iOutputIOIndex, iMode):
    err_code = _sdk.CameraSetOutPutIOMode(hCamera, iOutputIOIndex, iMode)
    SetLastError(err_code)
    return err_code

def CameraSetOutPutPWM(hCamera, iOutputIOIndex, iCycle, uDuty):
    err_code = _sdk.CameraSetOutPutPWM(hCamera, iOutputIOIndex, iCycle, uDuty)
    SetLastError(err_code)
    return err_code

def CameraSetAeAlgorithm(hCamera, iIspProcessor, iAeAlgorithmSel):
    err_code = _sdk.CameraSetAeAlgorithm(hCamera, iIspProcessor, iAeAlgorithmSel)
    SetLastError(err_code)
    return err_code

def CameraGetAeAlgorithm(hCamera, iIspProcessor):
    piAlgorithmSel = c_int()
    err_code = _sdk.CameraGetAeAlgorithm(hCamera, iIspProcessor, byref(piAlgorithmSel))
    SetLastError(err_code)
    return piAlgorithmSel.value

def CameraSetBayerDecAlgorithm(hCamera, iIspProcessor, iAlgorithmSel):
    err_code = _sdk.CameraSetBayerDecAlgorithm(hCamera, iIspProcessor, iAlgorithmSel)
    SetLastError(err_code)
    return err_code

def CameraGetBayerDecAlgorithm(hCamera, iIspProcessor):
    piAlgorithmSel = c_int()
    err_code = _sdk.CameraGetBayerDecAlgorithm(hCamera, iIspProcessor, byref(piAlgorithmSel))
    SetLastError(err_code)
    return piAlgorithmSel.value

def CameraSetIspProcessor(hCamera, iIspProcessor):
    err_code = _sdk.CameraSetIspProcessor(hCamera, iIspProcessor)
    SetLastError(err_code)
    return err_code

def CameraGetIspProcessor(hCamera):
    piIspProcessor = c_int()
    err_code = _sdk.CameraGetIspProcessor(hCamera, byref(piIspProcessor))
    SetLastError(err_code)
    return piIspProcessor.value

def CameraSetBlackLevel(hCamera, iBlackLevel):
    err_code = _sdk.CameraSetBlackLevel(hCamera, iBlackLevel)
    SetLastError(err_code)
    return err_code

def CameraGetBlackLevel(hCamera):
    piBlackLevel = c_int()
    err_code = _sdk.CameraGetBlackLevel(hCamera, byref(piBlackLevel))
    SetLastError(err_code)
    return piBlackLevel.value

def CameraSetWhiteLevel(hCamera, iWhiteLevel):
    err_code = _sdk.CameraSetWhiteLevel(hCamera, iWhiteLevel)
    SetLastError(err_code)
    return err_code

def CameraGetWhiteLevel(hCamera):
    piWhiteLevel = c_int()
    err_code = _sdk.CameraGetWhiteLevel(hCamera, byref(piWhiteLevel))
    SetLastError(err_code)
    return piWhiteLevel.value

def CameraSetIspOutFormat(hCamera, uFormat):
    err_code = _sdk.CameraSetIspOutFormat(hCamera, uFormat)
    SetLastError(err_code)
    return err_code

def CameraGetIspOutFormat(hCamera):
    puFormat = c_int()
    err_code = _sdk.CameraGetIspOutFormat(hCamera, byref(puFormat))
    SetLastError(err_code)
    return puFormat.value

def CameraGetErrorString(iStatusCode):
    _sdk.CameraGetErrorString.restype = c_char_p
    msg = _sdk.CameraGetErrorString(iStatusCode)
    if msg:
        return _string_buffer_to_str(msg)
    else:
        return ''

def CameraGetImageBufferEx2(hCamera, pImageData, uOutFormat, wTimes):
    piWidth = c_int()
    piHeight = c_int()
    err_code = _sdk.CameraGetImageBufferEx2(hCamera, c_void_p(pImageData), uOutFormat, byref(piWidth), byref(piHeight), wTimes)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (piWidth.value, piHeight.value)

def CameraGetImageBufferEx3(hCamera, pImageData, uOutFormat, wTimes):
    piWidth = c_int()
    piHeight = c_int()
    puTimeStamp = c_int()
    err_code = _sdk.CameraGetImageBufferEx3(hCamera, c_void_p(pImageData), uOutFormat, byref(piWidth), byref(piHeight), byref(puTimeStamp), wTimes)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (piWidth.value, piHeight.value, puTimeStamp.value)

def CameraGetCapabilityEx2(hCamera):
    pMaxWidth = c_int()
    pMaxHeight = c_int()
    pbColorCamera = c_int()
    err_code = _sdk.CameraGetCapabilityEx2(hCamera, byref(pMaxWidth), byref(pMaxHeight), byref(pbColorCamera))
    SetLastError(err_code)
    return (pMaxWidth.value, pMaxHeight.value, pbColorCamera.value)

def CameraReConnect(hCamera):
    err_code = _sdk.CameraReConnect(hCamera)
    SetLastError(err_code)
    return err_code

def CameraConnectTest(hCamera):
    err_code = _sdk.CameraConnectTest(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetLedEnable(hCamera, index, enable):
    err_code = _sdk.CameraSetLedEnable(hCamera, index, enable)
    SetLastError(err_code)
    return err_code

def CameraGetLedEnable(hCamera, index):
    enable = c_int()
    err_code = _sdk.CameraGetLedEnable(hCamera, index, byref(enable))
    SetLastError(err_code)
    return enable.value

def CameraSetLedOnOff(hCamera, index, onoff):
    err_code = _sdk.CameraSetLedOnOff(hCamera, index, onoff)
    SetLastError(err_code)
    return err_code

def CameraGetLedOnOff(hCamera, index):
    onoff = c_int()
    err_code = _sdk.CameraGetLedOnOff(hCamera, index, byref(onoff))
    SetLastError(err_code)
    return onoff.value

def CameraSetLedDuration(hCamera, index, duration):
    err_code = _sdk.CameraSetLedDuration(hCamera, index, duration)
    SetLastError(err_code)
    return err_code

def CameraGetLedDuration(hCamera, index):
    duration = c_uint()
    err_code = _sdk.CameraGetLedDuration(hCamera, index, byref(duration))
    SetLastError(err_code)
    return duration.value

def CameraSetLedBrightness(hCamera, index, uBrightness):
    err_code = _sdk.CameraSetLedBrightness(hCamera, index, uBrightness)
    SetLastError(err_code)
    return err_code

def CameraGetLedBrightness(hCamera, index):
    uBrightness = c_uint()
    err_code = _sdk.CameraGetLedBrightness(hCamera, index, byref(uBrightness))
    SetLastError(err_code)
    return uBrightness.value

def CameraEnableTransferRoi(hCamera, uEnableMask):
    err_code = _sdk.CameraEnableTransferRoi(hCamera, uEnableMask)
    SetLastError(err_code)
    return err_code

def CameraGetTransferRoiEnable(hCamera):
    uEnableMask = c_uint()
    err_code = _sdk.CameraGetTransferRoiEnable(hCamera, byref(uEnableMask))
    SetLastError(err_code)
    return uEnableMask.value

def CameraSetTransferRoi(hCamera, index, X1, Y1, X2, Y2):
    err_code = _sdk.CameraSetTransferRoi(hCamera, index, X1, Y1, X2, Y2)
    SetLastError(err_code)
    return err_code

def CameraGetTransferRoi(hCamera, index):
    pX1 = c_uint()
    pY1 = c_uint()
    pX2 = c_uint()
    pY2 = c_uint()
    err_code = _sdk.CameraGetTransferRoi(hCamera, index, byref(pX1), byref(pY1), byref(pX2), byref(pY2))
    SetLastError(err_code)
    return (pX1.value, pY1.value, pX2.value, pY2.value)

def CameraAlignMalloc(size, align = 16):
    _sdk.CameraAlignMalloc.restype = c_void_p
    r = _sdk.CameraAlignMalloc(size, align)
    return r

def CameraAlignFree(membuffer):
    _sdk.CameraAlignFree(c_void_p(membuffer))

def CameraSetAutoConnect(hCamera, bEnable):
    err_code = _sdk.CameraSetAutoConnect(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetAutoConnect(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetAutoConnect(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraGetReConnectCounts(hCamera):
    puCounts = c_int()
    err_code = _sdk.CameraGetReConnectCounts(hCamera, byref(puCounts))
    SetLastError(err_code)
    return puCounts.value

def CameraSetSingleGrabMode(hCamera, bEnable):
    err_code = _sdk.CameraSetSingleGrabMode(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetSingleGrabMode(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetSingleGrabMode(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraRestartGrab(hCamera):
    err_code = _sdk.CameraRestartGrab(hCamera)
    SetLastError(err_code)
    return err_code

def CameraEvaluateImageDefinition(hCamera, iAlgorithSel, pbyIn, pFrInfo):
    DefinitionValue = c_double()
    err_code = _sdk.CameraEvaluateImageDefinition(hCamera, iAlgorithSel, c_void_p(pbyIn), byref(pFrInfo), byref(DefinitionValue))
    SetLastError(err_code)
    return DefinitionValue.value

def CameraDrawText(pRgbBuffer, pFrInfo, pFontFileName, FontWidth, FontHeight, pText, Left, Top, Width, Height, TextColor, uFlags):
    err_code = _sdk.CameraDrawText(c_void_p(pRgbBuffer), byref(pFrInfo), _str_to_string_buffer(pFontFileName), FontWidth, FontHeight, _str_to_string_buffer(pText), Left, Top, Width, Height, TextColor, uFlags)
    SetLastError(err_code)
    return err_code

def CameraGigeEnumerateDevice(ipList, MaxCount = 32):
    if type(ipList) in (list, tuple):
        ipList = map(lambda x: _str_to_string_buffer(x), ipList)
    else:
        ipList = (_str_to_string_buffer(ipList),)
    numIP = len(ipList)
    ppIpList = (c_void_p * numIP)(*map(lambda x: addressof(x), ipList))
    Nums = c_int(MaxCount)
    pCameraList = (tSdkCameraDevInfo * Nums.value)()
    err_code = _sdk.CameraGigeEnumerateDevice(ppIpList, numIP, pCameraList, byref(Nums))
    SetLastError(err_code)
    return pCameraList[0:Nums.value]

def CameraGigeGetIp(pCameraInfo):
    CamIp = create_string_buffer(32)
    CamMask = create_string_buffer(32)
    CamGateWay = create_string_buffer(32)
    EtIp = create_string_buffer(32)
    EtMask = create_string_buffer(32)
    EtGateWay = create_string_buffer(32)
    err_code = _sdk.CameraGigeGetIp(byref(pCameraInfo), CamIp, CamMask, CamGateWay, EtIp, EtMask, EtGateWay)
    SetLastError(err_code)
    return (_string_buffer_to_str(CamIp), _string_buffer_to_str(CamMask), _string_buffer_to_str(CamGateWay),
        _string_buffer_to_str(EtIp), _string_buffer_to_str(EtMask), _string_buffer_to_str(EtGateWay) )

def CameraGigeSetIp(pCameraInfo, Ip, SubMask, GateWay, bPersistent):
    err_code = _sdk.CameraGigeSetIp(byref(pCameraInfo),
        _str_to_string_buffer(Ip), _str_to_string_buffer(SubMask), _str_to_string_buffer(GateWay), bPersistent)
    SetLastError(err_code)
    return err_code

def CameraGigeGetMac(pCameraInfo):
    CamMac = create_string_buffer(32)
    EtMac = create_string_buffer(32)
    err_code = _sdk.CameraGigeGetMac(byref(pCameraInfo), CamMac, EtMac)
    SetLastError(err_code)
    return (_string_buffer_to_str(CamMac), _string_buffer_to_str(EtMac) )

def CameraEnableFastResponse(hCamera):
    err_code = _sdk.CameraEnableFastResponse(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSetCorrectDeadPixel(hCamera, bEnable):
    err_code = _sdk.CameraSetCorrectDeadPixel(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetCorrectDeadPixel(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraGetCorrectDeadPixel(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraFlatFieldingCorrectSetEnable(hCamera, bEnable):
    err_code = _sdk.CameraFlatFieldingCorrectSetEnable(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraFlatFieldingCorrectGetEnable(hCamera):
    pbEnable = c_int()
    err_code = _sdk.CameraFlatFieldingCorrectGetEnable(hCamera, byref(pbEnable))
    SetLastError(err_code)
    return pbEnable.value

def CameraFlatFieldingCorrectSetParameter(hCamera, pDarkFieldingImage, pDarkFieldingFrInfo, pLightFieldingImage, pLightFieldingFrInfo):
    err_code = _sdk.CameraFlatFieldingCorrectSetParameter(hCamera, c_void_p(pDarkFieldingImage), byref(pDarkFieldingFrInfo), c_void_p(pLightFieldingImage), byref(pLightFieldingFrInfo))
    SetLastError(err_code)
    return err_code

def CameraFlatFieldingCorrectGetParameterState(hCamera):
    pbValid = c_int()
    pFilePath = create_string_buffer(1024)
    err_code = _sdk.CameraFlatFieldingCorrectGetParameterState(hCamera, byref(pbValid), pFilePath)
    SetLastError(err_code)
    return (pbValid.value, _string_buffer_to_str(pFilePath) )

def CameraFlatFieldingCorrectSaveParameterToFile(hCamera, pszFileName):
    err_code = _sdk.CameraFlatFieldingCorrectSaveParameterToFile(hCamera, _str_to_string_buffer(pszFileName))
    SetLastError(err_code)
    return err_code

def CameraFlatFieldingCorrectLoadParameterFromFile(hCamera, pszFileName):
    err_code = _sdk.CameraFlatFieldingCorrectLoadParameterFromFile(hCamera, _str_to_string_buffer(pszFileName))
    SetLastError(err_code)
    return err_code

def CameraCommonCall(hCamera, pszCall, uResultBufSize):
    pszResult = create_string_buffer(uResultBufSize) if uResultBufSize > 0 else None
    err_code = _sdk.CameraCommonCall(hCamera, _str_to_string_buffer(pszCall), pszResult, uResultBufSize)
    SetLastError(err_code)
    return _string_buffer_to_str(pszResult) if pszResult else ''

def CameraSetDenoise3DParams(hCamera, bEnable, nCount, Weights):
    assert(nCount >= 2 and nCount <= 8)
    if Weights:
        assert(len(Weights) == nCount)
        WeightsNative = (c_float * nCount)(*Weights)
    else:
        WeightsNative = None
    err_code = _sdk.CameraSetDenoise3DParams(hCamera, bEnable, nCount, WeightsNative)
    SetLastError(err_code)
    return err_code

def CameraGetDenoise3DParams(hCamera):
    bEnable = c_int()
    nCount = c_int()
    bUseWeight = c_int()
    Weights = (c_float * 8)()
    err_code = _sdk.CameraGetDenoise3DParams(hCamera, byref(bEnable), byref(nCount), byref(bUseWeight), Weights)
    SetLastError(err_code)
    bEnable, nCount, bUseWeight = bEnable.value, nCount.value, bUseWeight.value
    if bUseWeight:
        Weights = Weights[:nCount]
    else:
        Weights = None
    return (bEnable, nCount, bUseWeight, Weights)

def CameraManualDenoise3D(InFramesHead, InFramesData, nCount, Weights, OutFrameHead, OutFrameData):
    assert(nCount > 0)
    assert(len(InFramesData) == nCount)
    assert(Weights is None or len(Weights) == nCount)
    InFramesDataNative = (c_void_p * nCount)(*InFramesData)
    WeightsNative = (c_float * nCount)(*Weights) if Weights else None
    err_code = _sdk.CameraManualDenoise3D(byref(InFramesHead), InFramesDataNative, nCount, WeightsNative, byref(OutFrameHead), c_void_p(OutFrameData))
    SetLastError(err_code)
    return err_code

def CameraCustomizeDeadPixels(hCamera, hParent):
    err_code = _sdk.CameraCustomizeDeadPixels(hCamera, hParent)
    SetLastError(err_code)
    return err_code

def CameraReadDeadPixels(hCamera):
    pNumPixel = c_int()
    err_code = _sdk.CameraReadDeadPixels(hCamera, None, None, byref(pNumPixel))
    SetLastError(err_code)
    if pNumPixel.value < 1:
        return None
    UShortArray = c_ushort * pNumPixel.value
    pRows = UShortArray()
    pCols = UShortArray()
    err_code = _sdk.CameraReadDeadPixels(hCamera, pRows, pCols, byref(pNumPixel))
    SetLastError(err_code)
    if err_code == 0:
        pNumPixel = pNumPixel.value
    else:
        pNumPixel = 0
    return (pRows[:pNumPixel], pCols[:pNumPixel])

def CameraAddDeadPixels(hCamera, pRows, pCols, NumPixel):
    UShortArray = c_ushort * NumPixel
    pRowsNative = UShortArray(*pRows)
    pColsNative = UShortArray(*pCols)
    err_code = _sdk.CameraAddDeadPixels(hCamera, pRowsNative, pColsNative, NumPixel)
    SetLastError(err_code)
    return err_code

def CameraRemoveDeadPixels(hCamera, pRows, pCols, NumPixel):
    UShortArray = c_ushort * NumPixel
    pRowsNative = UShortArray(*pRows)
    pColsNative = UShortArray(*pCols)
    err_code = _sdk.CameraRemoveDeadPixels(hCamera, pRowsNative, pColsNative, NumPixel)
    SetLastError(err_code)
    return err_code

def CameraRemoveAllDeadPixels(hCamera):
    err_code = _sdk.CameraRemoveAllDeadPixels(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSaveDeadPixels(hCamera):
    err_code = _sdk.CameraSaveDeadPixels(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSaveDeadPixelsToFile(hCamera, sFileName):
    err_code = _sdk.CameraSaveDeadPixelsToFile(hCamera, _str_to_string_buffer(sFileName))
    SetLastError(err_code)
    return err_code

def CameraLoadDeadPixelsFromFile(hCamera, sFileName):
    err_code = _sdk.CameraLoadDeadPixelsFromFile(hCamera, _str_to_string_buffer(sFileName))
    SetLastError(err_code)
    return err_code

def CameraGetImageBufferPriority(hCamera, wTimes, Priority):
    pFrameInfo = tSdkFrameHead()
    pbyBuffer = c_void_p()
    err_code = _sdk.CameraGetImageBufferPriority(hCamera, byref(pFrameInfo), byref(pbyBuffer), wTimes, Priority)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (pbyBuffer.value, pFrameInfo)

def CameraGetImageBufferPriorityEx(hCamera, wTimes, Priority):
    _sdk.CameraGetImageBufferPriorityEx.restype = c_void_p
    piWidth = c_int()
    piHeight = c_int()
    pFrameBuffer = _sdk.CameraGetImageBufferPriorityEx(hCamera, byref(piWidth), byref(piHeight), wTimes, Priority)
    err_code = CAMERA_STATUS_SUCCESS if pFrameBuffer else CAMERA_STATUS_TIME_OUT
    SetLastError(err_code)
    if pFrameBuffer:
        return (pFrameBuffer, piWidth.value, piHeight.value)
    else:
        raise CameraException(err_code)

def CameraGetImageBufferPriorityEx2(hCamera, pImageData, uOutFormat, wTimes, Priority):
    piWidth = c_int()
    piHeight = c_int()
    err_code = _sdk.CameraGetImageBufferPriorityEx2(hCamera, c_void_p(pImageData), uOutFormat, byref(piWidth), byref(piHeight), wTimes, Priority)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (piWidth.value, piHeight.value)

def CameraGetImageBufferPriorityEx3(hCamera, pImageData, uOutFormat, wTimes, Priority):
    piWidth = c_int()
    piHeight = c_int()
    puTimeStamp = c_uint()
    err_code = _sdk.CameraGetImageBufferPriorityEx3(hCamera, c_void_p(pImageData), uOutFormat, byref(piWidth), byref(piHeight), byref(puTimeStamp), wTimes, Priority)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return (piWidth.value, piHeight.value, puTimeStamp.value)

def CameraClearBuffer(hCamera):
    err_code = _sdk.CameraClearBuffer(hCamera)
    SetLastError(err_code)
    return err_code

def CameraSoftTriggerEx(hCamera, uFlags):
    err_code = _sdk.CameraSoftTriggerEx(hCamera, uFlags)
    SetLastError(err_code)
    return err_code

def CameraSetHDR(hCamera, value):
    err_code = _sdk.CameraSetHDR(hCamera, value)
    SetLastError(err_code)
    return err_code

def CameraGetHDR(hCamera):
    value = c_int()
    err_code = _sdk.CameraGetHDR(hCamera, byref(value))
    SetLastError(err_code)
    return value.value

def CameraGetFrameID(hCamera):
    FrameID = c_uint()
    err_code = _sdk.CameraGetFrameID(hCamera, byref(FrameID))
    SetLastError(err_code)
    return FrameID.value

def CameraGetFrameTimeStamp(hCamera):
    TimeStamp = c_uint64()
    TimeStampL = c_uint32.from_buffer(TimeStamp)
    TimeStampH = c_uint32.from_buffer(TimeStamp, 4)
    err_code = _sdk.CameraGetFrameTimeStamp(hCamera, byref(TimeStampL), byref(TimeStampH))
    SetLastError(err_code)
    return TimeStamp.value

def CameraSetHDRGainMode(hCamera, value):
    err_code = _sdk.CameraSetHDRGainMode(hCamera, value)
    SetLastError(err_code)
    return err_code

def CameraGetHDRGainMode(hCamera):
    value = c_int()
    err_code = _sdk.CameraGetHDRGainMode(hCamera, byref(value))
    SetLastError(err_code)
    return value.value

def CameraCreateDIBitmap(hDC, pFrameBuffer, pFrameHead):
    outBitmap = c_void_p()
    err_code = _sdk.CameraCreateDIBitmap(hDC, c_void_p(pFrameBuffer), byref(pFrameHead), byref(outBitmap))
    SetLastError(err_code)
    return outBitmap.value

def CameraDrawFrameBuffer(pFrameBuffer, pFrameHead, hWnd, Algorithm, Mode):
    err_code = _sdk.CameraDrawFrameBuffer(c_void_p(pFrameBuffer), byref(pFrameHead), c_void_p(hWnd), Algorithm, Mode)
    SetLastError(err_code)
    return err_code

def CameraFlipFrameBuffer(pFrameBuffer, pFrameHead, Flags):
    err_code = _sdk.CameraFlipFrameBuffer(c_void_p(pFrameBuffer), byref(pFrameHead), Flags)
    SetLastError(err_code)
    return err_code

def CameraConvertFrameBufferFormat(hCamera, pInFrameBuffer, pOutFrameBuffer, outWidth, outHeight, outMediaType, pFrameHead):
    err_code = _sdk.CameraConvertFrameBufferFormat(hCamera, c_void_p(pInFrameBuffer), c_void_p(pOutFrameBuffer), outWidth, outHeight, outMediaType, byref(pFrameHead))
    SetLastError(err_code)
    return err_code

def CameraSetConnectionStatusCallback(hCamera, pCallBack, pContext = 0):
    err_code = _sdk.CameraSetConnectionStatusCallback(hCamera, pCallBack, c_void_p(pContext) )
    SetLastError(err_code)
    return err_code

def CameraSetFrameEventCallback(hCamera, pCallBack, pContext = 0):
    err_code = _sdk.CameraSetFrameEventCallback(hCamera, pCallBack, c_void_p(pContext) )
    SetLastError(err_code)
    return err_code

def CameraSetLightingControllerMode(hCamera, index, mode):
    err_code = _sdk.CameraSetLightingControllerMode(hCamera, index, mode)
    SetLastError(err_code)
    return err_code

def CameraSetLightingControllerState(hCamera, index, state):
    err_code = _sdk.CameraSetLightingControllerState(hCamera, index, state)
    SetLastError(err_code)
    return err_code

def CameraSetFrameResendCount(hCamera, count):
    err_code = _sdk.CameraSetFrameResendCount(hCamera, count)
    SetLastError(err_code)
    return err_code

def CameraSetUndistortParams(hCamera, width, height, cameraMatrix, distCoeffs):
    assert(len(cameraMatrix) == 4)
    assert(len(distCoeffs) == 5)
    cameraMatrixNative = (c_double * len(cameraMatrix))(*cameraMatrix)
    distCoeffsNative = (c_double * len(distCoeffs))(*distCoeffs)
    err_code = _sdk.CameraSetUndistortParams(hCamera, width, height, cameraMatrixNative, distCoeffsNative)
    SetLastError(err_code)
    return err_code

def CameraGetUndistortParams(hCamera):
    width = c_int()
    height = c_int()
    cameraMatrix = (c_double * 4)()
    distCoeffs = (c_double * 5)()
    err_code = _sdk.CameraGetUndistortParams(hCamera, byref(width), byref(height), cameraMatrix, distCoeffs)
    SetLastError(err_code)
    width, height = width.value, height.value
    cameraMatrix = cameraMatrix[:]
    distCoeffs = distCoeffs[:]
    return (width, height, cameraMatrix, distCoeffs)

def CameraSetUndistortEnable(hCamera, bEnable):
    err_code = _sdk.CameraSetUndistortEnable(hCamera, bEnable)
    SetLastError(err_code)
    return err_code

def CameraGetUndistortEnable(hCamera):
    value = c_int()
    err_code = _sdk.CameraGetUndistortEnable(hCamera, byref(value))
    SetLastError(err_code)
    return value.value

def CameraCustomizeUndistort(hCamera, hParent):
    err_code = _sdk.CameraCustomizeUndistort(hCamera, hParent)
    SetLastError(err_code)
    return err_code

def CameraGetEyeCount(hCamera):
    EyeCount = c_int()
    err_code = _sdk.CameraGetEyeCount(hCamera, byref(EyeCount))
    SetLastError(err_code)
    return EyeCount.value

def CameraMultiEyeImageProcess(hCamera, iEyeIndex, pbyIn, pInFrInfo, pbyOut, pOutFrInfo, uOutFormat, uReserved):
    err_code = _sdk.CameraMultiEyeImageProcess(hCamera, iEyeIndex, c_void_p(pbyIn), byref(pInFrInfo), c_void_p(pbyOut), byref(pOutFrInfo), uOutFormat, uReserved)
    SetLastError(err_code)
    return err_code

# CameraGrabber

def CameraGrabber_CreateFromDevicePage():
    Grabber = c_void_p()
    err_code = _sdk.CameraGrabber_CreateFromDevicePage(byref(Grabber))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return Grabber.value

def CameraGrabber_CreateByIndex(Index):
    Grabber = c_void_p()
    err_code = _sdk.CameraGrabber_CreateByIndex(byref(Grabber), Index)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return Grabber.value

def CameraGrabber_CreateByName(Name):
    Grabber = c_void_p()
    err_code = _sdk.CameraGrabber_CreateByName(byref(Grabber), _str_to_string_buffer(Name))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return Grabber.value

def CameraGrabber_Create(pDevInfo):
    Grabber = c_void_p()
    err_code = _sdk.CameraGrabber_Create(byref(Grabber), byref(pDevInfo))
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return Grabber.value

def CameraGrabber_Destroy(Grabber):
    err_code = _sdk.CameraGrabber_Destroy(c_void_p(Grabber))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetHWnd(Grabber, hWnd):
    err_code = _sdk.CameraGrabber_SetHWnd(c_void_p(Grabber), c_void_p(hWnd) )
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetPriority(Grabber, Priority):
    err_code = _sdk.CameraGrabber_SetPriority(c_void_p(Grabber), Priority)
    SetLastError(err_code)
    return err_code

def CameraGrabber_StartLive(Grabber):
    err_code = _sdk.CameraGrabber_StartLive(c_void_p(Grabber))
    SetLastError(err_code)
    return err_code

def CameraGrabber_StopLive(Grabber):
    err_code = _sdk.CameraGrabber_StopLive(c_void_p(Grabber))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SaveImage(Grabber, TimeOut):
    Image = c_void_p()
    err_code = _sdk.CameraGrabber_SaveImage(c_void_p(Grabber), byref(Image), TimeOut)
    SetLastError(err_code)
    if err_code != 0:
        raise CameraException(err_code)
    return Image.value

def CameraGrabber_SaveImageAsync(Grabber):
    err_code = _sdk.CameraGrabber_SaveImageAsync(c_void_p(Grabber))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SaveImageAsyncEx(Grabber, UserData):
    err_code = _sdk.CameraGrabber_SaveImageAsyncEx(c_void_p(Grabber), c_void_p(UserData))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetSaveImageCompleteCallback(Grabber, Callback, Context = 0):
    err_code = _sdk.CameraGrabber_SetSaveImageCompleteCallback(c_void_p(Grabber), Callback, c_void_p(Context))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetFrameListener(Grabber, Listener, Context = 0):
    err_code = _sdk.CameraGrabber_SetFrameListener(c_void_p(Grabber), Listener, c_void_p(Context))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetRawCallback(Grabber, Callback, Context = 0):
    err_code = _sdk.CameraGrabber_SetRawCallback(c_void_p(Grabber), Callback, c_void_p(Context))
    SetLastError(err_code)
    return err_code

def CameraGrabber_SetRGBCallback(Grabber, Callback, Context = 0):
    err_code = _sdk.CameraGrabber_SetRGBCallback(c_void_p(Grabber), Callback, c_void_p(Context))
    SetLastError(err_code)
    return err_code

def CameraGrabber_GetCameraHandle(Grabber):
    hCamera = c_int()
    err_code = _sdk.CameraGrabber_GetCameraHandle(c_void_p(Grabber), byref(hCamera))
    SetLastError(err_code)
    return hCamera.value

def CameraGrabber_GetStat(Grabber):
    stat = tSdkGrabberStat()
    err_code = _sdk.CameraGrabber_GetStat(c_void_p(Grabber), byref(stat))
    SetLastError(err_code)
    return stat

def CameraGrabber_GetCameraDevInfo(Grabber):
    DevInfo = tSdkCameraDevInfo()
    err_code = _sdk.CameraGrabber_GetCameraDevInfo(c_void_p(Grabber), byref(DevInfo))
    SetLastError(err_code)
    return DevInfo

# CameraImage

def CameraImage_Create(pFrameBuffer, pFrameHead, bCopy):
    Image = c_void_p()
    err_code = _sdk.CameraImage_Create(byref(Image), c_void_p(pFrameBuffer), byref(pFrameHead), bCopy)
    SetLastError(err_code)
    return Image.value

def CameraImage_CreateEmpty():
    Image = c_void_p()
    err_code = _sdk.CameraImage_CreateEmpty(byref(Image))
    SetLastError(err_code)
    return Image.value

def CameraImage_Destroy(Image):
    err_code = _sdk.CameraImage_Destroy(c_void_p(Image))
    SetLastError(err_code)
    return err_code

def CameraImage_GetData(Image):
    DataBuffer = c_void_p()
    HeadPtr = c_void_p()
    err_code = _sdk.CameraImage_GetData(c_void_p(Image), byref(DataBuffer), byref(HeadPtr))
    SetLastError(err_code)
    if err_code == 0:
        return (DataBuffer.value, tSdkFrameHead.from_address(HeadPtr.value) )
    else:
        return (0, None)

def CameraImage_GetUserData(Image):
    UserData = c_void_p()
    err_code = _sdk.CameraImage_GetUserData(c_void_p(Image), byref(UserData))
    SetLastError(err_code)
    return UserData.value

def CameraImage_SetUserData(Image, UserData):
    err_code = _sdk.CameraImage_SetUserData(c_void_p(Image), c_void_p(UserData))
    SetLastError(err_code)
    return err_code

def CameraImage_IsEmpty(Image):
    IsEmpty = c_int()
    err_code = _sdk.CameraImage_IsEmpty(c_void_p(Image), byref(IsEmpty))
    SetLastError(err_code)
    return IsEmpty.value

def CameraImage_Draw(Image, hWnd, Algorithm):
    err_code = _sdk.CameraImage_Draw(c_void_p(Image), c_void_p(hWnd), Algorithm)
    SetLastError(err_code)
    return err_code

def CameraImage_DrawFit(Image, hWnd, Algorithm):
    err_code = _sdk.CameraImage_DrawFit(c_void_p(Image), c_void_p(hWnd), Algorithm)
    SetLastError(err_code)
    return err_code

def CameraImage_DrawToDC(Image, hDC, Algorithm, xDst, yDst, cxDst, cyDst):
    err_code = _sdk.CameraImage_DrawToDC(c_void_p(Image), c_void_p(hDC), Algorithm, xDst, yDst, cxDst, cyDst)
    SetLastError(err_code)
    return err_code

def CameraImage_DrawToDCFit(Image, hDC, Algorithm, xDst, yDst, cxDst, cyDst):
    err_code = _sdk.CameraImage_DrawToDCFit(c_void_p(Image), c_void_p(hDC), Algorithm, xDst, yDst, cxDst, cyDst)
    SetLastError(err_code)
    return err_code

def CameraImage_BitBlt(Image, hWnd, xDst, yDst, cxDst, cyDst, xSrc, ySrc):
    err_code = _sdk.CameraImage_BitBlt(c_void_p(Image), c_void_p(hWnd), xDst, yDst, cxDst, cyDst, xSrc, ySrc)
    SetLastError(err_code)
    return err_code

def CameraImage_BitBltToDC(Image, hDC, xDst, yDst, cxDst, cyDst, xSrc, ySrc):
    err_code = _sdk.CameraImage_BitBltToDC(c_void_p(Image), c_void_p(hDC), xDst, yDst, cxDst, cyDst, xSrc, ySrc)
    SetLastError(err_code)
    return err_code

def CameraImage_SaveAsBmp(Image, FileName):
    err_code = _sdk.CameraImage_SaveAsBmp(c_void_p(Image), _str_to_string_buffer(FileName))
    SetLastError(err_code)
    return err_code

def CameraImage_SaveAsJpeg(Image, FileName, Quality):
    err_code = _sdk.CameraImage_SaveAsJpeg(c_void_p(Image), _str_to_string_buffer(FileName), Quality)
    SetLastError(err_code)
    return err_code

def CameraImage_SaveAsPng(Image, FileName):
    err_code = _sdk.CameraImage_SaveAsPng(c_void_p(Image), _str_to_string_buffer(FileName))
    SetLastError(err_code)
    return err_code

def CameraImage_SaveAsRaw(Image, FileName, Format):
    err_code = _sdk.CameraImage_SaveAsRaw(c_void_p(Image), _str_to_string_buffer(FileName), Format)
    SetLastError(err_code)
    return err_code

def CameraImage_IPicture(Image):
    NewPic = c_void_p()
    err_code = _sdk.CameraImage_IPicture(c_void_p(Image), byref(NewPic))
    SetLastError(err_code)
    return NewPic.value

def CameraGetInPutIOModeCapbility(hCamera, i):
    piCapbility = c_uint()
    err_code = _sdk.CameraGetInPutIOModeCapbility(hCamera, i, byref(piCapbility))
    SetLastError(err_code)
    return piCapbility.value

def CameraGetRotaryEncDir(hCamera):
    dir = c_int()
    err_code = _sdk.CameraGetRotaryEncDir(hCamera, byref(dir))
    SetLastError(err_code)
    return dir.value

def CameraGetRotaryEncFreq(hCamera):
    mul = c_int()
    div = c_int()
    err_code = _sdk.CameraGetRotaryEncFreq(hCamera, byref(mul), byref(div))
    SetLastError(err_code)
    return (mul.value, div.value)

def CameraSetRotaryEncTrigger(hCamera, action):
    err_code = _sdk.CameraSetRotaryEncTrigger(hCamera, action)
    SetLastError(err_code)
    return err_code

def CameraGetRotaryEncTrigger(hCamera):
    action = c_int()
    err_code = _sdk.CameraGetRotaryEncTrigger(hCamera, byref(action))
    SetLastError(err_code)
    return action.value

def CameraSetExtTrigBufferedDelayTime(hCamera, uDelayTimeUs):
    err_code = _sdk.CameraSetExtTrigBufferedDelayTime(hCamera, uDelayTimeUs)
    SetLastError(err_code)
    return err_code

def CameraSetRotaryEncDir(hCamera, dir):
    err_code = _sdk.CameraSetRotaryEncDir(hCamera, dir)
    SetLastError(err_code)
    return err_code

def CameraSetRotaryEncFreq(hCamera, mul, div):
    err_code = _sdk.CameraSetRotaryEncFreq(hCamera, mul, div)
    SetLastError(err_code)
    return err_code

def CameraSetFrameRate(hCamera, RateHZ):
    err_code = _sdk.CameraSetFrameRate(hCamera, RateHZ)
    SetLastError(err_code)
    return err_code

def CameraSetSpliceLines(hCamera, numLines):
    err_code = _sdk.CameraSetSpliceLines(hCamera, numLines)
    SetLastError(err_code)
    return err_code

def CameraGetExtTrigBufferedDelayTime(hCamera):
    puDelayTimeUs = c_uint()
    err_code = _sdk.CameraGetExtTrigBufferedDelayTime(hCamera, byref(puDelayTimeUs))
    SetLastError(err_code)
    return puDelayTimeUs.value
