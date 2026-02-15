extends CharacterBody3D

const SPEED = 5.0
const JUMP_VELOCITY = 4.5

var gravity = ProjectSettings.get_setting("physics/3d/default_gravity")

@onready var pivot = $Pivot
@onready var camera = $Pivot/Camera3D

signal interaction_requested(collider)

var last_highlighted_obj = null
var original_scale = Vector3.ONE

func _ready():
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	
	# Create Crosshair UI
	var canvas = CanvasLayer.new()
	add_child(canvas)
	var crosshair = ColorRect.new()
	crosshair.color = Color.WHITE
	crosshair.set_size(Vector2(4, 4))
	crosshair.position = get_viewport().get_visible_rect().size / 2 - Vector2(2, 2)
	# Keep centered if window resizes (simple anchor)
	crosshair.anchors_preset = Control.PRESET_CENTER
	canvas.add_child(crosshair)

var external_move_input = Vector2.ZERO
var external_look_input = Vector2.ZERO

func _physics_process(delta):
	if not is_on_floor():
		velocity.y -= gravity * delta

	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var input_dir = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	
	# Combine with external input (Joystick)
	input_dir += external_move_input
	# Clamp length to 1.0 to prevent double speed
	if input_dir.length() > 1.0:
		input_dir = input_dir.normalized()

	var direction = (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * SPEED
		velocity.z = direction.z * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0, SPEED)
		velocity.z = move_toward(velocity.z, 0, SPEED)
		
	# Handle External Look (Joystick)
	if external_look_input != Vector2.ZERO:
		rotate_y(-external_look_input.x * 0.05) # Adjust sensitivity
		pivot.rotate_x(-external_look_input.y * 0.05)
		pivot.rotation.x = clamp(pivot.rotation.x, -1.2, 0.5)

	move_and_slide()
	update_highlight()

func update_highlight():
	var space_state = get_world_3d().direct_space_state
	var center = get_viewport().get_visible_rect().size / 2
	var from = camera.project_ray_origin(center)
	var normal = camera.project_ray_normal(center)
	# Offset start to avoid self-collision (especially with SpringArm)
	from += normal * 1.5 
	var to = from + normal * 14.0
	
	var query = PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = true
	# Shelves/walls should block interaction rays for objects behind them.
	query.collide_with_bodies = true
	# Exclude self
	query.exclude = [self.get_rid()]
	
	var result = space_state.intersect_ray(query)
	var current_obj = null
	
	if result:
		var collider = result.collider
		var parent = collider.get_parent()
		var is_direct_interactable = collider.has_meta("topic") or collider.has_meta("shelf_category")
		var is_parent_interactable = parent and (parent.has_meta("topic") or parent.has_meta("shelf_category"))
		
		if is_direct_interactable or is_parent_interactable:
			# Support both textbooks (topic) and subject selectors (shelf_category).
			current_obj = collider
			if is_parent_interactable:
				current_obj = parent
	
	# Highlight Logic
	if current_obj != last_highlighted_obj:
		# Reset previous
		if last_highlighted_obj and is_instance_valid(last_highlighted_obj):
			# Reset scale of mesh child?
			var mesh = last_highlighted_obj.get_node_or_null("MeshInstance3D")
			if mesh:
				mesh.scale = Vector3(1, 1, 1) # Assuming original was 1,1,1
		
		# Set new
		if current_obj and is_instance_valid(current_obj):
			var mesh = current_obj.get_node_or_null("MeshInstance3D")
			if mesh:
				mesh.scale = Vector3(1.2, 1.2, 1.2) # Pop effect
		
		last_highlighted_obj = current_obj

func _input(event):
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * 0.005)
		pivot.rotate_x(-event.relative.y * 0.005)
		pivot.rotation.x = clamp(pivot.rotation.x, -1.2, 0.5)
	
	if event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	
	if event.is_action_pressed("interact") and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		if last_highlighted_obj:
			emit_signal("interaction_requested", last_highlighted_obj)

func _unhandled_input(event):
	if event is InputEventMouseButton and event.pressed and Input.mouse_mode == Input.MOUSE_MODE_VISIBLE:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
