"""
Skrip ini akan menerima bundle DTN melalui LoRa
dan menampilkan jumlah bundle yang diterima pada layar OLED.
Diadaptasi dari contoh oled-espnow-receiver.py.
Untuk dijalankan pada perangkat TTGO LORA32 (bertindak sebagai gateway).
Payload diterima dalam format CBOR.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import cbor

# --- FASE 1: Inisialisasi Perangkat Keras ---
print("Menginisialisasi Perangkat Keras...")
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

# --- Fungsi-fungsi pembantu ---
def get_battery_percentage():
    try:
        adc_val = adc.read()
        v_adc = adc_val / 4095 * 3.6
        v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0

# --- Inisialisasi ADC ---
adc = ADC(Pin(35))
adc.atten(ADC.ATTN_11DB)
gc.collect()

# --- Inisialisasi OLED ---
rst_pin_oled = Pin(23, Pin.OUT)
rst_pin_oled.value(0)
time.sleep_ms(50)
rst_pin_oled.value(1)
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
display = SSD1306_I2C(128, 64, i2c)
display.fill(0)
display.show()
gc.collect()
print(f"Memori setelah OLED: {gc.mem_free()} bytes")

# --- Inisialisasi LoRa ---
custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
custom_lora_parameters['frequency'] = 915E6
lora_cla = RF95LoRaCLA(
    device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
    lora_parameters=custom_lora_parameters
)
del custom_lora_parameters, LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()
print(f"Memori setelah LoRa: {gc.mem_free()} bytes")

# --- FASE 2: Jalankan Aplikasi DTN ---
print("Memuat framework DTN...")
try:
    from py_dtn7 import Bundle
    from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
    from dtn7zero.configuration import CONFIGURATION
    from dtn7zero.endpoints import LocalEndpoint
    from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
    from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
    gc.collect()

    class GatewayRouter(SimpleEpidemicRouter):
        def immediate_forwarding_attempt(self, full_node_uri: str, bundle_information) -> (bool, int):
            return (True, 0)

    # Setup DTN
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 25 
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 30

    clas = {CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}
    storage = SimpleInMemoryStorage()
    router = GatewayRouter(clas, storage)
    bpa = BundleProtocolAgent('ipn://2', storage, router)

    total_received = 0 # Variabel untuk menghitung total bundle yang diterima

    # ====================================================================
    # --- FUNGSI CALLBACK DENGAN NAMA VARIABEL YANG KONSISTEN ---
    def receive_callback(bundle: Bundle):
        global total_received
        total_received += 1
        reception_timestamp = time.ticks_ms()

        try:
            # 1. Dekode payload biner menggunakan cbor.loads()
            payload_data = cbor.loads(bundle.payload_block.data)

            # 2. Ekstrak data dari list dengan nama variabel yang sama seperti di PENGIRIM
            bundle_counter       = payload_data[0]
            sending_timestamp_ms = payload_data[1]
            level_air            = payload_data[2]

            # 3. Cetak log dengan nama yang konsisten
            print(f"#LOG ID:{bundle_counter}, Level: {level_air}, TX Time: {sending_timestamp_ms}, RX Time: {reception_timestamp}")

            # 4. Tampilkan data di OLED
            bat_percent = get_battery_percentage()
            display.fill(0)
            display.text("NODE GATEWAY", 0, 10)
            display.text(f"TX: {total_received}", 0, 25)
            display.text(f"Battery: {bat_percent}%", 0, 40)
            display.text(f"ID: {bundle_counter} Lvl: {level_air}", 0, 55)
            display.show()

        except Exception as e:
            print(f"Error processing bundle payload: {e}")
            display.fill(0)
            display.text("PAYLOAD ERROR", 0, 25)
            display.show()
            
    # ====================================================================

    receiver_endpoint = LocalEndpoint('1', receive_callback=receive_callback)
    bpa.register_endpoint(receiver_endpoint)

    bat_percent = get_battery_percentage()
    display.text("NODE GATEWAY", 0, 10)
    display.text(f"TX: Waiting...", 0, 25)
    display.text(f"Battery: {bat_percent}%", 0, 40)
    display.show()
    print('Receiver LoRa dimulai, menunggu bundle...')

    while True:
        bpa.update()
        time.sleep_ms(200)

except Exception as e:
    import sys
    sys.print_exception(e)
finally:
    if 'bpa' in locals() and 'receiver_endpoint' in locals():
        bpa.unregister_endpoint(receiver_endpoint)
    print("Receiver dihentikan.")