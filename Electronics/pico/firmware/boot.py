"""Rev E commissioning: hold the two-transistor fan driver STOP (GP16 low)."""
from machine import Pin
Pin(16, Pin.OUT, value=0)
