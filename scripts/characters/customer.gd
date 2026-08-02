extends Node2D
class_name Customer

enum State {
	SPAWN,
	MOVE_TO_TABLE,
	SEATED,
	LEAVE,
}

@export var move_speed: float = 120.0
@export var arrival_distance: float = 4.0
@export var show_debug_label: bool = true

@onready var status_label: Label = $StatusLabel

var state: State = State.SPAWN
var target_position: Vector2 = Vector2.ZERO
var assigned_table: Node = null

func _ready() -> void:
	if status_label != null:
		status_label.visible = show_debug_label
	_update_debug_label()

func _process(delta: float) -> void:
	if state == State.MOVE_TO_TABLE and not is_instance_valid(assigned_table):
		leave_towards(global_position)
		return
	if state == State.MOVE_TO_TABLE or state == State.LEAVE:
		_move_toward_target(delta)

func move_to_table(table: Node, seat_global_position: Vector2) -> void:
	assigned_table = table
	target_position = seat_global_position
	_set_state(State.MOVE_TO_TABLE)

func leave_towards(exit_global_position: Vector2) -> void:
	assigned_table = null
	target_position = exit_global_position
	_set_state(State.LEAVE)

func _move_toward_target(delta: float) -> void:
	global_position = global_position.move_toward(target_position, move_speed * delta)
	if global_position.distance_to(target_position) < arrival_distance:
		if state == State.MOVE_TO_TABLE:
			_set_state(State.SEATED)
		elif state == State.LEAVE:
			queue_free()

func _set_state(new_state: State) -> void:
	state = new_state
	_update_debug_label()

func _update_debug_label() -> void:
	if status_label == null:
		return
	match state:
		State.SPAWN:
			status_label.text = "SPAWN"
		State.MOVE_TO_TABLE:
			status_label.text = "MOVING"
		State.SEATED:
			status_label.text = "SEATED"
		State.LEAVE:
			status_label.text = "LEAVING"
