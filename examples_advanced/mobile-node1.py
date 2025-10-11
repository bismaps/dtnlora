# --- FASE 0: Persiapan Awal ---
import gc
import time

# --- FASE 1: Inisialisasi Perangkat Keras (Dibuat Lebih Ringan) ---
print("Menginisialisasi Perangkat Keras...")
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

# --- Fungsi-fungsi pembantu didefinisikan di awal ---
def get_battery_percentage():
    # Fungsi ini hanya akan dipanggil setelah setup selesai
    try:
        adc_val = adc.read()
        v_adc = adc_val / 4095 * 3.6
        v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0

class ControllableRf95LoRaCLA(RF95LoRaCLA):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sending_enabled = True
    def enable_sending(self): self.sending_enabled = True
    def disable_sending(self): self.sending_enabled = False
    def send_to(self, node, bundle_bytes):
        if not self.sending_enabled: return False
        return super().send_to(node, bundle_bytes)

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
display.text('Init OLED OK', 0, 0)
display.show()
gc.collect()
print(f"Memori setelah OLED: {gc.mem_free()} bytes")

# --- Inisialisasi LoRa ---
custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
custom_lora_parameters['frequency'] = 915E6
lora_cla = ControllableRf95LoRaCLA(
    device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
    lora_parameters=custom_lora_parameters
)
del custom_lora_parameters, LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()
print(f"Memori setelah LoRa: {gc.mem_free()} bytes")

# --- FASE 2: Jalankan Aplikasi DTN ---
print("Memuat framework DTN...")
try:
    # Impor semua yang dibutuhkan di sini
    from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
    from dtn7zero.configuration import CONFIGURATION
    from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
    from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout
    from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
    gc.collect()
    print(f"Memori setelah impor DTN: {gc.mem_free()} bytes")

    # --- Konfigurasi ---
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    
    # --- Inisialisasi Objek DTN (Titik Kritis) ---
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    print(f"Memori sebelum BPA: {gc.mem_free()} bytes")
    bpa = BundleProtocolAgent('ipn://3', storage, router) # Ganti ke 'ipn://4' untuk node kedua
    print(f"Memori setelah BPA: {gc.mem_free()} bytes")

    # --- FASE 3: Loop Utama ---
    last_display_update = 0
    last_switch_time = get_current_clock_millis()
    RECEIVE_DURATION_MS = 15000
    SEND_DURATION_MS = 5000
    is_in_receive_mode = True
    lora_cla.disable_sending()
    
    print('Mobile Node (Kurir Cerdas) dimulai...')
    while True:
        if is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, RECEIVE_DURATION_MS):
            is_in_receive_mode = False
            lora_cla.enable_sending()
            last_switch_time = get_current_clock_millis()
            print("--- Mode: TX ---")

        elif not is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, SEND_DURATION_MS):
            is_in_receive_mode = True
            lora_cla.disable_sending()
            last_switch_time = get_current_clock_millis()
            print("--- Mode: RX ---")
        
        bpa.update()

        if is_timestamp_older_than_timeout(last_display_update, 2000):
            try:
                display.fill(0)
                display.text(f"Stored: {len(storage.bundles)}", 0, 10)
                display.text(f"Battery: {get_battery_percentage()}%", 0, 30)
                display.show()
                last_display_update = get_current_clock_millis()
            except OSError as e:
                print(f"OSError saat update display (diabaikan): {e}")

        time.sleep_ms(200)

except Exception as e:
    import sys
    sys.print_exception(e)
finally:
    print("Mobile Node dihentikan.")