/* SPDX-License-Identifier: MIT */

#include "chickens.h"
#include "cpu_regs.h"
#include "utils.h"

static void init_t8030_common_thunder(void)
{
    reg_set(SYS_IMP_APL_EHID10, HID10_FORCE_WAIT_STATE_DRAIN_UC);
}

void init_t8030_thunder(int rev)
{
    (void)rev;

    init_t8030_common_thunder();
    reg_set(SYS_IMP_APL_HID5, HID5_DISABLE_FILL_2C_MERGE);
    /*
     * D421/A13 hangs during early m1n1 CPU init when this Thunder HID4
     * chicken bit is programmed under the current iBoot handoff path.
     * Leave it disabled until the required firmware/boot state difference
     * is understood.
     */
    /* reg_set(SYS_IMP_APL_HID4, HID4_FORCE_NS_ORD_LD_REQ_NO_OLDER_LD); */
    reg_set(SYS_IMP_APL_EHID10, EHID10_RCC_DISABLE_POWER_SAVE_PREFETCHER_CLOCK_OFF);

}
