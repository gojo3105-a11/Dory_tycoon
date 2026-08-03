extends Node2D
class_name CookingStation

enum State {
	IDLE,
	COOKING,
	READY,
}

@onready var status_label: Label = get_node_or_null("CookingStatus/StatusLabel") as Label
@onready var progress_bar: ProgressBar = get_node_or_null("CookingStatus/ProgressBar") as ProgressBar
@onready var ready_point: Node2D = get_node_or_null("ReadyPoint") as Node2D

var state: State = State.IDLE
var current_customer: Customer = null
var current_order: Dictionary = {}
var elapsed_time: float = 0.0
var cook_duration: float = 0.0

func _ready() -> void:
	_update_ui()

func _process(delta: float) -> void:
	if state != State.COOKING:
		return

	elapsed_time += delta
	_update_ui()

	if elapsed_time >= cook_duration:
		_finish_cooking()

func accept_order(customer: Customer, order: Dictionary) -> bool:
	if state != State.IDLE:
		return false
	if not _is_valid_order(order):
		return false
	if not is_instance_valid(customer):
		return false

	current_customer = customer
	current_order = order
	cook_duration = float(order["cook_time"])
	elapsed_time = 0.0
	state = State.COOKING

	print("Order received: ", order["food_name"])
	print("Cooking started: ", cook_duration)

	_update_ui()
	return true

func _is_valid_order(order: Dictionary) -> bool:
	if not (order.has("food_id") and order.has("food_name") and order.has("cook_time") and order.has("price")):
		return false

	var food_id_value: Variant = order["food_id"]
	var food_name_value: Variant = order["food_name"]
	var cook_time_value: Variant = order["cook_time"]
	var price_value: Variant = order["price"]

	if not (food_id_value is String) or (food_id_value as String).is_empty():
		return false
	if not (food_name_value is String) or (food_name_value as String).is_empty():
		return false
	if not (cook_time_value is float or cook_time_value is int) or float(cook_time_value) <= 0.0:
		return false
	if not (price_value is float or price_value is int) or float(price_value) <= 0.0:
		return false
	return true

func _finish_cooking() -> void:
	elapsed_time = cook_duration
	state = State.READY
	print("Cooking completed: ", current_order.get("food_name", ""))
	_update_ui()

func _progress_percent() -> float:
	match state:
		State.IDLE:
			return 0.0
		State.READY:
			return 100.0
		State.COOKING:
			if cook_duration <= 0.0:
				return 0.0
			return clamp((elapsed_time / cook_duration) * 100.0, 0.0, 100.0)
	return 0.0

func _status_text() -> String:
	var food_name: String = str(current_order.get("food_name", ""))
	match state:
		State.IDLE:
			return "대기 중"
		State.COOKING:
			return "%s 조리 중" % food_name
		State.READY:
			return "%s 완성" % food_name
	return ""

func _update_ui() -> void:
	if progress_bar != null:
		progress_bar.value = _progress_percent()
	if status_label != null:
		status_label.text = _status_text()
	if ready_point != null:
		ready_point.visible = state == State.READY
