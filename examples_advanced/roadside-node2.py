# mobile-node-new.py
# SKENARIO 2: Relay Bergerak (Store-Carry-Forward)
# Hardware: Node Mobile (Relay)
# Structure: Strict adaptation of 'mobile-node1.py' (Scenario 1)
# Changes: Static LoRa (SF7 CR4/7), Removed Config Rotation

import gc
import time
import ujson
import os
import machine
from machine import Pin, I2C, ADC
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout

# ====================================================================
# === KONFIGURASI NODE (UBAH INI UNTUK NODE 1 / NODE 2) ===
# Untuk Mobile Node 1, gunakan: 'ipn://3'
# Untuk Mobile Node 2, gunakan: 'ipn://4'
MY_NODE_EID = 'ipn://3500000002'
# ====================================================================

# --- Kelas Helper: Controllable CLA (PENTING: JANGAN DIUBAH) ---
# Kelas ini memungkinkan kita mematikan TX saat mode RX agar hemat baterai
# dan menghindari tabrakan sinyal (Half-Duplex management)
class ControllableRf95LoRaCLA(RF95LoRaCLA):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sending_enabled = True
    
    def enable_sending(self): 
        self.sending_enabled = True
        
    def disable_sending(self): 
        self.sending_enabled = False
        
    def send_to(self, node, bundle_bytes):
        if not self.sending_enabled: 
            return False
        return super().send_to(node, bundle_bytes)

# --- Helper Baterai ---
def get_battery_percentage(adc_pin):
    try:
        adc_val = adc_pin.read()
        v_adc = adc_val / 4095 * 3.6
        v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0

# --- FUNGSI UTAMA ---
def main():
    # 1. Inisialisasi Hardware
    print("--- MOBILE NODE SCENARIO 2 ---")
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    gc.collect()

    # Reset manual LoRa (Penting untuk stabilitas TTGO)
    lora_reset_pin = Pin(23, Pin.OUT)
    lora_reset_pin.value(0)
    time.sleep_ms(100)
    lora_reset_pin.value(1)
    time.sleep_ms(100)

    # 2. Inisialisasi LoRa (STATIS: SF7 CR4/7)
    # Kita kunci parameternya, tidak ada lagi rotasi JSON
    print(f"Setting LoRa: SF7 CR4/7 (Scenario 2 Optimized)")
    
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    custom_lora_parameters['spreading_factor'] = 7  # FIX SF7
    custom_lora_parameters['coding_rate'] = 7       # FIX CR4/7 (Library value 7 = 4/7)
    custom_lora_parameters['tx_power_level'] = 17    # FIX TX Power 17 dBm (Maksimum aman untuk TTGO)
    
    lora_cla = ControllableRf95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': lora_reset_pin, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    
    # Hapus dict config untuk hemat RAM
    del custom_lora_parameters
    gc.collect()

    # 3. Inisialisasi DTN
    print("Memuat framework DTN...")
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    # Batas memori sama seperti Skenario 1 agar aman
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100
    
    storage = SimpleInMemoryStorage()
    gc.collect()
    
    # Router Epidemic: Menerima & Menyebarkan ke siapa saja yang ditemui
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    gc.collect()
    
    bpa = BundleProtocolAgent(MY_NODE_EID, storage, router)
    gc.collect()
    print(f">>> DTN READY: {MY_NODE_EID} <<<")

    # 4. Inisialisasi Display
    display = None
    try:
        from ssd1306 import SSD1306_I2C
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        display = SSD1306_I2C(128, 64, i2c)
        
        # Tampilan Awal
        display.fill(0)
        display.text("MOBILE NODE S2", 0, 0)
        display.text("SF:7 CR:4/7", 0, 15)
        display.text(MY_NODE_EID, 0, 30)
        display.show()
        time.sleep(2)
    except Exception as e:
        print(f"Display Error: {e}")

    # 5. Loop Utama (RX/TX Switching)
    # Logika ini dipertahankan 100% dari Mobile Node Skenario 1
    last_status_update = 0
    last_switch_time = get_current_clock_millis()
    
    # Durasi Switching (dalam ms)
    RECEIVE_DURATION_MS = 15000 # 15 Detik Dengar
    SEND_DURATION_MS = 8000     # 8 Detik Kirim (Store-Carry-FORWARD)
    
    is_in_receive_mode = True
    lora_cla.disable_sending() # Default start as RX
    
    print("Entering Main Loop...")
    
    while True:
        # --- MODIFIKASI: Tangkap Error Memori & Tampilkan Traceback ---
        try:
            bpa.update()
        except MemoryError as e:  # Tangkap error sebagai variabel 'e'
            # 1. Ambil Statistik Terakhir
            current_stored = len(storage.bundles)
            try: free_ram = gc.mem_free()
            except: free_ram = 0
            
            # 2. Cetak Custom Log (Untuk Skripsi)
            print(f"\n[CRITICAL LOG] OUT OF MEMORY REACHED!")
            print(f"[CRITICAL LOG] Limit Bundle: {current_stored}")
            print(f"[CRITICAL LOG] Sisa RAM: {free_ram} bytes")
            
            # 3. Cetak Traceback Asli (Agar tahu error detailnya seperti dulu)
            print("\n--- SYSTEM TRACEBACK DETAIL ---")
            import sys
            sys.print_exception(e)  # <--- INI KUNCINYA
            print("-------------------------------")

            # 4. Tampilkan di OLED
            if display:
                display.fill(0)
                display.text("!!! OOM CRASH !!!", 0, 20)
                display.text(f"Limit: {current_stored} Bndl", 0, 35)
                display.text("See REPL Log...", 0, 50)
                display.show()
            
            print("[CRITICAL LOG] System will RESET in 5 seconds...")
            time.sleep(5) # Beri waktu lebih lama untuk copy-paste log
            machine.reset()
            
        except Exception as e:
            # Tangkap error umum lainnya juga
            print(f"\n[ERROR LAIN] {e}")
            sys.print_exception(e)
            time.sleep(5)
            machine.reset()
        # --------------------------------------------------------------

        current_time = get_current_clock_millis()
        
        # --- Logika Switching RX / TX ---
        if is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, RECEIVE_DURATION_MS):
            # Waktunya berpindah ke Mode KIRIM (Forwarding)
            is_in_receive_mode = False
            lora_cla.enable_sending()
            last_switch_time = current_time
            print("--- Mode Switch: TX (Forwarding) ---")
            
        elif not is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, SEND_DURATION_MS):
            # Waktunya kembali ke Mode DENGAR (Store/Carry)
            is_in_receive_mode = True
            lora_cla.disable_sending()
            last_switch_time = current_time
            print("--- Mode Switch: RX (Listening) ---")
            gc.collect() # Bersihkan memori saat switch mode

        # --- Logika Update Display (Setiap 1 detik) ---
        if is_timestamp_older_than_timeout(last_status_update, 1000):
            num_bundles_stored = len(storage.bundles)
            mode_text = "RX (Listen)" if is_in_receive_mode else "TX (Fwd)"
            bat_percent = get_battery_percentage(adc)

            if display:
                display.fill(0)
                display.text("MOBILE S2", 0, 0)
                display.text(f"SF:7 CR:4/7", 0, 12)
                display.text(f"Bundles: {num_bundles_stored}", 0, 28) # Penting: Cek jumlah paket yg dibawa
                display.text(f"Mode: {mode_text}", 0, 40)
                display.text(f"Bat: {bat_percent}%", 0, 54)
                display.show()
            else:
                print(f"Status: {mode_text}, Stored: {num_bundles_stored}")
                
            last_status_update = current_time
            
        time.sleep_ms(10)

# --- Blok Eksekusi (Safe Boot) ---
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("--- CRITICAL ERROR IN MAIN ---")
        import sys
        sys.print_exception(e)
        print("Rebooting in 5 seconds...")
        time.sleep(5)
        machine.reset()