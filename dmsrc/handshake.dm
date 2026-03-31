/datum/ss13lib
	/// The ID for this server. This must be sent in all authentication requests
	var/server_id

/// Before starting to fire off heartbeats, perform a handshake to get our server ID.
/datum/ss13lib/proc/perform_handshake()
	SS13LIB_LOG("Beginning handshake with hub server.")

	var/datum/ss13lib_http_response/response = perform_http_request(
		"[SS13LIB_HUB_SERVER]/handshake?port=[SS13LIB_SERVER_PORT]",
		SS13LIB_HTTP_GET
	)

	if(response.errored)
		SS13LIB_LOG("Error occured in handshake, client authentication via SS13Auth will fail.")
		return FALSE

	var/body

	try
		body = json_decode(response.body)
	catch
		SS13LIB_LOG("Could not decode handshake response, client authentication via SS13Auth will fail.")
		return FALSE

	if(!body || !length(body))
		SS13LIB_LOG("No valid JSON response during handshake, client authentication via SS13Auth will fail.")
		return FALSE

	var/server_id = body["server_id"]
	if(!server_id)
		SS13LIB_LOG("Response from hub server was invalid, client authentication via SS13Auth will fail.")
		return FALSE

	src.server_id = server_id
	SS13LIB_LOG("Handshake with hub server completed successfully.")

