extends Node3D

const SUBJECT_ORDER := ["Math", "Science", "History", "English"]
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
	"Math": Vector3(-4.2, 0.0, 4.8),
	"Science": Vector3(4.2, 0.0, 4.8),
	"History": Vector3(-4.2, 0.0, 9.1),
	"English": Vector3(4.2, 0.0, 9.1)
}
const SHELF_FOCUS_POINT := Vector3(0.0, 0.0, 0.6)

var network_manager
var player

var hud_xp: Label
var hud_level: Label
var hud_grade: Label
var grade_gauge: TextureProgressBar

var grade_percent_label: Label
var sidebar_panel: Panel
var joystick_left: VirtualJoystick
var joystick_right: VirtualJoystick
var hud_role: Label

var shelf_progress_bars := {}
var shelf_progress_labels := {}
var subject_selector_progress_labels := {}
var sidebar_subject_progress_bars := {}
var book_nodes := []

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
	player.position = Vector3(0, 0.5, 0)
	player.interaction_requested.connect(_on_interaction)
	add_child(player)

func _process(delta):
	selection_clock += delta

	# Feed joystick input to player
	if player and is_instance_valid(player):
		if joystick_left:
			player.external_move_input = joystick_left.get_output()

		if joystick_right:
			player.external_look_input = joystick_right.get_output()

	_update_books_animation(delta)
	_update_selection_feedback(delta)

func setup_ui():
	var canvas = CanvasLayer.new()
	add_child(canvas)

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
	canvas.add_child(sidebar_panel)

	# Menu Toggle Button (Always visible)
	var menu_btn = Button.new()
	menu_btn.text = "MENU"
	menu_btn.position = Vector2(10, 10)
	menu_btn.pressed.connect(_on_toggle_menu)
	canvas.add_child(menu_btn)

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

			canvas.add_child(joystick_left)

			joystick_right = joystick_scn.instantiate()
			# Anchor Bottom Right
			joystick_right.joystick_mode = "Look"
			joystick_right.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
			joystick_right.size = Vector2(250, 250)
			joystick_right.position = Vector2(get_viewport().get_visible_rect().size.x - 270, get_viewport().get_visible_rect().size.y - 270)

			canvas.add_child(joystick_right)

	# Container with Margins
	var mc = MarginContainer.new()
	mc.set_anchors_preset(Control.PRESET_FULL_RECT)
	mc.add_theme_constant_override("margin_left", 20)
	mc.add_theme_constant_override("margin_top", 20)
	mc.add_theme_constant_override("margin_right", 20)
	mc.add_theme_constant_override("margin_bottom", 20)
	sidebar_panel.add_child(mc)



	var content_vbox = VBoxContainer.new()
	content_vbox.add_theme_constant_override("separation", 15)
	mc.add_child(content_vbox)

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
	var exit_btn = Button.new()
	exit_btn.text = "Main Menu"
	exit_btn.pressed.connect(func(): get_tree().change_scene_to_file("res://scenes/Startup.tscn"))
	content_vbox.add_child(exit_btn)

	# Fetch Stats
	fetch_stats()

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
	# Reuse init_session struct for convenience or make empty request
	# get_player_stats uses init_session struct for username
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

		if stats.has("grade_completion"):
			var g_val = stats["grade_completion"]
			if grade_gauge:
				grade_gauge.value = g_val
			if grade_percent_label:
				grade_percent_label.text = str(g_val) + "%"

		for subject in SUBJECT_ORDER:
			var sidebar_key = subject.to_lower()
			if not sidebar_subject_progress_bars.has(subject):
				continue
			if stats.has(sidebar_key):
				sidebar_subject_progress_bars[subject].value = clamp(float(stats[sidebar_key]), 0.0, 100.0)

		for subject in SUBJECT_ORDER:
			var key = subject.to_lower()
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

	# Subject sections
	# Compact cluster near the spawn lane so all shelves stay visible and navigable.
	for subject in SUBJECT_ORDER:
		if not SHELF_LAYOUT.has(subject):
			continue
		var shelf_pos: Vector3 = SHELF_LAYOUT[subject]
		var shelf_yaw = _yaw_toward_point(shelf_pos, SHELF_FOCUS_POINT)
		setup_section(subject, shelf_pos, shelf_yaw)

	setup_college_portal()
	_setup_focus_ring()
	_setup_selection_hud()

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

	if role == "teacher":
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
	selector_box.size = Vector3(2.7, 0.95, 0.15)
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
	selector_shape.size = Vector3(2.75, 0.98, 0.24)
	selector_col.shape = selector_shape
	selector.add_child(selector_col)

	var title = Label3D.new()
	title.text = category + " SHELF"
	title.font_size = 52
	title.outline_size = 10
	title.position = Vector3(0, 0.13, 0.09)
	title.modulate = Color(1.0, 1.0, 1.0, 0.95)
	selector.add_child(title)

	var hint = Label3D.new()
	hint.text = "Click to resume"
	hint.font_size = 30
	hint.outline_size = 6
	hint.position = Vector3(0, -0.17, 0.09)
	hint.modulate = Color(1.0, 1.0, 1.0, 0.72)
	selector.add_child(hint)

	var progress_label = Label3D.new()
	progress_label.text = "0% complete"
	progress_label.font_size = 27
	progress_label.outline_size = 5
	progress_label.position = Vector3(0, -0.43, 0.09)
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
	level_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	level_label.position = Vector3(0, 0.1, 0.51)
	level_label.modulate = Color(1.0, 1.0, 1.0, 0.92)
	book_area.add_child(level_label)

	var code_label = Label3D.new()
	code_label.text = _subject_theme(category)["code"]
	code_label.font_size = 24
	code_label.outline_size = 6
	code_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
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
	portal.position = Vector3(0, 1, 12)
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
		goto_classroom(str(collider.get_meta("topic")))
	elif collider.has_meta("shelf_category"):
		var cat = collider.get_meta("shelf_category")
		print("Shelf selected: " + cat)
		resume_shelf(cat)
	elif collider.get_parent() and collider.get_parent().has_meta("topic"):
		goto_classroom(str(collider.get_parent().get_meta("topic")))

func resume_shelf(category):
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

func goto_classroom(topic):
	print("Switching to classroom for topic: ", topic)
	var game_manager = get_node("/root/GameManager")
	if game_manager:
		game_manager.set_topic(topic)

	get_tree().change_scene_to_file("res://scenes/Classroom.tscn")
