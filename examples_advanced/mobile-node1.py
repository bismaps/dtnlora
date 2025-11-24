"""
Versi Final mobile-node1.py (Logika Ganti Setiap Boot).
- Setiap kali boot (RST/Power Cycle): Ganti ke konfigurasi LoRa berikutnya.
- Stabil di firmware v1.23.0.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import ujson
import os
import machine
from machine import Pin, I2C, ADC
# (sisa import Anda tetap sama)
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout

# ====================================================================
# --- BAGIAN PENGUBAH PARAMETER LORA (LOGIKA GANTI SETIAP BOOT) ---

LORA_CONFIGS = [
    {'name': "SF:7 CR:4/5", 'sf': 7, 'coding_rate': 5},
    {'name': "SF:7 CR:4/7", 'sf': 7, 'coding_rate': 7},
    {'name': "SF:9 CR:4/5", 'sf': 9, 'coding_rate': 5},
    {'name': "SF:9 CR:4/7", 'sf': 9, 'coding_rate': 7},
    {'name': "SF:11 CR:4/5", 'sf': 11, 'coding_rate': 5},
    {'name': "SF:11 CR:4/7", 'sf': 11, 'coding_rate': 7},
]
CONFIG_FILE = "lora_config.json"
# Tidak perlu RESET_TRACKER_FILE

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
        return True # Berhasil disimpan
    except OSError:
        print("Gagal menyimpan konfigurasi berikutnya.")
        return False # Gagal disimpan

# ====================================================================

# --- Kelas dan Fungsi Pembantu Lainnya ---
class ControllableRf95LoRaCLA(RF95LoRaCLA):
    # ... (implementasi tetap sama) ...
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sending_enabled = True
    def enable_sending(self): self.sending_enabled = True
    def disable_sending(self): self.sending_enabled = False
    def send_to(self, node, bundle_bytes):
        if not self.sending_enabled: return False
        return super().send_to(node, bundle_bytes)

def get_battery_percentage(adc_pin):
    try:
        adc_val = adc_pin.read()
        v_adc = adc_val / 4095 * 3.6; v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0

# --- FUNGSI UTAMA PROGRAM ---
# Terima konfigurasi yang akan digunakan sebagai argumen
def main(active_config):
    # --- Inisialisasi Hardware ---
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35)); adc.atten(ADC.ATTN_11DB); gc.collect()

    # Reset manual LoRa tetap penting
    print("Melakukan reset manual modul LoRa...")
    lora_reset_pin = Pin(23, Pin.OUT)
    lora_reset_pin.value(0); time.sleep_ms(100); lora_reset_pin.value(1); time.sleep_ms(100)

    print(f"Menggunakan Konfigurasi LoRa: {active_config['name']}")

    # Inisialisasi LoRa dengan parameter terpilih
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    custom_lora_parameters['spreading_factor'] = active_config['sf']
    custom_lora_parameters['coding_rate'] = active_config['coding_rate']
    
    lora_cla = ControllableRf95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': lora_reset_pin, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    del custom_lora_parameters; gc.collect()

    # --- Inisialisasi DTN ---
    print("Memuat framework DTN...")
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100
    storage = SimpleInMemoryStorage(); gc.collect()
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage); gc.collect()
    bpa = BundleProtocolAgent('ipn://3', storage, router); gc.collect()
    print(">>> Inisialisasi DTN SUKSES <<<")

    # --- Inisialisasi Display (Lazy Loading) ---
    display = None
    try:
        from ssd1306 import SSD1306_I2C
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        display = SSD1306_I2C(128, 64, i2c)
        display.fill(0)
        display.text("LoRa Config:", 0, 10)
        display.text(active_config['name'], 0, 25)
        display.text("Loading...", 0, 45) # Pesan baru
        display.show()
        time.sleep(3)
        gc.collect()
        print(">>> Inisialisasi Display SUKSES <<<")
    except Exception as e:
        print(f"Gagal menginisialisasi display, berjalan dalam mode headless: {e}")

    # --- Loop Utama ---
    last_status_update = 0
    last_switch_time = get_current_clock_millis()
    RECEIVE_DURATION_MS = 15000
    SEND_DURATION_MS = 8000
    is_in_receive_mode = True
    lora_cla.disable_sending()
    print(f"Mobile Node ({active_config['name']}) dimulai...")
    while True:
        bpa.update()
        current_time = get_current_clock_millis()
        if is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, RECEIVE_DURATION_MS):
            is_in_receive_mode = False; lora_cla.enable_sending(); last_switch_time = current_time
            print("--- Mode: TX (Mengirim) ---")
        elif not is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, SEND_DURATION_MS):
            is_in_receive_mode = True; lora_cla.disable_sending(); last_switch_time = current_time
            print("--- Mode: RX (Menerima) ---")
        if is_timestamp_older_than_timeout(last_status_update, 1000):
            num_bundles_stored = len(storage.bundles)
            mode_text = "RX" if is_in_receive_mode else "TX"
            try: bat_percent = get_battery_percentage(adc)
            except NameError: bat_percent = 0

            if display:
                display.fill(0)
                display.text("MOBILE NODE", 0, 5)
                display.text(active_config['name'], 0, 15) # Tampilkan config aktif
                display.text(f"Stored: {num_bundles_stored}", 0, 30)
                display.text(f"Mode: {mode_text}", 0, 40)
                display.text(f"Battery: {bat_percent}%", 0, 50)
                display.show()
            else: print(f"Status - LoRa:{active_config['name']}, Mode:{mode_text}, Stored:{num_bundles_stored}")
            last_status_update = current_time
        time.sleep_ms(10)


# --- Blok Eksekusi Utama yang Aman ---
if __name__ == "__main__":
    
    # --- Logika Pemilihan Konfigurasi: GANTI SETIAP BOOT ---
    current_config, current_index = get_lora_config()
    print(f"Booting dengan config: {current_config['name']} (index {current_index})")
    save_next_lora_config(current_index) # Simpan index BERIKUTNYA untuk boot selanjutnya

    # Jalankan program utama dengan konfigurasi SAAT INI
    try:
        main(current_config) # Berikan config saat ini ke fungsi main
    except Exception as e:
        print("--- CRITICAL ERROR IN MAIN ---")
        import sys
        sys.print_exception(e)
        print("Rebooting in 5 seconds...")
        time.sleep(5)
        machine.reset() # Reboot otomatis jika ada error di main()