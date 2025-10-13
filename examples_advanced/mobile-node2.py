"""
Versi Eksperimental mobile-node1.py dengan 'Lazy Loading' Display.
Mencoba mengaktifkan kembali OLED setelah inisialisasi DTN yang kritis selesai.
"""
# --- FASE 0: Persiapan Awal (impor minimalis) ---
import gc
import time
from machine import Pin, I2C, ADC
# JANGAN impor ssd1306 di sini untuk menghemat memori awal
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout

# --- Kelas dan Fungsi Pembantu ---
class ControllableRf95LoRaCLA(RF95LoRaCLA):
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
def main():
    # --- Inisialisasi Hardware (tanpa display) ---
    print("Menginisialisasi Perangkat Keras (tanpa display)...")
    adc = ADC(Pin(35)); adc.atten(ADC.ATTN_11DB); gc.collect()

    shared_reset_pin = Pin(23, Pin.OUT)
    shared_reset_pin.value(0); time.sleep_ms(50); shared_reset_pin.value(1)

    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    lora_cla = ControllableRf95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': shared_reset_pin, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    del custom_lora_parameters; gc.collect()

    # --- Inisialisasi DTN (Prioritas Utama) ---
    print("Memuat framework DTN...")
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100

    storage = SimpleInMemoryStorage(); gc.collect()
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage); gc.collect()
    bpa = BundleProtocolAgent('ipn://4', storage, router); gc.collect()
    
    print(">>> Inisialisasi DTN SUKSES <<<")

    # --- Inisialisasi Display (Setelah DTN sukses) ---
    print("Mencoba menginisialisasi Display...")
    display = None
    try:
        from ssd1306 import SSD1306_I2C
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        display = SSD1306_I2C(128, 64, i2c)
        display.fill(0)
        display.text("DTN Init OK", 0, 0)
        display.show()
        gc.collect()
        print(">>> Inisialisasi Display SUKSES <<<")
    except Exception as e:
        print(f"Gagal menginisialisasi display, berjalan dalam mode headless: {e}")
        # Jika gagal, 'display' akan tetap None

    # --- Loop Utama ---
    last_status_update = 0
    last_switch_time = get_current_clock_millis()
    RECEIVE_DURATION_MS = 15000
    SEND_DURATION_MS = 15000
    is_in_receive_mode = True
    lora_cla.disable_sending()

    print('Mobile Node (Lazy Loading + OLED) dimulai...')
    while True:
        bpa.update()
        current_time = get_current_clock_millis()

        if is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, RECEIVE_DURATION_MS):
            is_in_receive_mode = False; lora_cla.enable_sending(); last_switch_time = current_time
            print("--- Mode: TX (Mengirim) ---")
        elif not is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, SEND_DURATION_MS):
            is_in_receive_mode = True; lora_cla.disable_sending(); last_switch_time = current_time
            print("--- Mode: RX (Menerima) ---")
        
        # Cetak status ke REPL atau OLED setiap detik
        if is_timestamp_older_than_timeout(last_status_update, 1000):
            num_bundles_stored = len(storage.bundles)
            mode_text = "RX" if is_in_receive_mode else "TX"
            bat_percent = get_battery_percentage(adc)

            if display:
                # Jika display berhasil diinisialisasi, gunakan OLED
                display.fill(0)
                display.text("MOBILE NODE", 0, 10)
                display.text(f"Stored: {num_bundles_stored}", 0, 25)
                display.text(f"Battery: {bat_percent}%", 0, 40)
                display.text(f"Mode: {mode_text}", 0, 55)
                display.show()
            else:
                # Jika tidak, cetak ke REPL sebagai fallback
                print(f"Status - Mode: {mode_text}, Bundel Tersimpan: {num_bundles_stored}, Baterai: {bat_percent}%")
            
            last_status_update = current_time

        time.sleep_ms(10)

# --- Blok Eksekusi Utama yang Aman ---
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("--- CRITICAL ERROR IN MAIN ---")
        import sys
        sys.print_exception(e)
        print("Rebooting in 15 seconds...")
        time.sleep(15)
        import machine
        machine.reset()