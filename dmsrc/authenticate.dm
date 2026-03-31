/// Performs authentication for a fresh client against the SS13Hub authentication API
/// Requires us to know our server id first, as this must be sent during every authentication request.
/// We also store the details for the clients launcher_port/key, as we can use these to retrieve thier
/// authticket in the event of a DreamSeeker reconnection
/datum/ss13lib/proc/handle_client(client/new_client, connection_params)
	var/params_list = params2list(connection_params)
	var/auth_ticket = topic_params["auth_ticket"]

	var/launcher_port = topic_params["launcher_port"]
	var/launcher_key = topic_params["launcher_key"]

	var/static/connection_to_launcher = list()
	if(launcher_port && launcher_key)
		connection_to_launcher["[new_client.address]+[new_client.computer_id]"] = list(
			"port" = launcher_port,
			"key" = launcher_key
		)

	if(auth_ticket)
		var/datum/ss13lib_auth_response/response = check_auth_ticket(auth_ticket)

		if(response)
			new_client.ckey = response.ckey_to_use
			return FALSE
		else
			SS13LIB_LOG("Failed to authenticate user via SS13Hub.")
			// TODO: handling here

	var/stored_launcher_details = connection_to_launcher["[new_client.address]+[new_client.computer_id]"]
	if(stored_launcher_details)
		var/mob/ss13lib_holder_mob/mob = new(null, stored_launcher_details)
		return mob

	// TODO: handle where authentication has failed but a user is still a guest
	// maybe a hook to see if they should be disconnected?
	// like if guest_ban is enabled

	return FALSE

/datum/ss13lib_auth_response
	var/ckey_to_use
	var/username

/datum/ss13lib/proc/check_auth_ticket(auth_ticket) as /datum/ss13lib_auth_response
	var/datum/ss13lib_http_response/response = perform_http_request(
		SS13LIB_HTTP_GET,
		"[SS13LIB_HUB_SERVER]/authenticate",
		list(
			"auth_ticket" = auth_ticket,
			"server_id" = src.server_id
		)
	)

	if(!response || response.errored)
		SS13LIB_LOG("Failed to communicate with authentication server.")
		return FALSE

	var/decoded

	try
		decoded = json_decode(response.body)
	catch(exception/decode_error)
		SS13LIB_LOG("Failed to decode JSON response from server: [decode_error.name]")
		return FALSE

	if(!decoded || !length(decoded))
		SS13LIB_LOG("Failed to parse JSON response from server.")
		return FALSE

	if(!decoded["ckey_to_use"] || !decoded["username"])
		SS13LIB_LOG("Server responded with an invalid result.")
		return FALSE

	var/datum/ss13lib_auth_response/auth = new
	auth.ckey_to_use = decoded["ckey_to_use"]
	auth.username = decoded["username"]

	return auth

/mob/ss13lib_holder_mob
	var/stored_launcher_details

/mob/ss13lib_holder_mob/New(loc, stored_launcher_details)
	src.stored_launcher_details = stored_launcher_details

/mob/ss13lib_holder_mob/Login()
	var/static/basehtml = {"
<!DOCTYPE html>
<html>

<head>
	<script>
		const port = %LAUNCHER_PORT%;
		const key = %LAUNCHER_KEY%;

		const mob_reference = %MOB_REFERENCE%;

		window.contact = (endpoint, params) => {
			const url = params ? `http://localhost:${port}/${endpoint}?${params}` : `http://localhost:${port}/${endpoint}`;
			return fetch(url, {
				'Launcher-Key': key,
			}).then((response) => {
				const contentType = response.headers.get('content-type');
				if (contentType && contentType.includes('application/json')) {
					return response.json().then((object) => {
						location.href = `byond://?src=%OBJ_REFERENCE%&command=${endpoint}&body=${encodeURIComponent(JSON.stringify(object))}`
						return object;
					});
				}
			});
		}
	</script>
</head>

<body>
	<script>
		window.contact("auth");
	</script>
</body>

</html>
	"}

	var/html = replacetext(basehtml, "%LAUNCHER_PORT%", stored_launcher_details["port"])
	html = replacetext(basehtml, "%LAUNCHER_KEY", "\"[stored_launcher_details["key"]]\"")
	html = replacetext(basehtml, "%MOB_REFERENCE", "\"\ref[src]\"")

	src << browse(html_to_send, "window=launcher-browser,size=1x1,titlebar=0,can_resize=0")
	winset(controlling, "launcher-browser", "is-visible=false")

/mob/ss13lib_holder_mob/Topic(href, href_list)
	if(usr != src)
		return

	var/command = href_list["command"]
	var/body = href_list["body"]

	if(command != "auth" || !body)
		return

	var/returned

	try
		returned = json_decode(body)
	catch
		SS13LIB_LOG("Failed to decode JSON in Topic response from user.")

	if(!returned)
		return

	var/auth_ticket = returned["auth_ticket"]
	if(!auth_ticket)
		SS13LIB_LOG("Invalid response in Topic response from user.")
		return

	var/client/authenticating_client = client
	client.mob = null
	client.New(list2params(
		list("auth_ticket" = auth_ticket)
	))
	return
