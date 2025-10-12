"""
Skrip ini akan mengirimkan bundle DTN melalui LoRa ke semua perangkat dalam jangkauan
dan menampilkan jumlah bundle yang terkirim pada layar OLED.
Diadaptasi dari contoh oled-espnow-sender.py untuk digunakan dengan LoRa.
Untuk dijalankan pada perangkat TTGO LORA32.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import cbor

# --- FASE 1: Inisialisasi Perangkat Keras ---
print("Menginisialisasi Perangkat Keras...")
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

# --- Fungsi-fungsi pembantu ---
def get_battery_percentage():
    try:
        adc_val = adc.read()
        v_adc = adc_val / 4095 * 3.6
        v_bat = v_adc * 2
        percentage = (v_bat - 3.2) / (4.2 - 3.2) * 100
        return int(max(0, min(100, percentage)))
    except Exception:
        return 0

# --- Inisialisasi ADC ---
adc = ADC(Pin(35))
adc.atten(ADC.ATTN_11DB)
gc.collect()

# --- Inisialisasi OLED ---
rst_pin_oled = Pin(23, Pin.OUT)
rst_pin_oled.value(0)
time.sleep_ms(50)
rst_pin_oled.value(1)
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000) # Frekuensi I2C stabil
display = SSD1306_I2C(128, 64, i2c)
display.fill(0)
display.show()
gc.collect()
print(f"Memori setelah OLED: {gc.mem_free()} bytes")

# --- Inisialisasi LoRa ---
custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
custom_lora_parameters['frequency'] = 915E6
lora_cla = RF95LoRaCLA(
    device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
    lora_parameters=custom_lora_parameters
)
del custom_lora_parameters, LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()
print(f"Memori setelah LoRa: {gc.mem_free()} bytes")

# --- FASE 2: Jalankan Aplikasi DTN ---
print("Memuat framework DTN...")
try:
    from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
    from dtn7zero.configuration import CONFIGURATION
    from dtn7zero.endpoints import LocalEndpoint
    from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
    from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
    from dtn7zero.utility import get_current_clock_millis, is_timestamp_older_than_timeout
    gc.collect()

    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    bpa = BundleProtocolAgent('ipn://1', storage, router)
    sender_endpoint = LocalEndpoint('0')
    bpa.register_endpoint(sender_endpoint)

    # --- FASE 3: Loop Utama (Struktur Stabil dengan 2 Timer) ---
    # message_str = 'ID:{};TIME:{};LEVEL:{}'
    bundle_counter = 0
    generation_complete = False

    # --- Gunakan dua timer terpisah untuk stabilitas ---
    last_transmission_time = 0
    last_display_update = 0
    TRANSMISSION_INTERVAL_MS = 1000
    DISPLAY_INTERVAL_MS = 1000

    print('Sender LoRa dimulai...')
    while True:
        # Selalu panggil bpa.update(). Ini penting untuk mekanisme "forward".
        # Saat node mobile mendekat, `update` akan menangani permintaan bundel.
        bpa.update()

        # --- Logika Pembuatan 20 Bundel (dengan timer sendiri) ---
        if not generation_complete and is_timestamp_older_than_timeout(last_transmission_time, TRANSMISSION_INTERVAL_MS):
            bundle_counter += 1
            
            sending_timestamp_ms = time.ticks_ms()
            level_air = 150 + (bundle_counter % 50)
            # payload_data = message_str.format(
            #     bundle_counter,
            #     sending_timestamp_ms,
            #     150 + (bundle_counter % 50)
            # ).encode('utf-8')

            # Buat list atau tuple
            data_to_send = [bundle_counter, sending_timestamp_ms, level_air]

            # Enkripsi data menjadi format biner (bytes)
            payload_data = cbor.dumps(data_to_send)
            
            # Perintah ini akan membuat bundel dan MENYIMPANNYA di 'storage'
            sender_endpoint.start_transmission(payload_data, 'ipn://2.1') 
            
            print(f"Membuat & menyimpan bundel #{bundle_counter} (Size: {len(payload_data)} bytes)")
            last_transmission_time = get_current_clock_millis()

            if bundle_counter >= 20:
                generation_complete = True
                print("20 bundel telah dibuat. Masuk mode CARRY & FORWARD.")

        # --- Logika Pembaruan Display (dengan timer terpisah) ---
        if is_timestamp_older_than_timeout(last_display_update, DISPLAY_INTERVAL_MS):
            try:
                bat_percent = get_battery_percentage()
                display.fill(0)
                display.text("NODE SENDER", 0, 10)
                display.text(f"TX: {bundle_counter}", 0, 25)
                display.text(f"Battery: {bat_percent}%", 0, 40)
                
                if generation_complete:
                    display.text("Mode: Carry", 0, 55)
                
                display.show()
                last_display_update = get_current_clock_millis()
            except OSError as e:
                print(f"OSError saat update display (diabaikan): {e}")

        # Beri "napas" pada sistem untuk mencegah crash
        time.sleep_ms(200)

except Exception as e:
    import sys
    sys.print_exception(e)
finally:
    if 'bpa' in locals() and 'sender_endpoint' in locals():
        bpa.unregister_endpoint(sender_endpoint)
    print("Sender dihentikan.")