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
     * XNU H12 tunables program ForceNsOrdLdReqNoOlderLd through EHID4
     * for Thunder. Using HID4 here hangs D421 during early m1n1 CPU init.
     */
    reg_set(SYS_IMP_APL_EHID4, HID4_FORCE_NS_ORD_LD_REQ_NO_OLDER_LD);
    reg_set(SYS_IMP_APL_EHID10, EHID10_RCC_DISABLE_POWER_SAVE_PREFETCHER_CLOCK_OFF);

}
