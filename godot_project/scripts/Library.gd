extends Node3D

const SUBJECT_ORDER := ["Math", "Science", "History", "English"]
const SUBJECT_API_KEY := {
	"Math": "Math",
	"Science": "Science",
	"History": "Social_Studies",
	"English": "ELA"
}
const SUBJECT_THEME := {
	"Math": {
		"base": Color(0.13, 0.47, 0.78),
		"accent": Color(0.52, 0.83, 1.0),
		"code": "MTH"
	},
	"Science": {
		"base": Color(0.16, 0.53, 0.37),
		"accent": Color(0.57, 0.95, 0.74),
		"code": "SCI"
	},
	"History": {
		"base": Color(0.68, 0.37, 0.19),
		"accent": Color(1.0, 0.77, 0.42),
		"code": "HIS"
	},
	"English": {
		"base": Color(0.49, 0.27, 0.67),
		"accent": Color(0.82, 0.64, 1.0),
		"code": "ENG"
	}
}
const BOOKS_PER_SUBJECT := 10
const BOOK_COLUMNS := 5
const BOOK_SPACING_X := 0.98
const BOOK_BASE_Y := 1.08
const BOOK_ROW_GAP := 1.22
const SHELF_LAYOUT := {
	"Math": Vector3(-5.0, 0.0, 4.2),
	"Science": Vector3(5.0, 0.0, 4.2),
	"History": Vector3(-5.0, 0.0, 11.2),
	"English": Vector3(5.0, 0.0, 11.2)
}
const SHELF_FOCUS_POINT := Vector3(0.0, 0.0, 0.6)
const BEACON_TEXT := {
	"Math": "Pattern Lab",
	"Science": "Discovery Wing",
	"History": "Story Archive",
	"English": "Language Studio"
}

var network_manager
var player

var hud_xp: Label
var hud_level: Label
var hud_grade: Label
var grade_gauge: TextureProgressBar
var ui_canvas: CanvasLayer

var grade_percent_label: Label
var sidebar_panel: Panel
var joystick_left: VirtualJoystick
var joystick_right: VirtualJoystick
var hud_role: Label
var profile_overlay: ColorRect
var profile_window: PanelContainer
var profile_scroll: ScrollContainer
var admin_overlay: ColorRect
var admin_window: PanelContainer
var admin_scroll: ScrollContainer
var teacher_overlay: ColorRect
var teacher_window: PanelContainer
var teacher_scroll: ScrollContainer
var sidebar_access_label: Label
var profile_email_input: LineEdit
var profile_avatar_option: OptionButton
var profile_openai_key_input: LineEdit
var profile_clear_key_check: CheckBox
var profile_key_hint_label: Label
var profile_status_label: Label
var teacher_request_username_input: LineEdit
var teacher_request_note_input: LineEdit
var teacher_request_button: Button
var teacher_links_list: ItemList
var teacher_revoke_button: Button
var teacher_link_status_label: Label
var billing_plan_label: Label
var billing_usage_label: Label
var billing_payment_label: Label
var billing_access_label: Label
var billing_access_code_input: LineEdit
var billing_access_code_button: Button
var billing_hosted_button: Button
var billing_byok_button: Button
var billing_manage_button: Button
var admin_access_button: Button
var teacher_dashboard_button: Button
var admin_status_label: Label
var admin_revoke_reason_input: LineEdit
var admin_code_assigned_input: LineEdit
var admin_code_plan_option: OptionButton
var admin_code_days_input: LineEdit
var admin_code_max_redemptions_input: LineEdit
var admin_code_custom_input: LineEdit
var admin_code_notes_input: LineEdit
var admin_last_created_code_input: LineEdit
var admin_grant_username_input: LineEdit
var admin_grant_plan_option: OptionButton
var admin_grant_days_input: LineEdit
var admin_grant_notes_input: LineEdit
var admin_filter_username_input: LineEdit
var admin_code_list: ItemList
var admin_grant_list: ItemList
var admin_code_entries := []
var admin_grant_entries := []
var teacher_link_entries := []
var teacher_pending_entries := []
var teacher_student_entries := []
var teacher_pending_list: ItemList
var teacher_student_list: ItemList
var teacher_drop_button: Button
var teacher_detail_label: RichTextLabel
var teacher_status_label: Label

var shelf_progress_bars := {}
var shelf_progress_labels := {}
var subject_selector_progress_labels := {}
var sidebar_subject_progress_bars := {}
var book_nodes := []
var animated_hall_nodes := []

var hover_target = null
var focus_ring: MeshInstance3D
var focus_ring_material: StandardMaterial3D

var selection_canvas: CanvasLayer
var selection_panel: PanelContainer
var selection_panel_style: StyleBoxFlat
var selection_subject_label: Label
var selection_topic_label: Label
var selection_hint_label: Label
var selection_mode_label: Label
var selection_clock := 0.0
var profile_grade_level := 1
var profile_role := "Student"
var profile_is_admin := false
var tutoring_access_loaded := false
var tutoring_access_allowed := false
var tutoring_access_reason := "Checking tutoring access..."


func _extract_explicit_admin_flag(stats: Dictionary) -> bool:
	if not stats.has("is_admin"):
		return false
	return typeof(stats["is_admin"]) == TYPE_BOOL and stats["is_admin"] == true

func _ready():
	randomize()
	# Init Network Manager
	network_manager = preload("res://scripts/NetworkManager.gd").new()
	add_child(network_manager)

	# Sync Username
	var gm = get_node("/root/GameManager")
	if gm:
		network_manager.current_username = gm.player_username
		profile_grade_level = clamp(int(round(float(gm.player_grade))), 1, BOOKS_PER_SUBJECT)

	setup_full_library()
	setup_ui()

	print("[Library] Player Grade: ", GameManager.player_grade)
	print("[Library] Manual Mode: ", GameManager.manual_selection_mode)

	# Connect player interaction
	var player_scn = load("res://scenes/Player.tscn")
	player = player_scn.instantiate()
	player.position = Vector3(0.0, 0.85, 2.35)
	player.interaction_requested.connect(_on_interaction)
	add_child(player)


func _set_sidebar_access_message(message: String, color: Color):
	if sidebar_access_label:
		sidebar_access_label.text = message
		sidebar_access_label.modulate = color


func _set_tutoring_access_loading():
	tutoring_access_loaded = false
	tutoring_access_allowed = false
	tutoring_access_reason = "Checking tutoring access..."
	_set_sidebar_access_message("Checking tutoring access...", Color(0.82, 0.84, 0.9, 0.95))


func _set_tutoring_access_state(allowed: bool, message: String):
	tutoring_access_loaded = true
	tutoring_access_allowed = allowed
	var display_message = message.strip_edges()
	if display_message == "":
		display_message = "Tutoring access requires an active subscription or access code."
	tutoring_access_reason = display_message
	if allowed:
		_set_sidebar_access_message(display_message, Color(0.74, 0.95, 0.8, 1.0))
	else:
		_set_sidebar_access_message(display_message + " Open Profile Settings to subscribe or redeem a code.", Color(1.0, 0.78, 0.72, 1.0))


func _ensure_tutoring_access() -> bool:
	if not tutoring_access_loaded:
		_set_sidebar_access_message("Checking tutoring access. Please wait a moment and try again.", Color(1.0, 0.84, 0.62, 1.0))
		if sidebar_panel:
			sidebar_panel.visible = true
		return false

	if tutoring_access_allowed:
		return true

	_set_tutoring_access_state(false, tutoring_access_reason)
	if sidebar_panel:
		sidebar_panel.visible = true
	return false

func _process(delta):
	selection_clock += delta

	# Feed joystick input to player
	if player and is_instance_valid(player):
		if joystick_left:
			player.external_move_input = joystick_left.get_output()

		if joystick_right:
			player.external_look_input = joystick_right.get_output()

	_update_hall_animation(delta)
	_update_books_animation(delta)
	_update_selection_feedback(delta)

func setup_ui():
	ui_canvas = CanvasLayer.new()
	add_child(ui_canvas)

	# Sidebar Background
	sidebar_panel = Panel.new()
	sidebar_panel.name = "Panel"
	sidebar_panel.custom_minimum_size = Vector2(240, 0)
# ...
	# Container with Margins
	var margin = MarginContainer.new()
	margin.name = "MarginContainer"
# ...
	var vbox = VBoxContainer.new()
	vbox.name = "VBoxContainer"
	sidebar_panel.set_anchors_preset(Control.PRESET_LEFT_WIDE)

	# Mobile Check (Simple heuristic or responsive)
	# For now, default to Hidden on start if screen width is small?
	# Or just add a toggle button and let user decide.

	# Style: Dark semi-transparent
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0.1, 0.1, 0.1, 0.9)
	sidebar_panel.add_theme_stylebox_override("panel", style)
	ui_canvas.add_child(sidebar_panel)

	# Menu Toggle Button (Always visible)
	var menu_btn = Button.new()
	menu_btn.text = "MENU"
	menu_btn.position = Vector2(10, 10)
	menu_btn.pressed.connect(_on_toggle_menu)
	ui_canvas.add_child(menu_btn)

	# Add Joysticks (Always add if touch capability or override)
	# Check feature "touchscreen"
	if true: # Force enable for testing/tablet support even on hybrid
		var joystick_scn = load("res://scenes/VirtualJoystick.tscn")
		if joystick_scn:
			joystick_left = joystick_scn.instantiate()
			# Anchor Bottom Left
			joystick_left.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
			joystick_left.offset_left = 50
			joystick_left.offset_bottom = -50
			joystick_left.position = Vector2(50, get_viewport().get_visible_rect().size.y - 250) # Fallback pos
			# Make it smaller region? No, it fills anchor unless we resize.
			# Our VJ scene is full screen control?
			# Wait, the VJ scene root is Anchors Preset 15 (Full Rect).
			# We should probably resize it or count on its internal logic.
			# Internal logic checks distance from Base center.
			# Base is center anchored.
			# We need to position the CONTROL node to the corner.
			joystick_left.custom_minimum_size = Vector2(250, 250)
			joystick_left.size = Vector2(250, 250)
			# Reset anchors to be simple
			joystick_left.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
			joystick_left.position = Vector2(20, get_viewport().get_visible_rect().size.y - 270)

			ui_canvas.add_child(joystick_left)

			joystick_right = joystick_scn.instantiate()
			# Anchor Bottom Right
			joystick_right.joystick_mode = "Look"
			joystick_right.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
			joystick_right.size = Vector2(250, 250)
			joystick_right.position = Vector2(get_viewport().get_visible_rect().size.x - 270, get_viewport().get_visible_rect().size.y - 270)

			ui_canvas.add_child(joystick_right)

	# Container with Margins
	var mc = MarginContainer.new()
	mc.set_anchors_preset(Control.PRESET_FULL_RECT)
	mc.add_theme_constant_override("margin_left", 20)
	mc.add_theme_constant_override("margin_top", 56)
	mc.add_theme_constant_override("margin_right", 20)
	mc.add_theme_constant_override("margin_bottom", 20)
	sidebar_panel.add_child(mc)



	var sidebar_scroll = ScrollContainer.new()
	sidebar_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sidebar_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sidebar_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	mc.add_child(sidebar_scroll)

	var content_vbox = VBoxContainer.new()
	content_vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content_vbox.add_theme_constant_override("separation", 15)
	sidebar_scroll.add_child(content_vbox)

	# 1. Player Stats
	hud_xp = Label.new()
	hud_xp.text = "XP: 0"
	content_vbox.add_child(hud_xp)

	hud_level = Label.new()
	hud_level.text = "Lvl: 1"
	content_vbox.add_child(hud_level)

	hud_grade = Label.new()
	hud_grade.text = "Grade: ?"

	content_vbox.add_child(hud_grade)

	# Role Label
	# Role Label
	hud_role = Label.new()
	hud_role.text = "Role: Student"
	hud_role.name = "HudRole"
	content_vbox.add_child(hud_role)

	var grade_label_small = Label.new()
	grade_label_small.text = "Grade Completion:"
	grade_label_small.add_theme_font_size_override("font_size", 12)
	content_vbox.add_child(grade_label_small)

	grade_gauge = TextureProgressBar.new()
	grade_gauge.min_value = 0
	grade_gauge.max_value = 100
	grade_gauge.value = 0
	grade_gauge.custom_minimum_size = Vector2(0, 15)
	grade_gauge.texture_under = _create_img_tex(Color(0.2, 0.2, 0.2), 200, 15)
	grade_gauge.texture_progress = _create_img_tex(Color(0.9, 0.5, 0.2), 200, 15)
	content_vbox.add_child(grade_gauge)

	grade_percent_label = Label.new()
	grade_percent_label.text = "0%"
	grade_percent_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	content_vbox.add_child(grade_percent_label)

	content_vbox.add_child(HSeparator.new())

	# 2. Course Menu
	var title = Label.new()
	title.text = "COURSES"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_font_size_override("font_size", 20)
	content_vbox.add_child(title)

	var subjects = ["Math", "Science", "History", "English"]
	for sub in subjects:
		var btn = Button.new()
		btn.text = sub
		btn.custom_minimum_size = Vector2(0, 45)
		# Connect with bind to pass argument
		btn.pressed.connect(resume_shelf.bind(sub))
		content_vbox.add_child(btn)

		# Progress Bar (Background)
		var p = TextureProgressBar.new()
		p.name = "Progress_" + sub
		p.texture_under = _create_img_tex(Color(0.2, 0.2, 0.2), 200, 5)
		p.texture_progress = _create_img_tex(Color(0, 0.8, 0.2), 200, 5)
		p.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
		p.custom_minimum_size = Vector2(0, 5)
		p.min_value = 0
		p.max_value = 100
		p.value = 0
		p.mouse_filter = Control.MOUSE_FILTER_IGNORE
		btn.add_child(p)
		sidebar_subject_progress_bars[sub] = p

	sidebar_access_label = Label.new()
	sidebar_access_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	sidebar_access_label.text = "Checking tutoring access..."
	sidebar_access_label.modulate = Color(0.82, 0.84, 0.9, 0.95)
	content_vbox.add_child(sidebar_access_label)

	# Spacer
	var spacer = Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	content_vbox.add_child(spacer)

	# 3. Controls Help
	var help = Label.new()
	help.text = "CONTROLS\n[WASD] Move\n[Mouse] Look\n[Click] Select\n[ESC] Cursor"
	help.modulate = Color(1, 1, 1, 0.6)
	help.autowrap_mode = TextServer.AUTOWRAP_WORD
	help.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	content_vbox.add_child(help)

	content_vbox.add_child(HSeparator.new())

	# 4. Log Out / Edit Profile
	var profile_btn = Button.new()
	profile_btn.text = "Profile Settings"
	profile_btn.pressed.connect(_on_profile_button_pressed)
	content_vbox.add_child(profile_btn)

	admin_access_button = Button.new()
	admin_access_button.text = "Admin Access"
	admin_access_button.visible = false
	admin_access_button.pressed.connect(_on_admin_button_pressed)
	content_vbox.add_child(admin_access_button)

	teacher_dashboard_button = Button.new()
	teacher_dashboard_button.text = "Teacher Dashboard"
	teacher_dashboard_button.visible = false
	teacher_dashboard_button.pressed.connect(_on_teacher_dashboard_pressed)
	content_vbox.add_child(teacher_dashboard_button)

	var exit_btn = Button.new()
	exit_btn.text = "Logout"
	exit_btn.pressed.connect(_logout_to_startup)
	content_vbox.add_child(exit_btn)

	_setup_profile_window()
	_setup_admin_window()
	_setup_teacher_window()
	_refresh_admin_visibility()
	_refresh_teacher_dashboard_visibility()

	# Fetch Stats
	fetch_stats()
	_set_tutoring_access_loading()
	_fetch_billing_status()

	# Start Hidden on Mobile?
	# sidebar_panel.visible = false

func _on_toggle_menu():
	if sidebar_panel:
		sidebar_panel.visible = not sidebar_panel.visible

func _create_img_tex(color, w, h):
	var img = Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(color)
	return ImageTexture.create_from_image(img)

func fetch_stats():
	var gm = get_node("/root/GameManager")
	var data = {"username": gm.player_username}
	NetworkManager.post_request("/get_player_stats", data, _on_stats_received, func(code, err): print("Stats Error: " + err))

func _on_stats_received(_code, response):
	if response and response.has("stats"):
		var stats = response["stats"]
		print("Received Stats: ", stats)

		# Update Grade UI
		if stats.has("current_grade_level") and hud_grade:
			hud_grade.text = "Grade: " + str(stats["current_grade_level"])
			profile_grade_level = clamp(int(round(float(stats["current_grade_level"]))), 1, BOOKS_PER_SUBJECT)

		if hud_role and stats.has("role"):
			hud_role.text = "Role: " + str(stats["role"])
			profile_role = str(stats["role"])
		profile_is_admin = _extract_explicit_admin_flag(stats)
		_refresh_admin_visibility()
		_refresh_teacher_dashboard_visibility()

		if stats.has("avatar_id"):
			GameManager.player_avatar_id = str(stats["avatar_id"])
			if player and is_instance_valid(player):
				player.apply_profile_avatar(GameManager.player_avatar_id)

		if stats.has("grade_completion"):
			var g_val = stats["grade_completion"]
			if grade_gauge:
				grade_gauge.value = g_val
			if grade_percent_label:
				grade_percent_label.text = str(g_val) + "%"

		for subject in SUBJECT_ORDER:
			var sidebar_key = SUBJECT_API_KEY.get(subject, subject)
			if not sidebar_subject_progress_bars.has(subject):
				continue
			if stats.has(sidebar_key):
				sidebar_subject_progress_bars[subject].value = clamp(float(stats[sidebar_key]), 0.0, 100.0)

		for subject in SUBJECT_ORDER:
			var key = SUBJECT_API_KEY.get(subject, subject)
			if not stats.has(key):
				continue

			var progress_val = clamp(float(stats[key]), 0.0, 100.0)
			if shelf_progress_bars.has(subject):
				shelf_progress_bars[subject].value = progress_val
			if shelf_progress_labels.has(subject):
				shelf_progress_labels[subject].text = str(int(round(progress_val))) + "%"
			if subject_selector_progress_labels.has(subject):
				subject_selector_progress_labels[subject].text = str(int(round(progress_val))) + "% complete"

		_refresh_book_emphasis()


func _setup_profile_window():
	if ui_canvas == null:
		return

	profile_overlay = ColorRect.new()
	profile_overlay.name = "ProfileOverlay"
	profile_overlay.color = Color(0.02, 0.03, 0.05, 0.72)
	profile_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	profile_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	ui_canvas.add_child(profile_overlay)
	profile_overlay.hide()

	profile_window = PanelContainer.new()
	profile_window.name = "ProfileWindow"
	profile_window.visible = false
	profile_window.mouse_filter = Control.MOUSE_FILTER_STOP
	var panel_style = StyleBoxFlat.new()
	panel_style.bg_color = Color(0.13, 0.14, 0.16, 0.98)
	panel_style.border_color = Color(0.52, 0.83, 1.0, 0.95)
	panel_style.border_width_left = 2
	panel_style.border_width_top = 2
	panel_style.border_width_right = 2
	panel_style.border_width_bottom = 2
	panel_style.corner_radius_top_left = 14
	panel_style.corner_radius_top_right = 14
	panel_style.corner_radius_bottom_right = 14
	panel_style.corner_radius_bottom_left = 14
	profile_window.add_theme_stylebox_override("panel", panel_style)
	profile_overlay.add_child(profile_window)

	var root = VBoxContainer.new()
	root.name = "ProfileVBox"
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.offset_left = 18
	root.offset_top = 18
	root.offset_right = -18
	root.offset_bottom = -18
	root.add_theme_constant_override("separation", 10)
	profile_window.add_child(root)

	var header_row = HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 10)
	root.add_child(header_row)

	var header_label = Label.new()
	header_label.text = "Profile Settings"
	header_label.add_theme_font_size_override("font_size", 20)
	header_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(header_label)

	var close_profile_button = Button.new()
	close_profile_button.text = "Close"
	close_profile_button.pressed.connect(_hide_profile_window)
	header_row.add_child(close_profile_button)

	root.add_child(HSeparator.new())

	profile_scroll = ScrollContainer.new()
	profile_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	profile_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	profile_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	root.add_child(profile_scroll)

	var content = VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.custom_minimum_size = Vector2(0, 980)
	profile_scroll.add_child(content)

	var intro = Label.new()
	intro.text = "Save a recovery email, switch avatars, bring your own OpenAI key, or manage your subscription."
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(intro)

	var email_label = Label.new()
	email_label.text = "Recovery Email"
	content.add_child(email_label)

	profile_email_input = LineEdit.new()
	profile_email_input.placeholder_text = "parent@example.com"
	profile_email_input.clear_button_enabled = true
	content.add_child(profile_email_input)

	var avatar_label = Label.new()
	avatar_label.text = "Avatar"
	content.add_child(avatar_label)

	profile_avatar_option = OptionButton.new()
	profile_avatar_option.add_item("Girl Avatar", 0)
	profile_avatar_option.add_item("Boy Avatar", 1)
	content.add_child(profile_avatar_option)

	var key_label = Label.new()
	key_label.text = "OpenAI API Key"
	content.add_child(key_label)

	profile_openai_key_input = LineEdit.new()
	profile_openai_key_input.placeholder_text = "Leave blank to keep current key"
	profile_openai_key_input.secret = true
	profile_openai_key_input.clear_button_enabled = true
	content.add_child(profile_openai_key_input)

	profile_key_hint_label = Label.new()
	profile_key_hint_label.text = "No personal key saved."
	profile_key_hint_label.modulate = Color(0.78, 0.85, 0.92, 0.82)
	content.add_child(profile_key_hint_label)

	profile_clear_key_check = CheckBox.new()
	profile_clear_key_check.text = "Remove saved personal key"
	content.add_child(profile_clear_key_check)

	content.add_child(HSeparator.new())

	var teacher_title = Label.new()
	teacher_title.text = "Teacher Connection"
	teacher_title.add_theme_font_size_override("font_size", 18)
	content.add_child(teacher_title)

	var teacher_intro = Label.new()
	teacher_intro.text = "Students can request a teacher here. Teachers must accept before they can view student progress."
	teacher_intro.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(teacher_intro)

	teacher_request_username_input = LineEdit.new()
	teacher_request_username_input.placeholder_text = "Teacher username"
	teacher_request_username_input.clear_button_enabled = true
	content.add_child(teacher_request_username_input)

	teacher_request_note_input = LineEdit.new()
	teacher_request_note_input.placeholder_text = "Optional note to the teacher"
	teacher_request_note_input.clear_button_enabled = true
	content.add_child(teacher_request_note_input)

	teacher_request_button = Button.new()
	teacher_request_button.text = "Request Teacher Approval"
	teacher_request_button.pressed.connect(_submit_teacher_request)
	content.add_child(teacher_request_button)

	teacher_links_list = ItemList.new()
	teacher_links_list.custom_minimum_size = Vector2(0, 120)
	content.add_child(teacher_links_list)

	teacher_revoke_button = Button.new()
	teacher_revoke_button.text = "Remove Selected Teacher Connection"
	teacher_revoke_button.pressed.connect(_revoke_selected_teacher_link)
	content.add_child(teacher_revoke_button)

	teacher_link_status_label = Label.new()
	teacher_link_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(teacher_link_status_label)

	content.add_child(HSeparator.new())

	var billing_title = Label.new()
	billing_title.text = "Subscription"
	billing_title.add_theme_font_size_override("font_size", 18)
	content.add_child(billing_title)

	billing_plan_label = Label.new()
	billing_plan_label.text = "Subscription: loading..."
	billing_plan_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(billing_plan_label)

	billing_usage_label = Label.new()
	billing_usage_label.text = "Usage: -"
	billing_usage_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(billing_usage_label)

	billing_payment_label = Label.new()
	billing_payment_label.text = "Payment Method: -"
	billing_payment_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(billing_payment_label)

	billing_access_label = Label.new()
	billing_access_label.text = ""
	billing_access_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(billing_access_label)

	var access_code_row = HBoxContainer.new()
	access_code_row.add_theme_constant_override("separation", 8)
	content.add_child(access_code_row)

	billing_access_code_input = LineEdit.new()
	billing_access_code_input.placeholder_text = "Redeem access code"
	billing_access_code_input.secret = true
	billing_access_code_input.clear_button_enabled = true
	billing_access_code_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	access_code_row.add_child(billing_access_code_input)

	billing_access_code_button = Button.new()
	billing_access_code_button.text = "Redeem"
	billing_access_code_button.pressed.connect(_redeem_profile_access_code)
	access_code_row.add_child(billing_access_code_button)

	var billing_button_box = VBoxContainer.new()
	billing_button_box.add_theme_constant_override("separation", 6)
	content.add_child(billing_button_box)

	billing_hosted_button = Button.new()
	billing_hosted_button.text = "Subscribe: Hosted AI"
	billing_hosted_button.pressed.connect(_start_hosted_checkout)
	billing_button_box.add_child(billing_hosted_button)

	billing_byok_button = Button.new()
	billing_byok_button.text = "Subscribe: Bring Your Own Key"
	billing_byok_button.pressed.connect(_start_byok_checkout)
	billing_button_box.add_child(billing_byok_button)

	billing_manage_button = Button.new()
	billing_manage_button.text = "Manage Billing"
	billing_manage_button.pressed.connect(_open_billing_portal)
	billing_button_box.add_child(billing_manage_button)

	var button_row = HBoxContainer.new()
	button_row.alignment = BoxContainer.ALIGNMENT_END
	content.add_child(button_row)

	var cancel_btn = Button.new()
	cancel_btn.text = "Close"
	cancel_btn.pressed.connect(_hide_profile_window)
	button_row.add_child(cancel_btn)

	var save_btn = Button.new()
	save_btn.text = "Save"
	save_btn.pressed.connect(_save_profile_settings)
	button_row.add_child(save_btn)

	profile_status_label = Label.new()
	profile_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	content.add_child(profile_status_label)


func _is_admin_user() -> bool:
	return profile_is_admin


func _is_teacher_dashboard_user() -> bool:
	return profile_role == "Teacher" or profile_is_admin


func _refresh_admin_visibility():
	if admin_access_button:
		admin_access_button.visible = _is_admin_user()


func _refresh_teacher_dashboard_visibility():
	if teacher_dashboard_button:
		teacher_dashboard_button.visible = _is_teacher_dashboard_user()


func _create_admin_plan_option() -> OptionButton:
	var option = OptionButton.new()
	option.add_item("Hosted AI", 0)
	option.add_item("Bring Your Own Key", 1)
	return option


func _admin_selected_plan_code(option: OptionButton) -> String:
	return "byok_monthly" if option and option.selected == 1 else "hosted_monthly"


func _setup_admin_window():
	if ui_canvas == null:
		return

	admin_overlay = ColorRect.new()
	admin_overlay.name = "AdminOverlay"
	admin_overlay.color = Color(0.02, 0.03, 0.05, 0.72)
	admin_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	admin_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	ui_canvas.add_child(admin_overlay)
	admin_overlay.hide()

	admin_window = PanelContainer.new()
	admin_window.name = "AdminWindow"
	admin_window.visible = false
	admin_window.mouse_filter = Control.MOUSE_FILTER_STOP
	var panel_style = StyleBoxFlat.new()
	panel_style.bg_color = Color(0.13, 0.14, 0.16, 0.98)
	panel_style.border_color = Color(0.42, 0.83, 0.73, 0.95)
	panel_style.border_width_left = 2
	panel_style.border_width_top = 2
	panel_style.border_width_right = 2
	panel_style.border_width_bottom = 2
	panel_style.corner_radius_top_left = 14
	panel_style.corner_radius_top_right = 14
	panel_style.corner_radius_bottom_right = 14
	panel_style.corner_radius_bottom_left = 14
	admin_window.add_theme_stylebox_override("panel", panel_style)
	admin_overlay.add_child(admin_window)

	var frame = VBoxContainer.new()
	frame.name = "AdminFrame"
	frame.set_anchors_preset(Control.PRESET_FULL_RECT)
	frame.offset_left = 18
	frame.offset_top = 18
	frame.offset_right = -18
	frame.offset_bottom = -18
	frame.add_theme_constant_override("separation", 10)
	admin_window.add_child(frame)

	var header_row = HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 10)
	frame.add_child(header_row)

	var header_label = Label.new()
	header_label.text = "Admin Access Management"
	header_label.add_theme_font_size_override("font_size", 20)
	header_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(header_label)

	var close_admin_button = Button.new()
	close_admin_button.text = "Close"
	close_admin_button.pressed.connect(_hide_admin_window)
	header_row.add_child(close_admin_button)

	frame.add_child(HSeparator.new())

	admin_scroll = ScrollContainer.new()
	admin_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	admin_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	admin_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	frame.add_child(admin_scroll)

	var root = VBoxContainer.new()
	root.add_theme_constant_override("separation", 10)
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.custom_minimum_size = Vector2(0, 900)
	admin_scroll.add_child(root)

	var intro = Label.new()
	intro.text = "Create access codes, grant direct evaluator access, review active grants, and revoke access without leaving the app."
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD
	root.add_child(intro)

	var code_title = Label.new()
	code_title.text = "Create Access Code"
	code_title.add_theme_font_size_override("font_size", 18)
	root.add_child(code_title)

	var code_grid = GridContainer.new()
	code_grid.columns = 2
	code_grid.add_theme_constant_override("h_separation", 12)
	code_grid.add_theme_constant_override("v_separation", 6)
	root.add_child(code_grid)

	var assigned_label = Label.new()
	assigned_label.text = "Assigned Username"
	code_grid.add_child(assigned_label)
	admin_code_assigned_input = LineEdit.new()
	admin_code_assigned_input.placeholder_text = "blank = redeemable by any user"
	code_grid.add_child(admin_code_assigned_input)

	var code_plan_label = Label.new()
	code_plan_label.text = "Plan"
	code_grid.add_child(code_plan_label)
	admin_code_plan_option = _create_admin_plan_option()
	code_grid.add_child(admin_code_plan_option)

	var code_days_label = Label.new()
	code_days_label.text = "Expires In Days"
	code_grid.add_child(code_days_label)
	admin_code_days_input = LineEdit.new()
	admin_code_days_input.placeholder_text = "blank = no expiry"
	code_grid.add_child(admin_code_days_input)

	var code_max_label = Label.new()
	code_max_label.text = "Max Redemptions"
	code_grid.add_child(code_max_label)
	admin_code_max_redemptions_input = LineEdit.new()
	admin_code_max_redemptions_input.text = "1"
	code_grid.add_child(admin_code_max_redemptions_input)

	var custom_code_label = Label.new()
	custom_code_label.text = "Custom Code"
	code_grid.add_child(custom_code_label)
	admin_code_custom_input = LineEdit.new()
	admin_code_custom_input.placeholder_text = "blank = auto-generate"
	code_grid.add_child(admin_code_custom_input)

	var code_notes_label = Label.new()
	code_notes_label.text = "Notes"
	code_grid.add_child(code_notes_label)
	admin_code_notes_input = LineEdit.new()
	admin_code_notes_input.placeholder_text = "Evaluator, launch partner, etc."
	code_grid.add_child(admin_code_notes_input)

	var code_button_row = HBoxContainer.new()
	code_button_row.add_theme_constant_override("separation", 8)
	root.add_child(code_button_row)

	var create_code_button = Button.new()
	create_code_button.text = "Create Access Code"
	create_code_button.pressed.connect(_create_admin_access_code)
	code_button_row.add_child(create_code_button)

	var copy_code_button = Button.new()
	copy_code_button.text = "Copy Last Code"
	copy_code_button.pressed.connect(_copy_admin_code_to_clipboard)
	code_button_row.add_child(copy_code_button)

	admin_last_created_code_input = LineEdit.new()
	admin_last_created_code_input.editable = false
	admin_last_created_code_input.placeholder_text = "Newly created code appears here once"
	root.add_child(admin_last_created_code_input)

	root.add_child(HSeparator.new())

	var grant_title = Label.new()
	grant_title.text = "Grant Direct Access"
	grant_title.add_theme_font_size_override("font_size", 18)
	root.add_child(grant_title)

	var grant_grid = GridContainer.new()
	grant_grid.columns = 2
	grant_grid.add_theme_constant_override("h_separation", 12)
	grant_grid.add_theme_constant_override("v_separation", 6)
	root.add_child(grant_grid)

	var grant_user_label = Label.new()
	grant_user_label.text = "Target Username"
	grant_grid.add_child(grant_user_label)
	admin_grant_username_input = LineEdit.new()
	admin_grant_username_input.placeholder_text = "student123"
	grant_grid.add_child(admin_grant_username_input)

	var grant_plan_label = Label.new()
	grant_plan_label.text = "Plan"
	grant_grid.add_child(grant_plan_label)
	admin_grant_plan_option = _create_admin_plan_option()
	grant_grid.add_child(admin_grant_plan_option)

	var grant_days_label = Label.new()
	grant_days_label.text = "Expires In Days"
	grant_grid.add_child(grant_days_label)
	admin_grant_days_input = LineEdit.new()
	admin_grant_days_input.placeholder_text = "blank = no expiry"
	grant_grid.add_child(admin_grant_days_input)

	var grant_notes_label = Label.new()
	grant_notes_label.text = "Notes"
	grant_grid.add_child(grant_notes_label)
	admin_grant_notes_input = LineEdit.new()
	admin_grant_notes_input.placeholder_text = "VC access, evaluator, partner"
	grant_grid.add_child(admin_grant_notes_input)

	var grant_button = Button.new()
	grant_button.text = "Grant Access"
	grant_button.pressed.connect(_grant_admin_access)
	root.add_child(grant_button)

	root.add_child(HSeparator.new())

	var filter_title = Label.new()
	filter_title.text = "Review And Revoke"
	filter_title.add_theme_font_size_override("font_size", 18)
	root.add_child(filter_title)

	var filter_row = HBoxContainer.new()
	filter_row.add_theme_constant_override("separation", 8)
	root.add_child(filter_row)

	admin_filter_username_input = LineEdit.new()
	admin_filter_username_input.placeholder_text = "Filter by username (optional)"
	admin_filter_username_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	filter_row.add_child(admin_filter_username_input)

	var refresh_all_button = Button.new()
	refresh_all_button.text = "Refresh"
	refresh_all_button.pressed.connect(_refresh_admin_lists)
	filter_row.add_child(refresh_all_button)

	admin_revoke_reason_input = LineEdit.new()
	admin_revoke_reason_input.placeholder_text = "Revocation reason (optional)"
	root.add_child(admin_revoke_reason_input)

	var code_list_label = Label.new()
	code_list_label.text = "Access Codes"
	root.add_child(code_list_label)

	admin_code_list = ItemList.new()
	admin_code_list.select_mode = ItemList.SELECT_SINGLE
	admin_code_list.custom_minimum_size = Vector2(0, 170)
	root.add_child(admin_code_list)

	var revoke_code_button = Button.new()
	revoke_code_button.text = "Revoke Selected Code"
	revoke_code_button.pressed.connect(_revoke_selected_admin_code)
	root.add_child(revoke_code_button)

	var grant_list_label = Label.new()
	grant_list_label.text = "Access Grants"
	root.add_child(grant_list_label)

	admin_grant_list = ItemList.new()
	admin_grant_list.select_mode = ItemList.SELECT_SINGLE
	admin_grant_list.custom_minimum_size = Vector2(0, 170)
	root.add_child(admin_grant_list)

	var revoke_grant_button = Button.new()
	revoke_grant_button.text = "Revoke Selected Grant"
	revoke_grant_button.pressed.connect(_revoke_selected_admin_grant)
	root.add_child(revoke_grant_button)

	admin_status_label = Label.new()
	admin_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	root.add_child(admin_status_label)


func _setup_teacher_window():
	if ui_canvas == null:
		return

	teacher_overlay = ColorRect.new()
	teacher_overlay.name = "TeacherOverlay"
	teacher_overlay.color = Color(0.02, 0.03, 0.05, 0.72)
	teacher_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	teacher_overlay.mouse_filter = Control.MOUSE_FILTER_STOP
	ui_canvas.add_child(teacher_overlay)
	teacher_overlay.hide()

	teacher_window = PanelContainer.new()
	teacher_window.name = "TeacherWindow"
	teacher_window.visible = false
	teacher_window.mouse_filter = Control.MOUSE_FILTER_STOP
	var panel_style = StyleBoxFlat.new()
	panel_style.bg_color = Color(0.13, 0.14, 0.16, 0.98)
	panel_style.border_color = Color(0.97, 0.84, 0.46, 0.95)
	panel_style.border_width_left = 2
	panel_style.border_width_top = 2
	panel_style.border_width_right = 2
	panel_style.border_width_bottom = 2
	panel_style.corner_radius_top_left = 14
	panel_style.corner_radius_top_right = 14
	panel_style.corner_radius_bottom_right = 14
	panel_style.corner_radius_bottom_left = 14
	teacher_window.add_theme_stylebox_override("panel", panel_style)
	teacher_overlay.add_child(teacher_window)

	var frame = VBoxContainer.new()
	frame.set_anchors_preset(Control.PRESET_FULL_RECT)
	frame.offset_left = 18
	frame.offset_top = 18
	frame.offset_right = -18
	frame.offset_bottom = -18
	frame.add_theme_constant_override("separation", 10)
	teacher_window.add_child(frame)

	var header_row = HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 10)
	frame.add_child(header_row)

	var header_label = Label.new()
	header_label.text = "Teacher Dashboard"
	header_label.add_theme_font_size_override("font_size", 20)
	header_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(header_label)

	var close_teacher_button = Button.new()
	close_teacher_button.text = "Close"
	close_teacher_button.pressed.connect(_hide_teacher_window)
	header_row.add_child(close_teacher_button)

	frame.add_child(HSeparator.new())

	teacher_scroll = ScrollContainer.new()
	teacher_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	teacher_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	teacher_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	frame.add_child(teacher_scroll)

	var root = VBoxContainer.new()
	root.add_theme_constant_override("separation", 10)
	root.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	root.custom_minimum_size = Vector2(0, 960)
	teacher_scroll.add_child(root)

	var intro = Label.new()
	intro.text = "Accept student requests, review linked learners, and inspect detailed progress without leaving the library."
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD
	root.add_child(intro)

	var pending_title = Label.new()
	pending_title.text = "Pending Student Requests"
	pending_title.add_theme_font_size_override("font_size", 18)
	root.add_child(pending_title)

	teacher_pending_list = ItemList.new()
	teacher_pending_list.select_mode = ItemList.SELECT_SINGLE
	teacher_pending_list.custom_minimum_size = Vector2(0, 150)
	root.add_child(teacher_pending_list)

	var pending_buttons = HBoxContainer.new()
	pending_buttons.add_theme_constant_override("separation", 8)
	root.add_child(pending_buttons)

	var accept_button = Button.new()
	accept_button.text = "Accept Selected Request"
	accept_button.pressed.connect(func(): _respond_to_selected_teacher_request("ACCEPTED"))
	pending_buttons.add_child(accept_button)

	var reject_button = Button.new()
	reject_button.text = "Reject Selected Request"
	reject_button.pressed.connect(func(): _respond_to_selected_teacher_request("REJECTED"))
	pending_buttons.add_child(reject_button)

	root.add_child(HSeparator.new())

	var student_title = Label.new()
	student_title.text = "Accepted Students"
	student_title.add_theme_font_size_override("font_size", 18)
	root.add_child(student_title)

	teacher_student_list = ItemList.new()
	teacher_student_list.select_mode = ItemList.SELECT_SINGLE
	teacher_student_list.custom_minimum_size = Vector2(0, 180)
	teacher_student_list.item_selected.connect(_load_selected_teacher_student)
	root.add_child(teacher_student_list)

	teacher_drop_button = Button.new()
	teacher_drop_button.text = "Drop Selected Student"
	teacher_drop_button.pressed.connect(_drop_selected_teacher_student)
	root.add_child(teacher_drop_button)

	var refresh_button = Button.new()
	refresh_button.text = "Refresh Dashboard"
	refresh_button.pressed.connect(_refresh_teacher_dashboard)
	root.add_child(refresh_button)

	teacher_detail_label = RichTextLabel.new()
	teacher_detail_label.custom_minimum_size = Vector2(0, 320)
	teacher_detail_label.fit_content = false
	teacher_detail_label.scroll_active = true
	teacher_detail_label.bbcode_enabled = false
	teacher_detail_label.text = "Select a student to view detailed progress."
	root.add_child(teacher_detail_label)

	teacher_status_label = Label.new()
	teacher_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD
	root.add_child(teacher_status_label)


func _on_teacher_dashboard_pressed():
	if teacher_window == null or not _is_teacher_dashboard_user():
		return

	teacher_status_label.text = "Loading teacher dashboard..."
	teacher_detail_label.text = "Select a student to view detailed progress."
	var viewport_rect = get_viewport().get_visible_rect().size
	var available_size = Vector2(
		max(viewport_rect.x - 28.0, 320.0),
		max(viewport_rect.y - 28.0, 280.0)
	)
	var target_size = Vector2(
		min(860.0, available_size.x),
		min(720.0, available_size.y)
	)
	target_size.x = max(target_size.x, min(560.0, available_size.x))
	target_size.y = max(target_size.y, min(420.0, available_size.y))
	teacher_overlay.show()
	teacher_window.show()
	teacher_window.size = target_size
	teacher_window.position = Vector2(
		floor((viewport_rect.x - target_size.x) * 0.5),
		max(18.0, floor((viewport_rect.y - target_size.y) * 0.5))
	)
	if teacher_scroll:
		teacher_scroll.scroll_vertical = 0
	_refresh_teacher_dashboard()


func _hide_teacher_window():
	if teacher_window:
		teacher_window.hide()
	if teacher_overlay:
		teacher_overlay.hide()


func _refresh_teacher_dashboard():
	if teacher_status_label == null:
		return
	teacher_status_label.text = "Refreshing teacher dashboard..."
	var payload = {"username": GameManager.player_username}
	NetworkManager.post_request("/teacher_dashboard", payload, _on_teacher_dashboard_loaded, func(_code, err):
		teacher_status_label.text = err if err != "" else "Unable to load teacher dashboard."
	)


func _on_teacher_dashboard_loaded(_code, response):
	teacher_pending_entries = response.get("pending_requests", [])
	teacher_student_entries = response.get("accepted_students", [])

	if teacher_pending_list:
		teacher_pending_list.clear()
		for entry in teacher_pending_entries:
			var note_text = str(entry.get("request_note", "")).strip_edges()
			var display = str(entry.get("student_username", "student"))
			if note_text != "":
				display += " | " + note_text
			teacher_pending_list.add_item(display)

	if teacher_student_list:
		teacher_student_list.clear()
		for entry in teacher_student_entries:
			var completion = "%.1f%%" % float(entry.get("grade_completion", 0.0))
			var display_name = str(entry.get("display_name", entry.get("username", "student")))
			teacher_student_list.add_item(display_name + " | Grade " + str(entry.get("grade_level", "?")) + " | " + completion)
	if teacher_drop_button:
		teacher_drop_button.disabled = teacher_student_entries.is_empty()

	if teacher_status_label:
		teacher_status_label.text = "Pending requests: %d | Linked students: %d" % [teacher_pending_entries.size(), teacher_student_entries.size()]
	if teacher_student_entries.size() == 0 and teacher_detail_label:
		teacher_detail_label.text = "No accepted students yet."
	elif teacher_student_entries.size() > 0 and teacher_student_list and teacher_student_list.get_selected_items().is_empty():
		teacher_student_list.select(0)
		_load_selected_teacher_student(0)


func _respond_to_selected_teacher_request(action: String):
	if teacher_pending_list == null or teacher_status_label == null:
		return
	var selected = teacher_pending_list.get_selected_items()
	if selected.is_empty():
		teacher_status_label.text = "Select a pending request first."
		return

	var entry = teacher_pending_entries[selected[0]]
	var payload = {
		"username": GameManager.player_username,
		"link_id": int(entry.get("id", -1)),
		"action": action,
		"response_note": ""
	}
	teacher_status_label.text = "Updating request..."
	NetworkManager.post_request("/respond_teacher_link", payload, func(_code, _response):
		teacher_status_label.text = "Request updated."
		_refresh_teacher_dashboard()
		_fetch_teacher_links()
	, func(_code, err):
		teacher_status_label.text = err if err != "" else "Unable to update teacher request."
	)


func _drop_selected_teacher_student():
	if teacher_student_list == null or teacher_status_label == null:
		return
	var selected = teacher_student_list.get_selected_items()
	if selected.is_empty():
		teacher_status_label.text = "Select a linked student first."
		return

	var entry = teacher_student_entries[selected[0]]
	var link_id = int(entry.get("teacher_link_id", -1))
	if link_id <= 0:
		teacher_status_label.text = "This student link is missing a teacher link id."
		return

	if teacher_drop_button:
		teacher_drop_button.disabled = true
	teacher_status_label.text = "Removing linked student..."
	var payload = {
		"username": GameManager.player_username,
		"link_id": link_id,
		"reason": "Dropped by teacher"
	}
	NetworkManager.post_request("/revoke_teacher_link", payload, func(_code, _response):
		if teacher_drop_button:
			teacher_drop_button.disabled = false
		if teacher_detail_label:
			teacher_detail_label.text = "Student link removed. Select another student to view detailed progress."
		teacher_status_label.text = "Student removed from teacher roster."
		_refresh_teacher_dashboard()
		_fetch_teacher_links()
	, func(_code, err):
		if teacher_drop_button:
			teacher_drop_button.disabled = false
		teacher_status_label.text = err if err != "" else "Unable to remove student."
	)


func _load_selected_teacher_student(index: int):
	if index < 0 or index >= teacher_student_entries.size():
		return
	var entry = teacher_student_entries[index]
	var payload = {
		"username": GameManager.player_username,
		"student_username": str(entry.get("username", ""))
	}
	teacher_status_label.text = "Loading student progress..."
	NetworkManager.post_request("/teacher_student_progress", payload, _on_teacher_student_progress_loaded, func(_code, err):
		teacher_status_label.text = err if err != "" else "Unable to load student progress."
	)


func _format_teacher_duration(total_seconds: int) -> String:
	var seconds = max(total_seconds, 0)
	var hours = int(seconds / 3600)
	var minutes = int((seconds % 3600) / 60)
	if hours > 0:
		return "%dh %dm" % [hours, minutes]
	return "%dm" % [minutes]


func _on_teacher_student_progress_loaded(_code, response):
	if teacher_detail_label == null:
		return

	var student = response.get("student", {})
	var subject_completion = student.get("subject_completion", {})
	var subjects_line = "Math %.1f%% | Science %.1f%% | History %.1f%% | English %.1f%%" % [
		float(subject_completion.get("Math", 0.0)),
		float(subject_completion.get("Science", 0.0)),
		float(subject_completion.get("Social_Studies", 0.0)),
		float(subject_completion.get("ELA", 0.0))
	]

	var detail_lines = []
	detail_lines.append(str(student.get("display_name", student.get("username", "Student"))))
	detail_lines.append("Username: " + str(student.get("username", "")))
	detail_lines.append("Grade: " + str(student.get("grade_level", "?")))
	detail_lines.append("Current Topic: " + str(student.get("current_topic", "None")))
	detail_lines.append("Current Node: " + str(student.get("current_node", "None")))
	detail_lines.append("Grade Completion: %.1f%%" % float(student.get("grade_completion", 0.0)))
	detail_lines.append("Correct Rate: %.1f%% | Avg Score: %.1f%%" % [
		float(student.get("correct_rate_percent", 0.0)),
		float(student.get("average_score_percent", 0.0))
	])
	detail_lines.append("Login Time: " + _format_teacher_duration(int(student.get("total_login_seconds", 0))) + " | Learning Time: " + _format_teacher_duration(int(student.get("total_learning_seconds", 0))))
	detail_lines.append("Sessions: %d | Requests: %d | Chat Turns: %d" % [
		int(student.get("session_count", 0)),
		int(student.get("total_request_count", 0)),
		int(student.get("total_chat_turns", 0))
	])
	detail_lines.append(subjects_line)
	detail_lines.append("")
	detail_lines.append("Topic Progress")

	var shown_topics = 0
	for topic in response.get("topics", []):
		if shown_topics >= 8:
			break
		detail_lines.append("- %s | %s | mastery %d%% | node %s | avg %.1f%%" % [
			str(topic.get("topic_name", "")),
			str(topic.get("status", "")),
			int(topic.get("mastery_score", 0)),
			str(topic.get("current_node", "None")),
			float(topic.get("average_score_percent", 0.0))
		])
		shown_topics += 1

	detail_lines.append("")
	detail_lines.append("Recent Node Activity")
	var shown_nodes = 0
	for node in response.get("nodes", []):
		if shown_nodes >= 10:
			break
		detail_lines.append("- %s | %s | attempts %d | avg %.1f%% | status %s" % [
			str(node.get("topic_name", "")),
			str(node.get("node_id", "")),
			int(node.get("attempt_count", 0)),
			float(node.get("average_score_percent", 0.0)),
			str(node.get("status", ""))
		])
		shown_nodes += 1

	teacher_detail_label.text = "\n".join(detail_lines)
	if teacher_status_label:
		teacher_status_label.text = "Detailed progress loaded."


func _on_profile_button_pressed():
	if profile_window == null:
		return

	profile_status_label.text = "Loading profile..."
	var viewport_rect = get_viewport().get_visible_rect().size
	var available_size = Vector2(
		max(viewport_rect.x - 28.0, 320.0),
		max(viewport_rect.y - 28.0, 280.0)
	)
	var target_size = Vector2(
		min(560.0, available_size.x),
		min(700.0, available_size.y)
	)
	target_size.x = max(target_size.x, min(460.0, available_size.x))
	target_size.y = max(target_size.y, min(420.0, available_size.y))
	profile_overlay.show()
	profile_window.show()
	profile_window.size = target_size
	profile_window.position = Vector2(
		floor((viewport_rect.x - target_size.x) * 0.5),
		max(18.0, floor((viewport_rect.y - target_size.y) * 0.5))
	)
	if profile_scroll:
		profile_scroll.scroll_vertical = 0
	_fetch_profile()
	_fetch_teacher_links()
	_fetch_billing_status()


func _on_admin_button_pressed():
	if admin_window == null or not _is_admin_user():
		return

	admin_status_label.text = "Loading admin data..."
	var viewport_rect = get_viewport().get_visible_rect().size
	var available_size = Vector2(
		max(viewport_rect.x - 28.0, 320.0),
		max(viewport_rect.y - 28.0, 280.0)
	)
	var target_size = Vector2(
		min(820.0, available_size.x),
		min(680.0, available_size.y)
	)
	target_size.x = max(target_size.x, min(520.0, available_size.x))
	target_size.y = max(target_size.y, min(420.0, available_size.y))
	admin_overlay.show()
	admin_window.show()
	admin_window.size = target_size
	admin_window.position = Vector2(
		floor((viewport_rect.x - target_size.x) * 0.5),
		max(18.0, floor((viewport_rect.y - target_size.y) * 0.5))
	)
	if admin_scroll:
		admin_scroll.scroll_vertical = 0
	_refresh_admin_lists()


func _hide_admin_window():
	if admin_window:
		admin_window.hide()
	if admin_overlay:
		admin_overlay.hide()


func _hide_profile_window():
	if profile_window:
		profile_window.hide()
	if profile_overlay:
		profile_overlay.hide()


func _logout_to_startup():
	_hide_profile_window()
	_hide_admin_window()
	_hide_teacher_window()
	var logout_username = GameManager.player_username
	if NetworkManager.auth_token != "" and logout_username != "":
		NetworkManager.post_request("/logout", {"username": logout_username}, func(_code, _response):
			_finish_logout_to_startup()
		, func(_code, _err):
			_finish_logout_to_startup()
		)
		return
	_finish_logout_to_startup()


func _finish_logout_to_startup():
	NetworkManager.auth_token = ""
	NetworkManager.session_id = ""
	NetworkManager.current_username = "Player1"
	GameManager.current_topic = ""
	GameManager.player_username = "Player1"
	GameManager.player_grade = -1
	GameManager.manual_selection_mode = false
	GameManager.password_cache = ""
	get_tree().change_scene_to_file("res://scenes/Startup.tscn")


func _fetch_profile():
	var data = {"username": GameManager.player_username}
	NetworkManager.post_request("/get_profile", data, _on_profile_loaded, func(code, err):
		if profile_status_label:
			profile_status_label.text = "Unable to load profile."
	)


func _on_profile_loaded(_code, response):
	if response == null:
		return

	if profile_email_input:
		profile_email_input.text = str(response.get("email", ""))

	if profile_avatar_option:
		var avatar_id = str(response.get("avatar_id", "schoolgirl"))
		profile_avatar_option.selected = 1 if avatar_id == "schoolboy" else 0

	if profile_key_hint_label:
		if response.get("has_personal_openai_key", false):
			var hint = str(response.get("openai_key_hint", "saved"))
			profile_key_hint_label.text = "Saved personal key: " + hint
		else:
			profile_key_hint_label.text = "No personal key saved."

	if profile_openai_key_input:
		profile_openai_key_input.text = ""
	if profile_clear_key_check:
		profile_clear_key_check.button_pressed = false
	if teacher_request_button:
		teacher_request_button.disabled = profile_role != "Student"
		teacher_request_button.text = "Request Teacher Approval" if profile_role == "Student" else "Teacher requests are student-only"
	if teacher_request_username_input:
		teacher_request_username_input.editable = profile_role == "Student"
	if teacher_request_note_input:
		teacher_request_note_input.editable = profile_role == "Student"
	if teacher_revoke_button:
		teacher_revoke_button.visible = profile_role == "Student"
		teacher_revoke_button.disabled = profile_role != "Student"
	if profile_status_label:
		profile_status_label.text = ""


func _fetch_teacher_links():
	var data = {"username": GameManager.player_username}
	NetworkManager.post_request("/list_teacher_links", data, _on_teacher_links_loaded, func(_code, err):
		if teacher_link_status_label:
			teacher_link_status_label.text = err if err != "" else "Unable to load teacher links."
	)


func _on_teacher_links_loaded(_code, response):
	teacher_link_entries = response.get("links", [])
	if teacher_links_list:
		teacher_links_list.clear()
		for entry in teacher_link_entries:
			var teacher_name = str(entry.get("teacher_username", "teacher"))
			var student_name = str(entry.get("student_username", "student"))
			var status = str(entry.get("status", "PENDING"))
			var display = teacher_name + " -> " + student_name + " [" + status + "]"
			if profile_role == "Student":
				display = teacher_name + " [" + status + "]"
			teacher_links_list.add_item(display)

	if teacher_link_status_label:
		if teacher_link_entries.is_empty():
			teacher_link_status_label.text = "No teacher connections yet."
		else:
			teacher_link_status_label.text = "Teacher links loaded."


func _revoke_selected_teacher_link():
	if teacher_links_list == null or teacher_link_status_label == null:
		return
	if profile_role != "Student":
		teacher_link_status_label.text = "Only students can remove teacher connections here."
		return
	var selected = teacher_links_list.get_selected_items()
	if selected.is_empty():
		teacher_link_status_label.text = "Select a teacher connection first."
		return

	var entry = teacher_link_entries[selected[0]]
	var payload = {
		"username": GameManager.player_username,
		"link_id": int(entry.get("id", -1)),
		"reason": "Revoked by student"
	}
	if teacher_revoke_button:
		teacher_revoke_button.disabled = true
	teacher_link_status_label.text = "Removing teacher connection..."
	NetworkManager.post_request("/revoke_teacher_link", payload, func(_code, _response):
		if teacher_revoke_button:
			teacher_revoke_button.disabled = false
		teacher_link_status_label.text = "Teacher connection removed."
		_fetch_teacher_links()
	, func(_code, err):
		if teacher_revoke_button:
			teacher_revoke_button.disabled = false
		teacher_link_status_label.text = err if err != "" else "Unable to remove teacher connection."
	)


func _submit_teacher_request():
	if teacher_request_button == null or teacher_link_status_label == null:
		return
	if profile_role != "Student":
		teacher_link_status_label.text = "Only student accounts can request a teacher."
		return

	var teacher_username = teacher_request_username_input.text.strip_edges() if teacher_request_username_input else ""
	if teacher_username == "":
		teacher_link_status_label.text = "Enter a teacher username first."
		return

	teacher_request_button.disabled = true
	teacher_link_status_label.text = "Sending teacher request..."
	var payload = {
		"username": GameManager.player_username,
		"teacher_username": teacher_username,
		"request_note": teacher_request_note_input.text.strip_edges() if teacher_request_note_input else ""
	}
	NetworkManager.post_request("/request_teacher_link", payload, func(_code, _response):
		if teacher_request_username_input:
			teacher_request_username_input.text = ""
		if teacher_request_note_input:
			teacher_request_note_input.text = ""
		if teacher_request_button:
			teacher_request_button.disabled = false
		teacher_link_status_label.text = "Teacher request sent."
		_fetch_teacher_links()
	, func(_code, err):
		if teacher_request_button:
			teacher_request_button.disabled = false
		teacher_link_status_label.text = err if err != "" else "Unable to send teacher request."
	)


func _fetch_billing_status():
	var data = {"username": GameManager.player_username}
	NetworkManager.post_request("/get_billing_status", data, _on_billing_loaded, func(code, err):
		_set_tutoring_access_state(false, "Unable to verify tutoring access right now.")
		if billing_access_label:
			billing_access_label.text = "Billing status unavailable."
	)


func _find_plan_summary(response: Dictionary, plan_code: String) -> Dictionary:
	for plan in response.get("plans", []):
		if str(plan.get("plan_code", "")) == plan_code:
			return plan
	return {}


func _format_price_cents(price_cents) -> String:
	return "$%.2f/mo" % (float(price_cents) / 100.0)


func _format_currency_cents(price_cents) -> String:
	return "$%.2f" % (float(price_cents) / 100.0)


func _format_cap_usage(used_value, cap_value) -> String:
	if cap_value == null:
		return str(used_value)
	return str(used_value) + "/" + str(cap_value)


func _on_billing_loaded(_code, response):
	if response == null:
		return

	var subscription_plan_code = str(response.get("subscription_plan_code", ""))
	var subscription_status = str(response.get("subscription_status", "inactive"))
	var effective_plan_code = str(response.get("effective_plan_code", subscription_plan_code))
	var current_plan = _find_plan_summary(response, effective_plan_code)
	var recommended_plan_code = str(response.get("recommended_plan_code", ""))
	var recommended_plan = _find_plan_summary(response, recommended_plan_code)
	var usage = response.get("usage", {})
	var access_source_label = str(response.get("access_source_label", ""))
	var access_source_type = str(response.get("access_source_type", ""))
	var active_subscription = subscription_plan_code != "" and subscription_status in ["active", "trialing", "past_due"]

	if billing_plan_label:
		if effective_plan_code == "":
			var recommended_name = str(recommended_plan.get("display_name", "No plan selected"))
			var recommended_price = ""
			if recommended_plan.has("monthly_price_cents"):
				recommended_price = " Recommended: " + recommended_name + " (" + _format_price_cents(recommended_plan["monthly_price_cents"]) + ")."
			billing_plan_label.text = "Subscription: none." + recommended_price
		else:
			var display_name = str(current_plan.get("display_name", effective_plan_code))
			var price_text = ""
			if current_plan.has("monthly_price_cents"):
				price_text = " " + _format_price_cents(current_plan["monthly_price_cents"])
			if access_source_type != "" and access_source_type != "subscription":
				billing_plan_label.text = "Access Plan: " + display_name + " via " + access_source_label + price_text
			else:
				billing_plan_label.text = "Subscription: " + display_name + " [" + subscription_status + "]" + price_text

	if billing_usage_label:
		var turns_text = _format_cap_usage(int(usage.get("tutor_turns_used", 0)), current_plan.get("monthly_tutor_turn_cap", null))
		var calls_text = _format_cap_usage(int(usage.get("llm_calls_used", 0)), current_plan.get("monthly_llm_call_cap", null))
		var cost_used = int(usage.get("estimated_cost_cents", 0))
		var cost_cap = current_plan.get("monthly_cost_cap_cents", null)
		var cost_text = _format_currency_cents(cost_used)
		if cost_cap != null:
			cost_text += " / " + _format_currency_cents(cost_cap)
		var model_text = str(response.get("active_hosted_model", ""))
		var usage_text = "Usage: turns " + turns_text + " | calls " + calls_text + " | hosted cost " + cost_text
		if model_text != "":
			usage_text += " | model " + model_text
		billing_usage_label.text = usage_text

	if billing_payment_label:
		var brand = str(response.get("payment_method_brand", ""))
		var last4 = str(response.get("payment_method_last4", ""))
		if brand != "" and last4 != "":
			billing_payment_label.text = "Payment Method: " + brand.capitalize() + " ending in " + last4
		else:
			billing_payment_label.text = "Payment Method: not available yet"

	if billing_access_label:
		if response.get("access_allowed", true):
			var access_message = "Tutoring access is active."
			if access_source_label != "":
				access_message = "Tutoring access is active via " + access_source_label + "."
			var grant_expires_at = response.get("access_grant_expires_at", null)
			if grant_expires_at != null and str(grant_expires_at) != "":
				access_message += " Expires: " + str(grant_expires_at) + "."
			billing_access_label.text = access_message
			_set_tutoring_access_state(true, access_message)
		else:
			var blocked_message = str(response.get("access_reason", "Tutoring access requires an active subscription or access code."))
			billing_access_label.text = blocked_message
			_set_tutoring_access_state(false, blocked_message)

	if billing_hosted_button:
		billing_hosted_button.disabled = not bool(response.get("checkout_available", false)) or active_subscription
	if billing_byok_button:
		billing_byok_button.disabled = not bool(response.get("checkout_available", false)) or active_subscription or not bool(response.get("uses_personal_key", false))
	if billing_manage_button:
		billing_manage_button.disabled = not bool(response.get("portal_available", false))


func _redeem_profile_access_code():
	if profile_status_label == null or billing_access_code_input == null:
		return

	var code_text = billing_access_code_input.text.strip_edges()
	if code_text == "":
		profile_status_label.text = "Enter an access code first."
		return

	if billing_access_code_button:
		billing_access_code_button.disabled = true
	profile_status_label.text = "Redeeming access code..."

	var payload = {
		"username": GameManager.player_username,
		"code": code_text
	}
	NetworkManager.post_request("/redeem_access_code", payload, func(_code, response):
		if billing_access_code_input:
			billing_access_code_input.text = ""
		if billing_access_code_button:
			billing_access_code_button.disabled = false
		profile_status_label.text = str(response.get("message", "Access code accepted."))
		_fetch_billing_status()
	, func(code, err):
		if billing_access_code_button:
			billing_access_code_button.disabled = false
		profile_status_label.text = err if err != "" else "Unable to redeem access code."
	)


func _admin_parse_optional_positive_int(input: LineEdit, field_name: String) -> Dictionary:
	if input == null:
		return {"ok": true, "value": null}

	var trimmed = input.text.strip_edges()
	if trimmed == "":
		return {"ok": true, "value": null}
	if not trimmed.is_valid_int():
		return {"ok": false, "message": field_name + " must be a whole number."}

	var value = int(trimmed)
	if value < 1:
		return {"ok": false, "message": field_name + " must be at least 1."}
	return {"ok": true, "value": value}


func _admin_parse_required_positive_int(input: LineEdit, field_name: String, fallback: int) -> Dictionary:
	if input == null:
		return {"ok": true, "value": fallback}

	var trimmed = input.text.strip_edges()
	if trimmed == "":
		return {"ok": true, "value": fallback}
	if not trimmed.is_valid_int():
		return {"ok": false, "message": field_name + " must be a whole number."}

	var value = int(trimmed)
	if value < 1:
		return {"ok": false, "message": field_name + " must be at least 1."}
	return {"ok": true, "value": value}


func _copy_admin_code_to_clipboard():
	if admin_last_created_code_input == null or admin_status_label == null:
		return
	if admin_last_created_code_input.text.strip_edges() == "":
		admin_status_label.text = "No code available to copy yet."
		return
	DisplayServer.clipboard_set(admin_last_created_code_input.text)
	admin_status_label.text = "Last created code copied to clipboard."


func _create_admin_access_code():
	if not _is_admin_user() or admin_status_label == null:
		return

	var days_result = _admin_parse_optional_positive_int(admin_code_days_input, "Expires in days")
	if not bool(days_result.get("ok", false)):
		admin_status_label.text = str(days_result.get("message", "Invalid expiration"))
		return

	var redemptions_result = _admin_parse_required_positive_int(admin_code_max_redemptions_input, "Max redemptions", 1)
	if not bool(redemptions_result.get("ok", false)):
		admin_status_label.text = str(redemptions_result.get("message", "Invalid max redemptions"))
		return

	admin_status_label.text = "Creating access code..."
	var payload = {
		"username": GameManager.player_username,
		"plan_code": _admin_selected_plan_code(admin_code_plan_option),
		"assigned_username": admin_code_assigned_input.text.strip_edges(),
		"duration_days": days_result.get("value"),
		"max_redemptions": int(redemptions_result.get("value", 1)),
		"notes": admin_code_notes_input.text.strip_edges()
	}
	var custom_code = admin_code_custom_input.text.strip_edges()
	if custom_code != "":
		payload["code"] = custom_code

	NetworkManager.post_request("/admin/create_access_code", payload, func(_code, response):
		var promo_code = response.get("promo_code", {})
		var assigned_username_value = promo_code.get("assigned_username", null)
		var assigned_username = "general use" if assigned_username_value == null or str(assigned_username_value) == "" else str(assigned_username_value)
		if admin_last_created_code_input:
			admin_last_created_code_input.text = str(response.get("code", ""))
		if admin_status_label:
			admin_status_label.text = "Created access code for " + assigned_username + "."
		if admin_code_custom_input:
			admin_code_custom_input.text = ""
		if admin_code_notes_input:
			admin_code_notes_input.text = ""
		_refresh_admin_lists()
	, func(code, err):
		if admin_status_label:
			admin_status_label.text = err if err != "" else "Unable to create access code."
	)


func _grant_admin_access():
	if not _is_admin_user() or admin_status_label == null:
		return

	var target_username = admin_grant_username_input.text.strip_edges() if admin_grant_username_input else ""
	if target_username == "":
		admin_status_label.text = "Target username is required."
		return

	var days_result = _admin_parse_optional_positive_int(admin_grant_days_input, "Expires in days")
	if not bool(days_result.get("ok", false)):
		admin_status_label.text = str(days_result.get("message", "Invalid expiration"))
		return

	admin_status_label.text = "Granting access..."
	var payload = {
		"username": GameManager.player_username,
		"target_username": target_username,
		"plan_code": _admin_selected_plan_code(admin_grant_plan_option),
		"duration_days": days_result.get("value"),
		"notes": admin_grant_notes_input.text.strip_edges()
	}
	NetworkManager.post_request("/admin/grant_access", payload, func(_code, response):
		if admin_status_label:
			admin_status_label.text = "Granted access to " + str(response.get("username", target_username)) + "."
		if admin_grant_notes_input:
			admin_grant_notes_input.text = ""
		_refresh_admin_lists()
	, func(code, err):
		if admin_status_label:
			admin_status_label.text = err if err != "" else "Unable to grant access."
	)


func _refresh_admin_lists():
	if not _is_admin_user():
		return
	_refresh_admin_code_list()
	_refresh_admin_grant_list()


func _refresh_admin_code_list():
	if admin_code_list == null:
		return

	var payload = {
		"username": GameManager.player_username,
		"assigned_username": admin_filter_username_input.text.strip_edges() if admin_filter_username_input else "",
		"include_revoked": false
	}
	NetworkManager.post_request("/admin/list_access_codes", payload, _on_admin_codes_loaded, func(code, err):
		if admin_status_label:
			admin_status_label.text = err if err != "" else "Unable to load access codes."
	)


func _refresh_admin_grant_list():
	if admin_grant_list == null:
		return

	var payload = {
		"username": GameManager.player_username,
		"target_username": admin_filter_username_input.text.strip_edges() if admin_filter_username_input else "",
		"include_revoked": false
	}
	NetworkManager.post_request("/admin/list_access_grants", payload, _on_admin_grants_loaded, func(code, err):
		if admin_status_label:
			admin_status_label.text = err if err != "" else "Unable to load access grants."
	)


func _on_admin_codes_loaded(_code, response):
	admin_code_entries = response.get("promo_codes", [])
	if admin_code_list == null:
		return

	admin_code_list.clear()
	for entry in admin_code_entries:
		admin_code_list.add_item(_format_admin_code_entry(entry))
	if admin_code_entries.is_empty():
		admin_code_list.add_item("No matching active access codes.")


func _on_admin_grants_loaded(_code, response):
	admin_grant_entries = response.get("grants", [])
	if admin_grant_list == null:
		return

	admin_grant_list.clear()
	for entry in admin_grant_entries:
		admin_grant_list.add_item(_format_admin_grant_entry(entry))
	if admin_grant_entries.is_empty():
		admin_grant_list.add_item("No matching active access grants.")


func _format_admin_code_entry(entry: Dictionary) -> String:
	var code_prefix = str(entry.get("code_prefix", ""))
	var assigned_username_value = entry.get("assigned_username", null)
	var assigned_username = "" if assigned_username_value == null else str(assigned_username_value)
	if assigned_username == "":
		assigned_username = "any user"
	var plan_code = str(entry.get("plan_code", ""))
	var max_redemptions = int(entry.get("max_redemptions", 1))
	var redemption_count = int(entry.get("redemption_count", 0))
	var expires_at = entry.get("expires_at", null)
	var expires_text = "no expiry" if expires_at == null or str(expires_at) == "" else str(expires_at)
	return "#" + str(entry.get("id", 0)) + " " + code_prefix + " -> " + assigned_username + " | " + plan_code + " | " + str(redemption_count) + "/" + str(max_redemptions) + " | " + expires_text


func _format_admin_grant_entry(entry: Dictionary) -> String:
	var username = str(entry.get("username", ""))
	var plan_code = str(entry.get("plan_code", ""))
	var source_type = str(entry.get("source_type", "manual"))
	var expires_at = entry.get("expires_at", null)
	var expires_text = "no expiry" if expires_at == null or str(expires_at) == "" else str(expires_at)
	return "#" + str(entry.get("id", 0)) + " " + username + " | " + plan_code + " | " + source_type + " | " + expires_text


func _revoke_selected_admin_code():
	if admin_code_list == null or admin_status_label == null:
		return

	var selected = admin_code_list.get_selected_items()
	if selected.size() == 0 or admin_code_entries.is_empty():
		admin_status_label.text = "Select an access code first."
		return

	var index = int(selected[0])
	if index < 0 or index >= admin_code_entries.size():
		admin_status_label.text = "Select a valid access code."
		return

	var entry = admin_code_entries[index]
	var payload = {
		"username": GameManager.player_username,
		"promo_code_id": int(entry.get("id", 0)),
		"reason": admin_revoke_reason_input.text.strip_edges() if admin_revoke_reason_input else "",
		"revoke_grants": true
	}
	admin_status_label.text = "Revoking access code..."
	NetworkManager.post_request("/admin/revoke_access_code", payload, func(_code, response):
		admin_status_label.text = "Revoked access code #" + str(response.get("id", 0)) + "."
		_refresh_admin_lists()
	, func(code, err):
		admin_status_label.text = err if err != "" else "Unable to revoke access code."
	)


func _revoke_selected_admin_grant():
	if admin_grant_list == null or admin_status_label == null:
		return

	var selected = admin_grant_list.get_selected_items()
	if selected.size() == 0 or admin_grant_entries.is_empty():
		admin_status_label.text = "Select an access grant first."
		return

	var index = int(selected[0])
	if index < 0 or index >= admin_grant_entries.size():
		admin_status_label.text = "Select a valid access grant."
		return

	var entry = admin_grant_entries[index]
	var payload = {
		"username": GameManager.player_username,
		"access_grant_id": int(entry.get("id", 0)),
		"reason": admin_revoke_reason_input.text.strip_edges() if admin_revoke_reason_input else ""
	}
	admin_status_label.text = "Revoking access grant..."
	NetworkManager.post_request("/admin/revoke_access_grant", payload, func(_code, response):
		admin_status_label.text = "Revoked access grant #" + str(response.get("id", 0)) + "."
		_refresh_admin_lists()
	, func(code, err):
		admin_status_label.text = err if err != "" else "Unable to revoke access grant."
	)


func _start_hosted_checkout():
	_start_checkout("hosted_monthly")


func _start_byok_checkout():
	_start_checkout("byok_monthly")


func _start_checkout(plan_code: String):
	if profile_status_label == null:
		return

	profile_status_label.text = "Opening secure checkout..."
	var payload = {
		"username": GameManager.player_username,
		"plan_code": plan_code
	}
	NetworkManager.post_request("/create_checkout_session", payload, _on_checkout_session_created, func(code, err):
		if profile_status_label:
			profile_status_label.text = "Unable to open checkout."
	)


func _on_checkout_session_created(_code, response):
	if response == null:
		return

	var url = str(response.get("url", ""))
	if url != "":
		OS.shell_open(url)
		if profile_status_label:
			profile_status_label.text = "Checkout opened in your browser."


func _open_billing_portal():
	if profile_status_label == null:
		return

	profile_status_label.text = "Opening billing portal..."
	var payload = {"username": GameManager.player_username}
	NetworkManager.post_request("/create_billing_portal_session", payload, _on_billing_portal_created, func(code, err):
		if profile_status_label:
			profile_status_label.text = "Unable to open billing portal."
	)


func _on_billing_portal_created(_code, response):
	if response == null:
		return

	var url = str(response.get("url", ""))
	if url != "":
		OS.shell_open(url)
		if profile_status_label:
			profile_status_label.text = "Billing portal opened in your browser."


func _save_profile_settings():
	if profile_status_label == null:
		return

	profile_status_label.text = "Saving profile..."

	var payload = {
		"username": GameManager.player_username,
		"email": profile_email_input.text.strip_edges(),
		"avatar_id": "schoolboy" if profile_avatar_option.selected == 1 else "schoolgirl",
		"openai_api_key": profile_openai_key_input.text.strip_edges(),
		"clear_openai_api_key": profile_clear_key_check.button_pressed
	}

	NetworkManager.post_request("/update_profile", payload, _on_profile_saved, func(code, err):
		if profile_status_label:
			profile_status_label.text = "Save failed."
	)


func _on_profile_saved(_code, response):
	if response == null:
		return

	GameManager.player_avatar_id = str(response.get("avatar_id", "schoolgirl"))
	if player and is_instance_valid(player):
		player.apply_profile_avatar(GameManager.player_avatar_id)

	if profile_key_hint_label:
		if response.get("has_personal_openai_key", false):
			profile_key_hint_label.text = "Saved personal key: " + str(response.get("openai_key_hint", "saved"))
		else:
			profile_key_hint_label.text = "No personal key saved."

	if profile_openai_key_input:
		profile_openai_key_input.text = ""
	if profile_clear_key_check:
		profile_clear_key_check.button_pressed = false
	if profile_status_label:
		profile_status_label.text = "Profile updated."

	fetch_stats()
	_fetch_billing_status()

func setup_full_library():
	print("Loading Library Asset from: res://assets/models/Library/library.glb")

	# Environment shell
	var lib_model = load("res://assets/models/Library/library.glb").instantiate()
	lib_model.scale = Vector3(1, 1, 1)
	add_child(lib_model)

	# Safety floor (in case imported mesh collisions are thin/missing)
	var floor_body = StaticBody3D.new()
	var floor_col = CollisionShape3D.new()
	var floor_shape = BoxShape3D.new()
	floor_shape.size = Vector3(100, 1, 100)
	floor_col.shape = floor_shape
	floor_col.position = Vector3(0, -0.5, 0)
	floor_body.add_child(floor_col)
	add_child(floor_body)
	_setup_play_area_collision()

	# Lighting tuned for readable shelves/cards/books.
	var env = WorldEnvironment.new()
	var environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.06, 0.07, 0.09)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.84, 0.89, 1.0)
	environment.ambient_light_energy = 0.75
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.glow_enabled = true
	environment.glow_strength = 0.55
	env.environment = environment
	add_child(env)

	var light = DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-38, 34, 0)
	light.shadow_enabled = true
	light.light_energy = 1.1
	light.light_color = Color(1.0, 0.95, 0.88)
	add_child(light)

	var center_fill = OmniLight3D.new()
	center_fill.omni_range = 48.0
	center_fill.light_energy = 2.15
	center_fill.position = Vector3(0, 8.5, 0)
	center_fill.light_color = Color(0.9, 0.92, 1.0)
	add_child(center_fill)

	var entry_fill = OmniLight3D.new()
	entry_fill.omni_range = 36.0
	entry_fill.light_energy = 1.7
	entry_fill.position = Vector3(0, 4, 16)
	entry_fill.light_color = Color(1.0, 0.9, 0.78)
	add_child(entry_fill)

	_setup_grand_hall()

	# Subject sections
	# Compact cluster near the spawn lane so all shelves stay visible and navigable.
	for subject in SUBJECT_ORDER:
		if not SHELF_LAYOUT.has(subject):
			continue
		var shelf_pos: Vector3 = SHELF_LAYOUT[subject]
		var shelf_yaw = _yaw_toward_point(shelf_pos, SHELF_FOCUS_POINT)
		setup_section(subject, shelf_pos, shelf_yaw)

	_setup_subject_beacons()
	setup_college_portal()
	_setup_focus_ring()
	_setup_selection_hud()


func _setup_grand_hall():
	var central_plaza = Node3D.new()
	central_plaza.name = "CentralPlaza"
	central_plaza.position = Vector3(0.0, 0.02, 2.35)
	add_child(central_plaza)

	var plaza_body = StaticBody3D.new()
	central_plaza.add_child(plaza_body)

	var plaza_collision = CollisionShape3D.new()
	var plaza_shape = CylinderShape3D.new()
	plaza_shape.radius = 2.55
	plaza_shape.height = 0.1
	plaza_collision.shape = plaza_shape
	plaza_collision.position = Vector3(0.0, 0.05, 0.0)
	plaza_body.add_child(plaza_collision)

	var floor_disc = MeshInstance3D.new()
	var disc_mesh = CylinderMesh.new()
	disc_mesh.top_radius = 2.55
	disc_mesh.bottom_radius = 2.75
	disc_mesh.height = 0.08
	floor_disc.mesh = disc_mesh
	var disc_mat = _build_material(Color(0.08, 0.1, 0.14), 0.18, 0.02)
	disc_mat.emission_enabled = true
	disc_mat.emission = Color(0.3, 0.56, 0.92)
	disc_mat.emission_energy_multiplier = 0.45
	floor_disc.material_override = disc_mat
	central_plaza.add_child(floor_disc)

	var inner_ring = MeshInstance3D.new()
	var ring_mesh = CylinderMesh.new()
	ring_mesh.top_radius = 1.9
	ring_mesh.bottom_radius = 1.9
	ring_mesh.height = 0.02
	inner_ring.mesh = ring_mesh
	inner_ring.position = Vector3(0.0, 0.06, 0.0)
	var ring_mat = _build_material(Color(0.62, 0.86, 1.0), 0.08, 0.0)
	ring_mat.emission_enabled = true
	ring_mat.emission = Color(0.62, 0.86, 1.0)
	ring_mat.emission_energy_multiplier = 1.0
	inner_ring.material_override = ring_mat
	central_plaza.add_child(inner_ring)
	_register_animated_hall_node(inner_ring, "pulse")

	var title = Label3D.new()
	title.text = "ADAPTIVE TUTOR"
	title.font_size = 60
	title.outline_size = 14
	title.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	title.position = Vector3(0.0, 3.95, 8.8)
	title.modulate = Color(0.96, 0.98, 1.0, 0.9)
	add_child(title)
	_register_animated_hall_node(title, "float")

	var subtitle = Label3D.new()
	subtitle.text = "Choose a shelf or resume your path from the center aisle"
	subtitle.font_size = 20
	subtitle.outline_size = 8
	subtitle.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	subtitle.position = Vector3(0.0, 3.45, 8.95)
	subtitle.modulate = Color(0.74, 0.85, 0.98, 0.8)
	add_child(subtitle)
	_register_animated_hall_node(subtitle, "float")

	var avatar_fill_light = OmniLight3D.new()
	avatar_fill_light.position = Vector3(0.0, 1.95, 1.9)
	avatar_fill_light.omni_range = 8.5
	avatar_fill_light.light_energy = 2.0
	avatar_fill_light.light_color = Color(1.0, 0.94, 0.86)
	central_plaza.add_child(avatar_fill_light)

	var avatar_rim_light = OmniLight3D.new()
	avatar_rim_light.position = Vector3(0.0, 2.1, -1.7)
	avatar_rim_light.omni_range = 6.8
	avatar_rim_light.light_energy = 0.95
	avatar_rim_light.light_color = Color(0.64, 0.82, 1.0)
	central_plaza.add_child(avatar_rim_light)

	for subject in SUBJECT_ORDER:
		var accent = _subject_theme(subject)["accent"]
		_create_floor_ribbon(Vector3(0.0, 0.03, 2.35), SHELF_LAYOUT[subject] + Vector3(0.0, 0.03, 0.9), accent)


func _setup_subject_beacons():
	for subject in SUBJECT_ORDER:
		if not SHELF_LAYOUT.has(subject):
			continue

		var theme = _subject_theme(subject)
		var accent: Color = theme["accent"]
		var base: Color = theme["base"]
		var anchor = SHELF_LAYOUT[subject] + Vector3(0.0, 0.0, 2.05)

		var mast = MeshInstance3D.new()
		var mast_mesh = CylinderMesh.new()
		mast_mesh.top_radius = 0.09
		mast_mesh.bottom_radius = 0.12
		mast_mesh.height = 3.4
		mast.mesh = mast_mesh
		mast.position = anchor + Vector3(0.0, 1.7, 0.0)
		var mast_mat = _build_material(base.darkened(0.32), 0.2, 0.05)
		mast_mat.emission_enabled = true
		mast_mat.emission = accent * 0.28
		mast_mat.emission_energy_multiplier = 0.55
		mast.material_override = mast_mat
		add_child(mast)

		var halo = MeshInstance3D.new()
		var halo_mesh = CylinderMesh.new()
		halo_mesh.top_radius = 0.58
		halo_mesh.bottom_radius = 0.58
		halo_mesh.height = 0.05
		halo.mesh = halo_mesh
		halo.position = anchor + Vector3(0.0, 2.7, 0.0)
		var halo_mat = _build_material(accent, 0.04, 0.0)
		halo_mat.emission_enabled = true
		halo_mat.emission = accent
		halo_mat.emission_energy_multiplier = 1.25
		halo.material_override = halo_mat
		add_child(halo)
		_register_animated_hall_node(halo, "ring")

		var orb = MeshInstance3D.new()
		var orb_mesh = SphereMesh.new()
		orb_mesh.radius = 0.18
		orb_mesh.height = 0.36
		orb.mesh = orb_mesh
		orb.position = anchor + Vector3(0.0, 3.05, 0.0)
		var orb_mat = _build_material(accent.lightened(0.2), 0.03, 0.0)
		orb_mat.emission_enabled = true
		orb_mat.emission = accent
		orb_mat.emission_energy_multiplier = 1.6
		orb.material_override = orb_mat
		add_child(orb)
		_register_animated_hall_node(orb, "hover")

		var sign = Label3D.new()
		sign.text = subject.to_upper() + "\n" + BEACON_TEXT[subject]
		sign.font_size = 36
		sign.outline_size = 10
		sign.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
		sign.position = anchor + Vector3(0.0, 3.65, 0.0)
		sign.modulate = Color(1.0, 1.0, 1.0, 0.95)
		add_child(sign)
		_register_animated_hall_node(sign, "float")


func _create_floor_ribbon(from: Vector3, to: Vector3, accent: Color):
	var ribbon = MeshInstance3D.new()
	var ribbon_mesh = BoxMesh.new()
	var ribbon_length = from.distance_to(to)
	ribbon_mesh.size = Vector3(0.24, 0.03, ribbon_length)
	ribbon.mesh = ribbon_mesh
	ribbon.position = (from + to) * 0.5
	ribbon.look_at(Vector3(to.x, ribbon.position.y, to.z), Vector3.UP)
	ribbon.rotate_y(PI)
	var ribbon_mat = _build_material(accent.darkened(0.22), 0.06, 0.0)
	ribbon_mat.emission_enabled = true
	ribbon_mat.emission = accent
	ribbon_mat.emission_energy_multiplier = 0.9
	ribbon.material_override = ribbon_mat
	add_child(ribbon)
	_register_animated_hall_node(ribbon, "pulse")


func _register_animated_hall_node(node: Node, style: String):
	if node == null:
		return
	node.set_meta("hall_anim_style", style)
	if node is Node3D:
		node.set_meta("hall_base_position", node.position)
		node.set_meta("hall_base_scale", node.scale)
	if node is Label3D:
		node.set_meta("hall_base_modulate", node.modulate)
	node.set_meta("hall_phase", randf() * TAU)
	animated_hall_nodes.append(node)


func _update_hall_animation(delta):
	for hall_node in animated_hall_nodes:
		if hall_node == null or not is_instance_valid(hall_node):
			continue

		var phase = float(hall_node.get_meta("hall_phase")) if hall_node.has_meta("hall_phase") else 0.0
		var style = str(hall_node.get_meta("hall_anim_style")) if hall_node.has_meta("hall_anim_style") else "float"
		var time_value = selection_clock + phase

		if hall_node is Node3D and hall_node.has_meta("hall_base_position"):
			var base_position: Vector3 = hall_node.get_meta("hall_base_position")
			var base_scale: Vector3 = hall_node.get_meta("hall_base_scale") if hall_node.has_meta("hall_base_scale") else Vector3.ONE

			match style:
				"hover":
					hall_node.position = base_position + Vector3(0.0, sin(time_value * 1.8) * 0.08, 0.0)
				"ring":
					hall_node.position = base_position + Vector3(0.0, sin(time_value * 1.2) * 0.04, 0.0)
					hall_node.rotation.y += delta * 0.65
					hall_node.scale = base_scale * (1.0 + sin(time_value * 2.2) * 0.04)
				"pulse":
					hall_node.scale = base_scale * (1.0 + sin(time_value * 2.8) * 0.035)
				_:
					hall_node.position = base_position + Vector3(0.0, sin(time_value * 1.1) * 0.05, 0.0)

		if hall_node is Label3D and hall_node.has_meta("hall_base_modulate"):
			var base_modulate: Color = hall_node.get_meta("hall_base_modulate")
			hall_node.modulate = Color(base_modulate.r, base_modulate.g, base_modulate.b, clamp(base_modulate.a + sin(time_value * 1.6) * 0.08, 0.6, 1.0))

func setup_section(category: String, pos: Vector3, rot_deg: float = 0.0):
	var theme = _subject_theme(category)
	var base_color: Color = theme["base"]
	var accent_color: Color = theme["accent"]

	var shelf_area = StaticBody3D.new()
	shelf_area.name = category + "Shelf"
	shelf_area.position = pos
	shelf_area.rotation_degrees = Vector3(0, rot_deg, 0)
	add_child(shelf_area)

	var col = CollisionShape3D.new()
	var shape = BoxShape3D.new()
	shape.size = Vector3(6.4, 4.8, 1.2)
	col.shape = shape
	col.position = Vector3(0, 2.1, -0.45)
	shelf_area.add_child(col)

	_add_shelf_structure(shelf_area, base_color, accent_color)
	_create_subject_selector_card(shelf_area, category, base_color, accent_color)
	_create_shelf_progress_display(shelf_area, category, accent_color)

	for i in range(BOOKS_PER_SUBJECT):
		var level = i + 1
		var row = int(i / BOOK_COLUMNS)
		var col_idx = i % BOOK_COLUMNS
		var x_pos = (float(col_idx) - ((BOOK_COLUMNS - 1) * 0.5)) * BOOK_SPACING_X
		var y_pos = BOOK_BASE_Y + (float(row) * BOOK_ROW_GAP)

		var book_area = _create_textbook(category, level, base_color, accent_color)
		book_area.position = Vector3(x_pos, y_pos, 0.28)
		book_area.rotation_degrees = Vector3(0, randf_range(-8.0, 8.0), 0)
		book_area.set_meta("rest_y", y_pos)
		book_area.set_meta("book_level", level)
		book_area.set_meta("book_subject", category)

		shelf_area.add_child(book_area)
		book_nodes.append(book_area)
		_apply_book_emphasis(book_area)

func _book_emphasis_for_level(level: int) -> String:
	var grade_focus = clamp(profile_grade_level, 1, BOOKS_PER_SUBJECT)
	var delta = abs(level - grade_focus)
	var role = str(profile_role).to_lower()

	if delta == 0:
		return "focus"

	if role == "teacher" or role == "admin":
		if delta <= 2:
			return "mid"
		return "dim"

	if delta == 1:
		return "mid"

	return "dim"

func _apply_book_emphasis(book_area):
	if book_area == null or not is_instance_valid(book_area):
		return

	var level = 1
	if book_area.has_meta("book_level"):
		level = int(book_area.get_meta("book_level"))

	var emphasis_state = _book_emphasis_for_level(level)
	book_area.set_meta("emphasis_state", emphasis_state)
	book_area.set_meta("adaptive_dimmed", emphasis_state == "dim")

	if hover_target != book_area:
		_set_interactable_style(book_area, false, emphasis_state == "dim")

func _refresh_book_emphasis():
	for book in book_nodes:
		if not is_instance_valid(book):
			continue
		_apply_book_emphasis(book)

func _yaw_toward_point(from: Vector3, to: Vector3) -> float:
	var dir = (to - from)
	if dir.length_squared() <= 0.0001:
		return 0.0
	dir = dir.normalized()
	return rad_to_deg(atan2(dir.x, dir.z))

func _subject_theme(subject: String) -> Dictionary:
	if SUBJECT_THEME.has(subject):
		return SUBJECT_THEME[subject]
	return {
		"base": Color(0.3, 0.32, 0.37),
		"accent": Color(0.8, 0.8, 0.8),
		"code": "SUB"
	}

func _build_material(albedo: Color, roughness: float = 0.58, metallic: float = 0.03) -> StandardMaterial3D:
	var material = StandardMaterial3D.new()
	material.albedo_color = albedo
	material.roughness = roughness
	material.metallic = metallic
	return material

func _add_shelf_structure(shelf_area: Node3D, base_color: Color, accent_color: Color):
	var back_panel = MeshInstance3D.new()
	var back_panel_mesh = BoxMesh.new()
	back_panel_mesh.size = Vector3(6.2, 4.45, 0.35)
	back_panel.mesh = back_panel_mesh
	back_panel.position = Vector3(0, 2.15, -0.58)
	var back_mat = _build_material(base_color.darkened(0.63), 0.95, 0.0)
	back_panel.material_override = back_mat
	shelf_area.add_child(back_panel)

	for plank_y in [0.75, 2.0]:
		var plank = MeshInstance3D.new()
		var plank_mesh = BoxMesh.new()
		plank_mesh.size = Vector3(5.55, 0.1, 1.05)
		plank.mesh = plank_mesh
		plank.position = Vector3(0, plank_y, 0.0)
		var plank_mat = _build_material(base_color.darkened(0.44), 0.82, 0.01)
		plank.material_override = plank_mat
		shelf_area.add_child(plank)

	var side_left = MeshInstance3D.new()
	var side_left_mesh = BoxMesh.new()
	side_left_mesh.size = Vector3(0.16, 4.2, 1.02)
	side_left.mesh = side_left_mesh
	side_left.position = Vector3(-2.85, 2.04, -0.03)
	side_left.material_override = _build_material(base_color.darkened(0.38), 0.8, 0.01)
	shelf_area.add_child(side_left)

	var side_right = MeshInstance3D.new()
	var side_right_mesh = BoxMesh.new()
	side_right_mesh.size = Vector3(0.16, 4.2, 1.02)
	side_right.mesh = side_right_mesh
	side_right.position = Vector3(2.85, 2.04, -0.03)
	side_right.material_override = _build_material(base_color.darkened(0.38), 0.8, 0.01)
	shelf_area.add_child(side_right)

	var header_light = MeshInstance3D.new()
	var header_light_mesh = BoxMesh.new()
	header_light_mesh.size = Vector3(4.8, 0.11, 0.05)
	header_light.mesh = header_light_mesh
	header_light.position = Vector3(0, 3.72, 0.38)
	var header_mat = _build_material(accent_color, 0.12, 0.0)
	header_mat.emission_enabled = true
	header_mat.emission = accent_color
	header_mat.emission_energy_multiplier = 0.6
	header_light.material_override = header_mat
	shelf_area.add_child(header_light)

func _create_subject_selector_card(shelf_area: Node3D, category: String, base_color: Color, accent_color: Color):
	var selector = Area3D.new()
	selector.name = category + "Selector"
	selector.position = Vector3(0, 0.53, 1.34)
	selector.set_meta("shelf_category", category)
	selector.set_meta("accent_color", accent_color)
	selector.add_to_group("interactable")
	shelf_area.add_child(selector)

	var selector_mesh = MeshInstance3D.new()
	var selector_box = BoxMesh.new()
	selector_box.size = Vector3(3.8, 1.08, 0.15)
	selector_mesh.mesh = selector_box
	var selector_mat = _build_material(base_color.darkened(0.12), 0.32, 0.05)
	selector_mat.emission_enabled = true
	selector_mat.emission = accent_color * 0.11
	selector_mat.emission_energy_multiplier = 0.32
	selector_mat.set_meta("base_albedo", selector_mat.albedo_color)
	selector_mesh.material_override = selector_mat
	selector.add_child(selector_mesh)

	var selector_col = CollisionShape3D.new()
	var selector_shape = BoxShape3D.new()
	selector_shape.size = Vector3(3.9, 1.12, 0.24)
	selector_col.shape = selector_shape
	selector.add_child(selector_col)

	var title = Label3D.new()
	title.text = category + " SHELF"
	title.font_size = 40
	title.outline_size = 10
	title.position = Vector3(0, 0.18, 0.09)
	title.modulate = Color(1.0, 1.0, 1.0, 0.95)
	selector.add_child(title)

	var hint = Label3D.new()
	hint.text = "Click to resume"
	hint.font_size = 24
	hint.outline_size = 6
	hint.position = Vector3(0, -0.11, 0.09)
	hint.modulate = Color(1.0, 1.0, 1.0, 0.72)
	selector.add_child(hint)

	var progress_label = Label3D.new()
	progress_label.text = "0% complete"
	progress_label.font_size = 22
	progress_label.outline_size = 5
	progress_label.position = Vector3(0, -0.36, 0.09)
	progress_label.modulate = accent_color.lightened(0.4)
	selector.add_child(progress_label)
	subject_selector_progress_labels[category] = progress_label

	selector.set_meta("display_mesh", selector_mesh)
	selector.set_meta("display_hint_label", hint)
	selector.set_meta("display_code_label", progress_label)
	selector.set_meta("display_level_label", title)
	selector.set_meta("base_scale", selector_mesh.scale)

func _create_textbook(category: String, level: int, base_color: Color, accent_color: Color) -> Area3D:
	var book_area = Area3D.new()
	book_area.name = category + "_Book_" + str(level)
	book_area.set_meta("topic", category + " " + str(level))
	book_area.set_meta("accent_color", accent_color)
	book_area.add_to_group("interactable")
	book_area.set_meta("float_phase", randf() * TAU)

	var body_mesh = MeshInstance3D.new()
	var body = BoxMesh.new()
	body.size = Vector3(0.43, 0.6, 0.84)
	body_mesh.mesh = body
	var variation = randf_range(-0.22, 0.2)
	var cover_color = base_color
	if variation > 0.0:
		cover_color = base_color.lightened(variation)
	else:
		cover_color = base_color.darkened(-variation)
	var book_material = _build_material(cover_color, 0.32, 0.03)
	book_material.emission_enabled = true
	book_material.emission = accent_color * 0.06
	book_material.emission_energy_multiplier = 0.2
	book_material.set_meta("base_albedo", cover_color)
	body_mesh.material_override = book_material
	book_area.add_child(body_mesh)

	var stripe_mesh = MeshInstance3D.new()
	var stripe = BoxMesh.new()
	stripe.size = Vector3(0.44, 0.09, 0.86)
	stripe_mesh.mesh = stripe
	stripe_mesh.position = Vector3(0, 0.24, 0)
	stripe_mesh.material_override = _build_material(accent_color, 0.45, 0.0)
	book_area.add_child(stripe_mesh)

	var level_label = Label3D.new()
	level_label.text = str(level)
	level_label.font_size = 56
	level_label.outline_size = 10
	level_label.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	level_label.position = Vector3(0, 0.1, 0.51)
	level_label.modulate = Color(1.0, 1.0, 1.0, 0.92)
	book_area.add_child(level_label)

	var code_label = Label3D.new()
	code_label.text = _subject_theme(category)["code"]
	code_label.font_size = 24
	code_label.outline_size = 6
	code_label.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	code_label.position = Vector3(0, -0.2, 0.51)
	code_label.modulate = Color(1.0, 1.0, 1.0, 0.8)
	book_area.add_child(code_label)

	var b_col = CollisionShape3D.new()
	var b_shape = BoxShape3D.new()
	# Slightly larger hitbox so upper row books are easier to target.
	b_shape.size = Vector3(0.58, 0.82, 1.05)
	b_col.shape = b_shape
	book_area.add_child(b_col)

	book_area.set_meta("display_mesh", body_mesh)
	book_area.set_meta("display_level_label", level_label)
	book_area.set_meta("display_code_label", code_label)
	book_area.set_meta("base_scale", body_mesh.scale)
	book_area.set_meta("adaptive_dimmed", false)

	return book_area

func _create_shelf_progress_display(shelf_area: Node3D, category: String, accent_color: Color):
	var viewport = SubViewport.new()
	viewport.size = Vector2i(360, 74)
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS

	var root = Control.new()
	root.custom_minimum_size = Vector2(360, 74)
	viewport.add_child(root)

	var panel_bg = ColorRect.new()
	panel_bg.color = Color(0.0, 0.0, 0.0, 0.55)
	panel_bg.size = Vector2(360, 74)
	root.add_child(panel_bg)

	var title = Label.new()
	title.text = category + " progress"
	title.position = Vector2(12, 5)
	title.modulate = Color(1.0, 1.0, 1.0, 0.82)
	root.add_child(title)

	var progress = TextureProgressBar.new()
	progress.min_value = 0.0
	progress.max_value = 100.0
	progress.value = 0.0
	progress.texture_under = _create_img_tex(Color(0.15, 0.15, 0.18, 0.95), 326, 18)
	progress.texture_progress = _create_img_tex(accent_color, 326, 18)
	progress.position = Vector2(12, 32)
	progress.custom_minimum_size = Vector2(326, 18)
	root.add_child(progress)

	var percent = Label.new()
	percent.text = "0%"
	percent.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	percent.position = Vector2(280, 52)
	percent.size = Vector2(70, 18)
	percent.modulate = accent_color.lightened(0.25)
	root.add_child(percent)

	var display_plane = MeshInstance3D.new()
	var plane = PlaneMesh.new()
	plane.size = Vector2(2.95, 0.6)
	display_plane.mesh = plane
	display_plane.position = Vector3(0, 3.42, 0.62)
	var plane_mat = StandardMaterial3D.new()
	plane_mat.albedo_texture = viewport.get_texture()
	plane_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	plane_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	plane_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	display_plane.material_override = plane_mat

	shelf_area.add_child(viewport)
	shelf_area.add_child(display_plane)

	shelf_progress_bars[category] = progress
	shelf_progress_labels[category] = percent


func _setup_play_area_collision():
	_add_boundary_wall(Vector3(0.0, 2.8, -2.4), Vector3(20.0, 5.6, 0.45))
	_add_boundary_wall(Vector3(0.0, 2.8, 16.25), Vector3(20.0, 5.6, 0.45))
	_add_boundary_wall(Vector3(-9.4, 2.8, 6.9), Vector3(0.45, 5.6, 20.0))
	_add_boundary_wall(Vector3(9.4, 2.8, 6.9), Vector3(0.45, 5.6, 20.0))


func _add_boundary_wall(center: Vector3, size: Vector3):
	var wall = StaticBody3D.new()
	var shape = CollisionShape3D.new()
	var box = BoxShape3D.new()
	box.size = size
	shape.shape = box
	shape.position = center
	wall.add_child(shape)
	add_child(wall)

func _setup_focus_ring():
	focus_ring = MeshInstance3D.new()
	var ring = CylinderMesh.new()
	ring.top_radius = 0.46
	ring.bottom_radius = 0.46
	ring.height = 0.03
	ring.radial_segments = 42
	focus_ring.mesh = ring
	focus_ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF

	focus_ring_material = StandardMaterial3D.new()
	focus_ring_material.albedo_color = Color(0.58, 0.86, 1.0, 0.35)
	focus_ring_material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	focus_ring_material.emission_enabled = true
	focus_ring_material.emission = Color(0.58, 0.86, 1.0)
	focus_ring_material.emission_energy_multiplier = 1.2
	focus_ring_material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	focus_ring_material.cull_mode = BaseMaterial3D.CULL_DISABLED
	focus_ring.material_override = focus_ring_material
	focus_ring.visible = false
	add_child(focus_ring)

func _setup_selection_hud():
	selection_canvas = CanvasLayer.new()
	selection_canvas.name = "SelectionCanvas"
	add_child(selection_canvas)

	selection_panel = PanelContainer.new()
	selection_panel.name = "SelectionPanel"
	selection_panel.anchor_left = 0.5
	selection_panel.anchor_right = 0.5
	selection_panel.anchor_top = 1.0
	selection_panel.anchor_bottom = 1.0
	selection_panel.offset_left = -250
	selection_panel.offset_right = 250
	selection_panel.offset_top = -155
	selection_panel.offset_bottom = -48
	selection_panel.visible = false

	selection_panel_style = StyleBoxFlat.new()
	selection_panel_style.bg_color = Color(0.03, 0.05, 0.08, 0.9)
	selection_panel_style.border_width_left = 2
	selection_panel_style.border_width_right = 2
	selection_panel_style.border_width_top = 2
	selection_panel_style.border_width_bottom = 2
	selection_panel_style.border_color = Color(0.55, 0.84, 1.0)
	selection_panel_style.corner_radius_top_left = 14
	selection_panel_style.corner_radius_top_right = 14
	selection_panel_style.corner_radius_bottom_left = 14
	selection_panel_style.corner_radius_bottom_right = 14
	selection_panel_style.content_margin_left = 16
	selection_panel_style.content_margin_right = 16
	selection_panel_style.content_margin_top = 12
	selection_panel_style.content_margin_bottom = 12
	selection_panel.add_theme_stylebox_override("panel", selection_panel_style)

	var info_vbox = VBoxContainer.new()
	info_vbox.add_theme_constant_override("separation", 4)
	selection_panel.add_child(info_vbox)

	selection_subject_label = Label.new()
	selection_subject_label.text = ""
	selection_subject_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	selection_subject_label.add_theme_font_size_override("font_size", 24)
	info_vbox.add_child(selection_subject_label)

	selection_topic_label = Label.new()
	selection_topic_label.text = ""
	selection_topic_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	selection_topic_label.modulate = Color(0.93, 0.96, 1.0, 0.92)
	info_vbox.add_child(selection_topic_label)

	selection_hint_label = Label.new()
	selection_hint_label.text = ""
	selection_hint_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	selection_hint_label.modulate = Color(1.0, 1.0, 1.0, 0.85)
	info_vbox.add_child(selection_hint_label)

	selection_mode_label = Label.new()
	selection_mode_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	selection_mode_label.modulate = Color(1.0, 1.0, 1.0, 0.66)
	info_vbox.add_child(selection_mode_label)

	selection_canvas.add_child(selection_panel)

func _update_books_animation(delta):
	for book in book_nodes:
		if not is_instance_valid(book):
			continue
		if not book.has_meta("rest_y") or not book.has_meta("float_phase"):
			continue

		var rest_y = float(book.get_meta("rest_y"))
		var phase = float(book.get_meta("float_phase"))
		var amplitude = 0.018
		if hover_target == book:
			amplitude = 0.045

		var target_y = rest_y + sin((selection_clock * 1.65) + phase) * amplitude
		var p = book.position
		p.y = lerp(p.y, target_y, clamp(delta * 7.0, 0.0, 1.0))
		book.position = p

func _update_selection_feedback(delta):
	if not player or not is_instance_valid(player):
		_set_hover_target(null)
		if selection_panel:
			selection_panel.visible = false
		if focus_ring:
			focus_ring.visible = false
		return

	var camera = player.get_node_or_null("Pivot/Camera3D")
	if camera == null:
		return

	var center = get_viewport().get_visible_rect().size * 0.5
	var from = camera.project_ray_origin(center)
	var normal = camera.project_ray_normal(center)
	from += normal * 1.5
	var to = from + normal * 14.0

	var query = PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = true
	# Include bodies so front shelves/walls block selection behind them.
	query.collide_with_bodies = true
	query.exclude = [player.get_rid()]

	var result = get_world_3d().direct_space_state.intersect_ray(query)
	var new_target = null
	if result and result.has("collider"):
		new_target = _resolve_interactable_target(result["collider"])

	if new_target != hover_target:
		_set_hover_target(new_target)

	if hover_target and is_instance_valid(hover_target):
		var accent = _target_accent(hover_target)
		_update_selection_panel(hover_target, accent)
		_update_focus_ring_material(accent)

		if focus_ring:
			var target_pos = hover_target.global_position + Vector3(0, -0.46, 0)
			if hover_target.has_meta("shelf_category") and not hover_target.has_meta("topic"):
				target_pos = hover_target.global_position + Vector3(0, -0.58, 0)
			var was_visible = focus_ring.visible
			focus_ring.visible = true
			if not was_visible:
				focus_ring.global_position = target_pos
			focus_ring.global_position = focus_ring.global_position.lerp(target_pos, clamp(delta * 12.0, 0.0, 1.0))
	else:
		if focus_ring:
			focus_ring.visible = false
		if selection_panel:
			selection_panel.visible = false

func _resolve_interactable_target(collider):
	if collider == null:
		return null
	if collider.has_meta("topic") or collider.has_meta("shelf_category"):
		return collider
	if collider.get_parent() and (collider.get_parent().has_meta("topic") or collider.get_parent().has_meta("shelf_category")):
		return collider.get_parent()
	return null

func _set_hover_target(target):
	if hover_target and is_instance_valid(hover_target):
		var was_dimmed = false
		if hover_target.has_meta("adaptive_dimmed"):
			was_dimmed = hover_target.get_meta("adaptive_dimmed")
		_set_interactable_style(hover_target, false, was_dimmed)

	hover_target = target

	if hover_target and is_instance_valid(hover_target):
		var is_dimmed = false
		if hover_target.has_meta("adaptive_dimmed"):
			is_dimmed = hover_target.get_meta("adaptive_dimmed")
		_set_interactable_style(hover_target, true, is_dimmed)

func _set_interactable_style(target, hovered: bool, adaptive_dimmed: bool = false):
	if target == null:
		return

	var emphasis_state = "normal"
	if target.has_meta("emphasis_state"):
		emphasis_state = str(target.get_meta("emphasis_state"))
	elif adaptive_dimmed:
		emphasis_state = "dim"

	var mesh = null
	if target.has_meta("display_mesh"):
		mesh = target.get_meta("display_mesh")
	elif target.has_node("MeshInstance3D"):
		mesh = target.get_node("MeshInstance3D")

	if mesh and is_instance_valid(mesh):
		var base_scale = Vector3.ONE
		if target.has_meta("base_scale"):
			base_scale = target.get_meta("base_scale")
		mesh.scale = base_scale * (1.12 if hovered else 1.0)

		if mesh.material_override and mesh.material_override is StandardMaterial3D:
			var mat = mesh.material_override as StandardMaterial3D
			var accent = _target_accent(target)
			mat.emission_enabled = true

			if mat.has_meta("base_albedo"):
				var base_albedo = mat.get_meta("base_albedo")
				var target_albedo = base_albedo
				if not hovered:
					match emphasis_state:
						"focus":
							target_albedo = base_albedo.lightened(0.14)
						"mid":
							target_albedo = base_albedo.darkened(0.08)
						"dim":
							target_albedo = base_albedo.darkened(0.62)
						_:
							target_albedo = base_albedo
				mat.albedo_color = target_albedo

			if hovered:
				mat.emission = accent
				mat.emission_energy_multiplier = 1.4
			else:
				match emphasis_state:
					"focus":
						mat.emission = accent * 0.35
						mat.emission_energy_multiplier = 0.92
					"mid":
						mat.emission = accent * 0.17
						mat.emission_energy_multiplier = 0.38
					"dim":
						mat.emission = accent * 0.03
						mat.emission_energy_multiplier = 0.1
					_:
						mat.emission = accent * 0.12
						mat.emission_energy_multiplier = 0.28

	for meta_key in ["display_level_label", "display_code_label", "display_hint_label"]:
		if not target.has_meta(meta_key):
			continue
		var label_node = target.get_meta(meta_key)
		if label_node and is_instance_valid(label_node):
			var label_alpha = 0.78
			match emphasis_state:
				"focus":
					label_alpha = 0.95
				"mid":
					label_alpha = 0.66
				"dim":
					label_alpha = 0.2
			if hovered:
				label_node.modulate = Color(1.0, 1.0, 1.0, 1.0)
			else:
				label_node.modulate = Color(1.0, 1.0, 1.0, label_alpha)

func _target_accent(target) -> Color:
	if target and target.has_meta("accent_color"):
		return target.get_meta("accent_color")
	return Color(0.58, 0.86, 1.0)

func _update_selection_panel(target, accent: Color):
	if selection_panel == null:
		return

	selection_panel.visible = true
	selection_panel_style.border_color = accent

	if target.has_meta("topic"):
		var topic = str(target.get_meta("topic"))
		var parts = topic.split(" ")
		var subject = parts[0] if parts.size() >= 1 else "Subject"
		var level = int(parts[1]) if parts.size() >= 2 else 0

		selection_subject_label.text = subject + " textbook"
		selection_topic_label.text = "Book " + str(level)

		if GameManager.manual_selection_mode:
			selection_hint_label.text = "[Click] Open this textbook"
			selection_mode_label.text = "Manual mode: exact book selection"
		else:
			selection_hint_label.text = "[Click] Open this textbook"
			selection_mode_label.text = "Adaptive support enabled for selected level"
	else:
		var category = str(target.get_meta("shelf_category"))
		selection_subject_label.text = category + " shelf"
		selection_topic_label.text = "Resume from your latest lesson in this subject"
		selection_hint_label.text = "[Click] Continue where you left off"
		selection_mode_label.text = "Shelf quick-launch"

func _update_focus_ring_material(accent: Color):
	if focus_ring_material == null:
		return

	var pulse = 0.85 + (sin(selection_clock * 7.5) * 0.18)
	focus_ring_material.albedo_color = Color(accent.r, accent.g, accent.b, 0.36)
	focus_ring_material.emission = accent
	focus_ring_material.emission_energy_multiplier = pulse

func setup_college_portal():
	var portal = Area3D.new()
	portal.position = Vector3(0, 1, 14.0)
	add_child(portal)

	var mesh = MeshInstance3D.new()
	var cyl = CylinderMesh.new()
	cyl.height = 0.1
	cyl.top_radius = 1.0
	cyl.bottom_radius = 1.0
	mesh.mesh = cyl
	var mat = _build_material(Color(0.08, 0.4, 0.82), 0.15, 0.0)
	mat.emission_enabled = true
	mat.emission = Color(0.35, 0.72, 1.0)
	mat.emission_energy_multiplier = 0.9
	mesh.material_override = mat
	portal.add_child(mesh)

	var col = CollisionShape3D.new()
	var shape = CylinderShape3D.new()
	shape.height = 2.0
	shape.radius = 1.0
	col.shape = shape
	col.position = Vector3(0, 1, 0)
	portal.add_child(col)

	var label = Label3D.new()
	label.text = "College Portal"
	label.position = Vector3(0, 2.0, 0)
	label.outline_size = 8
	label.billboard = BaseMaterial3D.BILLBOARD_FIXED_Y
	portal.add_child(label)

	portal.body_entered.connect(_on_portal_entered)

func _on_portal_entered(body):
	if body.name == "Player":
		print("College Portal Entered!")
		hud_xp.text = "Welcome to College!"

func _on_interaction(collider):
	print("Library received interaction with: ", collider)
	if collider.has_meta("topic"):
		# Book selection should honor the exact textbook clicked.
		if not _ensure_tutoring_access():
			return
		goto_classroom(str(collider.get_meta("topic")))
	elif collider.has_meta("shelf_category"):
		var cat = collider.get_meta("shelf_category")
		print("Shelf selected: " + cat)
		resume_shelf(cat)
	elif collider.get_parent() and collider.get_parent().has_meta("topic"):
		if not _ensure_tutoring_access():
			return
		goto_classroom(str(collider.get_parent().get_meta("topic")))

func resume_shelf(category):
	if not _ensure_tutoring_access():
		return
	var game_manager = get_node("/root/GameManager")
	var data = {
		"username": game_manager.player_username,
		"shelf_category": category
	}
	NetworkManager.post_request("/resume_shelf", data, _on_resume_success, _on_resume_fail)

func _on_resume_success(_code, response):
	print("Resuming: " + response["topic"])
	goto_classroom(response["topic"])

func _on_resume_fail(_code, err):
	print("Error resuming shelf: " + err)
	_set_tutoring_access_state(false, err if err != "" else "Tutoring access requires an active subscription or access code.")

func goto_classroom(topic):
	if not _ensure_tutoring_access():
		return
	print("Switching to classroom for topic: ", topic)
	var game_manager = get_node("/root/GameManager")
	if game_manager:
		game_manager.set_topic(topic)

	get_tree().change_scene_to_file("res://scenes/Classroom.tscn")
