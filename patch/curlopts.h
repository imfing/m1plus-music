/* libcurl 7.73 option and info numbers (curl/curl.h), the ones the payload uses: demo imports the easy interface, there is no header on the build host's side of the cross compile.
 * Used by patch/pcnet.c and patch/subsonic.c; test/pod/pcnet.py mocks these option and info numbers.
 *
 * Copyright (c) 2026 Xin. MIT licence (see LICENSE).
 */
#pragma once

#define CURLOPT_WRITEDATA 10001
#define CURLOPT_HEADERDATA 10029
#define CURLOPT_URL 10002
#define CURLOPT_RANGE 10007
#define CURLOPT_ERRORBUFFER 10010
#define CURLOPT_WRITEFUNCTION 20011
#define CURLOPT_HEADERFUNCTION 20079
#define CURLOPT_TIMEOUT 13
#define CURLOPT_USERAGENT 10018
#define CURLOPT_LOW_SPEED_LIMIT 19
#define CURLOPT_LOW_SPEED_TIME 20
#define CURLOPT_VERBOSE 41
#define CURLOPT_TIMECONDITION \
    33 /* CURL_TIMECOND_*: with the value below, a 304 and no body when the document is not newer */
#define CURLOPT_TIMEVALUE 34 /* seconds since 1970 */
#define CURL_TIMECOND_IFMODSINCE 1
#define CURLOPT_FILETIME 69 /* long 1: the document's Last-Modified is kept for CURLINFO_FILETIME */
#define CURLOPT_NOPROGRESS 43
#define CURLOPT_XFERINFODATA 10057 /* the data of the callback below (CURLOPT_PROGRESSDATA) */
#define CURLOPT_XFERINFOFUNCTION \
    20219 /* curl_xferinfo_callback(clientp, dltotal, dlnow, ultotal, ulnow), 64-bit counts; non-zero aborts */
#define CURLOPT_FOLLOWLOCATION 52
#define CURLOPT_CAINFO 10065
#define CURLOPT_MAXREDIRS 68
#define CURLOPT_CONNECTTIMEOUT 78
#define CURLOPT_DEBUGFUNCTION 20094
#define CURLOPT_DEBUGDATA 10095
#define CURLOPT_NOSIGNAL 99
#define CURLOPT_ACCEPT_ENCODING 10102
#define CURLOPT_FAILONERROR \
    45 /* an HTTP code of 400 or more fails the request (CURLE_HTTP_RETURNED_ERROR, 22) instead of handing over the error page */
#define CURLOPT_NOBODY 44 /* long 1: a header-only request (HEAD) */
#define CURLPROTO_HTTP 1
#define CURLPROTO_HTTPS 2
#define CURLOPT_PROTOCOLS 181
#define CURLOPT_REDIR_PROTOCOLS 182
#define CURLPROTO_HTTP_HTTPS 3 /* CURLPROTO_HTTP | CURLPROTO_HTTPS: a redirect to file:// or ftp:// is refused */
#define CURLINFO_EFFECTIVE_URL 0x100001
#define CURLINFO_RESPONSE_CODE 0x200002
/* CURLINFO_CONTENT_TYPE is CURLINFO_STRING + 18: the Content-Type header, a char * owned by libcurl (NULL when none). */
#define CURLINFO_CONTENT_TYPE 0x100012
#define CURLINFO_SSL_VERIFYRESULT 0x20000d
#define CURLINFO_FILETIME \
    0x20000e /* CURLINFO_LONG + 14: the server's Last-Modified, seconds since 1970, a long; -1 when it sent none */
#define CURLINFO_REDIRECT_COUNT 0x200014
#define CURLINFO_REDIRECT_URL \
    0x10001f /* CURLINFO_STRING + 31: the Location of a redirect that was not followed, absolute; owned by the handle */
#define CURLINFO_CONTENT_LENGTH_DOWNLOAD_T \
    0x60000f /* CURLINFO_OFF_T + 15: the length the server announced, -1 when it gave none */
#define CURLINFO_PRIMARY_IP 0x100020
#define CURLINFO_SIZE_DOWNLOAD_T 0x600008
#define CURLINFO_TOTAL_TIME_T 0x600032
#define CURLINFO_NAMELOOKUP_TIME_T 0x600033
#define CURLINFO_CONNECT_TIME_T 0x600034
#define CURLINFO_STARTTRANSFER_TIME_T 0x600036
#define CURLINFO_APPCONNECT_TIME_T 0x600038
#define CURL_GLOBAL_ALL 3
#define CURLINFO_TEXT 0
#define CURLINFO_HEADER_IN 1
/* curl_easy_perform results the refresh tells apart */
#define CURLE_COULDNT_RESOLVE_HOST 6
#define CURLE_PARTIAL_FILE 18
#define CURLE_HTTP_RETURNED_ERROR 22
#define CURLE_WRITE_ERROR 23
#define CURLE_RANGE_ERROR 33
#define CURLE_ABORTED_BY_CALLBACK 42
#define CURLE_OPERATION_TIMEDOUT 28
#define CURLE_SSL_CONNECT_ERROR 35
#define CURLE_PEER_FAILED_VERIFICATION 51
#define CURLE_SSL_CERTPROBLEM 58
#define CURLE_SSL_CIPHER 59
#define CURLE_SSL_CACERT 60
#define CURLE_SSL_CACERT_BADFILE 77
#define CURLE_SSL_ISSUER_ERROR 83
