# SPDX-License-Identifier: MIT
import struct

from ..utils import *
from m1n1.utils import *
from m1n1.setup import *

from .akf import StandardAKF
from .akf.base import *

# NSID
# 0 = non namespace specific
# 1 = main storage
# 2 = nvram
# 3 = illb
# 6 = syscfg

class ANS_Message(Register64):
    EP = 63, 56, Constant(0x20)
    IO = 1
    CMD = 0

class ANS_SetBase(ANS_Message):
    BASE = 51, 20
    UNK = 15, 4, Constant(0x118)
    IO = 1
    CMD = 0

class ANS_Cmd(ANS_Message):
    UNK = 31, 24
    ARG_2 = 19, 16 # (NSID * 2) & 0xf
    ARG_3 = 15, 12 # (NSID * 3) & 0xf
    NSID = 7, 4
    CMD = 0

class ANS_IO_Cmd(ANS_Cmd):
    IO = 1

class ANS_Admin_Cmd(ANS_Cmd):
    IO = 1

class ANSEndpoint(AKFBaseEndpoint):
    BASE_MESSAGE = ANS_Message
    SHORT = "ansep"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mon = RegMonitor(u, ascii=True, bufsize=0x8000000)
        self.base = None

    def ns_setup(self, ns, arg2, arg3):
        # UNK may be multiplier of ARG2 and ARG3
        self.send(ANS_Admin_Cmd(ARG_2=arg2, ARG_3=arg3, NSID=ns, UNK=0x23, IO=0, CMD=1))
        self.akf.work()
        self.mon.poll()

    def io_cmd(self, ns):
        self.send(ANS_IO_Cmd(ARG_2=0xf, ARG_3=0xf, NSID=ns, IO=1, CMD=1))
        self.akf.work()
        self.mon.poll()

    def start(self):
        pass

    def start_io(self):
        # this is used by the IOP so we use proxy function here
        self.base = self.akf.u.proxy.memalign(0x1000, 0x1000)
        self.akf.u.proxy.memset32(self.base, 0, 0x1000)   
        self.mon.add(self.base, 0x1000)
        self.send(ANS_SetBase(BASE=self.base, UNK=0x118, IO=0, CMD=0))
        self.akf.work()
        self.mon.poll()
        self.ns_setup(0, 0, 0)
        self.ns_setup(1, 2, 3)
        self.ns_setup(2, 4, 6)
        self.ns_setup(3, 6, 9)
        self.ns_setup(4, 8, 0xc)
        self.ns_setup(5, 0xa, 0xf)
        self.ns_setup(6, 0xd, 2) # arg2 off by one ????
        self.ns_setup(7, 0xf, 5)

    def stop(self):
        if self.base:
            self.akf.u.proxy.free(self.base)

    def handle_msg(self, msg):
        print(f"received ANS endpoint msg: {msg:#x}")
        return True

class ANSClient(StandardAKF):
    ENDPOINTS = {
        0x20: ANSEndpoint,
    }
