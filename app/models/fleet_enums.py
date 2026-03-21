"""Enums for fleet (trucks, trailers) models."""

from enum import Enum


class TruckStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    IN_SHOP = "in_shop"
    RETIRED = "retired"


class TrailerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    RETIRED = "retired"


class OwnershipType(str, Enum):
    COMPANY = "company"
    OWNER_OPERATOR = "owner_operator"
    LEASED = "leased"


class FuelType(str, Enum):
    DIESEL = "diesel"
    GAS = "gas"
    CNG = "cng"
    ELECTRIC = "electric"


class Transmission(str, Enum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    AUTOMATED_MANUAL = "automated_manual"


class TrailerType(str, Enum):
    DRY_VAN = "dry_van"
    REEFER = "reefer"
    FLATBED = "flatbed"
    STEP_DECK = "step_deck"
    LOWBOY = "lowboy"
    TANKER = "tanker"
    DUMP = "dump"
    CHASSIS = "chassis"
    OTHER = "other"


class DoorType(str, Enum):
    SWING = "swing"
    ROLL = "roll"
    CURTAIN = "curtain"


class FleetDocumentEntityType(str, Enum):
    TRUCK = "truck"
    TRAILER = "trailer"
    DRIVER = "driver"
