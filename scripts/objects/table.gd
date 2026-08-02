extends Node2D
class_name Table

@export var occupied: bool = false

@onready var seat_point: Marker2D = get_node_or_null("SeatPoint") as Marker2D

func has_seat_point() -> bool:
	return seat_point != null

func get_seat_position() -> Vector2:
	if seat_point == null:
		return global_position
	return seat_point.global_position

func assign_customer() -> void:
	occupied = true

func release_customer() -> void:
	occupied = false
