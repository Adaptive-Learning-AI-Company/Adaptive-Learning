extends Control

const DEFAULT_GRADE_LEVEL := 5
const DEFAULT_LOCATION := "New Hampshire"
const DEFAULT_LEARNING_STYLE := "Visual"
const DEFAULT_ROLE := "Student"

# Main UI
@onready var create_user_btn = $Panel/TopRightContainer/CreateUserButton
@onready var username_input = $Panel/MainContainer/UsernameInput
@onready var manual_check = get_node_or_null("Panel/MainContainer/ManualCheck")
@onready var advanced_btn = get_node_or_null("Panel/MainContainer/AdvancedButton")
@onready var start_button = $Panel/MainContainer/StartButton
@onready var status_label = $Panel/MainContainer/StatusLabel

@onready var advanced_popup = get_node_or_null("AdvancedPopup")
var forgot_pcode_popup: Window = null # Dynamic window for reset
var help_popup: Window = null

func _ready():
	# Dynamic Password Input for Login
	if not has_node("Panel/MainContainer/PasswordInput"):
		var pwd = LineEdit.new()
		pwd.name = "PasswordInput"
		pwd.placeholder_text = "Password"
		pwd.secret = true
		$Panel/MainContainer.add_child(pwd)
		$Panel/MainContainer.move_child(pwd, $Panel/MainContainer/StartButton.get_index())
		
	# Create Access Code Input for Login Form
	if not has_node("Panel/MainContainer/AccessCodeInput"):
		var access = LineEdit.new()
		access.name = "AccessCodeInput"
		access.placeholder_text = "Access Code (Optional)"
		access.secret = true
		$Panel/MainContainer.add_child(access)
	
	# Re-order Elements
	var container = $Panel/MainContainer
	var user_opt = $Panel/MainContainer/UsernameInput
	var pwd_input = $Panel/MainContainer/PasswordInput
	var acc_input = $Panel/MainContainer/AccessCodeInput
	var start_btn = $Panel/MainContainer/StartButton
	
	# Move to predictable indices
	container.move_child(user_opt, 0)
	container.move_child(pwd_input, 1)
	container.move_child(acc_input, 2)
	container.move_child(start_btn, 3)
	
	# Forgot Password Link
	if not has_node("Panel/MainContainer/ForgotLink"):
		var link = LinkButton.new()
		link.name = "ForgotLink"
		link.text = "Forgot Password?"
		link.underline = LinkButton.UNDERLINE_MODE_ALWAYS
		link.modulate = Color(0.5, 0.5, 1.0)
		link.pressed.connect(_on_forgot_password_pressed)
		$Panel/MainContainer.add_child(link)
	if not has_node("Panel/MainContainer/GetHelpLink"):
		var help_link = LinkButton.new()
		help_link.name = "GetHelpLink"
		help_link.text = "Get Help"
		help_link.underline = LinkButton.UNDERLINE_MODE_ALWAYS
		help_link.modulate = Color(0.5, 0.5, 1.0)
		help_link.pressed.connect(_on_get_help_pressed)
		$Panel/MainContainer.add_child(help_link)

	var forgot_link = $Panel/MainContainer.get_node("ForgotLink")
	var get_help_link = $Panel/MainContainer.get_node("GetHelpLink")
	$Panel/MainContainer.move_child(forgot_link, $Panel/MainContainer/StartButton.get_index() + 1)
	$Panel/MainContainer.move_child(get_help_link, forgot_link.get_index() + 1)
	
	create_user_btn.pressed.connect(_on_create_user_pressed)
	start_button.pressed.connect(_on_start_pressed)
	if username_input:
		username_input.text_submitted.connect(func(_text): _on_start_pressed())

	if manual_check:
		manual_check.visible = false
		manual_check.disabled = true
	if advanced_btn:
		advanced_btn.visible = false
		advanced_btn.disabled = true
	if advanced_popup:
		advanced_popup.visible = false

	_restore_preferences()

func _on_create_user_pressed():
	get_tree().change_scene_to_file("res://scenes/Registration.tscn")

func _on_start_pressed():
	var username = username_input.text.strip_edges()
	if username == "":
		status_label.text = "Please enter a username."
		return

	save_preferences(username)
	
	# Verify Password
	var pwd_input = $Panel/MainContainer/PasswordInput
	var password = pwd_input.text.strip_edges()
	
	if password == "":
		status_label.text = "Password required."
		return
		
	status_label.text = "Logging in..."
	start_button.disabled = true
	
	# Login Call
	# Use Global NetworkManager
	var url = NetworkManager.base_url + "/login"
	
	var http = HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(result, code, headers, body):
		start_button.disabled = false
		
		# Handle Login Response
		if code == 200:
			var resp = JSON.parse_string(body.get_string_from_utf8())
			status_label.text = "Success!"
			
			# Store Auth Token
			if resp and resp.has("access_token"):
				NetworkManager.auth_token = resp["access_token"]
				print("Startup: Auth Token Received & Stored.")
			
			# Proceed to select book/init session
			# GameManager.player_username = username # This line is commented out in the original snippet, but should be GameManager.player_username = username
			var gm = get_node("/root/GameManager")
			if gm:
				gm.player_username = username
			
			_redeem_access_code_then_initialize(username)
		else:
			print("Startup: Login failed with code: " + str(code))
			print("Startup: Login response body: " + body.get_string_from_utf8())
			status_label.text = "Login Failed."
			if code == 400:
				var err = JSON.parse_string(body.get_string_from_utf8())
				if err and err.has("detail"):
					status_label.text = str(err["detail"])
	)
	
	var data = {
		"username": username,
		"password": password
	}
	var headers = [
		"Content-Type: application/json",
		"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Accept: application/json, text/plain, */*",
		"Connection: keep-alive"
	]
	
	print("Startup: Attempting to login to: " + url)
	http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(data))
	
func _redeem_access_code_then_initialize(username):
	var acc_input = $Panel/MainContainer/AccessCodeInput
	var access_code = acc_input.text.strip_edges() if acc_input else ""
	if access_code == "":
		_load_profile_then_initialize(username)
		return

	status_label.text = "Redeeming access code..."
	start_button.disabled = true

	var payload = {
		"username": username,
		"code": access_code
	}
	NetworkManager.post_request("/redeem_access_code", payload, func(_code, response):
		if acc_input:
			acc_input.text = ""
		status_label.text = "Access code accepted."
		_load_profile_then_initialize(username)
	, func(code, err):
		start_button.disabled = false
		status_label.text = err if err != "" else "Access code failed."
	)

func _on_get_help_pressed():
	if help_popup == null:
		help_popup = Window.new()
		help_popup.title = "Get Help"
		help_popup.close_requested.connect(func(): help_popup.hide())
		help_popup.size = Vector2(420, 430)
		help_popup.position = Vector2(100, 100)
		add_child(help_popup)

		var scroll = ScrollContainer.new()
		scroll.name = "HelpScroll"
		scroll.set_anchors_preset(Control.PRESET_FULL_RECT)
		scroll.offset_left = 10
		scroll.offset_top = 10
		scroll.offset_right = -10
		scroll.offset_bottom = -10
		help_popup.add_child(scroll)

		var vbox = VBoxContainer.new()
		vbox.name = "VBoxContainer"
		vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		vbox.custom_minimum_size = Vector2(360, 0)
		scroll.add_child(vbox)

		var intro = Label.new()
		intro.text = "Send your question or comment to Adaptive Tutor support."
		intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		vbox.add_child(intro)

		var name_label = Label.new()
		name_label.text = "Name *"
		vbox.add_child(name_label)

		var name_input = LineEdit.new()
		name_input.name = "HelpNameInput"
		name_input.placeholder_text = "Your name"
		vbox.add_child(name_input)

		var email_label = Label.new()
		email_label.text = "Email *"
		vbox.add_child(email_label)

		var email_input = LineEdit.new()
		email_input.name = "HelpEmailInput"
		email_input.placeholder_text = "you@example.com"
		vbox.add_child(email_input)

		var user_label = Label.new()
		user_label.text = "User ID (Optional)"
		vbox.add_child(user_label)

		var user_input = LineEdit.new()
		user_input.name = "HelpUserIdInput"
		user_input.placeholder_text = "Your username"
		vbox.add_child(user_input)

		var message_label = Label.new()
		message_label.text = "Question / Comment *"
		vbox.add_child(message_label)

		var message_input = TextEdit.new()
		message_input.name = "HelpMessageInput"
		message_input.placeholder_text = "How can we help?"
		message_input.custom_minimum_size = Vector2(0, 140)
		message_input.size_flags_vertical = Control.SIZE_EXPAND_FILL
		vbox.add_child(message_input)

		var btn = Button.new()
		btn.name = "HelpSubmitButton"
		btn.text = "Send Help Request"
		btn.pressed.connect(_submit_help_request)
		vbox.add_child(btn)

		var status = Label.new()
		status.name = "Status"
		status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		status.modulate = Color(1, 1, 0)
		vbox.add_child(status)

	var help_user_input = help_popup.get_node("HelpScroll/VBoxContainer/HelpUserIdInput")
	if help_user_input and help_user_input.text.strip_edges() == "" and username_input:
		help_user_input.text = username_input.text.strip_edges()

	var help_status = help_popup.get_node("HelpScroll/VBoxContainer/Status")
	help_status.modulate = Color(1, 1, 0)
	help_status.text = ""
	help_popup.popup_centered()


func _submit_help_request():
	if help_popup == null:
		return

	var name_input = help_popup.get_node("HelpScroll/VBoxContainer/HelpNameInput")
	var email_input = help_popup.get_node("HelpScroll/VBoxContainer/HelpEmailInput")
	var user_input = help_popup.get_node("HelpScroll/VBoxContainer/HelpUserIdInput")
	var message_input = help_popup.get_node("HelpScroll/VBoxContainer/HelpMessageInput")
	var submit_button = help_popup.get_node("HelpScroll/VBoxContainer/HelpSubmitButton")
	var status = help_popup.get_node("HelpScroll/VBoxContainer/Status")

	var name_value = name_input.text.strip_edges()
	var email_value = email_input.text.strip_edges()
	var user_value = user_input.text.strip_edges()
	var message_value = message_input.text.strip_edges()

	if name_value == "" or email_value == "" or message_value == "":
		status.modulate = Color(1, 0.6, 0.6)
		status.text = "Name, email, and question / comment are required."
		return

	status.modulate = Color(1, 1, 0)
	status.text = "Sending..."
	submit_button.disabled = true

	var url = NetworkManager.base_url + "/request-help"
	var http = HTTPRequest.new()
	help_popup.add_child(http)
	http.request_completed.connect(func(_result, code, _headers, body):
		http.queue_free()
		submit_button.disabled = false

		if code == 200:
			status.modulate = Color(0.7, 1.0, 0.7)
			status.text = "Help request sent."
			message_input.text = ""
			return

		status.modulate = Color(1, 0.6, 0.6)
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed and parsed.has("detail"):
			status.text = str(parsed["detail"])
		else:
			status.text = "Unable to send help request."
	)

	var data = {
		"name": name_value,
		"email": email_value,
		"user_id": user_value,
		"message": message_value
	}
	var headers = [
		"Content-Type: application/json",
		"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Accept: application/json, text/plain, */*",
		"Connection: keep-alive"
	]
	http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(data))

func _on_forgot_password_pressed():
	# Create Popup if missing
	if forgot_pcode_popup == null:
		forgot_pcode_popup = Window.new()
		forgot_pcode_popup.title = "Reset Password"
		forgot_pcode_popup.close_requested.connect(func(): forgot_pcode_popup.hide())
		forgot_pcode_popup.size = Vector2(300, 150)
		forgot_pcode_popup.position = Vector2(100, 100) # Simplify
		add_child(forgot_pcode_popup)
		
		var vbox = VBoxContainer.new()
		vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
		vbox.offset_left = 10; vbox.offset_top = 10; vbox.offset_right = -10; vbox.offset_bottom = -10
		forgot_pcode_popup.add_child(vbox)
		
		var lbl = Label.new()
		lbl.text = "Enter Username:"
		vbox.add_child(lbl)
		
		var txt = LineEdit.new()
		txt.placeholder_text = "Username"
		txt.name = "ResetInput"
		vbox.add_child(txt)
		
		var btn = Button.new()
		btn.text = "Send Reset Link"
		btn.pressed.connect(func(): _send_reset_request(txt.text))
		vbox.add_child(btn)
		
		var STATUS = Label.new()
		STATUS.name = "Status"
		STATUS.modulate = Color(1, 1, 0)
		vbox.add_child(STATUS)
		
	forgot_pcode_popup.popup_centered()

func _send_reset_request(username):
	var status = forgot_pcode_popup.get_node("VBoxContainer/Status") if forgot_pcode_popup.has_node("VBoxContainer/Status") else forgot_pcode_popup.get_child(0).get_node("Status") 
	# Actually node path is simpler
	
	if username == "": return
	status.text = "Sending..."
	
	status.text = "Sending..."
	
	var url = NetworkManager.base_url + "/request-password-reset"
	
	var http = HTTPRequest.new()
	forgot_pcode_popup.add_child(http)
	http.request_completed.connect(func(res, code, headers, body):
		http.queue_free()
		# Always success message for security/simplicity
		status.text = "If user exists, email sent!"
	)
	
	var data = {"username": username}
	var headers = [
		"Content-Type: application/json",
		"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Accept: application/json, text/plain, */*",
		"Connection: keep-alive"
	]
	http.request(url, headers, HTTPClient.METHOD_POST, JSON.stringify(data))

func _load_manual_mode_preference() -> bool:
	var config = ConfigFile.new()
	config.load("user://settings.cfg")
	return bool(config.get_value("user", "manual_mode", false))


func _load_saved_grade_preference() -> int:
	var config = ConfigFile.new()
	config.load("user://settings.cfg")
	return int(config.get_value("user", "grade", DEFAULT_GRADE_LEVEL))


func _profile_text_value(profile_data, key: String, fallback: String) -> String:
	if profile_data != null and profile_data.has(key):
		var value = profile_data[key]
		if value != null:
			var normalized = str(value).strip_edges()
			if normalized != "":
				return normalized
	return fallback


func _load_profile_then_initialize(username):
	status_label.text = "Loading profile..."
	NetworkManager.post_request("/get_profile", {"username": username}, func(_code, response):
		_initialize_session(username, response)
	, func(_code, err):
		start_button.disabled = false
		status_label.text = err if err != "" else "Unable to load profile."
	)


func _initialize_session(username, profile_data = null):
	var grade_val = int(profile_data["grade_level"]) if profile_data != null and profile_data.has("grade_level") and profile_data["grade_level"] != null else _load_saved_grade_preference()
	var loc_val = _profile_text_value(profile_data, "location", DEFAULT_LOCATION)
	var style_val = _profile_text_value(profile_data, "learning_style", DEFAULT_LEARNING_STYLE)
	var role_val = _profile_text_value(profile_data, "role", DEFAULT_ROLE)
	var is_manual = _load_manual_mode_preference()

	save_preferences(username, grade_val)
	
	status_label.text = "Initializing Session..."
	start_button.disabled = true
	
	var nm = preload("res://scripts/NetworkManager.gd").new()
	add_child(nm)
	nm.session_ready.connect(_on_session_ready)
	
	# Set global manager state
	var gm = get_node("/root/GameManager")
	if gm:
		gm.player_username = username
		gm.manual_selection_mode = is_manual
		gm.player_grade = grade_val
		gm.player_location = loc_val
		gm.player_style = style_val
		
		# Sync NetworkManager
		NetworkManager.current_username = username
	
	var init_data = {
		"username": username,
		"grade_level": grade_val,
		"location": loc_val,
		"learning_style": style_val,
		"role": role_val,
		"save_profile": false
	}
	
	var init_http = HTTPRequest.new()
	add_child(init_http)
	init_http.request_completed.connect(func(result, code, headers, body):
		if code == 200:
			var json = JSON.parse_string(body.get_string_from_utf8())
			if json and json.has("avatar_id") and gm:
				gm.player_avatar_id = str(json["avatar_id"])
			get_tree().change_scene_to_file("res://scenes/Library.tscn")
		else:
			var error_text = "Error: " + str(code)
			var parsed = JSON.parse_string(body.get_string_from_utf8())
			if parsed and parsed.has("detail"):
				error_text = str(parsed["detail"])
			status_label.text = error_text
			start_button.disabled = false
	)
	
	var body_json = JSON.stringify(init_data)
	var headers = [
		"Content-Type: application/json",
		"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		"Accept: application/json, text/plain, */*",
		"Connection: keep-alive"
	]
	
	# Add Auth Token
	if NetworkManager.auth_token != "":
		headers.append("Authorization: Bearer " + NetworkManager.auth_token)
		
	init_http.request(NetworkManager.base_url + "/init_session", headers, HTTPClient.METHOD_POST, body_json)

func _on_session_ready(data):
	pass

func _restore_preferences():
	var config = ConfigFile.new()
	var err = config.load("user://settings.cfg")
	if err == OK:
		var saved_name = config.get_value("user", "username", "")
		if username_input:
			username_input.text = str(saved_name)

func save_preferences(name, grade = null):
	var config = ConfigFile.new()
	config.load("user://settings.cfg")
	config.set_value("user", "username", name)
	if grade != null:
		config.set_value("user", "grade", grade)
	config.save("user://settings.cfg")
