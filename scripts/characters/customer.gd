extends Node2D
class_name Customer

enum State {
	SPAWN,
	MOVE_TO_TABLE,
	SEATED,
	ORDER,
	WAIT,
	LEAVE,
}

signal order_created(customer: Customer, order: Dictionary)

const SEATED_Z_INDEX: int = 3
const MOVING_Z_INDEX: int = 6

@export var move_speed: float = 120.0
@export var arrival_distance: float = 4.0
@export var show_debug_label: bool = true
@export var min_order_delay: float = 0.5
@export var max_order_delay: float = 1.0

@onready var status_label: Label = $StatusLabel
@onready var order_bubble: Panel = $OrderBubble
@onready var order_label: Label = $OrderBubble/OrderLabel

var state: State = State.SPAWN
var target_position: Vector2 = Vector2.ZERO
var assigned_table: Node = null

var available_foods: Array = []
var ordered_food_id: String = ""
var ordered_food_name: String = ""
var ordered_cook_time: float = 0.0
var ordered_price: int = 0

func _ready() -> void:
	z_index = MOVING_Z_INDEX
	if status_label != null:
		status_label.visible = show_debug_label
	_update_debug_label()
	_update_order_bubble()

func _process(delta: float) -> void:
	if state == State.MOVE_TO_TABLE and not is_instance_valid(assigned_table):
		leave_towards(global_position)
		return
	if state == State.MOVE_TO_TABLE or state == State.LEAVE:
		_move_toward_target(delta)

func set_available_foods(food_list: Array) -> void:
	available_foods = food_list

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
		global_position = target_position
		if state == State.MOVE_TO_TABLE:
			_set_state(State.SEATED)
		elif state == State.LEAVE:
			queue_free()

func _on_seated() -> void:
	var wait_time: float = randf_range(min_order_delay, max_order_delay)
	await get_tree().create_timer(wait_time).timeout

	if not is_inside_tree():
		return
	if state != State.SEATED:
		return

	_set_state(State.ORDER)
	if _create_random_order():
		var order: Dictionary = {
			"food_id": ordered_food_id,
			"food_name": ordered_food_name,
			"cook_time": ordered_cook_time,
			"price": ordered_price,
		}
		order_created.emit(self, order)
		_set_state(State.WAIT)

func _create_random_order() -> bool:
	if available_foods.is_empty():
		return false

	var index: int = randi() % available_foods.size()
	var food: Variant = available_foods[index]
	if not (food is Dictionary):
		return false
	var food_dict: Dictionary = food
	if not (food_dict.has("id") and food_dict.has("name") and food_dict.has("cook_time") and food_dict.has("price")):
		return false

	ordered_food_id = str(food_dict["id"])
	ordered_food_name = str(food_dict["name"])
	ordered_cook_time = float(food_dict["cook_time"])
	ordered_price = int(food_dict["price"])
	_update_order_bubble()
	return true

func _set_state(new_state: State) -> void:
	state = new_state
	if new_state == State.SEATED:
		z_index = SEATED_Z_INDEX
		_on_seated()
	_update_debug_label()
	_update_order_bubble()

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
		State.ORDER:
			status_label.text = "ORDERING"
		State.WAIT:
			status_label.text = "WAITING"
		State.LEAVE:
			status_label.text = "LEAVING"

func _update_order_bubble() -> void:
	if order_bubble == null or order_label == null:
		return
	var show_bubble: bool = state == State.ORDER or state == State.WAIT
	order_bubble.visible = show_bubble
	if show_bubble and not ordered_food_name.is_empty():
		order_label.text = "주문: %s" % ordered_food_name
