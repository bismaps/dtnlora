# File: dtn7zero/routers/timed_epidemic_router.py
# Versi ini adalah modifikasi langsung dari simple_epidemic_router.py
# untuk kebutuhan spesifik Mobile Node (Kurir) pada hardware half-duplex.

import time
import gc
from typing import Dict, Iterable, Union

# Impor yang dibutuhkan, disalin dari file asli
from dtn7zero.configuration import CONFIGURATION
from dtn7zero.convergence_layer_adapters import PullBasedCLA, PushBasedCLA
from dtn7zero.data import BundleInformation, Node, BundleStatusReportReasonCodes
from dtn7zero.routers import Router
from dtn7zero.storage import Storage
from dtn7zero.utility import warning

class TimedEpidemicRouter(Router):
    """
    Router yang dioptimalkan untuk Mobile Node (Kurir) pada hardware half-duplex.
    - Menerima bundel secara pasif.
    - Mengirim (forwarding) semua bundel yang disimpan secara terjadwal.
    """
    def __init__(self, convergence_layer_adapters: Dict[str, Union[PullBasedCLA, PushBasedCLA]], storage: Storage):
        self.clas = convergence_layer_adapters
        self.storage = storage

    # --- FUNGSI MENERIMA (RX) ---
    # Logika ini disalin langsung dari SimpleEpidemicRouter untuk memastikan penerimaan berjalan normal.
    def generator_poll_bundles(self) -> Iterable[BundleInformation]:
        for cla in self.clas.values():
            if isinstance(cla, PushBasedCLA):
                for bundle_information in self._generator_poll_push_based(cla):
                    yield bundle_information
    
    def _generator_poll_push_based(self, cla: PushBasedCLA):
        bundle, node_address = cla.poll()
        while bundle is not None:
            if not self.storage.was_seen(bundle.bundle_id):
                self.storage.store_seen(bundle.bundle_id, node_address)
                bundle_information = BundleInformation(bundle)
                node = self.storage.get_node(node_address)
                if node is not None:
                    bundle_information.forwarded_to_nodes.append(node)
                yield bundle_information
            bundle, node_address = cla.poll()

    # --- FUNGSI FORWARDING OTOMATIS (DINONAKTIFKAN) ---
    # Ini adalah kunci untuk mencegah konflik radio.
    # Fungsi ini ditimpa agar tidak melakukan apa-apa saat dipanggil otomatis oleh BPA.
    def immediate_forwarding_attempt(self, full_node_uri: str, bundle_information: BundleInformation):
        # Langsung kembalikan 'sukses' agar tidak ada re-broadcast otomatis.
        return True, BundleStatusReportReasonCodes.NO_ADDITIONAL_INFORMATION

    # --- FUNGSI FORWARDING TERJADWAL (TX) ---
    # Fungsi ini dipanggil secara manual dari loop utama di mobile-node.py.
    def scheduled_forward(self, full_node_uri: str):
        print("--- Memulai siklus forwarding terjadwal ---")
        gc.collect()
        
        # Iterasi melalui bundel yang akan dikirim ulang
        for bundle_info in self.storage.get_bundles_to_retry():
            if not bundle_info.bundle.is_expired():
                print(f"Forwarding bundel: {bundle_info.bundle.bundle_id}")
                serialized_bundle = self.prepare_and_serialize_bundle(full_node_uri, bundle_info)
                
                # Kirim melalui LoRa
                if CONFIGURATION.IPND.IDENTIFIER_RF95_LORA in self.clas:
                    self.clas[CONFIGURATION.IPND.IDENTIFIER_RF95_LORA].send_to(None, serialized_bundle)
                
                time.sleep_ms(150) # Jeda antar pengiriman untuk stabilitas radio
        
        print("--- Siklus forwarding selesai ---")
        gc.collect()

    # Fungsi sisa dari SimpleEpidemicRouter
    def send_to_previous_node(self, full_node_uri: str, bundle_information: BundleInformation) -> bool:
        return False