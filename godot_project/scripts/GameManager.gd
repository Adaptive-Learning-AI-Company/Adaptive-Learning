extends Node

var current_topic: String = ""
var player_username = "Player1"
var player_grade = -1 # Default to -1 to force initialization checks
var player_location = "New Hampshire"
var player_style = "Visual"
var player_avatar_id = "schoolgirl"
var manual_selection_mode = false
var learning_mode = "teach_me"
var password_cache = "" # For session continuity

# Simple Global to hold state between scenes
func set_topic(topic: String):
	current_topic = topic
