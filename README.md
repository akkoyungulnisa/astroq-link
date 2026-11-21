# AstroQ-Link

![Python](https://img.shields.io/badge/Python-3.13%2B-blue)
![Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Stdlib%20Only)-brightgreen)
![Tests](https://img.shields.io/badge/Pytest-26%20Passed-success)
![Memory](https://img.shields.io/badge/Peak%20RAM-8.52%20KB%20(O(1))-blueviolet)

**AstroQ-Link**, hiçbir harici kütüphane kullanmadan (**zero-dependency**) sıfırdan inşa edilmiş; işaretçi tabanlı **Çift Yönlü Dairesel Bağlı Liste (`CircularDoublyLinkedList`)**, **Kritik LIFO Yığını (`CriticalLIFOStack`)** ve **kafes/sünger tabanlı kriptografik doğrulama** mimarilerini birleştiren, kesinti toleranslı telemetri yönlendirme ve çevrimdışı siber savunma kütüphanesidir.

---

## 1. Bu Uygulamayı Ne Amacıyla Yaptık?

Uç sistemlerde (roket/uydu aviyonik hatları ve internet bağlantısı kopabilen saha düğümleri) hazır veri yapıları ve klasik iletişim kuyrukları üç kritik soruna yol açar: **RAM şişmesi**, **kesinti sonrası bayat veri gecikmesi** ve **iletişim/bellek içi veri kurcalama**.

AstroQ-Link'i bu üç problemi temel veri yapıları düzeyinde çözmek amacıyla geliştirdik:

* **Sınırsız Veri Akışında Bellek Taşmasını Önlemek ($O(1)$ RAM):** Roket uçuşu boyunca sürekli üretilen sensör paketlerini büyüyen listeler yerine sabit kapasiteli `CircularDoublyLinkedList` halkasında tutarak, kapasite dolduğunda en eski düğümün üzerine $O(1)$ sürede yazmak ve bellek tüketimini sabitlemek.
* **Sinyal Kesintisi (Blackout) Sonrası En Güncel Durumu Kurtarmak:** Klasik FIFO kuyruklar bağlantı geri geldiğinde önce eski paketleri boşaltır. Biz ise kesinti anındaki kritik paketleri `CriticalLIFOStack` yığınına alarak, bağlantı döndüğü anda yığının tepesindeki **en son uçuş durumunu** $O(1)$ sürede yer istasyonuna ulaştırmayı amaçladık.
* **Bellek İçi Değişmezlik ve Kopyalanamazlık Sağlamak:** Telemetri paketlerini ve güvenlik kayıtlarını `frozen=True` ve `__slots__` ile koruyarak (`QuantumTelemetryPacket`), bellek üzerinde yetkisiz değişikliği ve `copy`/`deepcopy` ile çoğaltılmasını (`NoCloningViolationError`) engellemek.

---

## 2. Bizi Ayırt Eden Mühendislik ve Algoritma Yöntemlerimiz

Klasik yazılımlarda veri yapıları (tamponlama) ile güvenlik katmanı (şifreleme ve bütünlük kontrolü) birbirinden tamamen kopuk çalışır. AstroQ-Link'i ayırt eden temel yaklaşım, **veri yapılarının topolojisini doğrudan güvenlik ve kurtarma mekanizmasının parçası haline getirmektir**:

### A. Veri Yapısı ve Bütünlük Katmanının Tek Halkada Birleştirilmesi (`Tail -> Head` Dairesel Mühür)
* **Uygulandığı Yer:** `src/astroq_link/crypto/pqc_vault.py` (`PQCFileVault`)
* **Ayırt Edici Yöntem:** Dosyalar 64 baytlık bloklara ayrılır ve her blok düğümü (`CipherBlock`), kendi `SHA3-256` özetini kendinden önceki tüm blokların kümülatif imzasıyla (`prev_mac`) birleştirerek `CircularDoublyLinkedList` üzerinde zincirlenir. Ardından çift yönlü işaretçiler (`head.prev` $\rightarrow$ `tail`) kullanılarak **son düğüm ilk düğüme kilitlenir**. Bu kapalı halka topolojisi sayesinde dosyanın herhangi bir baytındaki **1-bitlik değişim** dahi zinciri kırar ve doğrulama geçilmeden diske tek bayt bile bozuk veri yazılması engellenir.

### B. Kesinti ve Saldırı Anında "En Güncel Durum Öncelikli" LIFO Kurtarma & Atomik Rollback
* **Uygulandığı Yer:** `src/astroq_link/engine/telemetry_router.py` ve `offline_shield.py`
* **Ayırt Edici Yöntem:** Uçuş telemetrisinde veya siber saldırı anında en kritik bilgi saniyeler önceki veri değil, **sistemin en son durumudur**. Bu nedenle klasik FIFO kuyruk yaklaşımını tersine çevirerek `CriticalLIFOStack` kullandık. Bağlantı geri geldiğinde yığının tepesindeki en taze veri $O(1)$ sürede (**1.90 µs**) kurtarılır. Aynı yığın yapısı, şifreleme ortasında disk hatası oluştuğunda veya çevrimdışı modda 1-baytlık müdahale yakalandığında tamamlanan adımları ters sırayla geri saran **Atomik Rollback** motoru olarak görev yapar.

### C. Polinom Halkası Üzerinde Anahtar Türetme, Sünger Akışı ve RAM Sıfırlama
* **Uygulandığı Yer:** `src/astroq_link/crypto/lattice_kdf.py` ve `offline_shield.py`
* **Ayırt Edici Yöntem:**
  * **Negatif Çevrimli Polinom Çarpımı:** Kullanıcı parolasından türetilen katsayılarla $\mathbb{Z}_q[X]/(X^n + 1)$ polinom halkası üzerinde ($q = 257$, $n = 8$) açık, gizli ve hata polinomlarıyla $b = a \cdot s + e \pmod{q, X^n + 1}$ işlemi yürütülerek yüksek difüzyonlu oturum tohumu üretilir.
  * **Sünger Tabanlı Anahtar Mandalama (Key Ratcheting):** `SHAKE-256` genişletilebilir çıktı fonksiyonu (XOF) ile her bloğun anahtar akışı bir önceki bloğun kümülatif özetine bağlanır; böylece 1-bitlik girdi farkı çıktıda **%49.33** bit değişimi (*avalanche effect*) üretir.
  * **Bellek Sıfırlama (Memory Zeroization):** Kullanımı biten anahtar tamponları çöp toplayıcıya (GC) bırakılmadan `secure_zero_bytearray` ile doğrudan RAM üzerinde `0x00` yazılarak silinir; internet kesik iken bile 4 yuvalı dairesel halkada yerel anahtar döndürme (*Offline Forward Secrecy*) sürdürülür.

### D. Sıfır Dış Bağımlılık ve Donanım Dostu Sabit Bellek Mimarisi
* **Uygulandığı Yer:** `src/astroq_link/core/` (`circular_dll.py`, `lifo_stack.py`, `models.py`)
* **Ayırt Edici Yöntem:** Hiçbir üçüncü taraf kütüphaneye bağımlı kalmadan tüm düğüm sınıfları `__slots__` ile tanımlanmıştır. Python'ın standart sözlük (`__dict__`) yükü ortadan kaldırıldığı için 50.000 paketlik kesintisiz akışta dahi bellek tüketimi **8.52 KB** seviyesinde sabit kalır.

---

## 3. Neyi Test Ettik ve Ne Ölçtük?

### A. Birim ve Sınır Durumu Testleri (`tests/` — 26 Otomatik Test)
* **İşaretçi Bütünlüğü (`test_circular_dll.py`):** Boş liste, tek düğümde kendi kendine işaret etme (`head.next is head`), baştan/ortadan/sondan silme, ileri-geri döndürme ($O(1)$ kanal geçişi) ve sabit kapasitede üzerine yazma davranışları doğrulandı.
* **Değişmezlik ve Kopyalanamazlık (`test_immutability.py`):** Paketlerin sonradan değiştirilemediği ve kopyalama girişimlerinde `NoCloningViolationError` fırlatıldığı test edildi.
* **1-Bayt Kurcalama ve Atomik Rollback (`test_pqc_vault.py`):** Şifreli dosyanın ortasındaki 1 bayt değiştirildiğinde (`Bit-Flip`) `IntegrityTamperError` fırlatıldığı ve diske bozuk veri yazılmadığı; disk kesintisinde ise yarım kalan dosyanın atomik olarak geri alınıp silindiği test edildi.
* **Kesinti ve Çevrimdışı Saldırı Senaryoları (`test_engine.py`, `test_io.py`):** 2000m roket kesintisinde en güncel paketin ilk kurtarıldığı, çevrimdışı modda yakalanan saldırıların bağlantı döndüğünde SOC merkezine LIFO sırasıyla iletildiği ve CLI çıkış kodlarının (`0`, `1`, `2`) doğruluğu test edildi.

### B. Gerçekçi Görev Simülasyonları (`examples/` — 3 Alan Demosu)
* **`01_rocket_2000m_blackout.py`:** 0m–2000m roket yükselişinde `1880m–1940m` arasındaki RF kesintisi ve `1600m` civarındaki QBER (> 0.11) kanal ihlali simüle edildi; tamponun 16 düğümde sabit kaldığı ve kesintideki paketlerin eksiksiz kurtarıldığı doğrulandı.
* **`02_offline_cyber_defense.py`:** İnternet kesik iken `T=3` ve `T=4` anlarında enjekte edilen 1-baytlık saldırılar engellendi, geri sarıldı ve `T=6`'da bağlantı döndüğünde SOC merkezine önce `T=4`, ardından `T=3` alarmı iletildi.
* **`03_pqc_file_encryption_demo.py`:** Gerçek bir telemetri CSV dosyası şifrelendi, `101. baytta` bit-flip saldırısı uygulandı ve `Diske Bozuk Veri Yazıldı mı? : False` çıktısıyla koruma doğrulandı.

### C. Nicel Performans ve Güvenlik Benchmarkları (`benchmarks/`)

| Test Senaryosu | Klasik Yaklaşım | AstroQ-Link Mimarisi | Ölçülen Kazanım |
| :--- | :---: | :---: | :---: |
| **10.000 Paket Kesinti Sonrası İlk Kritik Yanıt** | 182.40 µs (`deque` FIFO) | **1.90 µs (`CriticalLIFOStack`)** | **96.0x daha hızlı** |
| **50.000 Paket Akışında Tepe RAM Tüketimi** | $O(N)$ doğrusal bellek artışı | **8.52 KB (32 düğüm sabit)** | **$O(1)$ sabit bellek** |
| **1-Bit Girdi Değişiminde Çığ Etkisi (4 KB)** | — | **%49.33 bit değişimi** | İdeal difüzyon (~%50) |
| **1-Bayt Kurcalama (Bit-Flip) Saldırısı** | Bozuk veri diske yazılır | **Anında engellendi (`False`)** | Sıfır veri sızıntısı |

---

## Sistem Mimarisi ve Karmaşıklık Özeti

```mermaid
graph LR
    subgraph "Core Data Structures (Zero-Dependency)"
        IMM["Immutable (@dataclass frozen)<br/>No-Cloning & Veri Bütünlüğü"]
        CDLL(("Circular Doubly Linked List<br/>O(1) Ring Buffer & Dairesel Mühür"))
        STK["Critical LIFO Stack<br/>O(1) Kesinti Kurtarma & Rollback"]
    end

    subgraph "Cryptographic & Mission Layer"
        LWE["Polynomial Ring Z_q[X]/(X^n+1)<br/>+ SHAKE-256 Key Ratcheting"]
        TEL["2000m Telemetri Yönlendirici<br/>& Blackout Kurtarma"]
        SHD["Çevrimdışı Siber Savunma<br/>& SOC Öncelikli Alarm"]
    end

    IMM --> CDLL
    IMM --> STK
    LWE --> CDLL
    CDLL --> TEL
    CDLL --> SHD
    STK --> TEL
    STK --> SHD
```

| Bileşen | Veri Yapısı | Zaman Karmaşıklığı | Bellek Karmaşıklığı |
| :--- | :--- | :---: | :---: |
| **Sabit Bellekli Telemetri Tamponu** | `CircularDoublyLinkedList` | $O(1)$ ekleme / üzerine yazma | $O(K)$ sabit kapasite |
| **Dairesel Kriptografik Mühür** | `CircularDoublyLinkedList` | $O(N)$ blok zincirleme | $O(1)$ akış (streaming) |
| **Kesinti & Saldırı Kurtarma** | `CriticalLIFOStack` | $O(1)$ `push` / `pop` | $O(M)$ kritik yığın |
| **Atomik İşlem Geri Alma (Rollback)** | `CriticalLIFOStack` | $O(1)$ adım başı geri alma | $O(M)$ işlem kaydı |

---

## Kurulum ve Çalıştırma

```bash
# 1. Tüm birim testlerini çalıştırma (26 test)
python -m pytest -v

# 2. Alan demolarını çalıştırma
python examples/01_rocket_2000m_blackout.py
python examples/02_offline_cyber_defense.py
python examples/03_pqc_file_encryption_demo.py

# 3. Benchmark ölçümlerini çalıştırma
python benchmarks/fifo_vs_lifo_latency.py
python benchmarks/avalanche_and_memory.py

# 4. CLI üzerinden şifreleme, doğrulama ve simülasyon
PYTHONPATH=src python -m astroq_link.io.cli encrypt data/sample_telemetry.csv secret.pqc -p "GucluParola2026"
PYTHONPATH=src python -m astroq_link.io.cli decrypt secret.pqc restored.csv -p "GucluParola2026"
PYTHONPATH=src python -m astroq_link.io.cli simulate --altitude 2000 --export-csv data/ground_log.csv
```
