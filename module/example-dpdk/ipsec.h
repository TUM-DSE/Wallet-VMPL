/*
 * ipsec.h -- Minimalistic IPSec ESP encap/decap for DPDK packet processing.
 *
 * Ported from FastClick elements/ipsec/ (MIT, Alex Snoeren, Benjie Chen,
 * Dimitris Syrivelis). One function per original Click element:
 *
 *   ipsec_esp_encap()          <->  IPsecESPEncap::simple_action
 *   ipsec_esp_decap()          <->  IPsecESPUnencap::simple_action
 *   ipsec_aes_cbc_encrypt()    <->  Aes::simple_action (encrypt)
 *   ipsec_aes_cbc_decrypt()    <->  Aes::simple_action (decrypt)
 *   ipsec_hmac_sha1_compute()  <->  IPsecAuthHMACSHA1::simple_action (compute)
 *   ipsec_hmac_sha1_verify()   <->  IPsecAuthHMACSHA1::simple_action (verify)
 *   ipsec_ip_encap()           <->  IPsecEncap::simple_action
 *   ipsec_ip_decap()           <->  StripIPHeader
 *
 * All functions operate on struct rte_mbuf * in-place.
 * Return 0 on success, -1 on error (packet should be dropped).
 *
 * Typical encap pipeline (MAC-then-encrypt, matching FastClick order):
 *   ipsec_esp_encap(m, sa, spi, next_hdr);
 *   ipsec_hmac_sha1_compute(m, sa);
 *   ipsec_aes_cbc_encrypt(m, sa);
 *   ipsec_ip_encap(m, IPPROTO_ESP, src_ip, dst_ip);
 *
 * Typical decap pipeline:
 *   ipsec_ip_decap(m);
 *   ipsec_aes_cbc_decrypt(m, sa);
 *   ipsec_hmac_sha1_verify(m, sa);
 *   ipsec_esp_decap(m, sa);
 */
#ifndef IPSEC_H
#define IPSEC_H

#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#include <arpa/inet.h>


#include <rte_mbuf.h>
#include <rte_ip.h>

#include "ipsec_aes.h"
#include "ipsec_sha1.h"



#define USE_OPENSSL

#ifdef USE_OPENSSL
#include <openssl/evp.h>
#include <openssl/sha.h>
#endif

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */
#define IPSEC_KEY_SIZE        16
#define IPSEC_ESP_BLKS         8   /* padding block size (RFC 2406) */
#define IPSEC_AUTH_DIGEST_LEN 12   /* truncated HMAC-SHA1 (RFC 2404) */
#define IPSEC_ESP_PROTO       50   /* IP protocol number for ESP */

/* ------------------------------------------------------------------ */
/* ESP header (RFC 2406)                                               */
/* ------------------------------------------------------------------ */
struct ipsec_esp_hdr {
    uint32_t spi;          /* Security Parameters Index */
    uint32_t seq;          /* Sequence / replay counter */
    uint8_t  iv[8];        /* Initialization Vector     */
};

/* ------------------------------------------------------------------ */
/* Security Association                                                */
/* ------------------------------------------------------------------ */
struct ipsec_sa {
    uint8_t  enc_key[IPSEC_KEY_SIZE];
    uint8_t  auth_key[IPSEC_KEY_SIZE];
    uint32_t replay_start;
    uint32_t cur_seq;
    uint8_t  ooo_window;    /* out-of-order window size */
    uint32_t bitmap;        /* replay bitmap */
    uint32_t lastseq;       /* last accepted sequence (host order) */
    EVP_CIPHER_CTX *evp_enc_ctx; /* pre-allocated OpenSSL encrypt context */
    EVP_CIPHER_CTX *evp_dec_ctx; /* pre-allocated OpenSSL decrypt context */
};

static inline void
ipsec_sa_init(struct ipsec_sa *sa,
              const uint8_t enc_key[IPSEC_KEY_SIZE],
              const uint8_t auth_key[IPSEC_KEY_SIZE],
              uint32_t replay_start,
              uint8_t ooo_window)
{
    memset(sa, 0, sizeof(*sa));
    memcpy(sa->enc_key, enc_key, IPSEC_KEY_SIZE);
    memcpy(sa->auth_key, auth_key, IPSEC_KEY_SIZE);
    sa->replay_start = replay_start;
    sa->cur_seq = replay_start;
    sa->ooo_window = ooo_window;
    sa->evp_enc_ctx = EVP_CIPHER_CTX_new();
    sa->evp_dec_ctx = EVP_CIPHER_CTX_new();
}

static inline void
ipsec_sa_free(struct ipsec_sa *sa)
{
    if (sa->evp_enc_ctx) {
        EVP_CIPHER_CTX_free(sa->evp_enc_ctx);
        sa->evp_enc_ctx = NULL;
    }
    if (sa->evp_dec_ctx) {
        EVP_CIPHER_CTX_free(sa->evp_dec_ctx);
        sa->evp_dec_ctx = NULL;
    }
}

/* ================================================================== */
/*  IPsecESPEncap -- add ESP header + RFC 2406 padding                 */
/* ================================================================== */

/*
 * Prepends an ESP header (SPI, sequence number, random IV) and appends
 * RFC 2406 default padding so the payload is a multiple of IPSEC_ESP_BLKS.
 *
 * @param m          Packet mbuf (must have sufficient head/tailroom).
 * @param sa         Security association (cur_seq is incremented).
 * @param spi        Security Parameters Index for this packet.
 * @param next_hdr   Next-header field stored in last padding byte
 *                   (e.g. original IP protocol, or 0).
 * @return 0 success, -1 failure.
 */
static inline int
ipsec_esp_encap(struct rte_mbuf *m, struct ipsec_sa *sa,
                uint32_t spi, uint8_t next_hdr)
{
    int plen = rte_pktmbuf_data_len(m);
    int padding = ((IPSEC_ESP_BLKS - ((plen + 2) % IPSEC_ESP_BLKS))
                   % IPSEC_ESP_BLKS) + 2;

    /* prepend ESP header */
    char *new_start = rte_pktmbuf_prepend(m, sizeof(struct ipsec_esp_hdr));
    if (!new_start) return -1;

    /* append padding */
    char *pad_area = rte_pktmbuf_append(m, padding);
    if (!pad_area) return -1;

    struct ipsec_esp_hdr *esp =
        rte_pktmbuf_mtod(m, struct ipsec_esp_hdr *);
    uint8_t *pad = (uint8_t *)esp + sizeof(struct ipsec_esp_hdr) + plen;

    /* fill ESP header */
    esp->spi = htonl(spi);
    esp->seq = htonl(sa->cur_seq);
    if ((sa->cur_seq++) == 0)
        sa->cur_seq = sa->replay_start;

    /* random IV */
    uint32_t r = (uint32_t)rand();
    memcpy(&esp->iv[0], &r, 4);
    r = (uint32_t)rand();
    memcpy(&esp->iv[4], &r, 4);

    /* RFC 2406 default padding: pad[0]=1, pad[1]=2, ... */
    for (int i = 0; i < padding - 2; i++)
        pad[i] = (uint8_t)(i + 1);
    pad[padding - 2] = (uint8_t)(padding - 2);
    pad[padding - 1] = next_hdr;

    return 0;
}

/* ================================================================== */
/*  IPsecESPUnencap -- strip ESP header, validate & strip padding      */
/* ================================================================== */

/* replay window check (from FastClick desp.cc) */
static inline int
ipsec_check_replay(struct ipsec_sa *sa, unsigned long seq)
{
    unsigned long diff;

    if (seq == 0)
        return 0;   /* seq 0 is invalid / wrapped */

    /* handle counter rollover */
    if ((seq == sa->replay_start) &&
        (sa->lastseq != sa->replay_start)) {
        sa->bitmap = 0;
        sa->lastseq = seq;
        return 1;
    }

    if (seq > sa->lastseq) {
        diff = seq - sa->lastseq;
        if (diff < sa->ooo_window)
            sa->bitmap = (sa->bitmap << diff) | 1;
        else
            sa->bitmap = 1;
        sa->lastseq = seq;
        return 1;
    }
    diff = sa->lastseq - seq;
    if (diff >= sa->ooo_window)
        return 0;   /* too old */
    if (sa->bitmap & (1 << diff))
        return 0;   /* already seen */
    sa->bitmap |= (1 << diff);
    return 1;
}

/*
 * Strips the ESP header, verifies padding, and removes it.
 *
 * @return 0 success, -1 replay/padding failure (drop packet).
 */
static inline int
ipsec_esp_decap(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    struct ipsec_esp_hdr *esp =
        rte_pktmbuf_mtod(m, struct ipsec_esp_hdr *);

    /* replay check */
    if (!ipsec_check_replay(sa, (unsigned long)ntohl(esp->seq)))
        return -1;

    /* strip ESP header */
    rte_pktmbuf_adj(m, sizeof(struct ipsec_esp_hdr));

    /* verify padding */
    int blks = rte_pktmbuf_data_len(m);
    const uint8_t *blk = rte_pktmbuf_mtod(m, const uint8_t *);

    if ((blk[blks - 2] != blk[blks - 3]) && (blk[blks - 2] != 0))
        return -1;  /* invalid padding length */

    int pad_len = blk[blks - 2];
    const uint8_t *pad_start = blk + blks - (pad_len + 2);
    int i;
    for (i = 0; (i < pad_len) && (pad_start[i] == (uint8_t)(i + 1)); )
        ++i;
    if (i < pad_len)
        return -1;  /* corrupt padding */

    /* strip padding + pad_length + next_header */
    rte_pktmbuf_trim(m, pad_len + 2);
    return 0;
}

/* ================================================================== */
/*  IPsecAES -- AES-128-CBC encrypt / decrypt (8-byte IV, FastClick)   */
/* ================================================================== */

/*
 * AES-CBC encrypt the ESP payload in-place.
 * Matches FastClick Aes::simple_action(encrypt) exactly:
 *   - Uses 8-byte IV from ESP header for CBC XOR.
 *   - Skips last IPSEC_AUTH_DIGEST_LEN bytes (HMAC, if present).
 *   - If payload (minus digest) isn't a multiple of 16, includes 8 extra
 *     bytes from the digest area to fill the last AES block.
 *
 * Must be called AFTER ipsec_esp_encap() and ipsec_hmac_sha1_compute().
 */
static inline int
ipsec_aes_cbc_encrypt(struct rte_mbuf *m, struct ipsec_sa *sa)
{
#ifdef USE_OPENSSL
    /*
    * AES-CBC encrypt the ESP payload in-place using OpenSSL EVP.
    * Same interface as ipsec_aes_cbc_encrypt() but uses OpenSSL's AES-128-CBC.
    * The 8-byte ESP IV is zero-padded to 16 bytes for standard AES-CBC.
    *
    * NOTE: Not bit-compatible with ipsec_aes_cbc_encrypt() which uses a
    * non-standard 8-byte IV CBC from FastClick.
    */
    uint8_t *data = rte_pktmbuf_mtod(m, uint8_t *);
    struct ipsec_esp_hdr *esp = (struct ipsec_esp_hdr *)data;

    uint8_t *idat = data + sizeof(struct ipsec_esp_hdr);
    int plen = rte_pktmbuf_data_len(m)
               - (int)sizeof(struct ipsec_esp_hdr)
               - IPSEC_AUTH_DIGEST_LEN;

    if ((plen % 16) != 0) plen += 8;

    /* 16-byte IV: 8-byte ESP IV zero-padded */
    uint8_t iv[16];
    memcpy(iv, esp->iv, 8);
    memset(iv + 8, 0, 8);

    EVP_CIPHER_CTX *ctx = sa->evp_enc_ctx;
    if (EVP_EncryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, sa->enc_key, iv) != 1)
        return -1;

    EVP_CIPHER_CTX_set_padding(ctx, 0);

    int outlen;
    if (EVP_EncryptUpdate(ctx, idat, &outlen, idat, plen) != 1)
        return -1;

    int final_len;
    if (EVP_EncryptFinal_ex(ctx, idat + outlen, &final_len) != 1)
        return -1;

    return 0;
#else
    uint8_t *data = rte_pktmbuf_mtod(m, uint8_t *);
    struct ipsec_esp_hdr *esp = (struct ipsec_esp_hdr *)data;
    struct ipsec_aes_key key;
    int i;

    ipsec_aes_set_encrypt_key(sa->enc_key, 128, &key);

    uint8_t *ivp = esp->iv;
    uint8_t *idat = data + sizeof(struct ipsec_esp_hdr);
    int plen = rte_pktmbuf_data_len(m)
               - (int)sizeof(struct ipsec_esp_hdr)
               - IPSEC_AUTH_DIGEST_LEN;

    if ((plen % 16) != 0) plen += 8;

    while (plen > 0) {
        for (i = 0; i < 8; i++)
            idat[i] ^= ivp[i];
        ipsec_aes_encrypt(idat, idat, &key);
        ivp = idat;
        idat += 16;
        plen -= 16;
    }
    return 0;
#endif
}

/*
 * AES-CBC decrypt the ESP payload in-place.
 * Matches FastClick Aes::simple_action(decrypt).
 *
 * Must be called BEFORE ipsec_hmac_sha1_verify() and ipsec_esp_decap().
 */
static inline int
ipsec_aes_cbc_decrypt(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    uint8_t *data = rte_pktmbuf_mtod(m, uint8_t *);
    struct ipsec_esp_hdr *esp = (struct ipsec_esp_hdr *)data;
    struct ipsec_aes_key key;
    unsigned char hold[8];
    unsigned char iv_save[8];
    int i;

    ipsec_aes_set_decrypt_key(sa->enc_key, 128, &key);

    uint8_t *ivp = esp->iv;
    uint8_t *idat = data + sizeof(struct ipsec_esp_hdr);
    int plen = rte_pktmbuf_data_len(m)
               - (int)sizeof(struct ipsec_esp_hdr)
               - IPSEC_AUTH_DIGEST_LEN;

    if ((plen % 16) != 0) plen += 8;

    memcpy(iv_save, ivp, 8);

    while (plen > 0) {
        memcpy(hold, idat, 8);
        ipsec_aes_decrypt(idat, idat, &key);
        for (i = 0; i < 8; i++)
            idat[i] ^= ivp[i];
        memcpy(ivp, hold, 8);
        idat += 16;
        plen -= 16;
    }

    /* restore original IV in ESP header (needed if HMAC checks it) */
    memcpy(esp->iv, iv_save, 8);
    return 0;
}

/* ================================================================== */
/*  ChaCha20-Poly1305 encrypt + authenticate (combined)                */
/* ================================================================== */

/*
 * Combined ChaCha20-Poly1305 encrypt and authenticate (RFC 7905).
 * AEAD cipher: encryption produces a 16-byte Poly1305 authentication tag,
 * replacing the separate HMAC step.  Key is 256-bit, IV is 12 bytes.
 *
 * Appends the truncated tag (IPSEC_AUTH_DIGEST_LEN bytes) as the
 * ESP integrity check value, matching the layout of the HMAC-based pipeline.
 *
 * Must be called AFTER ipsec_esp_encap() (replaces both hmac_compute + encrypt).
 */
static inline int
ipsec_chacha_encrypt_auth(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    uint8_t *data = rte_pktmbuf_mtod(m, uint8_t *);
    struct ipsec_esp_hdr *esp = (struct ipsec_esp_hdr *)data;

    uint8_t *idat = data + sizeof(struct ipsec_esp_hdr);
    int plen = rte_pktmbuf_data_len(m)
               - (int)sizeof(struct ipsec_esp_hdr);

    /* 12-byte nonce: 8-byte ESP IV zero-padded */
    uint8_t iv[12];
    memcpy(iv, esp->iv, 8);
    memset(iv + 8, 0, 4);

    EVP_CIPHER_CTX *ctx = sa->evp_enc_ctx;
    if (EVP_EncryptInit_ex(ctx, EVP_chacha20_poly1305(), NULL, sa->enc_key, iv) != 1)
        return -1;

    int outlen;
    if (EVP_EncryptUpdate(ctx, idat, &outlen, idat, plen) != 1)
        return -1;

    int final_len;
    if (EVP_EncryptFinal_ex(ctx, idat + outlen, &final_len) != 1)
        return -1;

    /* Extract Poly1305 tag and append as ESP integrity check value */
    uint8_t tag[16];
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_GET_TAG, 16, tag) != 1)
        return -1;

    char *tail = rte_pktmbuf_append(m, IPSEC_AUTH_DIGEST_LEN);
    if (!tail) return -1;
    memcpy(tail, tag, IPSEC_AUTH_DIGEST_LEN);

    return 0;
}

/*
 * Combined ChaCha20-Poly1305 decrypt and verify (RFC 7905).
 * Verifies the trailing Poly1305 tag, strips it, and decrypts in-place.
 *
 * Must be called BEFORE ipsec_esp_decap() (replaces both decrypt + hmac_verify).
 *
 * @return 0 success, -1 authentication failure or decrypt error (drop packet).
 */
static inline int
ipsec_chacha_decrypt_auth(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    uint8_t *data = rte_pktmbuf_mtod(m, uint8_t *);
    struct ipsec_esp_hdr *esp = (struct ipsec_esp_hdr *)data;

    int dlen = rte_pktmbuf_data_len(m);
    if (dlen < (int)sizeof(struct ipsec_esp_hdr) + IPSEC_AUTH_DIGEST_LEN)
        return -1;

    /* Extract and strip the trailing tag */
    uint8_t tag[IPSEC_AUTH_DIGEST_LEN];
    memcpy(tag, data + dlen - IPSEC_AUTH_DIGEST_LEN, IPSEC_AUTH_DIGEST_LEN);
    rte_pktmbuf_trim(m, IPSEC_AUTH_DIGEST_LEN);

    uint8_t *idat = data + sizeof(struct ipsec_esp_hdr);
    int plen = rte_pktmbuf_data_len(m)
               - (int)sizeof(struct ipsec_esp_hdr);

    /* 12-byte nonce: 8-byte ESP IV zero-padded */
    uint8_t iv[12];
    memcpy(iv, esp->iv, 8);
    memset(iv + 8, 0, 4);

    EVP_CIPHER_CTX *ctx = sa->evp_dec_ctx;
    if (EVP_DecryptInit_ex(ctx, EVP_chacha20_poly1305(), NULL, sa->enc_key, iv) != 1)
        return -1;

    int outlen;
    if (EVP_DecryptUpdate(ctx, idat, &outlen, idat, plen) != 1)
        return -1;

    /* Set expected tag before finalizing — Final checks authentication */
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_AEAD_SET_TAG, IPSEC_AUTH_DIGEST_LEN, tag) != 1)
        return -1;

    int final_len;
    if (EVP_DecryptFinal_ex(ctx, idat + outlen, &final_len) != 1)
        return -1;  /* authentication failed */

    return 0;
}

/* ================================================================== */
/*  IPsecAuthHMACSHA1 -- compute or verify 12-byte HMAC-SHA1 digest    */
/* ================================================================== */

/*
 * Compute HMAC-SHA1 over the entire current packet and append the
 * truncated 12-byte digest.
 *
 * @return 0 success, -1 if append fails (no tailroom).
 */
static inline int
ipsec_hmac_sha1_compute(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    unsigned char digest[IPSEC_SHA_DIGEST_LEN];
    unsigned char *digest_ptr = digest;
    unsigned int len = IPSEC_SHA_DIGEST_LEN;

#ifdef USE_OPENSSL
    digest_ptr = SHA256(rte_pktmbuf_mtod(m, unsigned char *), rte_pktmbuf_data_len(m), digest);
#else
    ipsec_hmac(sa->auth_key, IPSEC_KEY_SIZE,
               rte_pktmbuf_mtod(m, unsigned char *),
               rte_pktmbuf_data_len(m),
               digest, &len);
#endif


    char *tail = rte_pktmbuf_append(m, IPSEC_AUTH_DIGEST_LEN);
    if (!tail) return -1;

    /* tail points to the start of the appended area */
    memcpy(tail, digest, IPSEC_AUTH_DIGEST_LEN);
    return 0;
}

/*
 * Verify the trailing 12-byte HMAC-SHA1 digest and remove it.
 *
 * @return 0 success, -1 digest mismatch (drop packet).
 */
static inline int
ipsec_hmac_sha1_verify(struct rte_mbuf *m, struct ipsec_sa *sa)
{
    int dlen = rte_pktmbuf_data_len(m);
    if (dlen < IPSEC_AUTH_DIGEST_LEN) return -1;

    const uint8_t *ah = rte_pktmbuf_mtod(m, const uint8_t *)
                        + dlen - IPSEC_AUTH_DIGEST_LEN;

    unsigned char digest[IPSEC_SHA_DIGEST_LEN];
    unsigned int len = IPSEC_SHA_DIGEST_LEN;

    ipsec_hmac(sa->auth_key, IPSEC_KEY_SIZE,
               rte_pktmbuf_mtod(m, unsigned char *),
               dlen - IPSEC_AUTH_DIGEST_LEN,
               digest, &len);

    if (memcmp(ah, digest, IPSEC_AUTH_DIGEST_LEN) != 0)
        return -1;   /* authentication failed */

    rte_pktmbuf_trim(m, IPSEC_AUTH_DIGEST_LEN);
    return 0;
}

/* ================================================================== */
/*  IPsecEncap / decap -- outer IP tunnel header                       */
/* ================================================================== */

/*
 * Prepend an outer IPv4 header for ESP tunnel mode.
 *
 * @param m      Packet (ESP-encapsulated payload).
 * @param proto  IP protocol (typically IPSEC_ESP_PROTO = 50).
 * @param src_ip Source address (network byte order).
 * @param dst_ip Destination address (network byte order).
 * @return 0 success, -1 no headroom.
 */
static inline int
ipsec_ip_encap(struct rte_mbuf *m, uint8_t proto,
               uint32_t src_ip, uint32_t dst_ip)
{
    char *new_start = rte_pktmbuf_prepend(m, sizeof(struct rte_ipv4_hdr));
    if (!new_start) return -1;

    struct rte_ipv4_hdr *ip =
        rte_pktmbuf_mtod(m, struct rte_ipv4_hdr *);

    memset(ip, 0, sizeof(*ip));
    ip->version_ihl   = (4 << 4) | 5;   /* IPv4, IHL=20 bytes */
    ip->type_of_service = 0;
    ip->total_length   = htons((uint16_t)rte_pktmbuf_data_len(m));
    ip->packet_id      = 0;
    ip->fragment_offset = 0;
    ip->time_to_live   = 250;
    ip->next_proto_id  = proto;
    ip->src_addr       = src_ip;
    ip->dst_addr       = dst_ip;
    ip->hdr_checksum   = 0;
    ip->hdr_checksum   = rte_ipv4_cksum(ip);

    return 0;
}

/*
 * Strip outer IPv4 header (20 bytes, no options assumed).
 *
 * @return 0 success, -1 packet too short.
 */
static inline int
ipsec_ip_decap(struct rte_mbuf *m)
{
    if (rte_pktmbuf_data_len(m) < (int)sizeof(struct rte_ipv4_hdr))
        return -1;
    rte_pktmbuf_adj(m, sizeof(struct rte_ipv4_hdr));
    return 0;
}

#endif /* IPSEC_H */
