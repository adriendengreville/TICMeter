#include "linky_contract.h"

#include <stddef.h>
#include <string.h>

const char *const linky_hist_str_contract[C_COUNT] = {
    [C_ANY] = "ANY",
    [C_BASE] = "BASE",
    [C_HC] = "HC..",
    [C_EJP] = "EJP.",
    [C_TEMPO] = "BBR",
};

const char *const linky_std_str_contract[C_COUNT] = {
    [C_ANY] = "ANY",
    [C_BASE] = "BASE",
    [C_HC] = "H PLEINE/CREUSE",
    [C_HEURES_SUPER_CREUSES] = "H SUPER CREUSES",
    [C_EJP] = "EJP",
    [C_TEMPO] = "TEMPO",
    [C_ZEN_FLEX] = "ZEN FLEX",
    [C_SEM_WE_LUNDI] = "SEM WE LUNDI",
    [C_SEM_WE_MERCREDI] = "SEM WE MERCREDI",
    [C_SEM_WE_VENDREDI] = "SEM WE VENDREDI",
    [C_HC_WE] = "HC et Week-End",
    [C_ZEN_ESTIVAL] = "HSC ETE HIVER",
    [C_SEM_WE] = "SEM WE",
    [C_HC_SEM_WE] = "HC SEM ET HC WE",
    [C_HC_SEM_WE_LUNDI] = "HC SEM WE LUNDI",
    [C_HC_SEM_WE_MERCREDI] = "HC SEM WE MERCR",
    [C_HC_SEM_WE_VENDREDI] = "HC SEM WE VENDR",
};

// The cloud product has a fixed enumeration. Do not invent new Tuya values.
// Every slot must be populated: tuya_verify_enum stops at the first NULL.
const char *const linky_tuya_str_contract[C_COUNT + 1] = {
    [C_UNKNOWN] = "INCONNU",
    [C_ANY] = "INCONNU",
    [C_BASE] = "BASE",
    [C_HC] = "HCHP",
    [C_HEURES_SUPER_CREUSES] = "HSC",
    [C_EJP] = "EJP",
    [C_TEMPO] = "TEMPO",
    [C_ZEN_FLEX] = "ZEN_FLEX",
    [C_SEM_WE_LUNDI] = "SEM_WE_LUNDI",
    [C_SEM_WE_MERCREDI] = "SEM_WE_MERCREDI",
    [C_SEM_WE_VENDREDI] = "SEM_WE_VENDREDI",
    [C_HC_WE] = "INCONNU",
    [C_ZEN_ESTIVAL] = "INCONNU",
    [C_SEM_WE] = "INCONNU",
    [C_HC_SEM_WE] = "INCONNU",
    [C_HC_SEM_WE_LUNDI] = "INCONNU",
    [C_HC_SEM_WE_MERCREDI] = "INCONNU",
    [C_HC_SEM_WE_VENDREDI] = "INCONNU",
    [C_COUNT] = NULL,
};

static bool normalize_contract(char *dest, size_t size, const char *src)
{
    size_t out = 0;
    if (src == NULL)
    {
        dest[0] = 0;
        return true;
    }
    for (size_t i = 0; src[i] != 0; i++)
    {
        unsigned char c = (unsigned char)src[i];
        if (c == ' ' || c == '\t')
        {
            continue;
        }
        // Reject corrupt/control bytes rather than silently repairing a name.
        if (c < ' ' || c > '~' || out >= size - 1)
        {
            dest[0] = 0;
            return false;
        }
        if (c >= 'a' && c <= 'z')
        {
            c -= 'a' - 'A';
        }
        dest[out++] = c;
    }
    dest[out] = 0;
    return true;
}

linky_contract_t linky_contract_detect(bool historical, const char *name, const char *tariff)
{
    char normalized[32];
    char candidate[32];
    if (!normalize_contract(normalized, sizeof(normalized), name))
    {
        return C_UNKNOWN;
    }

    const char *const *names = historical ? linky_hist_str_contract : linky_std_str_contract;
    if (normalized[0] != 0)
    {
        for (int i = C_BASE; i < C_COUNT; i++)
        {
            if (names[i] != NULL && normalize_contract(candidate, sizeof(candidate), names[i]) &&
                strcmp(normalized, candidate) == 0)
            {
                return i;
            }
        }

        if (historical)
        {
            // Historical Tempo has a fourth character identifying its variant.
            if (strlen(normalized) == 4 && strncmp(normalized, "BBR", 3) == 0)
            {
                return C_TEMPO;
            }
        }
        else if (strcmp(normalized, "POINTEMOBILE") == 0)
        {
            return C_ZEN_FLEX;
        }

        // A present but unknown calendar must not be overridden by a tariff.
        return C_UNKNOWN;
    }

    if (!historical && normalize_contract(normalized, sizeof(normalized), tariff))
    {
        static const char *const tempo_tariffs[] = {
            "HCBLEU", "HPBLEU", "HCBLANC", "HPBLANC",
            "HCROUGE", "HPROUGE", "HCROUG", "HPROUG",
        };
        for (size_t i = 0; i < sizeof(tempo_tariffs) / sizeof(tempo_tariffs[0]); i++)
        {
            if (strcmp(normalized, tempo_tariffs[i]) == 0)
            {
                return C_TEMPO;
            }
        }
    }
    return C_UNKNOWN;
}
