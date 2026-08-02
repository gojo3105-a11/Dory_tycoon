extends Control

const CUSTOMER_SCENE: PackedScene = preload("res://scenes/characters/customer.tscn")

@onready var world: Node2D = get_node_or_null("CenterContainer/DesignArea/World") as Node2D
@onready var spawn_point: Marker2D = get_node_or_null("CenterContainer/DesignArea/World/CustomerSpawnPoint") as Marker2D
@onready var tables: Array[Table] = [
	get_node_or_null("CenterContainer/DesignArea/World/Table1") as Table,
	get_node_or_null("CenterContainer/DesignArea/World/Table2") as Table,
]

func _ready() -> void:
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

	world.add_child(customer)
	customer.global_position = spawn_point.global_position

	var table: Table = _find_free_table()
	if table == null:
		var exit_position: Vector2 = spawn_point.global_position + Vector2(0, 60)
		customer.leave_towards(exit_position)
		return

	table.assign_customer()
	customer.move_to_table(table, table.get_seat_position())

func _find_free_table() -> Table:
	for table in tables:
		if table == null:
			continue
		if not table.has_seat_point():
			continue
		if not table.occupied:
			return table
	return null
