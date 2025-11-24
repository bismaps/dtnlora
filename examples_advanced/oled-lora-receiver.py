"""
Versi Produksi oled-lora-receiver.py + Logika Ganti Setiap Boot.
- Menambahkan rotasi konfigurasi LoRa seperti pada node_fixed.
- Fungsi utama penerimaan bundel tidak diubah.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import cbor
import ujson
import os
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from py_dtn7 import Bundle
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.endpoints import LocalEndpoint
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
import ucollections


# ====================================================================
# === ADOPSI LOGIKA GANTI SETIAP BOOT (DARI node_fixed) ===
LORA_CONFIGS = [
    {'name': "SF:7 CR:4/5", 'sf': 7, 'coding_rate': 5},
    {'name': "SF:7 CR:4/7", 'sf': 7, 'coding_rate': 7},
    {'name': "SF:9 CR:4/5", 'sf': 9, 'coding_rate': 5},
    {'name': "SF:9 CR:4/7", 'sf': 9, 'coding_rate': 7},
    {'name': "SF:11 CR:4/5", 'sf': 11, 'coding_rate': 5},
    {'name': "SF:11 CR:4/7", 'sf': 11, 'coding_rate': 7},
]
CONFIG_FILE = "lora_config.json"

def get_lora_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            index = ujson.load(f).get('index', 0) % len(LORA_CONFIGS)
    except (OSError, ValueError):
        index = 0
    return LORA_CONFIGS[index], index

def save_next_lora_config(current_index):
    next_index = (current_index + 1) % len(LORA_CONFIGS)
    try:
        with open(CONFIG_FILE, 'w') as f:
            ujson.dump({'index': next_index}, f)
        print(f"Konfigurasi BERIKUTNYA disimpan: {LORA_CONFIGS[next_index]['name']}")
        return True
    except OSError:
        print("Gagal menyimpan konfigurasi berikutnya.")
        return False
# ====================================================================


# --- Variabel Global untuk komunikasi aman antara callback dan loop utama ---
pending_bundles = ucollections.deque((), 50, 1)  # Antrian untuk menampung payload mentah
new_bundle_received_flag = False


# --- Callback penerimaan bundel ---
def receive_callback(bundle: Bundle):
    global new_bundle_received_flag
    try:
        pending_bundles.append(bundle.payload_block.data)
        new_bundle_received_flag = True
    except IndexError:
        pass  # Abaikan jika antrian penuh


# --- Fungsi pembantu ---
def get_battery_percentage(adc_pin):
    try:
        adc_val = adc_pin.read()
        v_adc = adc_val / 4095 * 3.6
        v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0


# --- FUNGSI UTAMA PROGRAM ---
def main(active_config):
    global new_bundle_received_flag

    # --- FASE 1: Inisialisasi Perangkat Keras ---
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    
    rst_pin_oled = Pin(23, Pin.OUT)
    rst_pin_oled.value(0)
    time.sleep_ms(50)
    rst_pin_oled.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    display = SSD1306_I2C(128, 64, i2c)
    
    # --- Terapkan konfigurasi LoRa aktif ---
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    custom_lora_parameters['spreading_factor'] = active_config['sf']
    custom_lora_parameters['coding_rate'] = active_config['coding_rate']
    print(f"Menggunakan Konfigurasi LoRa: {active_config['name']}")

    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    gc.collect()

    # --- FASE 2: Jalankan Aplikasi DTN ---
    print("Memuat framework DTN...")
    class GatewayRouter(SimpleEpidemicRouter):
        def immediate_forwarding_attempt(self, *args, **kwargs):
            return (True, 0)

    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100

    storage = SimpleInMemoryStorage()
    router = GatewayRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    bpa = BundleProtocolAgent('ipn://2', storage, router)
    receiver_endpoint = LocalEndpoint('1', receive_callback=receive_callback)
    bpa.register_endpoint(receiver_endpoint)

    total_received = 0
    last_bundle_data = {}
    last_display_update = 0

    print(f'Receiver LoRa dimulai... ({active_config["name"]})')

    # --- FASE 3: Loop Utama ---
    while True:
        bpa.update()

        # Proses antrian bundel
        if new_bundle_received_flag:
            while len(pending_bundles) > 0:
                payload_bytes = pending_bundles.popleft()
                total_received += 1
                
                try:
                    payload_data = cbor.loads(payload_bytes)
                    last_bundle_data['id'] = payload_data[0]
                    last_bundle_data['level'] = payload_data[2]
                    print(f"LOG,{total_received},{payload_data[0]},{payload_data[2]},{payload_data[1]},{time.ticks_ms()}")
                except Exception as e:
                    print(f"Error processing payload: {e}")
            
            new_bundle_received_flag = False
            gc.collect()

        # Update display
        if time.ticks_diff(time.ticks_ms(), last_display_update) > 1000:
            bat_percent = get_battery_percentage(adc)
            display.fill(0)
            display.text("NODE GATEWAY", 0, 10)
            display.text(active_config['name'], 0, 20)
            
            if total_received == 0:
                display.text("RX: Waiting...", 0, 35)
            else:
                display.text(f"RX: {total_received}", 0, 35)
                if last_bundle_data:
                    display.text(f"ID:{last_bundle_data['id']} Lvl:{last_bundle_data['level']}", 0, 55)
            
            display.text(f"Battery:{bat_percent}%", 0, 45)
            display.show()
            last_display_update = time.ticks_ms()

        time.sleep_ms(10)


# --- Blok Eksekusi Utama yang Aman ---
if __name__ == "__main__":
    # === ADOPSI LOGIKA GANTI SETIAP BOOT ===
    current_config, current_index = get_lora_config()
    print(f"Booting dengan config: {current_config['name']} (index {current_index})")
    save_next_lora_config(current_index)

    try:
        main(current_config)
    except Exception as e:
        print("--- CRITICAL ERROR IN MAIN ---")
        import sys
        sys.print_exception(e)
        print("Rebooting in 15 seconds...")
        time.sleep(15)
        import machine
        machine.reset()
