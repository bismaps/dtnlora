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
import random # ADDED: For Randomized TDD
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
MY_NODE_EID = 'ipn://3500000002'
# ====================================================================

# --- Kelas Helper: Controllable CLA ---
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

def get_formatted_time():
    t = time.localtime()
    return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])

# --- FUNGSI UTAMA ---
def main():
    # 1. Inisialisasi Hardware
    print("--- MOBILE NODE SCENARIO 2 ---")
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    gc.collect()

    # Reset manual LoRa
    lora_reset_pin = Pin(23, Pin.OUT)
    lora_reset_pin.value(0)
    time.sleep_ms(100)
    lora_reset_pin.value(1)
    time.sleep_ms(100)
    # 2. Inisialisasi LoRa (STATIS: SF7 CR4/7)
    print(f"Setting LoRa: SF7 CR4/7 (Scenario 2 Optimized)")
    
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 923E6
    custom_lora_parameters['spreading_factor'] = 11
    custom_lora_parameters['coding_rate'] = 7
    custom_lora_parameters['tx_power_level'] = 17
    
    lora_cla = ControllableRf95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': lora_reset_pin, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    
    del custom_lora_parameters
    gc.collect()

    # 3. Inisialisasi DTN
    print("Memuat framework DTN...")
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 20
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 50
    
    storage = SimpleInMemoryStorage()
    gc.collect()
    
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    gc.collect()
    
    bpa = BundleProtocolAgent(MY_NODE_EID, storage, router)
    gc.collect()
    print(f">>> DTN READY: {MY_NODE_EID} <<<")

    # 4. Inisialisasi Display
    display = None
    adc = ADC(Pin(35)); adc.atten(ADC.ATTN_11DB)
    try:
        from ssd1306 import SSD1306_I2C
        i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
        display = SSD1306_I2C(128, 64, i2c)
        
        display.fill(0)
        display.text("RELAY NODE 2", 0, 0)
        display.text("SF:11 CR:4/7", 0, 15)
        display.text(MY_NODE_EID, 0, 30)
        display.show()
        time.sleep(2)
    except Exception as e:
        print(f"Display Error: {e}")

    # 5. Tracking Variables
    total_bundles_received = 0
    total_bundles_dropped = 0

    # 6. Loop Utama (RX/TX Switching)
    last_status_update = 0
    last_switch_time = get_current_clock_millis()
    
    current_rx_duration = 30000
    current_tx_duration = 30000
    
    is_in_receive_mode = False
    lora_cla.enable_sending()
    
    print(f"[{get_formatted_time()}] Entering Main Loop... Init TX: {current_tx_duration}ms")
    
    while True:
        # Aggressive GC to prevent fragmentation
        gc.collect()
        
        # --- Track Bundle Reception & Drops ---
        prev_known_ids = len(storage.bundle_ids)
        prev_bundle_count = len(storage.bundles)
        
        try:
            bpa.update()
        except MemoryError as e:
            current_stored = len(storage.bundles)
            try: free_ram = gc.mem_free()
            except: free_ram = 0
            
            print(f"\n[CRITICAL LOG] OUT OF MEMORY REACHED!")
            print(f"[CRITICAL LOG] Limit Bundle: {current_stored}")
            print(f"[CRITICAL LOG] Total RX: {total_bundles_received}, Dropped: {total_bundles_dropped}")
            print(f"[CRITICAL LOG] Sisa RAM: {free_ram} bytes")
            
            print("\n--- SYSTEM TRACEBACK DETAIL ---")
            import sys
            sys.print_exception(e)
            print("-------------------------------")

            if display:
                display.fill(0)
                display.text("!!! OOM CRASH !!!", 0, 20)
                display.text(f"Limit: {current_stored}", 0, 35)
                display.text("See REPL Log...", 0, 50)
                display.show()
            
            print("[CRITICAL LOG] System will RESET in 5 seconds...")
            time.sleep(5)
            machine.reset()
            
        except Exception as e:
            print(f"\n[ERROR LAIN] {e}")
            import sys
            sys.print_exception(e)
            time.sleep(5)
            machine.reset()
        
        # Check if a NEW bundle was received
        current_known_ids = len(storage.bundle_ids)
        current_bundle_count = len(storage.bundles)
        
        if current_known_ids > prev_known_ids:
            # A new unique bundle arrived
            total_bundles_received += 1
            
            # Timestamp with MS precision (Split to avoid Float32 loss)
            t_recv_sec = time.time()
            t_recv_ms = time.ticks_ms() % 1000
            t_receive_str = "{}.{:03d}".format(t_recv_sec, t_recv_ms)
            
            if current_bundle_count > prev_bundle_count:
                # Bundle was stored successfully
                print(f"[{get_formatted_time()}] [RX] Bundle stored (Total RX: {total_bundles_received}, T_Receive: {t_receive_str}, Stored: {current_bundle_count})")
            else:
                # Bundle was dropped (storage full)
                total_bundles_dropped += 1
                print(f"[{get_formatted_time()}] [DROP] Bundle dropped! (Total RX: {total_bundles_received}, T_Receive: {t_receive_str}, Dropped: {total_bundles_dropped}, Stored: {current_bundle_count})")
            
            # Defragment heap immediately after processing bundle
            gc.collect()

        current_time = get_current_clock_millis()
        
        # --- Logika Switching RX / TX ---
        if not is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, current_tx_duration):
            # Sedang TX, waktunya habis → ganti ke RX
            is_in_receive_mode = True
            lora_cla.disable_sending()   # Matikan TX
            last_switch_time = current_time
            print(f"[{get_formatted_time()}] --- Switch: RX (For {current_rx_duration}ms) ---")
            gc.collect()

        elif is_in_receive_mode and is_timestamp_older_than_timeout(last_switch_time, current_rx_duration):
            # Sedang RX, waktunya habis → ganti ke TX
            is_in_receive_mode = False
            lora_cla.enable_sending()    # Nyalakan TX
            last_switch_time = current_time
            print(f"[{get_formatted_time()}] --- Switch: TX (For {current_tx_duration}ms) ---")

        # --- Logika Update Display ---
        if is_timestamp_older_than_timeout(last_status_update, 1000):
            num_bundles_stored = len(storage.bundles)
            mode_text = "RX" if is_in_receive_mode else "TX"
            bat_percent = get_battery_percentage(adc)

            if display:
                display.fill(0)
                display.text("RELAY NODE 2", 0, 0)
                display.text(f"SF:11 CR:4/7", 0, 10)
                display.text(f"RX:{total_bundles_received} Drop:{total_bundles_dropped}", 0, 22)
                display.text(f"Stored: {num_bundles_stored}/20", 0, 34)
                display.text(f"Mode: {mode_text}", 0, 46)
                display.text(f"Bat: {bat_percent}%", 0, 56)
                display.show()
            else:
                print(f"Status: {mode_text}, RX:{total_bundles_received}, Drop:{total_bundles_dropped}, Stored: {num_bundles_stored}")
                
            last_status_update = current_time
            
        time.sleep_ms(10)

# --- Blok Eksekusi ---
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