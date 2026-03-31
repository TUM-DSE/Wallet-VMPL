/*
 * ids.h -- Intrusion Detection System packet scanning via Hyperscan.
 *
 * Provides a simple IDS interface for scanning packet data against a
 * compiled set of regex patterns using Intel Hyperscan.
 *
 * Usage:
 *   ids_init();                             // compile patterns, allocate scratch
 *   ids_scan(pkt_data, pkt_len);            // scan a buffer
 *   printf("matches: %lu\n", ids_matches);  // read match count
 */
#ifndef IDS_H
#define IDS_H

#include <hs/hs.h>
#include <stdio.h>

static hs_database_t *ids_db = NULL;
static hs_scratch_t *ids_scratch = NULL;
static uint64_t ids_matches = 0;

static int ids_match_handler(unsigned int id, unsigned long long from,
                             unsigned long long to, unsigned int flags,
                             void *ctx)
{
    (void)id; (void)from; (void)to; (void)flags; (void)ctx;
    ids_matches++;
    return 0; /* continue scanning */
}

static inline void ids_init(void)
{
    const char *patterns[] = {
        "\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}",  /* IPv4 address */
        "[A-Fa-f0-9]{32}",                               /* hex token / hash */
        "HTTP/[12]\\.[01]",                               /* HTTP version */
    };
    const unsigned int flags[] = {
        HS_FLAG_DOTALL | HS_FLAG_SINGLEMATCH,
        HS_FLAG_DOTALL | HS_FLAG_SINGLEMATCH,
        HS_FLAG_DOTALL | HS_FLAG_SINGLEMATCH,
    };
    const unsigned int ids[] = { 1, 2, 3 };
    hs_compile_error_t *compile_err = NULL;

    if (hs_compile_multi(patterns, flags, ids,
                         sizeof(patterns) / sizeof(patterns[0]),
                         HS_MODE_BLOCK, NULL, &ids_db,
                         &compile_err) != HS_SUCCESS) {
        fprintf(stdout, "Hyperscan compile error: %s\n",
                compile_err ? compile_err->message : "unknown");
        fflush(stdout);
        if (compile_err) hs_free_compile_error(compile_err);
        return;
    }

    if (hs_alloc_scratch(ids_db, &ids_scratch) != HS_SUCCESS) {
        fprintf(stdout, "Hyperscan scratch alloc failed\n");
        fflush(stdout);
        hs_free_database(ids_db);
        ids_db = NULL;
        return;
    }
    fprintf(stdout, "Hyperscan IDS initialized (%lu patterns)\n",
            sizeof(patterns) / sizeof(patterns[0]));
    fflush(stdout);
}

static inline int ids_scan(const char *data, unsigned int len)
{
    if (!ids_db)
        return -1;
    return hs_scan(ids_db, data, len, 0,
                   ids_scratch, ids_match_handler, NULL) == HS_SUCCESS ? 0 : -1;
}

#endif /* IDS_H */
