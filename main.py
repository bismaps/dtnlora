# SKENARIO 2: Uji Performa DTN (Fixed Parameter, Variable Load)
# Hardware: Node Fixed (Sender)
# Structure: Based on Scenario 1 production code

import gc
import time
import cbor
import json
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
    print("--- SENDER SCENARIO 2 (FINAL) ---")
    adc = ADC(Pin(35)); adc.atten(ADC.ATTN_11DB)
    rst = Pin(23, Pin.OUT); rst.value(0); time.sleep_ms(50); rst.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    display = SSD1306_I2C(128, 64, i2c)
    
    # LoRa Init (SF7 CR4/7)
    lora_params = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    lora_params['frequency'] = 915E6
    lora_params['spreading_factor'] = 7
    lora_params['coding_rate'] = 7 
    lora_params['tx_power_level'] = 17
    
    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=lora_params
    )
    gc.collect()

    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    storage = SimpleInMemoryStorage() 
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    
    # ID SENDER (SENSOR): 3578031006
    bpa = BundleProtocolAgent('ipn://3578031006', storage, router)
    sender_endpoint = LocalEndpoint('1')
    bpa.register_endpoint(sender_endpoint)
    gc.collect()

    bundle_counter = 0
    target_bundles = test_config['bundles']
    interval_ms = test_config['interval_min'] * 60 * 1000
    
    PAYLOAD_LOKASI = 3578031006
    
    last_send_time = -interval_ms 
    last_display_time = 0
    cooldown_start_time = 0
    cooldown_duration_ms = 60000
    
    print(f"Config: {test_config['id']} (Bundles={target_bundles}, Int={test_config['interval_min']}m)")

    while True:
        bpa.update()
        current_time = time.ticks_ms()

        # --- LOGIKA PENGIRIMAN ---
        if bundle_counter < target_bundles:
            if time.ticks_diff(current_time, last_send_time) >= interval_ms:
                bundle_counter += 1
                
                dynamic_water = 150.0 + (bundle_counter / 1.15 % 15)
                sender_timestamp = time.ticks_ms()
                
                data = {
                    1: PAYLOAD_LOKASI,    
                    2: dynamic_water,     
                    3: sender_timestamp   
                }
                payload_bytes = cbor.dumps(data)
                
                sender_endpoint.start_transmission(payload_bytes, 'ipn://3578251001.1')
                
                print(f"Sent #{bundle_counter}: Val={dynamic_water}, T_Send={sender_timestamp}")
                last_send_time = current_time
                gc.collect()
        
        elif bundle_counter == target_bundles:
            print("--- DONE SENDING. Starting 60s cooldown for delivery... ---")
            cooldown_start_time = current_time
            bundle_counter += 1
        
        elif bundle_counter == target_bundles + 1:
            elapsed_ms = time.ticks_diff(current_time, cooldown_start_time)
            if elapsed_ms >= cooldown_duration_ms:
                print("--- COOLDOWN COMPLETE. IDLE. ---")
                bundle_counter += 1

        # --- TAMPILAN OLED ---
        if time.ticks_diff(current_time, last_display_time) > 1000:
            bat = get_battery_percentage(adc)
            display.fill(0)
            display.text("SOURCE NODE", 0, 0)
            display.text(f"SF:7 CR:4/7", 0, 10)
            display.text(f"Test: {test_config['id']}", 0, 22)
            display.text(f"Sent: {min(bundle_counter, target_bundles)}/{target_bundles}", 0, 34)
            
            if bundle_counter > target_bundles + 1:
                display.text("STATUS: DONE", 0, 46)
            elif bundle_counter == target_bundles + 1:
                remaining_ms = cooldown_duration_ms - time.ticks_diff(current_time, cooldown_start_time)
                remaining_s = max(0, remaining_ms // 1000)
                display.text(f"Cooldown: {remaining_s}s", 0, 46)
            else:
                display.text(f"Intv: {test_config['interval_min']}m", 0, 46)
                
            display.text(f"Bat: {bat}%", 0, 56)
            display.show()
            last_display_time = current_time
        
        time.sleep_ms(10)

# --- BOOTSTRAP ---
if __name__ == "__main__":
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