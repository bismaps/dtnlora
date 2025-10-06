"""
Skrip ini akan mengirimkan bundle DTN melalui LoRa ke semua perangkat dalam jangkauan
dan menampilkan jumlah bundle yang terkirim pada layar OLED.
Diadaptasi dari contoh oled-espnow-sender.py untuk digunakan dengan LoRa.
Untuk dijalankan pada perangkat TTGO LORA32.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time

# Jalankan garbage collector secepat mungkin untuk memori maksimal
gc.collect()
print(f"Memori bebas awal: {gc.mem_free()} bytes")


# --- FASE 1: Inisialisasi Hardware (OLED) ---
# Impor, inisialisasi, lalu segera bebaskan referensi dan panggil GC
print("Menginisialisasi OLED...")
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
gc.collect()

WIDTH = 128
HEIGHT = 64
rst_pin_oled = Pin(23, Pin.OUT)
rst_pin_oled.value(0)
time.sleep_ms(50)
rst_pin_oled.value(1)
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
display = SSD1306_I2C(WIDTH, HEIGHT, i2c)
display.fill(0)
display.show()
print("OLED OK.")
# Hapus referensi yang tidak perlu lagi untuk menghemat memori
del Pin, I2C
gc.collect()
print(f"Memori bebas setelah setup OLED: {gc.mem_free()} bytes")


# --- FASE 2: Inisialisasi Hardware (LoRa) ---
# Ulangi pola yang sama untuk LoRa
print("Menginisialisasi LoRa...")
from dtn7zero.convergence_layer_adapters.rf95_lora import RF95LoRaCLA
from sx127x import LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()

custom_device_config = {
    'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 12, 'dio_0': 26,
}
custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
custom_lora_parameters['frequency'] = 915E6
lora_cla = RF95LoRaCLA(
    device_config=custom_device_config,
    lora_parameters=custom_lora_parameters
)
print("LoRa OK.")
# Hapus referensi yang tidak perlu lagi
del LORA_PARAMETERS_RH_RF95_bw125cr45sf128
gc.collect()
print(f"Memori bebas setelah setup LoRa: {gc.mem_free()} bytes")


# --- FASE 3: Jalankan Aplikasi DTN (Logika Final yang Tangguh) ---
print("Memuat framework DTN untuk Sender...")
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
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 25
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 30

    clas = {CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter(clas, storage)
    bpa = BundleProtocolAgent('dtn://fixed-node/', storage, router)
    sender_endpoint = LocalEndpoint('flood_alert')
    bpa.register_endpoint(sender_endpoint)

    # Loop utama dengan jeda waktu dan pembersihan memori
    message_str = 'ID:{};TIME:{};LEVEL:{}'
    bundle_counter = 0
    last_transmission_time = 0
    # Atur jeda antar bundle (misal: 3 detik untuk memberi waktu sinkronisasi)
    TRANSMISSION_INTERVAL_MS = 3000 
    
    display.text('LORA SENDER', 20, 0, 1)
    display.text('Tx Count:', 0, 20, 1)
    display.show()
    print('Sender LoRa dimulai dengan mode siklus berulang...')

    # --- LOOP UTAMA TAK TERBATAS ---
    # Loop ini akan terus berjalan, memulai siklus baru setelah selesai.
    while True:
        # --- SIKLUS PENGIRIMAN 20 BUNDLE ---
        bundle_counter = 0
        last_transmission_time = 0
        
        while bundle_counter < 20:
            bpa.update()

            if is_timestamp_older_than_timeout(last_transmission_time, TRANSMISSION_INTERVAL_MS):
                bundle_counter += 1
                
                gc.collect()
                print(f"Memori bebas: {gc.mem_free()} bytes")

                sending_timestamp_ms = time.ticks_ms()
                simulated_water_level = 150 + (bundle_counter % 50)
                payload_data = message_str.format(
                    bundle_counter,
                    sending_timestamp_ms,
                    simulated_water_level
                ).encode('utf-8')
                
                sender_endpoint.start_transmission(payload_data, 'dtn://gateway/data-receiver')
                
                last_transmission_time = get_current_clock_millis()
                display.fill_rect(90, 20, 38, 8, 0)
                display.text(str(bundle_counter), 90, 20, 1)
                display.show()
                print(f"Membuat dan mengirim bundle #{bundle_counter}")

            time.sleep(0.1)

        # --- FASE PEMBERSIHAN SETELAH SIKLUS SELESAI ---
        print("Siklus pengiriman 20 bundle selesai. Membersihkan memori untuk siklus berikutnya...")
        display.text("CYCLE DONE", 20, 40, 1)
        display.show()
        
        # Beri waktu 10 detik agar bundle terakhir pasti terkirim
        end_time = time.ticks_add(time.ticks_ms(), 10000)
        while time.ticks_diff(end_time, time.ticks_ms()) > 0:
            bpa.update()
            time.sleep(0.1)

        # Hapus semua bundle dari storage untuk memulai dari awal
        storage.bundles.clear()
        storage.bundle_ids.clear()
        gc.collect() # Panggil garbage collector
        
        print(f"Memori dibersihkan. Memori bebas: {gc.mem_free()}. Memulai siklus baru dalam 5 detik...")
        display.fill_rect(0, 40, 128, 18, 0)
        display.text("NEW CYCLE...", 15, 40, 1)
        display.show()
        time.sleep(5) # Jeda sebelum memulai siklus baru

except Exception as e:
    print(f"Terjadi error fatal: {e}")
finally:
    if 'bpa' in locals() and 'sender_endpoint' in locals():
        bpa.unregister_endpoint(sender_endpoint)
    print("Sender dihentikan.")