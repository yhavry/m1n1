# SPDX-License-Identifier: MIT
import struct

from ..utils import *
from m1n1.utils import *
from m1n1.setup import *
from m1n1 import asm

from .akf import StandardAKF
from .akf.base import *

CMD_BUFFER_PER_NSID = 2240
NUM_NSID = 8

ASP_CMD_OP         = 0x0
ASP_CMD_LBA_OFF    = 0x4
ASP_CMD_NUM_LBA    = 0x8
ASP_CMD_OUT_BUFFER = 0x30
ASP_CMD_MAX_BUFS   = 512 # ?

code = u.malloc(0x1000)

util = asm.ARMAsm("""
dma_rmb:
    dmb oshld
    ret
dma_wmb:
    dmb oshst
    ret
""", code)

iface.writemem(code, util.data)
p.dc_cvau(code, len(util.data))
p.ic_ivau(code, len(util.data))

# NSID
# 0 = non namespace specific
# 1 = main storage
# 3 = nvram
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

    def ns_setup(self, ns):
        # UNK may be multiplier of ARG2 and ARG3
        arg3 = (ns * 3)
        # "Carry over" from arg3 to arg2, like in manual addition
        arg2 = ((ns * 2) & 0xf) + (arg3 >> 4) 
        arg3 &= 0xf
        self.send(ANS_Admin_Cmd(ARG_2=arg2, ARG_3=arg3, NSID=ns, UNK=0x23, IO=0, CMD=1))
        self.akf.work()
        self.mon.poll()

    def io_cmd(self, ns):
        self.send(ANS_IO_Cmd(ARG_2=0xf, ARG_3=0xf, NSID=ns, IO=1, CMD=1))
        self.akf.work_for(0.5)
        self.mon.poll()

    def asp_read(self, nsid, lba, bfr):
        if not self.base:
            print("IO not initialized yet")
            return
        
        if nsid >= NUM_NSID:
            print("Invalid NSID!")
            return
        
        if ((bfr & 0xffffff00000000fff) != 0):
            print("Buffer not 0x1000 aligned")
            return

        self.mon.poll()

        cmd = self.base + CMD_BUFFER_PER_NSID * nsid
        self.akf.u.proxy.memset32(cmd, 0, CMD_BUFFER_PER_NSID)
        # 3 in bit 7, 4 = read   
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0x80037 | nsid << 8)
        self.akf.u.proxy.write32(cmd + ASP_CMD_LBA_OFF, lba)
        self.akf.u.proxy.write32(cmd + ASP_CMD_NUM_LBA, 1) # num buffers in out_buffer
        self.akf.u.proxy.write32(cmd + ASP_CMD_OUT_BUFFER, bfr >> 12)

        self.akf.u.proxy.call(util.dma_wmb)

        self.io_cmd(nsid)

        self.akf.u.proxy.call(util.dma_rmb)
        self.mon.poll()

    def start(self):
        pass

    def start_io(self):
        # this is used by the IOP so we use proxy function here
        self.base = self.akf.u.proxy.memalign(0x1000, CMD_BUFFER_PER_NSID * NUM_NSID)
        self.akf.u.proxy.memset32(self.base, 0, CMD_BUFFER_PER_NSID * NUM_NSID)   
        self.mon.add(self.base, CMD_BUFFER_PER_NSID)
        self.send(ANS_SetBase(BASE=self.base, UNK=0x118, IO=0, CMD=0))
        self.akf.work()
        self.mon.poll()
        for i in range(0, 8):
            self.ns_setup(i)
        for i in range(0, 8):
            self.akf.u.proxy.write32(self.base + CMD_BUFFER_PER_NSID * i, i << 8)
        self.mon.poll()
        """
        cmd = self.base

        # geometry?
        self.io_cmd(0)
        self.mon.poll()

        # ???
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0x72)
        self.io_cmd(0)
        self.mon.poll()

        # "set to high power mode"
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0x80)
        self.io_cmd(0)
        self.mon.poll()
        """

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
