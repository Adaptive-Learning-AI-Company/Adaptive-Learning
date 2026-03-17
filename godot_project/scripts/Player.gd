extends CharacterBody3D

const SPEED = 5.0
const JUMP_VELOCITY = 4.5
const AVATAR_SCENES := {
	"schoolgirl": {
		"path": "res://assets/models/Schoolgirl/schoolgirl.glb",
		"position": Vector3(0.0, 0.0, 0.0),
		"rotation_degrees": Vector3(0.0, 180.0, 0.0),
		"scale": Vector3(1.2, 1.2, 1.2)
	},
	"schoolboy": {
		"path": "res://assets/models/Schoolboy/character-b.glb",
		"position": Vector3(0.0, 0.0, 0.0),
		"rotation_degrees": Vector3(0.0, 180.0, 0.0),
		"scale": Vector3(0.9, 0.9, 0.9)
	}
}

var gravity = ProjectSettings.get_setting("physics/3d/default_gravity")

@onready var avatar_root = $AvatarRoot
@onready var pivot = $Pivot
@onready var camera = $Pivot/Camera3D

signal interaction_requested(collider)

var last_highlighted_obj = null
var avatar_instance: Node3D = null
var avatar_config_id := "schoolgirl"
var avatar_clock := 0.0
var avatar_has_manual_limb_animation := false
var avatar_parts := {}
var avatar_part_rotations := {}
var avatar_part_positions := {}
var avatar_base_position := Vector3.ZERO
var avatar_base_rotation := Vector3.ZERO

var external_move_input = Vector2.ZERO
var external_look_input = Vector2.ZERO


func _ready():
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	_load_profile_avatar()
	_create_crosshair()


func _physics_process(delta):
	if not is_on_floor():
		velocity.y -= gravity * delta

	if Input.is_action_just_pressed("ui_accept") and is_on_floor():
		velocity.y = JUMP_VELOCITY

	var input_dir = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	input_dir += external_move_input
	if input_dir.length() > 1.0:
		input_dir = input_dir.normalized()

	var direction = (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * SPEED
		velocity.z = direction.z * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0, SPEED)
		velocity.z = move_toward(velocity.z, 0, SPEED)

	if external_look_input != Vector2.ZERO:
		rotate_y(-external_look_input.x * 0.05)
		pivot.rotate_x(-external_look_input.y * 0.05)
		pivot.rotation.x = clamp(pivot.rotation.x, -1.2, 0.5)

	move_and_slide()
	_update_avatar_animation(delta)
	update_highlight()


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


func apply_profile_avatar(new_avatar_id: String):
	var requested_avatar = new_avatar_id.to_lower()
	if not AVATAR_SCENES.has(requested_avatar):
		requested_avatar = "schoolgirl"

	if requested_avatar == avatar_config_id and avatar_instance and is_instance_valid(avatar_instance):
		return

	avatar_config_id = requested_avatar
	_mount_avatar(requested_avatar)


func update_highlight():
	var space_state = get_world_3d().direct_space_state
	var center = get_viewport().get_visible_rect().size / 2
	var from = camera.project_ray_origin(center)
	var normal = camera.project_ray_normal(center)
	from += normal * 1.5
	var to = from + normal * 14.0

	var query = PhysicsRayQueryParameters3D.create(from, to)
	query.collide_with_areas = true
	query.collide_with_bodies = true
	query.exclude = [self.get_rid()]

	var result = space_state.intersect_ray(query)
	var current_obj = null

	if result:
		var collider = result.collider
		var parent = collider.get_parent()
		var is_direct_interactable = collider.has_meta("topic") or collider.has_meta("shelf_category")
		var is_parent_interactable = parent and (parent.has_meta("topic") or parent.has_meta("shelf_category"))

		if is_direct_interactable or is_parent_interactable:
			current_obj = collider
			if is_parent_interactable:
				current_obj = parent

	if current_obj != last_highlighted_obj:
		if last_highlighted_obj and is_instance_valid(last_highlighted_obj):
			var previous_mesh = last_highlighted_obj.get_node_or_null("MeshInstance3D")
			if previous_mesh:
				previous_mesh.scale = Vector3.ONE

		if current_obj and is_instance_valid(current_obj):
			var current_mesh = current_obj.get_node_or_null("MeshInstance3D")
			if current_mesh:
				current_mesh.scale = Vector3(1.2, 1.2, 1.2)

		last_highlighted_obj = current_obj


func _create_crosshair():
	var canvas = CanvasLayer.new()
	add_child(canvas)

	var crosshair = ColorRect.new()
	crosshair.color = Color.WHITE
	crosshair.set_size(Vector2(4, 4))
	crosshair.position = get_viewport().get_visible_rect().size / 2 - Vector2(2, 2)
	crosshair.anchors_preset = Control.PRESET_CENTER
	canvas.add_child(crosshair)


func _load_profile_avatar():
	var gm = get_node_or_null("/root/GameManager")
	var requested_avatar = "schoolgirl"
	if gm:
		requested_avatar = str(gm.player_avatar_id)

	apply_profile_avatar(requested_avatar)


func _mount_avatar(avatar_id: String):
	if avatar_instance and is_instance_valid(avatar_instance):
		avatar_instance.queue_free()

	avatar_parts.clear()
	avatar_part_rotations.clear()
	avatar_part_positions.clear()
	avatar_has_manual_limb_animation = false

	var config = AVATAR_SCENES.get(avatar_id, AVATAR_SCENES["schoolgirl"])
	var scene = load(config["path"])
	if scene == null:
		push_warning("Failed to load avatar scene: " + str(config["path"]))
		return

	avatar_instance = scene.instantiate()
	avatar_instance.position = config["position"]
	avatar_instance.rotation_degrees = config["rotation_degrees"]
	avatar_instance.scale = config["scale"]
	avatar_root.add_child(avatar_instance)

	avatar_base_position = avatar_instance.position
	avatar_base_rotation = avatar_instance.rotation

	_cache_avatar_parts()
	_try_play_model_animation()


func _cache_avatar_parts():
	if avatar_instance == null or not is_instance_valid(avatar_instance):
		return

	for part_name in ["root", "torso", "head", "arm-left", "arm-right", "leg-left", "leg-right"]:
		var part = avatar_instance.find_child(part_name, true, false)
		if part and part is Node3D:
			avatar_parts[part_name] = part
			avatar_part_rotations[part_name] = part.rotation
			avatar_part_positions[part_name] = part.position

	avatar_has_manual_limb_animation = avatar_parts.has("leg-left") and avatar_parts.has("leg-right")


func _try_play_model_animation():
	if avatar_instance == null or not is_instance_valid(avatar_instance):
		return

	var animation_player = avatar_instance.find_child("AnimationPlayer", true, false)
	if animation_player and animation_player is AnimationPlayer:
		var animation_names = animation_player.get_animation_list()
		if animation_names.size() > 0:
			animation_player.play(animation_names[0])


func _update_avatar_animation(delta):
	if avatar_instance == null or not is_instance_valid(avatar_instance):
		return

	var horizontal_speed = Vector2(velocity.x, velocity.z).length()
	var movement_strength = clamp(horizontal_speed / SPEED, 0.0, 1.0)
	var animation_speed = 1.8 + (movement_strength * 5.0)
	avatar_clock += delta * animation_speed

	if avatar_has_manual_limb_animation:
		_update_blocky_avatar_animation(movement_strength)
	else:
		_update_generic_avatar_animation(movement_strength)


func _update_blocky_avatar_animation(movement_strength: float):
	var walk_swing = sin(avatar_clock * 1.2) * (0.7 * movement_strength)
	var arm_swing = walk_swing * 0.75
	var bob = sin(avatar_clock * 2.4) * (0.035 + (movement_strength * 0.025))

	avatar_instance.position = avatar_base_position + Vector3(0.0, bob, 0.0)

	_set_part_rotation("leg-left", Vector3(walk_swing, 0.0, 0.0))
	_set_part_rotation("leg-right", Vector3(-walk_swing, 0.0, 0.0))
	_set_part_rotation("arm-left", Vector3(-arm_swing, 0.0, 0.0))
	_set_part_rotation("arm-right", Vector3(arm_swing, 0.0, 0.0))
	_set_part_rotation("torso", Vector3(0.0, 0.0, sin(avatar_clock * 1.2) * 0.06 * max(0.3, movement_strength)))
	_set_part_rotation("head", Vector3(0.0, sin(avatar_clock * 0.75) * 0.06, 0.0))


func _update_generic_avatar_animation(movement_strength: float):
	var idle_bob = sin(avatar_clock * 1.35) * 0.025
	var walk_bob = sin(avatar_clock * 2.4) * 0.03 * movement_strength
	avatar_instance.position = avatar_base_position + Vector3(0.0, idle_bob + walk_bob, 0.0)
	avatar_instance.rotation = avatar_base_rotation + Vector3(0.0, 0.0, sin(avatar_clock * 1.1) * 0.035 * max(0.2, movement_strength))


func _set_part_rotation(part_name: String, delta_rotation: Vector3):
	if not avatar_parts.has(part_name):
		return

	var part = avatar_parts[part_name]
	if not is_instance_valid(part):
		return

	part.rotation = avatar_part_rotations[part_name] + delta_rotation
