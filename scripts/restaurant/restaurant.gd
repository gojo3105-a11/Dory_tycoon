extends Control

const CUSTOMER_SCENE: PackedScene = preload("res://scenes/characters/customer.tscn")
const FOODS_PATH: String = "res://data/foods.json"

@export var show_coordinate_debug: bool = false

@onready var world: Node2D = get_node_or_null("CenterContainer/DesignArea/World") as Node2D
@onready var spawn_point: Marker2D = get_node_or_null("CenterContainer/DesignArea/World/CustomerSpawnPoint") as Marker2D
@onready var tables: Array[Table] = [
	get_node_or_null("CenterContainer/DesignArea/World/Table1") as Table,
	get_node_or_null("CenterContainer/DesignArea/World/Table2") as Table,
]
@onready var cooking_station: CookingStation = get_node_or_null("CenterContainer/DesignArea/World/KitchenCounter") as CookingStation

var food_list: Array = []

func _ready() -> void:
	food_list = _load_food_list()

	# CenterContainer/DesignArea only resolve their final layout position
	# after at least one layout pass, so global_position reads taken in the
	# same frame as _ready() can still reflect the pre-centering position.
	# Waiting two process frames lets that settle on mobile before we read
	# CustomerSpawnPoint/SeatPoint global_position and spawn the customer.
	await get_tree().process_frame
	await get_tree().process_frame

	if not is_inside_tree():
		return

	_spawn_customer()

func _spawn_customer() -> void:
	if world == null or spawn_point == null:
		push_error("Restaurant: World or CustomerSpawnPoint not found, cannot spawn customer.")
		return
	if CUSTOMER_SCENE == null:
		push_error("Restaurant: customer scene failed to load.")
		return

	var customer: Customer = CUSTOMER_SCENE.instantiate() as Customer
	if customer == null:
		push_error("Restaurant: failed to instantiate customer scene.")
		return

	if not customer.order_created.is_connected(_on_customer_order_created):
		customer.order_created.connect(_on_customer_order_created)

	world.add_child(customer)
	customer.global_position = spawn_point.global_position
	customer.set_available_foods(food_list)

	if show_coordinate_debug:
		print("Spawn: ", spawn_point.global_position)
		if tables.size() > 0 and tables[0] != null:
			print("Table1 seat: ", tables[0].get_seat_position())
		if tables.size() > 1 and tables[1] != null:
			print("Table2 seat: ", tables[1].get_seat_position())

	var table: Table = _find_free_table()
	if table == null:
		var exit_position: Vector2 = spawn_point.global_position + Vector2(0, 60)
		customer.leave_towards(exit_position)
		return

	table.assign_customer()
	customer.move_to_table(table, table.get_seat_position())

func _on_customer_order_created(customer: Customer, order: Dictionary) -> void:
	if cooking_station == null:
		push_error("Restaurant: CookingStation not found.")
		return

	if not cooking_station.accept_order(customer, order):
		push_warning("Restaurant: CookingStation is busy.")

func _find_free_table() -> Table:
	for table in tables:
		if table == null:
			continue
		if not table.has_seat_point():
			continue
		if not table.occupied:
			return table
	return null

func _load_food_list() -> Array:
	if not FileAccess.file_exists(FOODS_PATH):
		push_error("Restaurant: foods.json not found at %s" % FOODS_PATH)
		return []

	var file: FileAccess = FileAccess.open(FOODS_PATH, FileAccess.READ)
	if file == null:
		push_error("Restaurant: failed to open foods.json (error %d)" % FileAccess.get_open_error())
		return []

	var text: String = file.get_as_text()
	file.close()

	var parsed: Variant = JSON.parse_string(text)
	if not (parsed is Array):
		push_error("Restaurant: foods.json did not parse to an Array.")
		return []

	var valid_foods: Array = []
	for entry in parsed:
		if not (entry is Dictionary):
			continue
		var food: Dictionary = entry
		if _is_valid_food(food):
			valid_foods.append(food)

	return valid_foods

func _is_valid_food(food: Dictionary) -> bool:
	if not (food.has("id") and food.has("name") and food.has("cook_time") and food.has("price")):
		return false

	var id_value: Variant = food["id"]
	var name_value: Variant = food["name"]
	var cook_time_value: Variant = food["cook_time"]
	var price_value: Variant = food["price"]

	if not (id_value is String) or (id_value as String).is_empty():
		return false
	if not (name_value is String) or (name_value as String).is_empty():
		return false
	if not (cook_time_value is float or cook_time_value is int) or float(cook_time_value) <= 0.0:
		return false
	if not (price_value is float or price_value is int) or float(price_value) <= 0.0:
		return false
	return true
