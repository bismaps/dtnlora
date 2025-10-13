"""
Versi Produksi oled-lora-receiver.py.
Stabil untuk penggunaan lapangan dengan arsitektur anti-bottleneck
untuk memaksimalkan penerimaan bundel.
"""
# --- FASE 0: Persiapan Awal ---
import gc
import time
import cbor
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

# --- Variabel Global untuk komunikasi aman antara callback dan loop utama ---
pending_bundles = ucollections.deque((), 50, 1)  # Antrian untuk menampung payload mentah
new_bundle_received_flag = False

# --- Callback yang sangat ringan untuk menerima bundel ---
# Tujuannya hanya untuk mengambil data secepat mungkin tanpa memprosesnya.
def receive_callback(bundle: Bundle):
    global new_bundle_received_flag
    try:
        pending_bundles.append(bundle.payload_block.data)
        new_bundle_received_flag = True
    except IndexError:
        # Ini terjadi jika antrian penuh. Abaikan saja agar tidak crash.
        pass

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
    global new_bundle_received_flag

    # --- FASE 1: Inisialisasi Perangkat Keras ---
    print("Menginisialisasi Perangkat Keras...")
    adc = ADC(Pin(35))
    adc.atten(ADC.ATTN_11DB)
    
    rst_pin_oled = Pin(23, Pin.OUT)
    rst_pin_oled.value(0)
    time.sleep_ms(50)
    rst_pin_oled.value(1)
    i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000) # Percepat I2C
    display = SSD1306_I2C(128, 64, i2c)
    
    custom_lora_parameters = LORA_PARAMETERS_RH_RF95_bw125cr45sf128.copy()
    custom_lora_parameters['frequency'] = 915E6
    lora_cla = RF95LoRaCLA(
        device_config={'miso': 19, 'mosi': 27, 'sck': 5, 'ss': 18, 'rst': 23, 'dio_0': 26},
        lora_parameters=custom_lora_parameters
    )
    gc.collect()

    # --- FASE 2: Jalankan Aplikasi DTN ---
    print("Memuat framework DTN...")
    class GatewayRouter(SimpleEpidemicRouter):
        def immediate_forwarding_attempt(self, *args, **kwargs):
            return (True, 0)

    CONFIGURATION.IPND.ENABLED = False
    CONFIGURATION.MICROPYTHON_CHECK_WIFI = False
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_STORED_BUNDLES = 50
    CONFIGURATION.SIMPLE_IN_MEMORY_STORAGE_MAX_KNOWN_BUNDLE_IDS = 100

    storage = SimpleInMemoryStorage()
    router = GatewayRouter({CONFIGURATION.IPND.IDENTIFIER_RF95_LORA: lora_cla}, storage)
    bpa = BundleProtocolAgent('ipn://2', storage, router)
    receiver_endpoint = LocalEndpoint('1', receive_callback=receive_callback)
    bpa.register_endpoint(receiver_endpoint)

    total_received = 0
    last_bundle_data = {}  # Dictionary untuk menyimpan info bundel terakhir
    last_display_update = 0

    print('Receiver LoRa dimulai, menunggu bundle...')

    # --- FASE 3: Loop Utama yang Stabil dan Efisien ---
    while True:
        # Tugas 1: Selalu cek BPA secepat mungkin
        bpa.update()

        # Tugas 2: Proses antrian bundel jika ada
        if new_bundle_received_flag:
            while len(pending_bundles) > 0:
                payload_bytes = pending_bundles.popleft()
                total_received += 1
                
                try:
                    payload_data = cbor.loads(payload_bytes)
                    # Simpan data bundel terakhir untuk ditampilkan di OLED nanti
                    last_bundle_data['id'] = payload_data[0]
                    last_bundle_data['level'] = payload_data[2]
                    
                    # Cetak log (ini cukup cepat)
                    print(f"LOG,{total_received},{payload_data[0]},{payload_data[2]},{payload_data[1]},{time.ticks_ms()}")

                except Exception as e:
                    print(f"Error processing payload: {e}")
            
            new_bundle_received_flag = False
            gc.collect() # Bersihkan memori setelah memproses antrian

        # Tugas 3: Update display secara berkala (TIDAK setiap menerima bundel)
        if time.ticks_diff(time.ticks_ms(), last_display_update) > 1000:
            bat_percent = get_battery_percentage(adc)
            display.fill(0)
            display.text("NODE GATEWAY", 0, 10)
            
            if total_received == 0:
                display.text("RX: Waiting...", 0, 25)
            else:
                display.text(f"RX: {total_received}", 0, 25)
                if last_bundle_data:
                    display.text(f"ID: {last_bundle_data['id']} Lvl: {last_bundle_data['level']}", 0, 55)
            
            display.text(f"Battery: {bat_percent}%", 0, 40) # Pindahkan ke sini untuk konsistensi
            display.show()
            last_display_update = time.ticks_ms()

        # Beri jeda sangat singkat agar loop tidak berjalan 100%
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