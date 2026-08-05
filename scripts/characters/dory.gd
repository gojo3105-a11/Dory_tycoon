extends Node2D
class_name Dory

enum State {
	IDLE,
	MOVE_TO_KITCHEN,
	PICKUP,
	MOVE_TO_CUSTOMER,
	SERVE,
	RETURN_HOME,
}

const MOVING_Z_INDEX: int = 6

@export var move_speed: float = 130.0
@export var arrival_distance: float = 4.0
@export var show_debug_state: bool = false

@onready var cooking_station: CookingStation = get_node_or_null("../KitchenCounter") as CookingStation
@onready var skeleton: Skeleton2D = get_node_or_null("Skeleton2D") as Skeleton2D
@onready var animation_player: AnimationPlayer = get_node_or_null("AnimationPlayer") as AnimationPlayer
@onready var carry_indicator: Panel = get_node_or_null("CarryIndicator") as Panel
@onready var carry_label: Label = get_node_or_null("CarryIndicator/CarryLabel") as Label
@onready var debug_state_label: Label = get_node_or_null("DebugStateLabel") as Label

var state: State = State.IDLE
var home_position: Vector2 = Vector2.ZERO
var home_z_index: int = 0
var target_position: Vector2 = Vector2.ZERO
var target_customer: Customer = null
var carried_order: Dictionary = {}

func _ready() -> void:
	home_position = global_position
	home_z_index = z_index

	if carry_indicator != null:
		carry_indicator.visible = false
	if debug_state_label != null:
		debug_state_label.visible = show_debug_state

	_update_animation()
	_update_debug_label()

func _process(delta: float) -> void:
	if state == State.MOVE_TO_KITCHEN or state == State.MOVE_TO_CUSTOMER or state == State.RETURN_HOME:
		_move_toward_target(delta)

func start_serving(pickup_position: Vector2, customer: Customer, order: Dictionary) -> bool:
	if state != State.IDLE:
		return false
	if not is_instance_valid(customer):
		return false
	if order.is_empty():
		return false

	target_customer = customer
	carried_order = order.duplicate(true)
	target_position = pickup_position
	_set_state(State.MOVE_TO_KITCHEN)
	return true

func _move_toward_target(delta: float) -> void:
	var direction: Vector2 = target_position - global_position
	if skeleton != null and abs(direction.x) > 1.0:
		skeleton.scale.x = 1.0 if direction.x < 0.0 else -1.0

	global_position = global_position.move_toward(target_position, move_speed * delta)
	if global_position.distance_to(target_position) <= arrival_distance:
		global_position = target_position
		_on_target_reached()

func _on_target_reached() -> void:
	match state:
		State.MOVE_TO_KITCHEN:
			_set_state(State.PICKUP)
			_do_pickup()
		State.MOVE_TO_CUSTOMER:
			_set_state(State.SERVE)
			_do_serve()
		State.RETURN_HOME:
			target_customer = null
			carried_order = {}
			_show_carry_indicator(false)
			z_index = home_z_index
			_set_state(State.IDLE)

func _do_pickup() -> void:
	if cooking_station == null or not is_instance_valid(target_customer):
		_abort_to_home()
		return

	var picked_order: Dictionary = cooking_station.take_ready_order(target_customer)
	if picked_order.is_empty():
		_abort_to_home()
		return

	carried_order = picked_order
	print("Dory picked up: ", str(carried_order.get("food_name", "")))
	_show_carry_indicator(true)

	if not is_instance_valid(target_customer):
		_abort_to_home()
		return

	target_position = target_customer.get_serve_position()
	_set_state(State.MOVE_TO_CUSTOMER)

func _do_serve() -> void:
	var served: bool = false
	if is_instance_valid(target_customer):
		served = target_customer.receive_order(carried_order)
		if served:
			print("Dory served: ", str(carried_order.get("food_name", "")))

	if not served:
		push_warning("Dory: failed to deliver order to customer.")
	else:
		# Only clear the carried order on a successful hand-off, so a failed
		# delivery still walks home with the walk_carry animation instead of
		# looking like the food vanished mid-air.
		carried_order = {}
		_show_carry_indicator(false)

	target_customer = null
	target_position = home_position
	_set_state(State.RETURN_HOME)

func _abort_to_home() -> void:
	_show_carry_indicator(false)
	carried_order = {}
	target_customer = null
	target_position = home_position
	_set_state(State.RETURN_HOME)

func _show_carry_indicator(shown: bool) -> void:
	if carry_indicator == null:
		return
	carry_indicator.visible = shown
	if shown and carry_label != null:
		carry_label.text = str(carried_order.get("food_name", ""))

func _set_state(new_state: State) -> void:
	if state == new_state:
		return

	state = new_state
	if new_state == State.MOVE_TO_KITCHEN or new_state == State.MOVE_TO_CUSTOMER or new_state == State.RETURN_HOME:
		z_index = MOVING_Z_INDEX
	_update_animation()
	_update_debug_label()

func _update_animation() -> void:
	if animation_player == null:
		return

	var animation_name: String = "idle"

	match state:
		State.IDLE:
			animation_name = "idle"
		State.MOVE_TO_KITCHEN:
			animation_name = "walk"
		State.PICKUP:
			animation_name = "pickup"
		State.MOVE_TO_CUSTOMER:
			animation_name = "walk_carry"
		State.SERVE:
			animation_name = "serve"
		State.RETURN_HOME:
			animation_name = "walk" if carried_order.is_empty() else "walk_carry"

	if animation_player.current_animation != animation_name or not animation_player.is_playing():
		animation_player.play(animation_name)

func _update_debug_label() -> void:
	if debug_state_label == null:
		return
	match state:
		State.IDLE:
			debug_state_label.text = "IDLE"
		State.MOVE_TO_KITCHEN:
			debug_state_label.text = "TO KITCHEN"
		State.PICKUP:
			debug_state_label.text = "PICKUP"
		State.MOVE_TO_CUSTOMER:
			debug_state_label.text = "TO CUSTOMER"
		State.SERVE:
			debug_state_label.text = "SERVING"
		State.RETURN_HOME:
			debug_state_label.text = "RETURNING"
