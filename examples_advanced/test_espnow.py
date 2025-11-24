"""
Optimized OLED + ESP-NOW DTN sender for TTGO-LORA32
Firmware Glenn20 compatible
"""
import time
import gc
from machine import Pin, SoftI2C
from ssd1306 import SSD1306_I2C

# -----------------------------
# 1. DISPLAY SETUP
# -----------------------------
WIDTH = 128
HEIGHT = 64

# reset pin optional, bisa dicoba jika oled hang
rst = Pin(16, Pin.OUT)
rst.value(1)

# I2C default TTGO-LORA32 pins
i2c = SoftI2C(sda=Pin(21), scl=Pin(22))
display = SSD1306_I2C(WIDTH, HEIGHT, i2c)
display.fill(0)
display.text("Initializing...", 0, 0)
display.show()

# -----------------------------
# 2. ESP-NOW CLA SETUP
# -----------------------------
from dtn7zero.convergence_layer_adapters.espnow_cla import EspNowCLA

print("Init EspNowCLA...")
espnow_cla = EspNowCLA()
print("ESP-NOW CLA initialized successfully!")

gc.collect()  # bersihkan RAM setelah init ESP-NOW

display.fill(0)
display.text("ESP-NOW OK", 0, 0)
display.show()
time.sleep(0.2)

# -----------------------------
# 3. DTN7Zero SETUP
# -----------------------------
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.endpoints import LocalEndpoint
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout

# Configuration
CONFIGURATION.IPND.ENABLED = False
CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 2
CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 4

clas = {CONFIGURATION.IPND.IDENTIFIER_ESPNOW: espnow_cla}
storage = SimpleInMemoryStorage()
router = SimpleEpidemicRouter(clas, storage)
bpa = BundleProtocolAgent('dtn://esp-0/', storage, router)
sender_endpoint = LocalEndpoint('sender')
bpa.register_endpoint(sender_endpoint)

# -----------------------------
# 4. MAIN LOOP
# -----------------------------
message_str = 'hello_world {}'
bundle_counter = 0
last_transmission = get_current_clock_millis()

display.fill(0)
display.text('ESPNOW TEST', 20, 0, 1)
display.text('num bundles', 0, 24, 1)
display.text('sent: {}'.format(bundle_counter), 0, 40, 1)
display.show()

print('sender started')
try:
    while True:
        bpa.update()

        if is_timestamp_older_than_timeout(last_transmission, 2000):
            bundle_counter += 1
            sender_endpoint.start_transmission(
                message_str.format(bundle_counter).encode('utf-8'),
                'dtn://esp-1/incoming'
            )

            # update OLED
            display.fill_rect(0, 40, 128, 16, 0)
            display.text('sent: {}'.format(bundle_counter), 0, 40, 1)
            display.show()
            time.sleep(0.1)

            last_transmission = get_current_clock_millis()

        time.sleep(0.05)
        gc.collect()  # bersihkan RAM tiap loop untuk stabilitas

except KeyboardInterrupt:
    print("Stopping sender...")

bpa.unregister_endpoint(sender_endpoint)
