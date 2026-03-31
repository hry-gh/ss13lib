#ifndef SS13LIB_HUB_SERVER
#define SS13LIB_HUB_SERVER "https://hub.spacestation13.com"
#endif

#ifndef SS13LIB_SERVER_PORT
#define SS13LIB_SERVER_PORT world.port
#endif

#ifdef RUST_G
#define SS13LIB_HTTP_GET RUSTG_HTTP_METHOD_GET
#define SS13LIB_HTTP_POST RUSTG_HTTP_METHOD_POST
#else
#define SS13LIB_HTTP_GET "GET"
#define SS13LIB_HTTP_POST "POST"
#endif

#ifndef SS13LIB_LOG
#define SS13LIB_LOG(x)
#endif
