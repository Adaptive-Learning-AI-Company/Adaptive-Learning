extends Node3D

# var network_manager # Replaced by Global Autoload
var current_topic = ""
var chat_log: RichTextLabel
var input_field: LineEdit
var gauge_unit: TextureProgressBar
var gauge_subj: TextureProgressBar
var gauge_grade: TextureProgressBar

var mastery_labels = {} # Map gauge name to label node
var lbl_current_topic: Label
var lbl_prev_topic: Label

var lbl_next_topic: Label
var lbl_status: Label # [NEW] Status Ticker
var graph_overlay: Panel
var ui_layer: CanvasLayer

var waiting_for_response = false
var waiting_timer = 0.0
var custom_loading_message = ""

var view_as_student: bool = false
var btn_mode_toggle: CheckButton
var opt_grade_override: OptionButton
var lbl_grade_override: Label
var current_grade_level: int = 5 # Default, should sync from session
var current_learning_mode := "teach_me"
var current_role_name := ""
var action_buttons := []



func _ready():
	# Use Global NetworkManager (Autoload)
	# Connect signals from the global instance
	# Note: We should ensure we don't double-connect if returning to scene, 
	# but typically signal connections to 'self' are auto-cleaned or we can check is_connected.
	if not NetworkManager.chat_response_received.is_connected(_on_agent_response):
		NetworkManager.chat_response_received.connect(_on_agent_response)
	
	if not NetworkManager.session_ready.is_connected(_on_session_ready):
		NetworkManager.session_ready.connect(_on_session_ready)
		
	if not NetworkManager.progress_updated.is_connected(_on_progress_updated):
		NetworkManager.progress_updated.connect(_on_progress_updated)
	if not NetworkManager.error_occurred.is_connected(_on_network_error):
		NetworkManager.error_occurred.connect(_on_network_error)
	
	# Sync Username
	var gm = get_node("/root/GameManager")
	if gm:
		NetworkManager.current_username = gm.player_username
		current_learning_mode = str(gm.learning_mode)
	
	# Camera Setup (Since we removed player)
	var cam = Camera3D.new()
	add_child(cam)
	cam.position = Vector3(0, 2, 4)
	cam.look_at(Vector3(0, 1, 0))
	
	setup_ui()
	
	# Check for global topic
	if gm and gm.current_topic != "":
		initialize(gm.current_topic)
	else:
		initialize("Demo Topic") # Fallback

func initialize(topic: String):
	current_topic = topic
	# Delay message slightly to allow UI to build
	await get_tree().create_timer(0.5).timeout
	
	_start_loading("Initializing " + topic + "...")
	NetworkManager.select_book(topic)
	# append_chat("System", "Welcome to the " + topic + " class.") # Moved to after load? or keep? Select book is async.
	# We rely on _on_session_ready to stop loading? 
	# Yes. _on_session_ready calls update_gauge etc. 
	# Note: session_ready doesn't call _stop_loading explicitly unless we add it.
	# I should add _stop_loading to _on_session_ready.

func setup_classroom():
	# Environment
	var env = WorldEnvironment.new()
	var environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.1, 0.1, 0.15) # Dark Blue-Gray
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.5, 0.5, 0.5)
	env.environment = environment
	add_child(env)

	# Floor
	var floor_mesh = MeshInstance3D.new()
	floor_mesh.mesh = BoxMesh.new()
	floor_mesh.mesh.size = Vector3(10, 0.5, 10)
	floor_mesh.position.y = -0.25
	add_child(floor_mesh)
	
	# Directional Light
	var light = DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-60, 30, 0)
	light.shadow_enabled = true
	add_child(light)

	# FILL Light (Omni) for character visibility
	var omni = OmniLight3D.new()
	omni.omni_range = 10.0
	omni.position = Vector3(0, 3, 2)
	add_child(omni)

	# Teacher (Capsule)
	var teacher = MeshInstance3D.new()
	teacher.mesh = CapsuleMesh.new()
	teacher.position = Vector3(0, 1, -3)
	var t_mat = StandardMaterial3D.new()
	t_mat.albedo_color = Color.ORANGE
	teacher.material_override = t_mat
	add_child(teacher)
	
	var t_label = Label3D.new()
	t_label.text = "Teacher"
	t_label.position = Vector3(0, 2.2, -3)
	t_label.font_size = 64
	t_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(t_label)
	
	# Tutor (Sphere)
	var tutor = MeshInstance3D.new()
	tutor.mesh = SphereMesh.new()
	tutor.position = Vector3(2, 1, -2)
	var tu_mat = StandardMaterial3D.new()
	tu_mat.albedo_color = Color.CYAN
	tutor.material_override = tu_mat
	add_child(tutor)

	var tu_label = Label3D.new()
	tu_label.text = "Tutor"
	tu_label.position = Vector3(2, 1.8, -2)
	tu_label.font_size = 64
	tu_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	add_child(tu_label)

func setup_ui():
	ui_layer = CanvasLayer.new()
	add_child(ui_layer)
	
	# Main Container (Split View)
	var main_hbox = HBoxContainer.new()
	main_hbox.anchor_right = 1.0
	main_hbox.anchor_bottom = 1.0
	main_hbox.offset_left = 20
	main_hbox.offset_top = 20
	main_hbox.offset_right = -20
	main_hbox.offset_bottom = -20
	main_hbox.add_theme_constant_override("separation", 20)
	main_hbox.offset_bottom = -20
	main_hbox.add_theme_constant_override("separation", 20)
	ui_layer.add_child(main_hbox)
	
	# [LEFT] Sidebar (20%) - Wrapped in ScrollContainer
	var sidebar_scroll = ScrollContainer.new()
	sidebar_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sidebar_scroll.size_flags_stretch_ratio = 0.25
	sidebar_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED # Vertical only
	main_hbox.add_child(sidebar_scroll)
	
	var sidebar = VBoxContainer.new()
	sidebar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sidebar.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sidebar_scroll.add_child(sidebar)
	
	var back_btn = Button.new()
	back_btn.text = "< Back to Library"
	back_btn.pressed.connect(func(): get_tree().change_scene_to_file("res://scenes/Library.tscn"))
	sidebar.add_child(back_btn)
	
	# Spacer
	var spacer = Control.new()
	spacer.custom_minimum_size = Vector2(0, 20)
	sidebar.add_child(spacer)
	
	# Action Buttons
	var actions = ["Teach Me", "Quiz Me", "Explain", "Examples"]
	for a in actions:
		var btn = Button.new()
		btn.text = a
		btn.custom_minimum_size = Vector2(0, 40)
		btn.pressed.connect(func(): _on_submit(a))
		sidebar.add_child(btn)
		action_buttons.append(btn)
		
	# Spacer
	var spacer2 = Control.new()
	spacer2.custom_minimum_size = Vector2(0, 30)
	sidebar.add_child(spacer2)
	
	# Mastery Gauges
	var gauge_configs = [
		{"name": "subject", "label": "Subject Mastery", "color": Color(0.2, 0.6, 0.9)},
		{"name": "unit", "label": "Unit Mastery", "color": Color(0, 0.8, 0.2)}
	]
	
	for conf in gauge_configs:
		var lbl = Label.new()
		lbl.text = conf["label"] + ": 0.0%"
		sidebar.add_child(lbl)
		mastery_labels[conf["name"]] = lbl
		
		var g = TextureProgressBar.new()
		g.min_value = 0
		g.max_value = 100
		g.value = 0
		
		var bg_img = Image.create(200, 15, false, Image.FORMAT_RGBA8)
		bg_img.fill(Color(0.2, 0.2, 0.2))
		
		var fill_img = Image.create(200, 15, false, Image.FORMAT_RGBA8)
		fill_img.fill(conf["color"])
		
		g.texture_under = ImageTexture.create_from_image(bg_img)
		g.texture_progress = ImageTexture.create_from_image(fill_img)
		sidebar.add_child(g)
		
		if conf["name"] == "unit": gauge_unit = g
		elif conf["name"] == "subject": gauge_subj = g
		
		# Small Spacer
		var sp = Control.new()
		sp.custom_minimum_size = Vector2(0, 10)
		sidebar.add_child(sp)
	
	sidebar.add_child(HSeparator.new())
	
	# Topic Navigation Info
	lbl_current_topic = Label.new()
	lbl_current_topic.text = "Current: " + current_topic
	lbl_current_topic.modulate = Color(1, 1, 0.5)
	lbl_current_topic.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	sidebar.add_child(lbl_current_topic)
	
	lbl_prev_topic = Label.new()
	lbl_prev_topic.text = "Prev: -"
	lbl_prev_topic.modulate = Color(0.7, 0.7, 0.7)
	lbl_prev_topic.add_theme_font_size_override("font_size", 12)
	sidebar.add_child(lbl_prev_topic)
	
	lbl_next_topic = Label.new()
	lbl_next_topic.text = "Next: -"
	lbl_next_topic.modulate = Color(0.7, 1.0, 0.7)
	lbl_next_topic.add_theme_font_size_override("font_size", 12)
	sidebar.add_child(lbl_next_topic)
	
	sidebar.add_child(HSeparator.new())
	
	# Show Graph Button
	var btn_graph = Button.new()
	btn_graph.text = "Show All Topics"
	btn_graph.pressed.connect(_on_show_graph)
	sidebar.add_child(btn_graph)
	
	sidebar.add_child(HSeparator.new())
	
	# Content Grade Override
	lbl_grade_override = Label.new()
	lbl_grade_override.text = "Content Grade:"
	lbl_grade_override.add_theme_font_size_override("font_size", 12)
	lbl_grade_override.modulate = Color(0.8, 0.8, 0.8)
	sidebar.add_child(lbl_grade_override)
	
	opt_grade_override = OptionButton.new()
	opt_grade_override.add_item("Default (Profile)", 0)
	for i in range(1, 13):
		opt_grade_override.add_item("Grade " + str(i), i)
	opt_grade_override.item_selected.connect(_on_grade_override_selected)
	sidebar.add_child(opt_grade_override)
	
	sidebar.add_child(HSeparator.new())
	
	# Teacher Mode Toggle (Hidden by default)
	btn_mode_toggle = CheckButton.new()
	btn_mode_toggle.text = "Student Mode"
	btn_mode_toggle.visible = false
	btn_mode_toggle.toggled.connect(_on_mode_toggled)
	sidebar.add_child(btn_mode_toggle)

	_refresh_learning_mode_ui()

		
	# [RIGHT] Chat Interface (80%)
	var chat_panel = Panel.new()
	chat_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	chat_panel.size_flags_stretch_ratio = 1.0
	chat_panel.modulate = Color(1, 1, 1, 0.9)
	main_hbox.add_child(chat_panel)
	
	var chat_vbox = VBoxContainer.new()
	chat_vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	chat_vbox.offset_left = 10
	chat_vbox.offset_top = 10
	chat_vbox.offset_right = -10
	chat_vbox.offset_bottom = -10
	chat_panel.add_child(chat_vbox)
	
	chat_log = RichTextLabel.new()
	chat_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	chat_log.scroll_following = true
	chat_log.selection_enabled = true
	chat_vbox.add_child(chat_log)
	
	# Status Label (Above input)
	lbl_status = Label.new()
	lbl_status.text = ""
	lbl_status.modulate = Color(1.0, 0.2, 0.2) # Red
	lbl_status.add_theme_font_size_override("font_size", 18) # Larger
	chat_vbox.add_child(lbl_status)
		
	input_field = LineEdit.new()
	input_field.placeholder_text = _input_placeholder_text()
	input_field.focus_mode = Control.FOCUS_ALL
	input_field.text_submitted.connect(_on_submit)
	input_field.gui_input.connect(_on_input_field_gui_input)
	# input_field.focus_entered.connect(_on_focus) # No longer needed without captured mouse
	# input_field.focus_exited.connect(_on_unfocus)
	chat_vbox.add_child(input_field)
	
	# Ensure mouse is visible since we removed the FPS player
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func setup_simplified_ui(parent):
	var grid = HBoxContainer.new()
	grid.size_flags_vertical = Control.SIZE_SHRINK_END
	grid.custom_minimum_size = Vector2(0, 100)
	parent.add_child(grid)
	
	var actions = ["Yes", "No", "Explain", "Quiz Me"]
	for a in actions:
		var btn = Button.new()
		btn.text = a
		btn.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		btn.pressed.connect(func(): _on_submit(a))
		grid.add_child(btn)


func _refresh_learning_mode_ui():
	if input_field:
		input_field.placeholder_text = _input_placeholder_text()
	if current_learning_mode == "knowledge_tracing":
		var tracing_labels = ["Adaptive Quiz", "Another Check", "Challenge Me", "Review Node"]
		for index in range(min(action_buttons.size(), tracing_labels.size())):
			action_buttons[index].text = tracing_labels[index]
		if lbl_grade_override:
			lbl_grade_override.text = "Content Grade: profile-locked"
		if opt_grade_override:
			opt_grade_override.disabled = true
			opt_grade_override.select(0)
	else:
		var teach_me_labels = ["Teach Me", "Quiz Me", "Explain", "Examples"]
		for index in range(min(action_buttons.size(), teach_me_labels.size())):
			action_buttons[index].text = teach_me_labels[index]
		if lbl_grade_override:
			lbl_grade_override.text = "Content Grade:"
		if opt_grade_override:
			opt_grade_override.disabled = false

	_refresh_teacher_mode_toggle()

func _refresh_teacher_mode_toggle():
	if btn_mode_toggle == null:
		return

	var teacher_capable = current_role_name == "teacher" or current_role_name == "admin"
	btn_mode_toggle.visible = teacher_capable
	if not teacher_capable:
		view_as_student = false
		btn_mode_toggle.disabled = true
		btn_mode_toggle.tooltip_text = ""
		btn_mode_toggle.set_pressed_no_signal(false)
		return

	if current_learning_mode == "knowledge_tracing":
		view_as_student = true
		btn_mode_toggle.disabled = true
		btn_mode_toggle.tooltip_text = "Knowledge tracing is always student-facing."
		btn_mode_toggle.set_pressed_no_signal(true)
		return

	btn_mode_toggle.disabled = false
	btn_mode_toggle.tooltip_text = ""
	btn_mode_toggle.set_pressed_no_signal(view_as_student)

func _input_placeholder_text() -> String:
	if current_learning_mode == "knowledge_tracing":
		return "Type your answer here or use the menu..."
	return "Type your question here or use the menu..."

func _input(event):
	# Shortcut to focus chat
	if event.is_action_pressed("ui_accept") and not input_field.has_focus():
		input_field.grab_focus()
		# Player absorbs input unless we release mouse, but focusing line edit usually helps?
		# We need to explicitly tell player (or just set mouse mode)
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _on_focus():
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _on_unfocus():
	# Don't immediately capture, let user click?
	# Or capture if they click game world (handled by Player)
	pass

func _process(delta):
	if waiting_for_response:
		waiting_timer += delta
		var dot_count = int(waiting_timer * 2) % 4
		var dots = ".".repeat(dot_count)
		
		# Use custom message base
		var base_msg = custom_loading_message if custom_loading_message != "" else "Agent is thinking"
		var msg = base_msg + dots + " (" + str(int(waiting_timer)) + "s)"
		
		# If > 15 seconds, show patience request
		if waiting_timer > 15.0:
			msg += " - Please be patient, complex calculation in progress!"
			lbl_status.modulate = Color(1.0, 0.5, 0.0) # Orange warning
		else:
			# Default Red as requested
			lbl_status.modulate = Color(1.0, 0.2, 0.2) # Red
			
		lbl_status.text = msg

func _start_loading(msg="Agent is thinking"):
	waiting_for_response = true
	waiting_timer = 0.0
	custom_loading_message = msg
	if lbl_status: lbl_status.text = msg + "..."

func _stop_loading():
	waiting_for_response = false
	if lbl_status: lbl_status.text = ""


func _focus_input_field():
	if input_field == null or not is_instance_valid(input_field):
		return
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	_focus_input_field_deferred.call_deferred()


func _focus_input_field_deferred():
	if input_field == null or not is_instance_valid(input_field):
		return
	input_field.grab_focus()
	input_field.set_caret_column(input_field.text.length())
	await get_tree().process_frame
	if input_field == null or not is_instance_valid(input_field):
		return
	input_field.grab_focus()
	input_field.set_caret_column(input_field.text.length())


func _on_input_field_gui_input(event: InputEvent):
	if input_field == null or not is_instance_valid(input_field):
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		input_field.call_deferred("grab_focus")

func _on_submit(new_text):
	if new_text.strip_edges() == "": return

	var outbound_text = new_text
	if current_learning_mode == "knowledge_tracing":
		match new_text:
			"Teach Me", "Quiz Me", "Adaptive Quiz":
				outbound_text = "Quiz me on the next concept."
			"Explain", "Another Check", "Review Node":
				outbound_text = "Give me another question on this concept."
			"Examples", "Challenge Me":
				outbound_text = "Challenge me with a slightly harder question on this concept."
	
	input_field.text = ""
	
	append_chat("You", outbound_text)
	
	_start_loading()
	
	# Check for Grade / Role Override
	var override_val = -1
	if current_learning_mode != "knowledge_tracing" and opt_grade_override and opt_grade_override.selected > 0:
		override_val = opt_grade_override.get_selected_id()
		
	NetworkManager.send_message(outbound_text, view_as_student, override_val)

func _on_agent_response(response, action, state: Dictionary):
	_stop_loading()
	print("Agent Response State: ", state)
	append_chat("Agent", response)
	_focus_input_field()
	
	# Update Navigation Info
	if state.has("current_node_label"):
		lbl_current_topic.text = "Current: " + str(state["current_node_label"])
		
	# Fallback if state has no current label but we know the topic
	if lbl_current_topic.text == "Current: " and current_topic != "":
		lbl_current_topic.text = "Current: " + current_topic
		
	if state.has("prev_node_label"):
		lbl_prev_topic.text = "Prev: " + str(state["prev_node_label"])
	if state.has("next_node_label"):
		lbl_next_topic.text = "Next: " + str(state["next_node_label"])

func _on_session_ready(data):
	var summary = data.get("history_summary")
	if summary == null:
		summary = ""

	current_role_name = str(data.get("role", "")).to_lower()
	current_learning_mode = str(data.get("learning_mode", current_learning_mode))
	if data.has("resolved_topic"):
		current_topic = str(data["resolved_topic"])
	var topic_label = str(data.get("topic_label", current_topic))
	_refresh_learning_mode_ui()
	
	# Initial mastery
	update_gauge(data.get("mastery", 0))
	
	# Initial Nav Labels
	var state = data.get("state_snapshot", {})
	if state:
		if state.has("current_node_label"):
			lbl_current_topic.text = "Current: " + str(state["current_node_label"])
		if state.has("prev_node_label"):
			lbl_prev_topic.text = "Prev: " + str(state["prev_node_label"])
		if state.has("next_node_label"):
			lbl_next_topic.text = "Next: " + str(state["next_node_label"])

	append_chat("System", "Session loaded. Mastery: " + str(data.get("mastery", 0)) + "%. " + summary)
	
	# Stop "Initializing" ticker now that session is ready
	_stop_loading()
	_focus_input_field()
	
	if lbl_current_topic and topic_label != "" and (not state or not state.has("current_node_label")):
		lbl_current_topic.text = "Current: " + topic_label

	# Show Teacher Toggle if Role is Teacher
	if current_role_name == "teacher" or current_role_name == "admin":
		if current_learning_mode == "knowledge_tracing":
			append_chat("System", "Teacher knowledge tracing uses student view automatically.")
		else:
			append_chat("System", "Teacher Mode Active. Use toggle to switch views.")

	var should_start_tracing = false
	if current_learning_mode == "knowledge_tracing":
		var tracing_mastery_level = int(data.get("mastery_level", 0))
		var current_action = str(state.get("current_action", "IDLE"))
		should_start_tracing = tracing_mastery_level < 10 and current_action != "PROBLEM_GIVEN"

	if should_start_tracing:
		var override_val = -1
		_start_loading("Agent is preparing the assessment...")
		append_chat("System", "Adaptive testing is starting. Please wait for the first checkpoint.")
		NetworkManager.send_message("Quiz me on the next concept.", view_as_student, override_val)
	# Proactive Trigger if mastery is 0 (New Topic)
	elif data.get("mastery", 0) == 0:
		var override_val = -1
		if current_learning_mode != "knowledge_tracing" and opt_grade_override and opt_grade_override.selected > 0:
			override_val = opt_grade_override.get_selected_id()

		if current_learning_mode != "knowledge_tracing":
			_start_loading("Agent is preparing the lesson...")
			append_chat("System", "Agent is preparing the lesson, please wait...")
			NetworkManager.send_message("Please start the lesson.", view_as_student, override_val)


func _on_network_error(msg: String):
	_stop_loading()
	if lbl_status:
		lbl_status.text = msg
	append_chat("System", msg)
	_focus_input_field()

func _on_progress_updated(xp, level, mastery):
	update_gauge(mastery)

func update_gauge(val):
	var u = 0
	var s = 0
	var g = 0
	
	if typeof(val) == TYPE_DICTIONARY:
		u = val.get("unit", 0)
		s = val.get("subject", 0)
		g = val.get("grade", 0)
	else:
		# Compatibility fallback
		u = int(val)
		# s = u # Don't update others if unknown
		
	if gauge_unit: _tween_gauge(gauge_unit, u)
	if gauge_subj: _tween_gauge(gauge_subj, s)
	
	if mastery_labels.has("unit"): mastery_labels["unit"].text = "Unit Mastery: " + str(snapped(u, 0.1)) + "%"
	if mastery_labels.has("subject"): mastery_labels["subject"].text = "Subject Mastery: " + str(snapped(s, 0.1)) + "%"

func _tween_gauge(gauge, target_val):
	var tween = create_tween()
	tween.tween_property(gauge, "value", target_val, 0.5)

	

	


func append_chat(sender, msg):
	var bbcode = markdown_to_bbcode(msg)
	
	var color_tag = ""
	if sender == "Agent":
		color_tag = "[color=#00AA00]" # Green
	elif sender == "You":
		color_tag = "[color=#AAAAAA]" # Grey
	elif sender == "System":
		color_tag = "[color=#FFDD44]" # Gold
		
	var sender_txt = sender
	if color_tag != "":
		sender_txt = color_tag + sender + "[/color]"
		# Also color the message for Agent? "UI color of the prompt (Agent?) to green".
		# Let's keep message white for readability, but maybe green tint?
		# User said "UI color of the prompt to green".
		# I will wrap the whole Agent message in Green? No, that might be too much.
		# I'll stick to Green Header for now unless "prompt" means input field?
		# "Inbetween prompts add a solid line... UI color of the prompt to green".
		# If "prompt" = Agent Response, then Green Header.
	
	# Separator (Solid Line)
	chat_log.append_text("\n[color=#444444]________________________________________________[/color]\n")
	
	chat_log.append_text("[b]" + sender_txt + ":[/b] " + bbcode + "\n")

func markdown_to_bbcode(text: String) -> String:
	# Basic Markdown to BBCode converter
	var res = text
	# Bold **text** -> [b]text[/b]
	# We use regex or simple replacement for now
	# Godot's RegEx support is good.
	
	var regex = RegEx.new()
	
	# Bold **...**
	regex.compile("\\*\\*(.*?)\\*\\*")
	res = regex.sub(res, "[b]$1[/b]", true)
	
	# Italic *...*
	regex.compile("\\*(.*?)\\*")
	res = regex.sub(res, "[i]$1[/i]", true)
	
	# Headers # ... -> [font_size=24]...[/font_size]
	# regex.compile("^# (.*)$") # Multiline flag needed? simpler loop?
	# Simple header replace for now
	if res.begins_with("# "):
		res = "[font_size=24]" + res.substr(2) + "[/font_size]"
	
	
	if res.begins_with("# "):
		res = "[font_size=24]" + res.substr(2) + "[/font_size]"
	
	return res

func _on_mode_toggled(pressed: bool):
	view_as_student = pressed
	if pressed:
		append_chat("System", "Switched to Student View. Agent will now treat you as a student.")
	else:
		append_chat("System", "Switched to Teacher Guide View. Agent will explain HOW to teach.")
	
	# Detect active override value to include
	var override_val = -1
	if opt_grade_override and opt_grade_override.selected > 0:
		override_val = opt_grade_override.get_selected_id()

	# Notify Agent silently to update role context
	# Notify Agent silently to update role context
	_start_loading("Updating Role...")
	NetworkManager.send_message("[System] Update Role Context.", view_as_student, override_val)



func _on_grade_override_selected(index):
	var grade_val = opt_grade_override.get_selected_id()
	if grade_val == 0:
		append_chat("System", "Content Grade reset to Profile Default.")
	else:
		append_chat("System", "Content Grade set to Grade " + str(grade_val) + ".")
	
	# Notify Agent silently to update state
	# We send a system-like message or just empty?
	# Agent needs a trigger. "Update context."
	# Ensure grade_val is int
	# Ensure grade_val is int
	_start_loading("Updating Grade Context...")
	NetworkManager.send_message("[System] Update Grade Level Context.", view_as_student, int(grade_val))

func _on_show_graph(focus_id = null):
	# Create Overlay
	if graph_overlay: graph_overlay.queue_free()
	
	graph_overlay = Panel.new()
	graph_overlay.set_anchors_preset(Control.PRESET_FULL_RECT)
	# Dark transparent bg
	var style = StyleBoxFlat.new()
	style.bg_color = Color(0, 0, 0, 0.9)
	graph_overlay.add_theme_stylebox_override("panel", style)
	
	# Add to UI Layer to ensure it covers everything
	if ui_layer:
		ui_layer.add_child(graph_overlay)
	else:
		add_child(graph_overlay)
	
	var vbox = VBoxContainer.new()
	vbox.set_anchors_preset(Control.PRESET_FULL_RECT)
	vbox.offset_left = 50
	vbox.offset_top = 50
	vbox.offset_right = -50
	vbox.offset_bottom = -50
	graph_overlay.add_child(vbox)
	
	# Header
	var header = HBoxContainer.new()
	vbox.add_child(header)
	
	var btn_prev = Button.new()
	btn_prev.text = " < Prev "
	header.add_child(btn_prev)
	# Logic added in data callback
	
	var title = Label.new()
	var graph_title_topic = current_topic.replace(" [Knowledge Tracing]", "")
	title.text = "Knowledge Graph: " + graph_title_topic
	title.add_theme_font_size_override("font_size", 24)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	header.add_child(title)
	
	var btn_next = Button.new()
	btn_next.text = " Next > "
	header.add_child(btn_next)
	
	var close = Button.new()
	close.text = " Close "
	close.modulate = Color(1, 0.5, 0.5)
	close.pressed.connect(func(): graph_overlay.queue_free())
	header.add_child(close)
	
	vbox.add_child(HSeparator.new())
	
	# Scroll Area
	var scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vbox.add_child(scroll)
	
	var content = VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(content)
	
	var loading = Label.new()
	loading.text = "Loading Graph..."
	content.add_child(loading)
	
	# Fetch Data with Focus ID
	# We need to update NetworkManager signature or dict?
	# NetworkManager.get_topic_graph expects (topic, success, error) currently in my last update.
	# I need to update NetworkManager.gd OR update how I call it if I changed it to take a dict?
	# I updated NetworkManager.gd to take ONLY topic.
	# I need to update NetworkManager.gd to accept optional params OR update it now to accept a Dict/Extra arg.
	# Let's update call here assuming I fix NetworkManager.gd next.
	NetworkManager.get_topic_graph(current_topic, 
		func(code, data): _on_graph_data(data, content, loading, btn_prev, btn_next), 
		func(code, err): loading.text = "Error: " + err,
		focus_id # Passing extra arg!
	)

func _on_graph_data(data: Dictionary, container: Control, loading_lbl: Label, btn_prev: Button, btn_next: Button):
	loading_lbl.queue_free()
	var nodes = data.get("nodes", [])
	if nodes.is_empty():
		var l = Label.new()
		l.text = "No data found."
		container.add_child(l)
		# Disable buttons if no data?
		btn_prev.disabled = true
		btn_next.disabled = true
		return
		
	# Bind Buttons
	# Prev -> First Node ID
	var start_id = nodes[0]["id"]
	var end_id = nodes[-1]["id"]
	
	btn_prev.pressed.connect(func(): _on_show_graph(start_id))
	btn_next.pressed.connect(func(): _on_show_graph(end_id))
		
	# Build Hierarchy (Simple indent based on type/parent?)
	# Or just list them with status?
	# Users asked for "Green Checkmark".
	
	# We can organize by ID path or just list linearly if sorted?
	# The API returns list. Let's try to group by hierarchy or just indent.
	# Simplest: Sort by ID (usually groups topics).
	
	# Sort nodes manually by ID (path)
	# nodes is a List of Dictionaries (from Pydantic JSON)
	# Sort by 'id'
	# nodes.sort_custom(func(a, b): return a["id"] < b["id"]) 
	# Actually keys in Dic: id, label, status, type, grade_level
	
	# We want to traverse. 
	# Let's map parent->children
	var node_map = {}
	var roots = []
	
	for n in nodes:
		node_map[n["id"]] = n
		n["children"] = []
	
	for n in nodes:
		if n.get("parent"):
			var p = node_map.get(n["parent"])
			if p:
				p["children"].append(n)
			else:
				roots.append(n)
		else:
			roots.append(n)
			
	# Recursive Render
	var target_node = null
	for r in roots:
		var res = _render_node(r, container, 0)
		if res and target_node == null:
			# Prioritize "current" > "completed" (last) > "available"
			if r["status"] == "current":
				target_node = res
	
	# If no current, look for first available in grade level
	if target_node == null:
		# Scan flattened list in UI? Or re-scan data?
		# Let's just find first "available" node.
		pass 
	
	# Scroll Logic
	# We need to wait for layout?
	await get_tree().process_frame
	
	# Simple scroll attempt: if we found a "current" node control, try to center it.
	# But finding the specific Control from _render_node recursion is cleaner.
	# Let's make _render_node return the Control if it matches criteria?
	
	# Re-scan for "current" node control
	var current_ctrl = _find_current_control(container)
	if current_ctrl:
		# Calculate position
		var y_pos = current_ctrl.position.y
		var scroll_c = container.get_parent() # ScrollContainer
		if scroll_c is ScrollContainer:
			scroll_c.scroll_vertical = int(y_pos) - 100 # Offset

func _find_current_control(parent):
	for c in parent.get_children():
		if c.has_meta("status") and c.get_meta("status") == "current":
			return c
		# Recursion in UI tree? 
		# Our _render_node flattens the hierarchy into VBox (with indent spacers).
		# So `content` has all node HBoxes as direct children.
	return null

func _render_node(node: Dictionary, container: Control, depth: int) -> Control:
	var hbox = HBoxContainer.new()
	container.add_child(hbox)
	hbox.set_meta("status", node["status"])
	hbox.set_meta("id", node["id"])
	
	# Indent
	if depth > 0:
		var spacer = Control.new()
		spacer.custom_minimum_size = Vector2(depth * 30, 0)
		hbox.add_child(spacer)
		
	# Checkmark
	var icon = Label.new()
	icon.custom_minimum_size = Vector2(24, 0)
	if node["status"] == "completed":
		icon.text = "✅" 
	elif node["status"] == "current":
		icon.text = "👉"
	elif node.get("is_tentative", false):
		icon.text = "🟡"
	elif node["status"] == "locked":
		icon.text = "🔒"
	else:
		icon.text = "⚪" # Available
	hbox.add_child(icon)
	
	# Interactive Label (Button)
	var btn = Button.new()
	var type_marker = ""
	if node["type"] == "topic": type_marker = "[T] "
	elif node["type"] == "subtopic": type_marker = "  "
	
	var mastery_suffix = ""
	if node.has("mastery_level") and int(node["mastery_level"]) > 0:
		mastery_suffix = " [L" + str(node["mastery_level"]) + "/10]"
	btn.text = type_marker + node["label"] + " (G" + str(node["grade_level"]) + ")" + mastery_suffix
	btn.flat = true # Make it look like label but clickable
	btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
	
	if node["status"] == "current":
		btn.modulate = Color(1, 1, 0) # Yellow highlight
	elif node["status"] == "completed":
		btn.modulate = Color(0.5, 1, 0.5) # Green
	elif node["status"] == "locked":
		btn.modulate = Color(0.5, 0.5, 0.5)
		# Disable click for locked?
		# User said "allow user to click ANY node".
		# locked might just mean future.
		
	btn.pressed.connect(func(): _on_node_clicked(node))
	
	hbox.add_child(btn)
	
	var returned_control = null
	if node["status"] == "current":
		returned_control = hbox
	
	# Children
	if node.has("children"):
		for c in node["children"]:
			var res = _render_node(c, container, depth + 1)
			if res and returned_control == null:
				returned_control = res
				
	return returned_control

func _on_node_clicked(node):
	print("Clicked node: ", node["id"])
	# Call backend
	NetworkManager.set_current_node(current_topic, node["id"], 
		func(code, data): _on_node_set_success(node),
		func(code, err): print("Error setting node: ", err)
	)

func _on_node_set_success(node):
	print("Node set. Refreshing context.")
	# Update local label immediately?
	lbl_current_topic.text = "Current: " + node["label"]
	
	# Send message to prompt teacher?
	# "Teach me about [Label]"
	_on_submit("Teach me about " + node["label"])
	
	# Close graph
	if graph_overlay: graph_overlay.queue_free()
