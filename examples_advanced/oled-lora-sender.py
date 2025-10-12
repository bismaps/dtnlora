"""
Versi Produksi oled-lora-sender.py.
Stabil untuk penggunaan lapangan dengan interval pengiriman yang aman
untuk mencegah crash 'abort()'.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import cbor
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.endpoints import LocalEndpoint
from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout

# --- Fungsi-fungsi pembantu ---
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
def main():
    # --- FASE 1: Inisialisasi Perangkat Keras ---
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    
    rst_pin_oled = Pin(23, Pin.OUT)
    rst_pin_oled.value(0)
    time.sleep_ms(50)
    rst_pin_oled.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
    display = SSD1306_I2C(128, 64, i2c)
    display.fill(0)
    display.show()

    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    gc.collect()

    # --- FASE 2: Jalankan Aplikasi DTN ---
    print("Memuat framework DTN...")
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    bpa = BundleProtocolAgent('ipn://1', storage, router)
    sender_endpoint = LocalEndpoint('0')
    bpa.register_endpoint(sender_endpoint)
    gc.collect()

    # --- FASE 3: Loop Utama ---
    bundle_counter = 0
    generation_complete = False
    last_transmission_time = 0
    last_display_update = 0
    
    # =================================================================
    # PERUBAHAN KRUSIAL: Tingkatkan interval pengiriman secara signifikan
    # Memberi waktu 5 detik bagi sistem untuk pulih sepenuhnya antar pengiriman.
    TRANSMISSION_INTERVAL_MS = 5000  # Interval aman: 5 detik
    DISPLAY_INTERVAL_MS = 1000
    # =================================================================

    print('Sender LoRa dimulai...')
    while True:
        bpa.update()

        # Logika Pembuatan Bundel
        if not generation_complete and is_timestamp_older_than_timeout(last_transmission_time, TRANSMISSION_INTERVAL_MS):
            bundle_counter += 1
            
            payload_data = cbor.dumps([bundle_counter, time.ticks_ms(), 150 + (bundle_counter % 50)])
            sender_endpoint.start_transmission(payload_data, 'ipn://2.1') 
            
            print(f"Membuat bundel #{bundle_counter} (Interval: {TRANSMISSION_INTERVAL_MS/1000}s)")
            last_transmission_time = get_current_clock_millis()

            if bundle_counter >= 20:
                generation_complete = True
                print("20 bundel dibuat. Masuk mode CARRY & FORWARD.")
            
            gc.collect()

        # Logika Pembaruan Display
        if is_timestamp_older_than_timeout(last_display_update, DISPLAY_INTERVAL_MS):
            bat_percent = get_battery_percentage(adc)
            display.fill(0)
            display.text("NODE SENDER", 0, 10)
            display.text(f"TX: {bundle_counter}", 0, 25)
            display.text(f"Battery: {bat_percent}%", 0, 40)
            if generation_complete:
                display.text("Mode: Carry", 0, 55)
            display.show()
            last_display_update = get_current_clock_millis()

        time.sleep_ms(200)

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