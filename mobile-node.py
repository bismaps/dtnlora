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


# --- FASE 3: Jalankan Aplikasi DTN (Versi Sederhana) ---
print("Memuat framework DTN untuk Mobile Node...")
try:
    from dtn7zero.bundle_protocol_agent import BundleProtocolAgent
    from dtn7zero.configuration import CONFIGURATION
    from dtn7zero.storage.simple_in_memory_storage import SimpleInMemoryStorage
    from dtn7zero.routers.simple_epidemic_router import SimpleEpidemicRouter
    gc.collect()

    # Setup DTN (mirip dengan yang lain)
    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    
    clas = {CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}
    storage = SimpleInMemoryStorage()
    router = SimpleEpidemicRouter(clas, storage)
    
    # Beri alamat unik untuk mobile node, misal 'dtn://mobile-1/'
    bpa = BundleProtocolAgent('dtn://mobile-1/', storage, router)

    # --- TIDAK PERLU REGISTER ENDPOINT ---
    # Mobile node tidak membuat atau mengonsumsi data, hanya merutekan.

    # Loop utama aplikasi
    display.text('MOBILE NODE', 20, 0, 1)
    display.text('Mode: Kurir', 0, 20, 1)
    display.text('Berjalan...', 0, 40, 1)
    display.show()
    
    print('Mobile Node (Kurir) dimulai...')
    while True:
        # Cukup panggil bpa.update(). 
        # Logika store-carry-forward sudah ditangani oleh router.
        bpa.update()
        time.sleep(0.1)

except Exception as e:
    print(f"Terjadi error fatal: {e}")
finally:
    print("Mobile Node dihentikan.")