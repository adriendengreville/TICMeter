#ifndef LINKY_CONTRACT_H
#define LINKY_CONTRACT_H

#include <stdbool.h>

typedef enum
{
    C_UNKNOWN,
    C_ANY,
    C_BASE,
    C_HC,
    C_HEURES_SUPER_CREUSES,
    C_EJP,
    C_TEMPO,
    C_ZEN_FLEX,
    C_SEM_WE_LUNDI,
    C_SEM_WE_MERCREDI,
    C_SEM_WE_VENDREDI,
    C_HC_WE,
    // Append contracts to preserve existing numeric identifiers.
    C_ZEN_ESTIVAL,
    C_SEM_WE,
    C_HC_SEM_WE,
    C_HC_SEM_WE_LUNDI,
    C_HC_SEM_WE_MERCREDI,
    C_HC_SEM_WE_VENDREDI,
    C_COUNT,
} linky_contract_t;

extern const char *const linky_hist_str_contract[C_COUNT];
extern const char *const linky_std_str_contract[C_COUNT];
extern const char *const linky_tuya_str_contract[C_COUNT + 1];

// Inputs are NUL-terminated copies of OPTARIF/NGTF and LTARF respectively.
// LTARF only supplies an unambiguous Tempo fallback when NGTF is absent.
linky_contract_t linky_contract_detect(bool historical, const char *name, const char *tariff);

#endif
