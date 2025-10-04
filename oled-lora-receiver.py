"""
Skrip ini akan menerima bundle DTN melalui LoRa
dan menampilkan jumlah bundle yang diterima pada layar OLED.
Diadaptasi dari contoh oled-espnow-receiver.py.
Untuk dijalankan pada perangkat TTGO LORA32 (bertindak sebagai gateway).
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time

gc.collect()
print(f"Memori bebas awal: {gc.mem_free()} bytes")

# --- FASE 1: Inisialisasi Hardware (OLED) ---
print("Menginisialisasi OLED...")
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
gc.collect()

WIDTH = 128
HEIGHT = 64
rst_pin_oled = Pin(23, Pin.OUT)
rst_pin_oled.value(0)
time.sleep_ms(50)
rst_pin_oled.value(1)
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
display = SSD1306_I2C(WIDTH, HEIGHT, i2c)
display.fill(0)
display.show()
print("OLED OK.")
del Pin, I2C
gc.collect()

# --- FASE 2: Inisialisasi Hardware (LoRa) ---
print("Menginisialisasi LoRa...")
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

custom_device_config = {
    'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 12, 'dio_0': 26,
}
custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
custom_lora_parameters['frequency'] = 915E6
lora_cla = RF95LoRaCLA(
    device_config=custom_device_config,
    lora_parameters=custom_lora_parameters
)
print("LoRa OK.")
del LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

# --- FASE 3: Jalankan Aplikasi DTN ---
print("Memuat framework DTN...")
try:
    from py_dtn7 import Bundle
    from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
    from dtn7zero.configuration import CONFIGURATION
    from dtn7zero.endpoints import LocalEndpoint
    from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
    from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
    gc.collect()

    # Setup DTN
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 3
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 8

    clas = {CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter(clas, storage)
    bpa = BundleProtocolAgent('dtn://gateway/', storage, router)

    bundle_counter = 0
    last_payload = ""

    def receive_callback(bundle: Bundle):
        global bundle_counter, last_payload
        bundle_counter += 1
        payload_text = bundle.payload_block.data.decode('utf-8')
        last_payload = payload_text

        # --- TAMBAHAN PENTING UNTUK LOGGING ---
        # Waktu penerimaan bisa didapat dari sistem
        reception_timestamp = time.ticks_ms() 

        # Cetak ke konsol serial dalam format CSV
        # Format: No_Bundle, Payload, Waktu_Terima_ms
        print(f"LOG,{bundle_counter},{payload_text},{reception_timestamp}")
        # ----------------------------------------

        display.fill(0)
        display.text('LORA RECEIVER', 20, 0, 1)
        display.text('Rx:', 0, 20, 1)
        display.text(str(bundle_counter), 40, 20, 1)
        display.text('Message:', 0, 40, 1)
        display.text(last_payload[:16], 0, 50, 1)
        display.show()

    receiver_endpoint = LocalEndpoint('data-receiver', receive_callback=receive_callback)
    bpa.register_endpoint(receiver_endpoint)

    display.text('LORA RECEIVER', 15, 0, 1)
    display.text('Waiting...', 0, 30, 1)
    display.show()
    print('Receiver LoRa dimulai, menunggu bundle...')

    while True:
        bpa.update()
        time.sleep(0.1)

except Exception as e:
    print(f"Terjadi error fatal: {e}")
finally:
    if 'bpa' in locals() and 'receiver_endpoint' in locals():
        bpa.unregister_endpoint(receiver_endpoint)
    print("Receiver dihentikan.")