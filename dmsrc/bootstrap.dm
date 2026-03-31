/// Gets SS13Lib or creates it if this is the first time we're accessing it
/world/proc/get_or_init_ss13lib()
	var/static/datum/ss13lib/lib
	if(!lib)
		lib = new

	return lib

#ifndef SS13LIB_INIT_HANDLER
/// If the codebase doesn't start us up, start us up ourselves.
/world/proc/___ss13lib_init()
	var/static/_ = SS13LIB
#endif

/datum/ss13lib/New()
	perform_handshake()

#ifndef SS13LIB_HEARTBEAT_HANDLER
/// Only perform any work here if we're set up to do so.
/// Servers can override the heartbeat loop if they use a custom
/// MC setup and don't want us running our own loop.
	heartbeat_loop()

/datum/ss13lib/proc/heartbeat_loop()
	while(TRUE)
		perform_heartbeat()
		sleep(300)
#endif
