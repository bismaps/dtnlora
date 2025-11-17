# SKENARIO 2: Uji Performa DTN (Fixed Parameter, Variable Load)
# Hardware: Node Fixed (Sender)
# Structure: Based on Scenario 1 production code

import gc
import time
import cbor
import ujson
import machine
import os
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.endpoints import LocalEndpoint
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter

# ====================================================================
# === LOGIKA ROTASI SKENARIO (Traffic Load) ===
# Variabel Independen: Jumlah Bundle & Interval
TEST_MATRIX = [
    {'id': "S2.1", 'bundles': 20, 'interval_min': 1},
    {'id': "S2.2", 'bundles': 20, 'interval_min': 2},
    {'id': "S2.3", 'bundles': 30, 'interval_min': 1},
    {'id': "S2.4", 'bundles': 30, 'interval_min': 2},
    {'id': "S2.5", 'bundles': 40, 'interval_min': 1},
    {'id': "S2.6", 'bundles': 40, 'interval_min': 2},
]
STATE_FILE = "skenario_state.txt"

def get_test_config():
    try:
        with open(STATE_FILE, 'r') as f:
            content = f.read()
            index = int(content) if content else 0
            index = index % len(TEST_MATRIX)
    except Exception:
        index = 0
    return TEST_MATRIX[index], index

def save_next_test_config(current_index):
    next_index = (current_index + 1) % len(TEST_MATRIX)
    try:
        with open(STATE_FILE, 'w') as f:
            f.write(str(next_index))
        print(f"Next Boot Config: Index {next_index}")
    except Exception as e:
        print(f"Failed to save state: {e}")
# ====================================================================

# --- Helpers ---
def get_battery_percentage(adc_pin):
    try:
        adc_val = adc_pin.read()
        v_bat = (adc_val / 4095 * 3.6) * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except:
        return 0

# --- MAIN PROGRAM ---
def main(test_config):
    # 1. Hardware Init
    print("--- INIT HARDWARE ---")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    
    rst_oled = Pin(23, Pin.OUT)
    rst_oled.value(0); time.sleep_ms(50); rst_oled.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000) # Speed up I2C
    display = SSD1306_I2C(128, 64, i2c)
    
    # 2. LoRa Init (STATIC PARAMETERS - OPTIMAL RESULT SCENARIO 1)
    # SF7, CR4/7, BW125
    lora_params = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    lora_params['frequency'] = 915E6
    lora_params['spreading_factor'] = 7
    lora_params['coding_rate'] = 7 
    
    print(f"LoRa Config: SF7 CR4/7 (Static)")
    print(f"Test Config: {test_config['id']} (N={test_config['bundles']}, T={test_config['interval_min']}m)")

    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=lora_params
    )
    gc.collect()

    # 3. DTN Stack Init
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    
    # Storage disesuaikan agar cukup menampung antrian uji (max 40 + buffer)
    storage = SimpleInMemoryStorage() 
    # Router
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    # BPA: Source ID spesifik untuk tracking
    bpa = BundleProtocolAgent('ipn://3578110005', storage, router)
    sender_endpoint = LocalEndpoint('1')
    bpa.register_endpoint(sender_endpoint)
    
    gc.collect()

    # 4. Execution Loop
    bundle_counter = 0
    target_bundles = test_config['bundles']
    interval_ms = test_config['interval_min'] * 60 * 1000
    
    # Data Payload (Simulasi Sensor)
    PAYLOAD_LOKASI = 3578110005
    PAYLOAD_VAL = 150.75
    
    last_send_time = -interval_ms # Force send immediately
    last_display_time = 0
    
    print("--- STARTING TEST LOOP ---")

    while True:
        bpa.update()
        current_time = time.ticks_ms()

        # A. Sending Logic
        if bundle_counter < target_bundles:
            if time.ticks_diff(current_time, last_send_time) >= interval_ms:
                bundle_counter += 1
                
                # Construct Payload (Map CBOR ~ 17 bytes raw data + overhead)
                # Key 1: Lokasi (int), Key 2: Sensor (float)
                data = {1: PAYLOAD_LOKASI, 2: PAYLOAD_VAL}
                payload_bytes = cbor.dumps(data)
                
                # Send to Gateway
                # Destination EID: ipn://3578051002.1 (Node Gateway)
                sender_endpoint.start_transmission(payload_bytes, 'ipn://3578051002.1')
                
                print(f"[{test_config['id']}] Sent Bundle #{bundle_counter}/{target_bundles}")
                last_send_time = current_time
                gc.collect() # Critical for memory
        
        else:
            # Selesai mengirim, masuk mode diam/maintenance
            if bundle_counter == target_bundles:
                print("--- ALL BUNDLES SENT. IDLE MODE. ---")
                bundle_counter += 1 # Increment sekali lagi agar tidak print terus

        # B. Display Logic
        if time.ticks_diff(current_time, last_display_time) > 1000:
            bat = get_battery_percentage(adc)
            display.fill(0)
            display.text(f"SCENARIO 2: {test_config['id']}", 0, 0)
            display.text(f"SF:7 CR:4/7", 0, 10)
            display.text(f"Sent: {min(bundle_counter, target_bundles)} / {target_bundles}", 0, 25)
            
            if bundle_counter > target_bundles:
                display.text("STATUS: DONE", 0, 40)
            else:
                display.text(f"Intv: {test_config['interval_min']}m", 0, 40)
                
            display.text(f"Bat: {bat}%", 0, 54)
            display.show()
            last_display_time = current_time
        
        time.sleep_ms(10)

# --- BOOTSTRAP ---
if __name__ == "__main__":
    # Load Config & Prepare Next State
    cfg, idx = get_test_config()
    save_next_test_config(idx)
    
    try:
        main(cfg)
    except Exception as e:
        print("CRITICAL ERROR - REBOOTING")
        import sys
        sys.print_exception(e)
        time.sleep(5)
        machine.reset()