extends Control

# Main UI
@onready var create_user_btn = $Panel/TopRightContainer/CreateUserButton
@onready var username_input = $Panel/MainContainer/UsernameInput
@onready var manual_check = $Panel/MainContainer/ManualCheck
@onready var advanced_btn = $Panel/MainContainer/AdvancedButton
@onready var start_button = $Panel/MainContainer/StartButton
@onready var status_label = $Panel/MainContainer/StatusLabel

# Advanced UI
@onready var advanced_popup = $AdvancedPopup
@onready var grade_option = $AdvancedPopup/VBox/GradeOption
var role_option = null # Initialized in _ready (Dynamic)
@onready var location_option = $AdvancedPopup/VBox/LocationOption
@onready var style_option = $AdvancedPopup/VBox/StyleOption
@onready var save_check = $AdvancedPopup/VBox/SaveProfileCheck
@onready var close_advanced_btn = $AdvancedPopup/VBox/CloseAdvanced
var forgot_pcode_popup: Window = null # Dynamic window for reset
var manual_help_popup: PanelContainer = null

const MANUAL_DEFAULTS_HELP := "When enabled, Adaptive Tutor stops auto-adjusting the lesson from your saved profile. Use Advanced Settings to force a specific grade level, location, learning style, or role for this session."

func _ready():
	# Setup Dropdowns (Advanced)
	grade_option.clear()
	grade_option.add_item("Kindergarten", 0)
	for i in range(1, 13):
		grade_option.add_item("Grade " + str(i), i)
	grade_option.add_item("Undergraduate", 13)
	grade_option.add_item("Masters", 15)
	grade_option.select(5)
	
	location_option.clear()
	var locs = ["New Hampshire", "California", "Texas", "New York", "International"]
	for l in locs:
		location_option.add_item(l)
	
	style_option.clear()
	var styles = ["Visual", "Text-Based", "Auditory", "Kinesthetic"]
	for s in styles:
		style_option.add_item(s)

	# Role Setup
	if not has_node("AdvancedPopup/VBox/RoleOption"):
		role_option = OptionButton.new()
		role_option.name = "RoleOption"
		$AdvancedPopup/VBox.add_child(role_option)
		$AdvancedPopup/VBox.move_child(role_option, 1)
	else:
		role_option = $AdvancedPopup/VBox/RoleOption
		
	role_option.clear()
	role_option.add_item("Student", 0)
	role_option.add_item("Teacher", 1)
	role_option.selected = 0
	
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
	var manual = $Panel/MainContainer/ManualCheck
	var adv_btn = $Panel/MainContainer/AdvancedButton
	
	# Move to predictable indices
	container.move_child(user_opt, 0)
	container.move_child(pwd_input, 1)
	container.move_child(acc_input, 2)
	container.move_child(manual, 3)
	container.move_child(adv_btn, 4)
	container.move_child(start_btn, 5)
	
	# Forgot Password Link
	if not has_node("Panel/MainContainer/ForgotLink"):
		var link = LinkButton.new()
		link.name = "ForgotLink"
		link.text = "Forgot Password?"
		link.underline = LinkButton.UNDERLINE_MODE_ALWAYS
		link.modulate = Color(0.5, 0.5, 1.0)
		link.pressed.connect(_on_forgot_password_pressed)
		$Panel/MainContainer.add_child(link)
		$Panel/MainContainer.move_child(link, $Panel/MainContainer/StartButton.get_index() + 1)
	
	create_user_btn.pressed.connect(_on_create_user_pressed)
	advanced_btn.pressed.connect(_on_advanced_pressed)
	close_advanced_btn.pressed.connect(_on_close_advanced_pressed)
	start_button.pressed.connect(_on_start_pressed)
	if username_input:
		username_input.text_submitted.connect(func(_text): _on_start_pressed())

	_setup_manual_help_popup()
	_restore_preferences()

func _on_create_user_pressed():
	get_tree().change_scene_to_file("res://scenes/Registration.tscn")

func _on_advanced_pressed():
	advanced_popup.visible = true

func _on_close_advanced_pressed():
	advanced_popup.visible = false

func _on_start_pressed():
	var username = username_input.text.strip_edges()
	if username == "":
		status_label.text = "Please enter a username."
		return

	save_preferences(username, grade_option.get_selected_id())
	
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

	# Gather settings from Advanced (even if hidden, they hold values)
	
func _redeem_access_code_then_initialize(username):
	var acc_input = $Panel/MainContainer/AccessCodeInput
	var access_code = acc_input.text.strip_edges() if acc_input else ""
	if access_code == "":
		_initialize_session(username)
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
		_initialize_session(username)
	, func(code, err):
		start_button.disabled = false
		status_label.text = err if err != "" else "Access code failed."
	)

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

func _initialize_session(username):
	var grade_val = grade_option.get_selected_id()
	var loc_val = location_option.get_item_text(location_option.selected)
	var style_val = style_option.get_item_text(style_option.selected)

	var role_val = "Student"
	if role_option and role_option.selected == 1:
		role_val = "Teacher"
		
	var do_save = save_check.button_pressed
	var is_manual = manual_check.button_pressed
	
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
		
		# Sync NetworkManager
		NetworkManager.current_username = username
	
	var init_data = {
		"username": username,
		"grade_level": grade_val,
		"location": loc_val,
		"learning_style": style_val,

		"role": role_val,
		"save_profile": do_save
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
		
		# Load advanced settings?
		var s_grade = config.get_value("user", "grade", 10)
		# Select grade
		for i in range(grade_option.item_count):
			if grade_option.get_item_id(i) == s_grade:
				grade_option.selected = i
				break

func save_preferences(name, grade):
	var config = ConfigFile.new()
	config.set_value("user", "username", name)
	config.set_value("user", "grade", grade)
	config.save("user://settings.cfg")


func _setup_manual_help_popup():
	if manual_check == null:
		return

	manual_check.tooltip_text = ""
	manual_check.mouse_entered.connect(_show_manual_help)
	manual_check.mouse_exited.connect(_hide_manual_help)
	manual_check.focus_entered.connect(func(): _show_manual_help(false))
	manual_check.focus_exited.connect(func(): _hide_manual_help())
	manual_check.gui_input.connect(_on_manual_check_gui_input)

	manual_help_popup = PanelContainer.new()
	manual_help_popup.visible = false
	manual_help_popup.z_index = 50
	manual_help_popup.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var panel_style = StyleBoxFlat.new()
	panel_style.bg_color = Color(0.08, 0.1, 0.14, 0.96)
	panel_style.border_color = Color(0.58, 0.86, 1.0, 0.95)
	panel_style.border_width_left = 2
	panel_style.border_width_top = 2
	panel_style.border_width_right = 2
	panel_style.border_width_bottom = 2
	panel_style.corner_radius_top_left = 12
	panel_style.corner_radius_top_right = 12
	panel_style.corner_radius_bottom_right = 12
	panel_style.corner_radius_bottom_left = 12
	manual_help_popup.add_theme_stylebox_override("panel", panel_style)
	manual_help_popup.custom_minimum_size = Vector2(420, 110)
	add_child(manual_help_popup)

	var help_margin = MarginContainer.new()
	help_margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	help_margin.add_theme_constant_override("margin_left", 14)
	help_margin.add_theme_constant_override("margin_top", 12)
	help_margin.add_theme_constant_override("margin_right", 14)
	help_margin.add_theme_constant_override("margin_bottom", 12)
	manual_help_popup.add_child(help_margin)

	var help_label = Label.new()
	help_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	help_label.text = MANUAL_DEFAULTS_HELP
	help_label.custom_minimum_size = Vector2(392, 0)
	help_margin.add_child(help_label)


func _show_manual_help(_unused = null):
	if manual_help_popup == null or manual_check == null:
		return

	var checkbox_rect = manual_check.get_global_rect()
	var viewport_rect = get_viewport_rect()
	var popup_size = manual_help_popup.custom_minimum_size
	var desired_position = Vector2(
		checkbox_rect.position.x,
		checkbox_rect.position.y + checkbox_rect.size.y + 10.0
	)
	desired_position.x = clamp(desired_position.x, 16.0, max(16.0, viewport_rect.size.x - popup_size.x - 16.0))
	desired_position.y = clamp(desired_position.y, 16.0, max(16.0, viewport_rect.size.y - popup_size.y - 16.0))
	manual_help_popup.position = desired_position
	manual_help_popup.show()

func _hide_manual_help():
	if manual_help_popup:
		manual_help_popup.hide()


func _on_manual_check_gui_input(event):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			_show_manual_help()
		else:
			_hide_manual_help()
	elif event is InputEventScreenTouch:
		if event.pressed:
			_show_manual_help()
		else:
			_hide_manual_help()
