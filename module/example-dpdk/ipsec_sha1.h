/*
 * ipsec_sha1.h -- SHA1 and HMAC-SHA1 for IPSec ESP authentication.
 *
 * Ported from FastClick elements/ipsec/ (sha1_impl.{hh,cc}, hmac.{hh,cc}).
 * Original SHA1: Eric Young (eay@cryptsoft.com), SSLeay.
 * Original HMAC: Eric Young (eay@cryptsoft.com), SSLeay.
 * SA/HMAC integration: Dimitris Syrivelis, University of Thessaly.
 *
 */
#ifndef IPSEC_SHA1_H
#define IPSEC_SHA1_H

#include <stdint.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/* SHA1 constants                                                      */
/* ------------------------------------------------------------------ */
#define IPSEC_SHA_CBLOCK      64
#define IPSEC_SHA_LBLOCK      16
#define IPSEC_SHA_BLOCK       16
#define IPSEC_SHA_LAST_BLOCK  56
#define IPSEC_SHA_DIGEST_LEN  20

/* ------------------------------------------------------------------ */
/* HMAC constants                                                      */
/* ------------------------------------------------------------------ */
#define IPSEC_HMAC_MAX_CBLOCK 128
#define IPSEC_HMAC_TRUNC_LEN  12   /* 96-bit truncated digest (RFC 2404) */
#define IPSEC_EVP_MAX_MD_SIZE 64

/* ------------------------------------------------------------------ */
/* SHA1 context                                                        */
/* ------------------------------------------------------------------ */
typedef struct {
    unsigned long h0, h1, h2, h3, h4;
    unsigned long Nl, Nh;
    unsigned long data[IPSEC_SHA_LBLOCK];
    int num;
} ipsec_sha1_ctx;

/* ------------------------------------------------------------------ */
/* HMAC-SHA1 context                                                   */
/* ------------------------------------------------------------------ */
typedef struct {
    ipsec_sha1_ctx md_ctx;
    ipsec_sha1_ctx i_ctx;
    ipsec_sha1_ctx o_ctx;
    unsigned int   key_length;
    unsigned char  key[IPSEC_HMAC_MAX_CBLOCK];
} ipsec_hmac_ctx;

/* ================================================================== */
/*  Internal SHA1 macros (from SSLeay)                                 */
/* ================================================================== */

#define IPSEC_SHA_ROTATE(a,n) (((a)<<(n))|(((a)&0xffffffff)>>(32-(n))))

#define ipsec_Endian_Reverse32(a) do {        \
    unsigned long _l = (a);                   \
    _l = (((_l&0xFF00FF00)>>8L)|((_l&0x00FF00FF)<<8L)); \
    (a) = IPSEC_SHA_ROTATE(_l, 16L);         \
} while(0)

/* bytes → big-endian unsigned long */
#define ipsec_c2nl(c,l) \
    (l  = (((unsigned long)(*((c)++)))<<24), \
     l |= (((unsigned long)(*((c)++)))<<16), \
     l |= (((unsigned long)(*((c)++)))<< 8), \
     l |= (((unsigned long)(*((c)++)))))

#define ipsec_p_c2nl(c,l,n) do {                       \
    switch (n) {                                        \
    case 0: l  = ((unsigned long)(*((c)++)))<<24; /* fall through */ \
    case 1: l |= ((unsigned long)(*((c)++)))<<16; /* fall through */ \
    case 2: l |= ((unsigned long)(*((c)++)))<< 8; /* fall through */ \
    case 3: l |= ((unsigned long)(*((c)++)));                        \
    }                                                   \
} while(0)

#define ipsec_c2nl_p(c,l,n) do {                        \
    l = 0; (c) += (n);                                  \
    switch (n) {                                         \
    case 3: l  = ((unsigned long)(*(--(c))))<< 8; /* fall through */ \
    case 2: l |= ((unsigned long)(*(--(c))))<<16; /* fall through */ \
    case 1: l |= ((unsigned long)(*(--(c))))<<24;                    \
    }                                                    \
} while(0)

#define ipsec_p_c2nl_p(c,l,sc,len) do {                 \
    switch (sc) {                                        \
    case 0: l  = ((unsigned long)(*((c)++)))<<24;        \
            if (--(len) == 0) break; /* fall through */  \
    case 1: l |= ((unsigned long)(*((c)++)))<<16;        \
            if (--(len) == 0) break; /* fall through */  \
    case 2: l |= ((unsigned long)(*((c)++)))<< 8;        \
    }                                                    \
} while(0)

/* big-endian unsigned long → bytes */
#define ipsec_nl2c(l,c) \
    (*((c)++) = (unsigned char)(((l)>>24)&0xff), \
     *((c)++) = (unsigned char)(((l)>>16)&0xff), \
     *((c)++) = (unsigned char)(((l)>> 8)&0xff), \
     *((c)++) = (unsigned char)(((l)    )&0xff))

/* SHA1 round functions */
#define IPSEC_F_00_19(b,c,d) ((((c) ^ (d)) & (b)) ^ (d))
#define IPSEC_F_20_39(b,c,d) ((b) ^ (c) ^ (d))
#define IPSEC_F_40_59(b,c,d) (((b) & (c)) | (((b)|(c)) & (d)))
#define IPSEC_F_60_79(b,c,d) IPSEC_F_20_39(b,c,d)

/* SHA-1 message schedule expansion */
#define ipsec_Xupdate(a,i,ia,ib,ic,id) \
    (a) = (ia[(i)&0x0f]^ib[((i)+2)&0x0f]^ic[((i)+8)&0x0f]^id[((i)+13)&0x0f]); \
    X[(i)&0x0f] = (a) = IPSEC_SHA_ROTATE((a),1);

#define IPSEC_K_00_19 0x5a827999L
#define IPSEC_K_20_39 0x6ed9eba1L
#define IPSEC_K_40_59 0x8f1bbcdcL
#define IPSEC_K_60_79 0xca62c1d6L

#define IPSEC_INIT_h0 0x67452301L
#define IPSEC_INIT_h1 0xefcdab89L
#define IPSEC_INIT_h2 0x98badcfeL
#define IPSEC_INIT_h3 0x10325476L
#define IPSEC_INIT_h4 0xc3d2e1f0L

#define IPSEC_BODY_00_15(i,a,b,c,d,e,f,xa) \
    (f) = xa[i]+(e)+IPSEC_K_00_19+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_00_19((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

#define IPSEC_BODY_16_19(i,a,b,c,d,e,f,xa,xb,xc,xd) \
    ipsec_Xupdate(f,i,xa,xb,xc,xd); \
    (f) += (e)+IPSEC_K_00_19+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_00_19((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

#define IPSEC_BODY_20_31(i,a,b,c,d,e,f,xa,xb,xc,xd) \
    ipsec_Xupdate(f,i,xa,xb,xc,xd); \
    (f) += (e)+IPSEC_K_20_39+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_20_39((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

#define IPSEC_BODY_32_39(i,a,b,c,d,e,f,xa) \
    ipsec_Xupdate(f,i,xa,xa,xa,xa); \
    (f) += (e)+IPSEC_K_20_39+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_20_39((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

#define IPSEC_BODY_40_59(i,a,b,c,d,e,f,xa) \
    ipsec_Xupdate(f,i,xa,xa,xa,xa); \
    (f) += (e)+IPSEC_K_40_59+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_40_59((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

#define IPSEC_BODY_60_79(i,a,b,c,d,e,f,xa) \
    ipsec_Xupdate(f,i,xa,xa,xa,xa); \
    (f) = X[(i)&0x0f]+(e)+IPSEC_K_60_79+IPSEC_SHA_ROTATE((a),5)+IPSEC_F_60_79((b),(c),(d)); \
    (b) = IPSEC_SHA_ROTATE((b),30);

/* ================================================================== */
/*  SHA1 block transform                                               */
/* ================================================================== */
static void
ipsec_sha1_block(ipsec_sha1_ctx *c, unsigned long *W, int num)
{
    unsigned long A, B, C, D, E, T;
    unsigned long X[16];

    A = c->h0; B = c->h1; C = c->h2; D = c->h3; E = c->h4;

    for (;;) {
        IPSEC_BODY_00_15( 0, A, B, C, D, E, T, W);
        IPSEC_BODY_00_15( 1, T, A, B, C, D, E, W);
        IPSEC_BODY_00_15( 2, E, T, A, B, C, D, W);
        IPSEC_BODY_00_15( 3, D, E, T, A, B, C, W);
        IPSEC_BODY_00_15( 4, C, D, E, T, A, B, W);
        IPSEC_BODY_00_15( 5, B, C, D, E, T, A, W);
        IPSEC_BODY_00_15( 6, A, B, C, D, E, T, W);
        IPSEC_BODY_00_15( 7, T, A, B, C, D, E, W);
        IPSEC_BODY_00_15( 8, E, T, A, B, C, D, W);
        IPSEC_BODY_00_15( 9, D, E, T, A, B, C, W);
        IPSEC_BODY_00_15(10, C, D, E, T, A, B, W);
        IPSEC_BODY_00_15(11, B, C, D, E, T, A, W);
        IPSEC_BODY_00_15(12, A, B, C, D, E, T, W);
        IPSEC_BODY_00_15(13, T, A, B, C, D, E, W);
        IPSEC_BODY_00_15(14, E, T, A, B, C, D, W);
        IPSEC_BODY_00_15(15, D, E, T, A, B, C, W);
        IPSEC_BODY_16_19(16, C, D, E, T, A, B, W, W, W, W);
        IPSEC_BODY_16_19(17, B, C, D, E, T, A, W, W, W, W);
        IPSEC_BODY_16_19(18, A, B, C, D, E, T, W, W, W, W);
        IPSEC_BODY_16_19(19, T, A, B, C, D, E, W, W, W, X);

        IPSEC_BODY_20_31(20, E, T, A, B, C, D, W, W, W, X);
        IPSEC_BODY_20_31(21, D, E, T, A, B, C, W, W, W, X);
        IPSEC_BODY_20_31(22, C, D, E, T, A, B, W, W, W, X);
        IPSEC_BODY_20_31(23, B, C, D, E, T, A, W, W, W, X);
        IPSEC_BODY_20_31(24, A, B, C, D, E, T, W, W, X, X);
        IPSEC_BODY_20_31(25, T, A, B, C, D, E, W, W, X, X);
        IPSEC_BODY_20_31(26, E, T, A, B, C, D, W, W, X, X);
        IPSEC_BODY_20_31(27, D, E, T, A, B, C, W, W, X, X);
        IPSEC_BODY_20_31(28, C, D, E, T, A, B, W, W, X, X);
        IPSEC_BODY_20_31(29, B, C, D, E, T, A, W, W, X, X);
        IPSEC_BODY_20_31(30, A, B, C, D, E, T, W, X, X, X);
        IPSEC_BODY_20_31(31, T, A, B, C, D, E, W, X, X, X);
        IPSEC_BODY_32_39(32, E, T, A, B, C, D, X);
        IPSEC_BODY_32_39(33, D, E, T, A, B, C, X);
        IPSEC_BODY_32_39(34, C, D, E, T, A, B, X);
        IPSEC_BODY_32_39(35, B, C, D, E, T, A, X);
        IPSEC_BODY_32_39(36, A, B, C, D, E, T, X);
        IPSEC_BODY_32_39(37, T, A, B, C, D, E, X);
        IPSEC_BODY_32_39(38, E, T, A, B, C, D, X);
        IPSEC_BODY_32_39(39, D, E, T, A, B, C, X);

        IPSEC_BODY_40_59(40, C, D, E, T, A, B, X);
        IPSEC_BODY_40_59(41, B, C, D, E, T, A, X);
        IPSEC_BODY_40_59(42, A, B, C, D, E, T, X);
        IPSEC_BODY_40_59(43, T, A, B, C, D, E, X);
        IPSEC_BODY_40_59(44, E, T, A, B, C, D, X);
        IPSEC_BODY_40_59(45, D, E, T, A, B, C, X);
        IPSEC_BODY_40_59(46, C, D, E, T, A, B, X);
        IPSEC_BODY_40_59(47, B, C, D, E, T, A, X);
        IPSEC_BODY_40_59(48, A, B, C, D, E, T, X);
        IPSEC_BODY_40_59(49, T, A, B, C, D, E, X);
        IPSEC_BODY_40_59(50, E, T, A, B, C, D, X);
        IPSEC_BODY_40_59(51, D, E, T, A, B, C, X);
        IPSEC_BODY_40_59(52, C, D, E, T, A, B, X);
        IPSEC_BODY_40_59(53, B, C, D, E, T, A, X);
        IPSEC_BODY_40_59(54, A, B, C, D, E, T, X);
        IPSEC_BODY_40_59(55, T, A, B, C, D, E, X);
        IPSEC_BODY_40_59(56, E, T, A, B, C, D, X);
        IPSEC_BODY_40_59(57, D, E, T, A, B, C, X);
        IPSEC_BODY_40_59(58, C, D, E, T, A, B, X);
        IPSEC_BODY_40_59(59, B, C, D, E, T, A, X);

        IPSEC_BODY_60_79(60, A, B, C, D, E, T, X);
        IPSEC_BODY_60_79(61, T, A, B, C, D, E, X);
        IPSEC_BODY_60_79(62, E, T, A, B, C, D, X);
        IPSEC_BODY_60_79(63, D, E, T, A, B, C, X);
        IPSEC_BODY_60_79(64, C, D, E, T, A, B, X);
        IPSEC_BODY_60_79(65, B, C, D, E, T, A, X);
        IPSEC_BODY_60_79(66, A, B, C, D, E, T, X);
        IPSEC_BODY_60_79(67, T, A, B, C, D, E, X);
        IPSEC_BODY_60_79(68, E, T, A, B, C, D, X);
        IPSEC_BODY_60_79(69, D, E, T, A, B, C, X);
        IPSEC_BODY_60_79(70, C, D, E, T, A, B, X);
        IPSEC_BODY_60_79(71, B, C, D, E, T, A, X);
        IPSEC_BODY_60_79(72, A, B, C, D, E, T, X);
        IPSEC_BODY_60_79(73, T, A, B, C, D, E, X);
        IPSEC_BODY_60_79(74, E, T, A, B, C, D, X);
        IPSEC_BODY_60_79(75, D, E, T, A, B, C, X);
        IPSEC_BODY_60_79(76, C, D, E, T, A, B, X);
        IPSEC_BODY_60_79(77, B, C, D, E, T, A, X);
        IPSEC_BODY_60_79(78, A, B, C, D, E, T, X);
        IPSEC_BODY_60_79(79, T, A, B, C, D, E, X);

        c->h0 = (c->h0 + E) & 0xffffffffL;
        c->h1 = (c->h1 + T) & 0xffffffffL;
        c->h2 = (c->h2 + A) & 0xffffffffL;
        c->h3 = (c->h3 + B) & 0xffffffffL;
        c->h4 = (c->h4 + C) & 0xffffffffL;

        num -= 64;
        if (num <= 0) break;

        A = c->h0; B = c->h1; C = c->h2; D = c->h3; E = c->h4;
        W += 16;
    }
}

/* ================================================================== */
/*  SHA1 public API                                                    */
/* ================================================================== */

static inline void
ipsec_sha1_init(ipsec_sha1_ctx *c)
{
    c->h0 = IPSEC_INIT_h0;
    c->h1 = IPSEC_INIT_h1;
    c->h2 = IPSEC_INIT_h2;
    c->h3 = IPSEC_INIT_h3;
    c->h4 = IPSEC_INIT_h4;
    c->Nl = 0;
    c->Nh = 0;
    c->num = 0;
}

static void
ipsec_sha1_update(ipsec_sha1_ctx *c, unsigned char *data, unsigned long len)
{
    unsigned long *p;
    int ew, ec, sw, sc;
    unsigned long l;

    if (len == 0) return;

    l = (c->Nl + (len << 3)) & 0xffffffffL;
    if (l < c->Nl) c->Nh++;
    c->Nh += (len >> 29);
    c->Nl = l;

    if (c->num != 0) {
        p = c->data;
        sw = c->num >> 2;
        sc = c->num & 0x03;

        if ((c->num + len) >= IPSEC_SHA_CBLOCK) {
            l = p[sw];
            ipsec_p_c2nl(data, l, sc);
            p[sw++] = l;
            for (; sw < IPSEC_SHA_LBLOCK; sw++) {
                ipsec_c2nl(data, l);
                p[sw] = l;
            }
            len -= (IPSEC_SHA_CBLOCK - c->num);
            ipsec_sha1_block(c, p, 64);
            c->num = 0;
        } else {
            c->num += (int)len;
            if ((sc + len) < 4) {
                l = p[sw];
                ipsec_p_c2nl_p(data, l, sc, len);
                p[sw] = l;
            } else {
                ew = (c->num >> 2);
                ec = (c->num & 0x03);
                l = p[sw];
                ipsec_p_c2nl(data, l, sc);
                p[sw++] = l;
                for (; sw < ew; sw++) {
                    ipsec_c2nl(data, l);
                    p[sw] = l;
                }
                if (ec) {
                    ipsec_c2nl_p(data, l, ec);
                    p[sw] = l;
                }
            }
            return;
        }
    }

    p = c->data;
    while (len >= IPSEC_SHA_CBLOCK) {
        for (sw = (IPSEC_SHA_BLOCK / 4); sw; sw--) {
            ipsec_c2nl(data, l); *(p++) = l;
            ipsec_c2nl(data, l); *(p++) = l;
            ipsec_c2nl(data, l); *(p++) = l;
            ipsec_c2nl(data, l); *(p++) = l;
        }
        p = c->data;
        ipsec_sha1_block(c, p, 64);
        len -= IPSEC_SHA_CBLOCK;
    }
    ec = (int)len;
    c->num = ec;
    ew = (ec >> 2);
    ec &= 0x03;

    for (sw = 0; sw < ew; sw++) {
        ipsec_c2nl(data, l);
        p[sw] = l;
    }
    ipsec_c2nl_p(data, l, ec);
    p[sw] = l;
}

static void
ipsec_sha1_final(unsigned char *md, ipsec_sha1_ctx *c)
{
    int i, j;
    unsigned long l;
    unsigned long *p;
    static unsigned char end[4] = { 0x80, 0x00, 0x00, 0x00 };
    unsigned char *cp = end;

    p = c->data;
    j = c->num;
    i = j >> 2;
    l = p[i];
    ipsec_p_c2nl(cp, l, j & 0x03);
    p[i] = l;
    i++;

    if (c->num >= IPSEC_SHA_LAST_BLOCK) {
        for (; i < IPSEC_SHA_LBLOCK; i++)
            p[i] = 0;
        ipsec_sha1_block(c, p, 64);
        i = 0;
    }
    for (; i < (IPSEC_SHA_LBLOCK - 2); i++)
        p[i] = 0;
    p[IPSEC_SHA_LBLOCK - 2] = c->Nh;
    p[IPSEC_SHA_LBLOCK - 1] = c->Nl;
    ipsec_sha1_block(c, p, 64);

    cp = md;
    l = c->h0; ipsec_nl2c(l, cp);
    l = c->h1; ipsec_nl2c(l, cp);
    l = c->h2; ipsec_nl2c(l, cp);
    l = c->h3; ipsec_nl2c(l, cp);
    l = c->h4; ipsec_nl2c(l, cp);
    c->num = 0;
}

/* ================================================================== */
/*  HMAC-SHA1                                                          */
/* ================================================================== */

static inline void
ipsec_hmac_ctx_init(ipsec_hmac_ctx *ctx)
{
    ipsec_sha1_init(&ctx->i_ctx);
    ipsec_sha1_init(&ctx->o_ctx);
    ipsec_sha1_init(&ctx->md_ctx);
}

static inline void
ipsec_hmac_ctx_cleanup(ipsec_hmac_ctx *ctx)
{
    memset(ctx, 0, sizeof(*ctx));
}

static void
ipsec_hmac_init_ex(ipsec_hmac_ctx *ctx, const void *key, int len)
{
    int i, reset = 0;
    unsigned char pad[IPSEC_HMAC_MAX_CBLOCK];

    if (key != NULL) {
        reset = 1;
        if (IPSEC_SHA_CBLOCK < len) {
            ipsec_sha1_init(&ctx->md_ctx);
            ipsec_sha1_update(&ctx->md_ctx, (unsigned char *)key, len);
            ipsec_sha1_final(ctx->key, &ctx->md_ctx);
        } else {
            memcpy(ctx->key, key, len);
            ctx->key_length = len;
        }
        if (ctx->key_length != IPSEC_HMAC_MAX_CBLOCK)
            memset(&ctx->key[ctx->key_length], 0,
                   IPSEC_HMAC_MAX_CBLOCK - ctx->key_length);
    }

    if (reset) {
        for (i = 0; i < IPSEC_HMAC_MAX_CBLOCK; i++)
            pad[i] = 0x36 ^ ctx->key[i];
        ipsec_sha1_init(&ctx->i_ctx);
        ipsec_sha1_update(&ctx->i_ctx, pad, IPSEC_SHA_CBLOCK);

        for (i = 0; i < IPSEC_HMAC_MAX_CBLOCK; i++)
            pad[i] = 0x5c ^ ctx->key[i];
        ipsec_sha1_init(&ctx->o_ctx);
        ipsec_sha1_update(&ctx->o_ctx, pad, IPSEC_SHA_CBLOCK);
    }
    memcpy(&ctx->md_ctx, &ctx->i_ctx, sizeof(ipsec_sha1_ctx));
}

static inline void
ipsec_hmac_init(ipsec_hmac_ctx *ctx, const void *key, int len)
{
    if (key)
        ipsec_hmac_ctx_init(ctx);
    ipsec_hmac_init_ex(ctx, key, len);
}

static inline void
ipsec_hmac_update(ipsec_hmac_ctx *ctx, unsigned char *data, size_t len)
{
    ipsec_sha1_update(&ctx->md_ctx, data, len);
}

static void
ipsec_hmac_final(ipsec_hmac_ctx *ctx, unsigned char *md, unsigned int *len)
{
    unsigned char buf[IPSEC_EVP_MAX_MD_SIZE];
    ipsec_sha1_final(buf, &ctx->md_ctx);
    memcpy(&ctx->md_ctx, &ctx->o_ctx, sizeof(ipsec_sha1_ctx));
    ipsec_sha1_update(&ctx->md_ctx, buf, (unsigned long)*len);
    ipsec_sha1_final(md, &ctx->md_ctx);
}

/* Convenience: compute HMAC-SHA1 in one call */
static inline unsigned char *
ipsec_hmac(void *key, int key_len,
           unsigned char *d, size_t n,
           unsigned char *md, unsigned int *md_len)
{
    ipsec_hmac_ctx c;
    static unsigned char m[IPSEC_EVP_MAX_MD_SIZE];
    if (md == NULL) md = m;
    ipsec_hmac_ctx_init(&c);
    ipsec_hmac_init(&c, key, key_len);
    ipsec_hmac_update(&c, d, n);
    ipsec_hmac_final(&c, md, md_len);
    ipsec_hmac_ctx_cleanup(&c);
    return md;
}

#endif /* IPSEC_SHA1_H */
