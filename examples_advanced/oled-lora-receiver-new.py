# REVISI: Menghapus akses 'source_eid' yang menyebabkan crash.
# Payload tetap berisi data lokasi, jadi data penelitian aman.

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

# --- Variabel Global ---
pending_bundles = ucollections.deque((), 50, 1)
new_bundle_received_flag = False

# --- Callback (DIPERBAIKI) ---
def receive_callback(bundle: Bundle):
    global new_bundle_received_flag
    try:
        # PERBAIKAN: Hanya ambil data payload. Jangan ambil source_eid (bikin crash).
        pending_bundles.append(bundle.payload_block.data)
        new_bundle_received_flag = True
    except IndexError:
        pass
    except Exception as e:
        print(f"Err CB: {e}")

# --- Helper ---
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
    global new_bundle_received_flag

    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    
    rst_pin_oled = Pin(23, Pin.OUT)
    rst_pin_oled.value(0)
    time.sleep_ms(50)
    rst_pin_oled.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
    display = SSD1306_I2C(128, 64, i2c)
    
    # --- Terapkan konfigurasi LoRa (STATIS SF7 CR4/7) ---
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    custom_lora_parameters['spreading_factor'] = 7  
    custom_lora_parameters['coding_rate'] = 7       
    
    print("Menggunakan Konfigurasi LoRa: SF7 CR4/7 (Skenario 2)")

    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    gc.collect()

    print("Memuat framework DTN...")
    
    class GatewayRouter(SimpleEpidemicRouter):
        def immediate_forwarding_attempt(self, *args, **kwargs):
            return (True, 0)

    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    # Tingkatkan sedikit buffer agar aman
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100

    storage = SimpleInMemoryStorage()
    router = GatewayRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    
    # EID Node Gateway
    bpa = BundleProtocolAgent('ipn://3578051002', storage, router)
    
    # Endpoint ID '1'
    receiver_endpoint = LocalEndpoint('1', receive_callback=receive_callback)
    bpa.register_endpoint(receiver_endpoint)

    total_received = 0
    last_bundle_val = "Waiting"
    last_display_update = 0

    print('Receiver LoRa Gateway Skenario 2 Dimulai... (FIXED)')

    # --- FASE 3: Loop Utama ---
    while True:
        bpa.update()

        # Proses antrian bundel
        if new_bundle_received_flag:
            while len(pending_bundles) > 0:
                try:
                    # Ambil data dari queue (Sekarang cuma payload bytes)
                    payload_bytes = pending_bundles.popleft()
                    total_received += 1
                    
                    # Decoding Payload
                    try:
                        payload_data = cbor.loads(payload_bytes)
                        
                        # Ekstrak Data (Map/Dict CBOR)
                        lokasi = payload_data.get(1, 0)
                        sensor_val = payload_data.get(2, 0.0)
                        
                        last_bundle_val = f"{sensor_val:.2f}"
                        
                        # Format Logging CSV (Source kita hardcode 'LoRa' karena EID tidak diambil)
                        # LOG, TotalRx, Source, Lokasi, Sensor, Timestamp
                        print(f"LOG,{total_received},LoRaNode,{lokasi},{sensor_val},{time.ticks_ms()}")
                        
                    except Exception as e_decode:
                        print(f"LOG_ERR,DecodeFail,{len(payload_bytes)},{e_decode}")
                        
                except Exception as e:
                    print(f"Error processing queue: {e}")
            
            new_bundle_received_flag = False
            gc.collect()

        # Update display
        if time.ticks_diff(time.ticks_ms(), last_display_update) > 1000:
            bat_percent = get_battery_percentage(adc)
            display.fill(0)
            display.text("GATEWAY SCEN 2", 0, 0)
            display.text("SF:7 CR:4/7", 0, 12)
            
            if total_received == 0:
                display.text("RX: Waiting...", 0, 30)
            else:
                display.text(f"RX Total: {total_received}", 0, 30)
                display.text(f"Val: {last_bundle_val}", 0, 42)
            
            display.text(f"Bat: {bat_percent}%", 0, 54)
            display.show()
            last_display_update = time.ticks_ms()

        time.sleep_ms(10)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("--- CRITICAL ERROR IN MAIN ---")
        import sys
        sys.print_exception(e)
        print("Rebooting in 5 seconds...")
        time.sleep(5)
        import machine
        machine.reset()