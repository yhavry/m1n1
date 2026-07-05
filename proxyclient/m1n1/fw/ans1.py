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

class ANS_SetBase(ANS_Message):
    BASE = 55, 16
    UNK = 15, 4, Constant(0x118)
    IO = 1
    CMD = 0

class ANS_Cmd(ANS_Message):
    UNK = 31, 24
    ARG_2 = 19, 16 # (NSID * 2) & 0xf
    ARG_3 = 15, 12 # (NSID * 3) & 0xf
    NSID = 7, 4
    IO = 1
    CMD = 0

class ANS_IO_Cmd(ANS_Cmd):
    IO = 1

class ANS_Admin_Cmd(ANS_Cmd):
    IO = 1

class ANS_Reply(ANS_Message):
    EP = 63, 56, Constant(0x20)
    STATUS = 15, 12
    TAG = 11, 4
    TYPE = 3, 0

class ANSEndpoint(AKFBaseEndpoint):
    BASE_MESSAGE = ANS_Message
    SHORT = "ansep"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mon = RegMonitor(u, ascii=True, bufsize=0x8000000)
        self.base = None
        self.in_progress = False
        self.verbose = 1

    def ns_setup(self, ns):
        # UNK may be multiplier of ARG2 and ARG3
        arg3 = (ns * 3)
        # "Carry over" from arg3 to arg2, like in manual addition
        arg2 = ((ns * 2) & 0xf) + (arg3 >> 4) 
        arg3 &= 0xf
        self.send(ANS_Admin_Cmd(ARG_2=arg2, ARG_3=arg3, NSID=ns, UNK=0x23, IO=0, CMD=1))
        self.akf.work()
        self.mon.poll()

    def send_cmd(self, ns, io):
        self.akf.u.proxy.call(util.dma_wmb)
        self.in_progress = True
        self.send(ANS_Cmd(ARG_2=0xf, ARG_3=0xf,  NSID=ns, IO=io, CMD=1))
        while self.in_progress:
            self.akf.work()
        self.akf.u.proxy.call(util.dma_rmb)
        return self.base
    
    def cmdbuf_for_ns(self, ns):
        buf = self.base + CMD_BUFFER_PER_NSID * ns
        self.akf.u.proxy.memset32(buf, 0, CMD_BUFFER_PER_NSID)
        return buf

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

        cmd = self.cmdbuf_for_ns(nsid)
        # 3 in bit 7, 4 = read   
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0x80031 | nsid << 8)
        self.akf.u.proxy.write32(cmd + ASP_CMD_LBA_OFF, lba)
        self.akf.u.proxy.write32(cmd + ASP_CMD_NUM_LBA, 1) # num buffers in out_buffer
        self.akf.u.proxy.write32(cmd + ASP_CMD_OUT_BUFFER, bfr >> 12)

        self.send_cmd(nsid, True)

    def start(self):
        pass

    def identify(self):
        # IDENTIFY
        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8)
        self.send_cmd(0, True)

        lba = self.akf.u.proxy.read32(cmd + 0x30)
        lba_sz = self.akf.u.proxy.read32(cmd + 0x34)

        print(f"[ansep] {lba} LBAs, sector size {lba_sz}, total {lba * lba_sz} bytes")

    def cmd_init(self):
        # These are done by iboot after identification before first disk I/O
        # This updates the command buffer, so maybe another identification
        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8 | 0x72) # 'r'
        self.send_cmd(0, True)

        # These are possibly power management
        # maybe tunables?
        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8 | 0x80)
        self.akf.u.proxy.write32(cmd + 0x38, 0x2a)
        self.akf.u.proxy.write32(cmd + 0x44, 0x400000)
        self.akf.u.proxy.write32(cmd + 0x48, 0x400000)
        self.send_cmd(0, True)

        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8 | 0x80)
        self.akf.u.proxy.write32(cmd + 0x38, 0x13)
        self.akf.u.proxy.write32(cmd + 0x3c, 0x3)
        self.akf.u.proxy.write32(cmd + 0x44, 0x2)
        self.akf.u.proxy.write32(cmd + 0x48, 0x2)
        self.akf.u.proxy.write32(cmd + 0x4c, 0x4)
        self.akf.u.proxy.write32(cmd + 0x50, 0x2)
        self.akf.u.proxy.write32(cmd + 0x54, 0x4)
        self.akf.u.proxy.write32(cmd + 0x58, 0x4)
        self.akf.u.proxy.write32(cmd + 0x5c, 0x2)
        self.akf.u.proxy.write32(cmd + 0x60, 0x2)
        self.send_cmd(0, True)

        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8 | 0x80)
        self.akf.u.proxy.write32(cmd + 0x38, 0x25)
        self.akf.u.proxy.write32(cmd + 0x3c, 0x3)
        self.akf.u.proxy.write32(cmd + 0x44, 0x1)
        self.akf.u.proxy.write32(cmd + 0x48, 0x1)
        self.akf.u.proxy.write32(cmd + 0x4c, 0x1)
        self.akf.u.proxy.write32(cmd + 0x50, 0x1)
        self.akf.u.proxy.write32(cmd + 0x54, 0x1)
        self.akf.u.proxy.write32(cmd + 0x58, 0x1)
        self.akf.u.proxy.write32(cmd + 0x5c, 0x1)
        self.akf.u.proxy.write32(cmd + 0x60, 0x1)

        # "setting asp to high power mode"
        # this updates the command buffer
        cmd = self.cmdbuf_for_ns(0)
        self.akf.u.proxy.write32(cmd + ASP_CMD_OP, 0 << 8 | 0x80)
        self.akf.u.proxy.write32(cmd + 0x38, 0x26)
        self.akf.u.proxy.write32(cmd + 0x44, 0x1)

        self.send_cmd(0, True)

    def start_io(self):
        # this is used by the IOP so we use proxy function here
        self.base = self.akf.u.proxy.memalign(0x1000, CMD_BUFFER_PER_NSID * NUM_NSID)
        self.akf.u.proxy.memset32(self.base, 0, CMD_BUFFER_PER_NSID * NUM_NSID)   
        self.in_progress = True
        self.send(ANS_SetBase(BASE=self.base, UNK=0x118, IO=0, CMD=0))
        while self.in_progress:
            self.akf.work()
            self.mon.poll()
        for i in range(0, 8):
            self.ns_setup(i)
        for i in range(0, 8):
            self.akf.u.proxy.write32(self.base + CMD_BUFFER_PER_NSID * i, i << 8)
        self.mon.poll()
        if (self.verbose >= 1):
            self.identify()
        self.cmd_init()


    def stop(self):
        if self.base:
            self.akf.u.proxy.free(self.base)

    def handle_msg(self, msg):
        msg_f = ANS_Reply(msg)
        # 2 == in progress, 4 == complete
        if self.akf.verbose >= 3:
            print(f"Tag: {msg_f.TAG} return status {msg_f.STATUS:#x}, type: {msg_f.TYPE:#x}")
        if (msg_f.TYPE == 4):
            self.in_progress = False
        if (msg_f.TYPE not in (2, 4)):
            print("Received Unknown ANS Message")
            return False
        return True

class ANSClient(StandardAKF):
    ENDPOINTS = {
        0x20: ANSEndpoint,
    }
