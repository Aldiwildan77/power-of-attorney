"""Catalogue of letter templates.

Each entry holds:
    label   : human-readable name of the errand (shown by --list-types)
    purpose : opening sentence of the KHUSUS clause ("Untuk mewakili ...")
    powers  : list of granted powers (optional, rendered as a numbered list)
    limits  : sentence restricting the powers (optional)

The letter text itself is Indonesian on purpose; the config can override any
of these fields under [document].
"""

GENERAL_LIMITS = (
    "Kuasa ini tidak memberikan kewenangan kepada Penerima Kuasa untuk menjual, "
    "mengalihkan, atau menjaminkan aset milik Pemberi Kuasa, melakukan transaksi "
    "keuangan, menarik dana, mengajukan kredit atau pinjaman, maupun melakukan "
    "tindakan hukum yang menurut peraturan perundang-undangan memerlukan surat "
    "kuasa khusus tersendiri."
)

TEMPLATES = {
    "dukcapil": {
        "label": "Administrasi Kependudukan (Dukcapil)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus seluruh administrasi "
            "kependudukan pada Dinas Kependudukan dan Pencatatan Sipil (Dukcapil)."
        ),
        "powers": [
            "Mengurus penerbitan, perubahan, dan penggantian Kartu Tanda Penduduk (KTP) "
            "serta Kartu Keluarga (KK).",
            "Mengajukan permohonan perubahan data kependudukan dan surat keterangan pindah.",
            "Mengurus legalisasi dokumen kependudukan.",
            "Menyerahkan dan mengambil dokumen pada instansi terkait.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Memberikan keterangan dan klarifikasi atas data Pemberi Kuasa.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "bpjs_tk": {
        "label": "BPJS Ketenagakerjaan",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus seluruh administrasi "
            "kepesertaan BPJS Ketenagakerjaan."
        ),
        "powers": [
            "Mengajukan dan mengurus klaim Jaminan Hari Tua (JHT) serta program jaminan lainnya.",
            "Mengajukan perubahan dan pembaruan data peserta.",
            "Melakukan verifikasi data kepesertaan.",
            "Menyerahkan dan mengambil dokumen pada kantor BPJS Ketenagakerjaan.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Memberikan keterangan dan klarifikasi atas data Pemberi Kuasa.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "bpjs_kes": {
        "label": "BPJS Kesehatan",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus seluruh administrasi "
            "kepesertaan BPJS Kesehatan."
        ),
        "powers": [
            "Mengajukan perubahan dan pembaruan data peserta.",
            "Mengurus aktivasi maupun penonaktifan kepesertaan.",
            "Mengurus penggantian dan pencetakan kartu peserta.",
            "Menyerahkan dan mengambil dokumen pada kantor BPJS Kesehatan.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "pajak": {
        "label": "Direktorat Jenderal Pajak (NPWP)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi perpajakan "
            "pada Direktorat Jenderal Pajak."
        ),
        "powers": [
            "Mengurus pendaftaran, perubahan, dan penghapusan Nomor Pokok Wajib Pajak (NPWP).",
            "Mengurus permohonan dan pengaktifan EFIN.",
            "Mengajukan perubahan data Wajib Pajak.",
            "Menyerahkan dan mengambil dokumen pada Kantor Pelayanan Pajak.",
            "Menyampaikan keterangan dan klarifikasi administratif.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "imigrasi": {
        "label": "Imigrasi (Paspor)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi keimigrasian "
            "pada Kantor Imigrasi."
        ),
        "powers": [
            "Mengambil paspor yang telah selesai diterbitkan.",
            "Mengajukan permohonan perubahan data keimigrasian.",
            "Menyerahkan dan mengambil dokumen pada Kantor Imigrasi.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "skck": {
        "label": "Kepolisian (SKCK)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi pada Kepolisian "
            "Negara Republik Indonesia, khususnya pengambilan Surat Keterangan Catatan "
            "Kepolisian (SKCK)."
        ),
        "powers": [
            "Mengambil Surat Keterangan Catatan Kepolisian (SKCK) milik Pemberi Kuasa.",
            "Menyerahkan dokumen pendukung yang dipersyaratkan.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "kendaraan": {
        "label": "Kendaraan Bermotor (Samsat)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi kendaraan bermotor "
            "pada Kantor Bersama Samsat."
        ),
        "powers": [
            "Melakukan pembayaran pajak kendaraan bermotor tahunan.",
            "Mengurus pengesahan dan pengambilan STNK.",
            "Mengurus perubahan data administrasi kendaraan.",
            "Menyerahkan dan mengambil dokumen pada Kantor Samsat.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang diperbolehkan menurut peraturan "
            "perundang-undangan yang berlaku.",
        ],
        "limits": (
            "Kuasa ini tidak memberikan kewenangan untuk menjual, mengalihkan, "
            "menjaminkan, maupun membalik nama kepemilikan kendaraan bermotor milik "
            "Pemberi Kuasa."
        ),
    },
    "bank": {
        "label": "Perbankan (Administrasi)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi perbankan pada "
            "bank tempat Pemberi Kuasa menjadi nasabah."
        ),
        "powers": [
            "Mengajukan perubahan data nasabah.",
            "Mengambil buku tabungan, kartu ATM, rekening koran, dan surat keterangan bank.",
            "Mengambil dokumen administrasi lain milik Pemberi Kuasa.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
        ],
        "limits": (
            "Kuasa ini tidak memberikan kewenangan untuk menarik dana, memindahbukukan "
            "dana, membuka rekening, menutup rekening, mengajukan pinjaman, maupun "
            "melakukan transaksi keuangan dalam bentuk apa pun."
        ),
    },
    "hr": {
        "label": "Perusahaan / HR (Kepegawaian)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi kepegawaian pada "
            "perusahaan tempat Pemberi Kuasa bekerja atau pernah bekerja."
        ),
        "powers": [
            "Mengambil surat keterangan kerja (paklaring) dan surat pengalaman kerja.",
            "Mengambil dokumen payroll, slip gaji, dan dokumen personalia lainnya.",
            "Menyerahkan dan mengambil dokumen pada bagian personalia.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "pendidikan": {
        "label": "Pendidikan (Ijazah / Transkrip)",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi pendidikan pada "
            "satuan pendidikan tempat Pemberi Kuasa terdaftar."
        ),
        "powers": [
            "Mengambil ijazah, transkrip nilai, dan sertifikat milik Pemberi Kuasa.",
            "Mengurus legalisasi dokumen pendidikan.",
            "Menyerahkan dan mengambil dokumen pada bagian akademik atau tata usaha.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "asuransi": {
        "label": "Asuransi",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi asuransi pada "
            "perusahaan asuransi tempat Pemberi Kuasa menjadi pemegang polis."
        ),
        "powers": [
            "Mengajukan perubahan data polis.",
            "Mengajukan dan melengkapi berkas klaim asuransi.",
            "Menyerahkan dan mengambil dokumen pada perusahaan asuransi.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": (
            "Kuasa ini tidak memberikan kewenangan untuk menerima pencairan dana klaim, "
            "mengubah penerima manfaat, membatalkan polis, maupun melakukan transaksi "
            "keuangan atas nama Pemberi Kuasa."
        ),
    },
    "instansi": {
        "label": "BUMN / BUMD / Instansi Pemerintah",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi pada instansi "
            "pemerintah, pemerintah daerah, Badan Usaha Milik Negara (BUMN), maupun "
            "Badan Usaha Milik Daerah (BUMD)."
        ),
        "powers": [
            "Menyerahkan dan mengambil dokumen pada instansi terkait.",
            "Mengajukan permohonan perubahan data.",
            "Mengurus legalisasi dan verifikasi dokumen.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Memberikan keterangan dan klarifikasi atas data Pemberi Kuasa.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "utilitas": {
        "label": "PLN / PDAM / Telkom / ISP",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus administrasi layanan utilitas "
            "pada penyedia layanan terkait."
        ),
        "powers": [
            "Mengajukan perubahan data pelanggan.",
            "Mengajukan permohonan administrasi layanan.",
            "Menyerahkan dan mengambil dokumen pada kantor penyedia layanan.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "ambil_dokumen": {
        "label": "Pengambilan Dokumen",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam melakukan pengambilan dokumen milik "
            "Pemberi Kuasa."
        ),
        "powers": [
            "Mengambil ijazah, sertifikat, surat resmi, dokumen perusahaan, paket, arsip, "
            "maupun dokumen administratif lainnya milik Pemberi Kuasa.",
            "Menandatangani bukti penerimaan atau tanda terima apabila diperlukan.",
            "Menunjukkan dokumen identitas dan surat kuasa ini kepada pihak yang menyerahkan.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "custom": {
        "label": "Custom - tulis sendiri",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus keperluan sebagaimana "
            "diuraikan di bawah ini."
        ),
        "powers": [
            "Menyerahkan dan mengambil dokumen yang diperlukan.",
            "Menandatangani formulir dan tanda terima administrasi.",
        ],
        "limits": GENERAL_LIMITS,
    },
    "umum": {
        "label": "Administrasi Umum",
        "purpose": (
            "Untuk mewakili Pemberi Kuasa dalam mengurus berbagai keperluan administrasi "
            "pada instansi pemerintah maupun swasta."
        ),
        "powers": [
            "Menyerahkan dan mengambil dokumen pada instansi terkait.",
            "Mengajukan permohonan perubahan data.",
            "Mengurus legalisasi dan verifikasi dokumen.",
            "Menandatangani formulir dan tanda terima administrasi yang diperlukan.",
            "Memberikan keterangan dan klarifikasi atas data Pemberi Kuasa.",
            "Melakukan tindakan administratif lain yang berkaitan dengan hal-hal di atas.",
        ],
        "limits": GENERAL_LIMITS,
    },
}


def get_template(key):
    try:
        return TEMPLATES[key]
    except KeyError:
        raise KeyError(
            f"Unknown letter type '{key}'. Available: {', '.join(sorted(TEMPLATES))}"
        ) from None
