extends Control

@onready var form_container = $Panel/ScrollContainer/VBoxContainer
@onready var username_input = $Panel/ScrollContainer/VBoxContainer/UsernameInput
@onready var sex_option = $Panel/ScrollContainer/VBoxContainer/SexOption
@onready var interests_input = $Panel/ScrollContainer/VBoxContainer/InterestsInput
@onready var grade_option = $Panel/ScrollContainer/VBoxContainer/GradeOption
@onready var location_option = $Panel/ScrollContainer/VBoxContainer/LocationOption
@onready var style_option = $Panel/ScrollContainer/VBoxContainer/StyleOption
@onready var role_option = $Panel/ScrollContainer/VBoxContainer/RoleOption
@onready var status_label = $Panel/ScrollContainer/VBoxContainer/StatusLabel
@onready var create_button = $Panel/ScrollContainer/VBoxContainer/CreateButton
@onready var back_button = $Panel/ScrollContainer/VBoxContainer/BackButton

var email_input: LineEdit
var password_input: LineEdit
var avatar_option: OptionButton
var openai_key_input: LineEdit


func _ready():
	_setup_dropdowns()
	_setup_dynamic_fields()

	create_button.pressed.connect(_on_create_pressed)
	back_button.pressed.connect(_on_back_pressed)


func _on_back_pressed():
	get_tree().change_scene_to_file("res://scenes/Startup.tscn")


func _on_create_pressed():
	var username = username_input.text.strip_edges()
	if username == "":
		status_label.text = "Username required."
		return

	var email = email_input.text.strip_edges()
	if email == "":
		status_label.text = "Email required for password resets."
		return

	var password = password_input.text.strip_edges()
	if password.length() < 8:
		status_label.text = "Password must be at least 8 characters."
		return

	var sex_idx = sex_option.selected
	if sex_idx == 0:
		status_label.text = "Please select sex."
		return
	var sex_val = sex_option.get_item_text(sex_idx)

	var role_val = "Student"
	if role_option and role_option.selected == 1:
		role_val = "Teacher"

	var year = $Panel/ScrollContainer/VBoxContainer/Birthday/HBoxContainer/Year.value
	var month = $Panel/ScrollContainer/VBoxContainer/Birthday/HBoxContainer/Month.value
	var day = $Panel/ScrollContainer/VBoxContainer/Birthday/HBoxContainer/Day.value
	var birthday_val = "%04d-%02d-%02d" % [year, month, day]

	var data = {
		"username": username,
		"password": password,
		"email": email,
		"grade_level": grade_option.get_selected_id(),
		"location": location_option.get_item_text(location_option.selected),
		"learning_style": style_option.get_item_text(style_option.selected),
		"sex": sex_val,
		"role": role_val,
		"birthday": birthday_val,
		"interests": interests_input.text.strip_edges(),
		"avatar_id": _selected_avatar_id(),
		"openai_api_key": openai_key_input.text.strip_edges(),
		"save_profile": true
	}

	status_label.text = "Creating profile..."
	create_button.disabled = true

	var http = HTTPRequest.new()
	add_child(http)
	http.request_completed.connect(func(result, code, headers, body):
		http.queue_free()
		if code == 200:
			status_label.text = "Profile created."
			get_tree().change_scene_to_file("res://scenes/Startup.tscn")
			return

		var error_text = "Error: " + str(code)
		var parsed = JSON.parse_string(body.get_string_from_utf8())
		if parsed and parsed.has("detail"):
			error_text = str(parsed["detail"])
		status_label.text = error_text
		create_button.disabled = false
	)

	var headers = ["Content-Type: application/json"]
	http.request(NetworkManager.base_url + "/register", headers, HTTPClient.METHOD_POST, JSON.stringify(data))


func _setup_dropdowns():
	sex_option.clear()
	sex_option.add_item("Select Sex...", 0)
	sex_option.set_item_disabled(0, true)
	sex_option.add_item("Male", 1)
	sex_option.add_item("Female", 2)
	sex_option.add_item("Other", 3)
	sex_option.selected = 0

	role_option.clear()
	role_option.add_item("Student", 0)
	role_option.add_item("Teacher", 1)
	role_option.selected = 0

	grade_option.clear()
	for i in range(1, 13):
		grade_option.add_item("Grade " + str(i), i)
	grade_option.select(5)

	location_option.clear()
	for location_name in ["New Hampshire", "California", "Texas", "New York", "International"]:
		location_option.add_item(location_name)

	style_option.clear()
	for learning_style in ["Visual", "Text-Based", "Auditory", "Kinesthetic"]:
		style_option.add_item(learning_style)


func _setup_dynamic_fields():
	email_input = _ensure_line_edit(
		"EmailInput",
		"LabelEmail",
		"Email for password resets:",
		"Parent or teacher email",
		false,
		3
	)

	password_input = _ensure_line_edit(
		"PasswordInput",
		"LabelPassword",
		"Password:",
		"Create a password",
		true,
		5
	)

	avatar_option = _ensure_avatar_option(12)
	openai_key_input = _ensure_line_edit(
		"OpenAIKeyInput",
		"LabelOpenAIKey",
		"OpenAI API Key (optional):",
		"sk-... personal key",
		true,
		20
	)


func _ensure_line_edit(node_name: String, label_name: String, label_text: String, placeholder: String, is_secret: bool, insert_index: int) -> LineEdit:
	var label_node = form_container.get_node_or_null(label_name)
	if label_node == null:
		label_node = Label.new()
		label_node.name = label_name
		label_node.text = label_text
		form_container.add_child(label_node)
	form_container.move_child(label_node, insert_index)

	var input_node = form_container.get_node_or_null(node_name)
	if input_node == null:
		input_node = LineEdit.new()
		input_node.name = node_name
		form_container.add_child(input_node)
	input_node.placeholder_text = placeholder
	input_node.secret = is_secret
	input_node.clear_button_enabled = true
	form_container.move_child(input_node, insert_index + 1)
	return input_node


func _ensure_avatar_option(insert_index: int) -> OptionButton:
	var label_node = form_container.get_node_or_null("LabelAvatar")
	if label_node == null:
		label_node = Label.new()
		label_node.name = "LabelAvatar"
		label_node.text = "Avatar:"
		form_container.add_child(label_node)
	form_container.move_child(label_node, insert_index)

	var option_node = form_container.get_node_or_null("AvatarOption")
	if option_node == null:
		option_node = OptionButton.new()
		option_node.name = "AvatarOption"
		form_container.add_child(option_node)
	option_node.clear()
	option_node.add_item("Girl Avatar", 0)
	option_node.add_item("Boy Avatar", 1)
	option_node.selected = 0
	form_container.move_child(option_node, insert_index + 1)
	return option_node


func _selected_avatar_id() -> String:
	if avatar_option and avatar_option.selected == 1:
		return "schoolboy"
	return "schoolgirl"
