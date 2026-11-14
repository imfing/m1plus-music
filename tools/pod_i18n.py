#!/usr/bin/env python3
"""The translations of every text M1+ Music adds (docs/ui.md "Localisation").

The stock app translates through AWTK: a widget's `tr_text` is a key into strings/<lang>_<COUNTRY>.bin
(locale_info_tr 0x658db4, a binary search by strcmp; a key the table lacks comes back unchanged).
M1+ Music's texts use two kinds of key:

  * STOCK    a key the stock tables already carry with a good translation in every language (checked by
             test/pod/i18n.py against the shipped tables): used as it is.
  * TEXT     our own keys. The key IS the English text, so a missing table or entry shows English, which is
             also the text of en_US. tools/mod_strings.py adds these to all 16 tables.

Brand names stay as they are (M1+ Music, Tidal, Shanling inside a longer text). Locales: the language menu
reaches 13 tables (switch_language 0x4cca40: zh_CN is the default, then zh_HK en_US ja_JP ko_KR fr_FR ge_DE
sp_ES it_IT th_TH po_PL ru_RU uk_UK); de_DE, es_ES and pl_PL are 11-entry stubs of the CD ripper strings
that nothing loads: they get our keys as their twin's text (ge_DE, sp_ES, po_PL = German, Spanish, Polish).
The terms follow the stock tables where they are sound (library = 曲库 / Datenbank / librería ...,
artist = 歌手 / Künstler ...).
"""

LOCALES = ['en_US', 'zh_CN', 'zh_HK', 'ja_JP', 'ko_KR', 'fr_FR', 'ge_DE', 'sp_ES', 'it_IT', 'th_TH', 'po_PL', 'ru_RU', 'uk_UK']
TWINS = {'de_DE': 'ge_DE', 'es_ES': 'sp_ES', 'pl_PL': 'po_PL'}      # unreachable stub tables -> the table that holds their language
ALL_TABLES = sorted(LOCALES + list(TWINS))

# Stock keys used as they are: key -> the English text of en_US (the test compares it with the shipped table).
STOCK = {
    'cdrippersettings': 'Settings',   # the Pod's Settings row and level title (patch/ipod.c)
    'local_allsong': 'All Songs',     # the first row of an artist's album list and the title of its songs (patch/ipod.c); the stock All Songs, translated in every table
    'hr': 'Hi-Res',
    'sset_updatemusic': 'Update Library',
    'cdripper': 'CD Ripper',
    'album': 'Album',
    'playlist_create': 'New playlist',    # the New playlist keyboard's title (the stock Playlists page's own row text)
    'msg_newplaylists': 'Enter a playlist name',   # the New playlist keyboard's placeholder (the stock keyboard dialog's own hint, patch/playlists.c)
    'msg_playlistfull': 'Playlist Is Full',        # the message boxes of a New playlist that cannot be made (the stock create handler's)
    'msg_playlistexist': 'Playlist Already Exists',
    'msg_addplaylistsuccess': 'Added To Playlist',   # the Daily Mix page's Add disc and the stock playlist picker (@0x53d51c) after a successful add
    'msg_addfavsuccess': 'Added To Fav',   # the picker's Favourites row after a successful add (stock Add button's Favourites path, @0x52822c)
    'msg_delsong': 'Delete Song?',             # its confirm dialog and the stock message boxes it shows
    'msg_delsongfailed': 'Failed To Delete Song',
    'msg_delsongsuccess': 'Song Deleted',
    'msg_addfailed': 'Adding Failed',
    'msg_delplaylist': 'Delete Playlist?',     # the Playlists page's select mode: the stock delete handler's confirm dialog and message boxes (@0x53dbcc)
    'msg_delplaylistfailed': 'Failed To Delete Playlist',
    'msg_delplaylistsuccess': 'Playlist Deleted',
    'msg_delfile': 'Delete File?',             # the Folders page's select mode: the stock folder handler's confirm dialog and message boxes (@0x5324d0), and the stock messages of a level that cannot be entered
    'msg_delfilefailed': 'Failed To Delete File',
    'msg_delfilesuccess': 'File Deleted',
    'msg_notsupportdel': "Can't be removed",
    'msg_nottf': 'No TF Card Found',
    'msg_nototg': 'No OTG Found',
    'msg_notfile': 'File Not Found',
    # the Wi-Fi page's three confirmations: stock's own texts (patch/wifipage.c); msg_wifi_open holds the coex warning (COEX_TEXT)
    'msg_wifidisconnect': 'Disconnect Now?',
    'msg_wificancelsave': 'Delete Record?',
    'msg_wifi_open': 'Bluetooth audio may stutter while Wi-Fi is on.',
    'powerm_sleep': 'Sleep Timer',   # Now Playing's More sheet row that opens the stock Power page: the same text as that page's own Sleep Timer row (patch/playmore.c)
}

_L = LOCALES[1:]    # the order of the translations below (English is the key)


def _t(key, *texts, **by):
    """key -> {locale: text}; texts are in _L order, `by` overrides or supplies single locales."""
    d = dict(zip(_L, texts)); d.update(by); d['en_US'] = key
    assert set(d) == set(LOCALES), (key, sorted(set(LOCALES) - set(d)))
    return key, d


#       zh_CN   zh_HK    ja_JP    ko_KR    fr_FR    ge_DE    sp_ES    it_IT    th_TH    po_PL    ru_RU    uk_UK
TEXT = dict([
    _t('Appearance', '外观', '外觀', '外観', '화면 모드', 'Apparence', 'Darstellung',
       'Apariencia', 'Aspetto', 'รูปแบบหน้าจอ', 'Wygląd', 'Оформление', 'Вигляд'),
    _t('Light', '浅色', '淺色', 'ライト', '밝게', 'Clair', 'Hell',
       'Claro', 'Chiaro', 'สว่าง', 'Jasny', 'Светлая', 'Світла'),
    _t('Dark', '深色', '深色', 'ダーク', '어둡게', 'Sombre', 'Dunkel',
       'Oscuro', 'Scuro', 'มืด', 'Ciemny', 'Тёмная', 'Темна'),
    _t('Now Playing', '正在播放', '正在播放', '再生中', '지금 재생 중', 'En lecture', 'Jetzt läuft',
       'Reproduciendo', 'In riproduzione', 'กำลังเล่น', 'Teraz gra', 'Сейчас играет', 'Зараз грає'),
    _t('Cover Flow', '封面流', '封面流', 'カバーフロー', '커버 플로우', 'Cover Flow', 'Cover Flow',
       'Cover Flow', 'Cover Flow', 'Cover Flow', 'Cover Flow', 'Cover Flow', 'Cover Flow'),
    _t('Albums', '专辑', '專輯', 'アルバム', '앨범', 'Albums', 'Alben',
       'Álbumes', 'Album', 'อัลบั้ม', 'Albumy', 'Альбомы', 'Альбоми'),
    _t('Artists', '歌手', '歌手', 'アーティスト', '아티스트', 'Artistes', 'Künstler',
       'Artistas', 'Artisti', 'ศิลปิน', 'Wykonawcy', 'Исполнители', 'Виконавці'),
    _t('Songs', '歌曲', '歌曲', '曲', '노래', 'Titres', 'Titel',
       'Canciones', 'Brani', 'เพลง', 'Utwory', 'Песни', 'Пісні'),
    _t('Playlists', '歌单', '歌單', 'プレイリスト', '플레이리스트', 'Playlists', 'Playlists',
       'Listas', 'Playlist', 'เพลย์ลิสต์', 'Playlisty', 'Плейлисты', 'Плейлисти'),
    _t('Shuffle', '随机播放', '隨機播放', 'シャッフル', '임의 재생', 'Aléatoire', 'Zufall',
       'Aleatorio', 'Casuale', 'สุ่มเพลง', 'Losowo', 'Перемешать', 'Перемішати'),
    _t('Genres', '风格', '風格', 'ジャンル', '장르', 'Genres', 'Genres',
       'Géneros', 'Generi', 'ประเภท', 'Gatunki', 'Жанры', 'Жанри'),
    _t('Folders', '文件夹', '資料夾', 'フォルダ', '폴더', 'Dossiers', 'Ordner',
       'Carpetas', 'Cartelle', 'โฟลเดอร์', 'Foldery', 'Папки', 'Папки'),
    _t('Extras', '附加功能', '附加功能', 'エクストラ', '부가 기능', 'Extras', 'Extras',
       'Extras', 'Extra', 'เพิ่มเติม', 'Dodatki', 'Дополнительно', 'Додатково'),
    _t('Shuffle Songs', '随机播放歌曲', '隨機播放歌曲', '曲をシャッフル', '노래 임의 재생', 'Titres aléatoires', 'Titel mischen',
       'Canciones aleatorias', 'Brani casuali', 'สุ่มเพลง', 'Losuj utwory', 'Перемешать песни', 'Перемішати пісні'),
    _t('Shuffle Albums', '随机播放专辑', '隨機播放專輯', 'アルバムをシャッフル', '앨범 임의 재생', 'Albums aléatoires', 'Alben mischen',
       'Álbumes aleatorios', 'Album casuali', 'สุ่มอัลบั้ม', 'Losuj albumy', 'Перемешать альбомы', 'Перемішати альбоми'),
    _t('Shuffle Folders', '随机播放文件夹', '隨機播放資料夾', 'フォルダをシャッフル', '폴더 임의 재생', 'Dossiers aléatoires', 'Ordner mischen',
       'Carpetas aleatorias', 'Cartelle casuali', 'สุ่มโฟลเดอร์', 'Losuj foldery', 'Перемешать папки', 'Перемішати папки'),
    _t('Main Menu', '主菜单', '主選單', 'メインメニュー', '메인 메뉴', 'Menu principal', 'Hauptmenü',
       'Menú principal', 'Menu principale', 'เมนูหลัก', 'Menu główne', 'Главное меню', 'Головне меню'),
    _t('Home Screen', '主屏幕', '主畫面', 'ホーム画面', '홈 화면', "Écran d'accueil", 'Startbildschirm',
       'Pantalla de inicio', 'Schermata Home', 'หน้าจอหลัก', 'Ekran główny', 'Главный экран', 'Головний екран'),
    _t('Boot to M1+ Music', '开机进入 M1+ Music', '開機進入 M1+ Music', '起動時に M1+ Music', '부팅 시 M1+ Music', 'Lancer M1+ Music', 'Start mit M1+ Music',
       'Iniciar M1+ Music', 'Avvio in M1+ Music', 'บูตเข้า M1+ Music', 'Start w M1+ Music', 'Запуск M1+ Music', 'Запуск M1+ Music'),
    _t('Settings', '设置', '設定', '設定', '설정', 'Réglages', 'Einstellungen',
       'Ajustes', 'Impostazioni', 'การตั้งค่า', 'Ustawienia', 'Настройки', 'Налаштування'),
    _t('Developer', '开发者', '開發者', '開発者向け', '개발자', 'Développeur', 'Entwickler',
       'Desarrollador', 'Sviluppatore', 'นักพัฒนา', 'Programista', 'Разработчик', 'Розробник'),
    _t('Playback', '播放', '播放', '再生', '재생', 'Lecture', 'Wiedergabe',
       'Reproducción', 'Riproduzione', 'การเล่น', 'Odtwarzanie', 'Воспроизведение', 'Відтворення'),
    # Settings (docs/modules/settings.md): the top page's rows, headers and notes. Rows with a value at the right (Language, Theme) have short labels: the value takes the room.
    _t('Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi',
       'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi', 'Wi-Fi'),
    _t('Bluetooth', '蓝牙', '藍牙', 'Bluetooth', '블루투스', 'Bluetooth', 'Bluetooth',
       'Bluetooth', 'Bluetooth', 'บลูทูธ', 'Bluetooth', 'Bluetooth', 'Bluetooth'),
    _t('On', '开', '開', 'オン', '켜짐', 'Activé', 'An',
       'Activado', 'Attivo', 'เปิด', 'Wł.', 'Вкл.', 'Увімк.'),
    _t('Off', '关', '關', 'オフ', '꺼짐', 'Désactivé', 'Aus',
       'Desactivado', 'Disattivo', 'ปิด', 'Wył.', 'Выкл.', 'Вимк.'),
    _t('EQ', 'EQ', 'EQ', 'EQ', 'EQ', 'EQ', 'EQ',
       'EQ', 'EQ', 'EQ', 'EQ', 'EQ', 'EQ'),
    _t('All Playback Settings', '全部播放设置', '全部播放設定', 'すべての再生設定', '모든 재생 설정', 'Réglages de lecture', 'Wiedergabe-Optionen',
       'Ajustes de reproducción', 'Impostazioni riproduzione', 'การตั้งค่าการเล่นทั้งหมด', 'Ustawienia odtwarzania', 'Параметры плеера', 'Параметри плеєра'),
    _t('System', '系统', '系統', 'システム', '시스템', 'Système', 'System',
       'Sistema', 'Sistema', 'ระบบ', 'System', 'Система', 'Система'),
    # Settings > System > Appearance > Control Center (patch/pulldown.c; iOS's names for its Control Center): the page, and the two tile captions whose stock text shows the
    # state (High / Low, USB AUDIO / DAC / Storage)
    _t('Control Center', '控制中心', '控制中心', 'コントロールセンター', '제어 센터', 'Centre de contrôle', 'Kontrollzentrum',
       'Centro de control', 'Centro di Controllo', 'ศูนย์ควบคุม', 'Centrum sterowania', 'Пункт управления', 'Пункт керування'),
    _t('Gain', '增益', '增益', 'ゲイン', '게인', 'Gain', 'Verstärkung',
       'Ganancia', 'Guadagno', 'เกน', 'Wzmocnienie', 'Усиление', 'Підсилення'),
    _t('USB Mode', 'USB 模式', 'USB 模式', 'USBモード', 'USB 모드', 'Mode USB', 'USB-Modus',
       'Modo USB', 'Modalità USB', 'โหมด USB', 'Tryb USB', 'Режим USB', 'Режим USB'),
    _t('Button Lock', '按键锁', '按鍵鎖', 'ボタンロック', '버튼 잠금', 'Verrou touches', 'Tastensperre',
       'Bloqueo', 'Blocco tasti', 'ล็อกปุ่ม', 'Blokada', 'Блокировка', 'Блокування'),
    _t('Output', '输出', '輸出', '出力', '출력', 'Sortie', 'Ausgang',
       'Salida', 'Uscita', 'เอาต์พุต', 'Wyjście', 'Выход', 'Вихід'),
    _t('Display', '显示', '顯示', 'ディスプレイ', '디스플레이', 'Affichage', 'Anzeige',
       'Pantalla', 'Display', 'การแสดงผล', 'Wyświetlacz', 'Дисплей', 'Дисплей'),
    _t('About', '关于', '關於', '概要', '정보', 'À propos', 'Info',
       'Acerca de', 'Info', 'เกี่ยวกับ', 'Informacje', 'О плеере', 'Про пристрій'),
    _t('All System Settings', '全部系统设置', '全部系統設定', 'すべてのシステム設定', '모든 시스템 설정', 'Réglages système', 'Systemeinstellungen',
       'Ajustes del sistema', 'Impostazioni di sistema', 'การตั้งค่าระบบทั้งหมด', 'Ustawienia systemowe', 'Системные настройки', 'Налаштування системи'),
    # Settings > System > About (our own page, docs/modules/settings.md "About"): the section headers and the row labels (values are data; the credits' names and licences are brands)
    _t('Firmware', '固件版本', '韌體版本', 'ファームウェア', '펌웨어', 'Firmware', 'Firmware',
       'Firmware', 'Firmware', 'เฟิร์มแวร์', 'Oprogramowanie', 'Прошивка', 'Прошивка'),
    _t('Device', '设备', '裝置', 'デバイス', '기기', 'Appareil', 'Gerät',
       'Dispositivo', 'Dispositivo', 'อุปกรณ์', 'Urządzenie', 'Устройство', 'Пристрій'),
    _t('Model', '型号', '型號', 'モデル', '모델', 'Modèle', 'Modell',
       'Modelo', 'Modello', 'รุ่น', 'Model', 'Модель', 'Модель'),
    _t('Serial Number', '序列号', '序號', 'シリアル番号', '일련번호', 'N° de série', 'Seriennr.',
       'N.º de serie', 'N. di serie', 'หมายเลขเครื่อง', 'Nr seryjny', 'Серийный №', 'Серійний №'),
    _t('Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC',
       'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC', 'Wi-Fi MAC'),
    _t('IP Address', 'IP 地址', 'IP 位址', 'IPアドレス', 'IP 주소', 'Adresse IP', 'IP-Adresse',
       'Dirección IP', 'Indirizzo IP', 'ที่อยู่ IP', 'Adres IP', 'IP-адрес', 'IP-адреса'),
    _t('Storage', '存储', '儲存空間', 'ストレージ', '저장공간', 'Stockage', 'Speicher',
       'Almacenamiento', 'Archiviazione', 'พื้นที่จัดเก็บ', 'Pamięć', 'Хранилище', 'Сховище'),
    _t('Capacity', '容量', '容量', '容量', '용량', 'Capacité', 'Kapazität',
       'Capacidad', 'Capacità', 'ความจุ', 'Pojemność', 'Ёмкость', 'Ємність'),
    _t('Available', '可用', '可用', '空き', '사용 가능', 'Disponible', 'Verfügbar',
       'Disponible', 'Disponibile', 'ว่าง', 'Dostępne', 'Доступно', 'Доступно'),
    _t('Theme', '主题', '主題', 'テーマ', '테마', 'Thème', 'Design',
       'Tema', 'Tema', 'ธีม', 'Motyw', 'Тема', 'Тема'),
    _t('Open Shanling Home', '打开山灵主页', '打開山靈主頁', 'Shanling ホームを開く', 'Shanling 홈 열기', 'Accueil Shanling', 'Shanling-Start öffnen',
       'Abrir Inicio Shanling', 'Apri Home Shanling', 'เปิดหน้าหลัก Shanling', 'Otwórz ekran Shanling', 'Открыть экран Shanling', 'Відкрити екран Shanling'),
    _t('Startup', '启动', '啟動', '起動', '시작', 'Démarrage', 'Start',
       'Inicio', 'Avvio', 'เริ่มต้น', 'Uruchamianie', 'Запуск', 'Запуск'),
    _t('Streaming', '流媒体', '串流', 'ストリーミング', '스트리밍', 'Streaming', 'Streaming',
       'Streaming', 'Streaming', 'สตรีมมิง', 'Streaming', 'Стриминг', 'Стримінг'),
    _t('Tools', '工具', '工具', 'ツール', '도구', 'Outils', 'Werkzeuge',
       'Herramientas', 'Strumenti', 'เครื่องมือ', 'Narzędzia', 'Инструменты', 'Інструменти'),
    _t('Shown on Home below the menu', '显示在主屏幕菜单下方', '顯示在主畫面選單下方', 'ホームのメニューの下に表示', '홈 메뉴 아래에 표시', "Affiché sous le menu d'accueil", 'Unter dem Menü auf dem Startbildschirm',
       'Se muestra bajo el menú de inicio', 'Mostrato sotto il menu in Home', 'แสดงใต้เมนูในหน้าหลัก', 'Widoczne pod menu na ekranie głównym', 'Под меню на главном экране', 'Під меню на головному екрані'),
    _t('A new mix the next time Home opens', '下次打开主屏幕时生成新的精选', '下次開啟主畫面時產生新的精選', '次にホームを開くと新しいミックス', '다음에 홈을 열면 새 믹스', "Un nouveau mix à la prochaine ouverture", 'Beim nächsten Öffnen ein neuer Mix',
       'Una mezcla nueva al abrir Inicio', 'Un nuovo mix alla prossima apertura', 'มิกซ์ใหม่เมื่อเปิดหน้าหลักครั้งถัดไป', 'Nowy miks przy następnym otwarciu', 'Новый микс при следующем открытии', 'Новий мікс при наступному відкритті'),
    _t('New mix when Home opens', '主屏幕打开时生成新精选', '主畫面開啟時產生新精選', 'ホームを開くと新しいミックス', '홈을 열면 새 믹스', "Nouveau mix à l'ouverture", 'Neuer Mix beim Öffnen',
       'Nueva mezcla al abrir Inicio', "Nuovo mix all'apertura", 'มิกซ์ใหม่เมื่อเปิดหน้าหลัก', 'Nowy miks po otwarciu', 'Новый микс при открытии', 'Новий мікс при відкритті'),
    _t('Applies the next time Cassette Mode opens.', '下次打开磁带模式时生效。', '下次開啟錄音帶模式時生效。', '次回カセットモード起動時に反映', '다음에 카세트 모드를 열 때 적용됩니다.', "S'applique à la prochaine ouverture.", 'Gilt beim nächsten Öffnen.',
       'Se aplica la próxima vez que se abre.', 'Si applica alla prossima apertura.', 'มีผลเมื่อเปิดครั้งถัดไป', 'Zastosowane przy następnym otwarciu.', 'Применится при следующем открытии.', 'Застосується при наступному відкритті.'),
    # Settings > Now Playing > Idle Display (patch/bigcover.c, docs/modules/bigcover.md "Idle view")
    _t('Idle Display', '空闲显示', '閒置顯示', '待機表示', '대기 화면', 'Affichage veille', 'Ruheanzeige',
       'Vista reposo', 'Vista inattiva', 'แสดงขณะว่าง', 'Ekran czuwania', 'Экран простоя', 'Заставка'),
    _t('Album Cover', '专辑封面', '專輯封面', 'アルバムカバー', '앨범 커버', 'Pochette', 'Albumcover',
       'Portada', 'Copertina', 'ปกอัลบั้ม', 'Okładka', 'Обложка', 'Обкладинка'),
    _t('Cassette', '磁带', '錄音帶', 'カセット', '카세트', 'Cassette', 'Kassette',
       'Casete', 'Cassetta', 'เทป', 'Kaseta', 'Кассета', 'Касета'),
    _t('Vinyl', '黑胶', '黑膠', 'レコード', '바이닐', 'Vinyle', 'Vinyl',
       'Vinilo', 'Vinile', 'แผ่นเสียง', 'Winyl', 'Винил', 'Вініл'),
    _t('Shown after 10 seconds on Now Playing.', '在正在播放界面停留10秒后显示。', '在正在播放畫面停留10秒後顯示。', '再生画面で10秒後に表示されます。', '지금 재생 화면에서 10초 후 표시됩니다.', "Affichée après 10 s sur Lecture en cours.", 'Nach 10 Sekunden auf „Jetzt läuft“.',
       'Se muestra tras 10 s en Reproduciendo.', 'Mostrata dopo 10 secondi in Riproduzione.', 'แสดงหลัง 10 วินาทีในหน้ากำลังเล่น', 'Pokazywane po 10 s na ekranie odtwarzania.', 'Через 10 с на экране «Сейчас играет».', 'Через 10 секунд на екрані «Зараз грає».'),
    # The Wi-Fi page (patch/wifipage.c, docs/modules/wifi.md): the group headers, Other..., the toasts and the Bluetooth question
    _t("Enterprise isn't supported yet", '暂不支持企业级网络', '暫不支援企業級網路', 'エンタープライズは未対応です', '엔터프라이즈는 아직 지원되지 않음', 'Entreprise : pas encore pris en charge', 'Enterprise wird noch nicht unterstützt',
       'Empresarial aún no es compatible', 'Enterprise non ancora supportato', 'ยังไม่รองรับเครือข่ายองค์กร', 'Enterprise nie jest jeszcze obsługiwane', 'Корпоративные сети пока не поддерживаются', 'Корпоративні мережі ще не підтримуються'),
    _t("WEP isn't supported", '不支持 WEP', '不支援 WEP', 'WEP には対応していません', 'WEP는 지원되지 않음', "WEP n'est pas pris en charge", 'WEP wird nicht unterstützt',
       'WEP no es compatible', 'WEP non supportato', 'ไม่รองรับ WEP', 'WEP nie jest obsługiwane', 'WEP не поддерживается', 'WEP не підтримується'),
    _t("This network isn't supported", '不支持此网络', '不支援此網路', 'このネットワークには対応していません', '이 네트워크는 지원되지 않음', 'Réseau non pris en charge', 'Netzwerk wird nicht unterstützt',
       'Red no compatible', 'Rete non supportata', 'ไม่รองรับเครือข่ายนี้', 'Ta sieć nie jest obsługiwana', 'Эта сеть не поддерживается', 'Ця мережа не підтримується'),
    _t("Couldn't connect", '无法连接', '無法連線', '接続できません', '연결할 수 없음', 'Connexion impossible', 'Verbindung fehlgeschlagen',
       'No se pudo conectar', 'Impossibile connettersi', 'เชื่อมต่อไม่ได้', 'Nie można połączyć', 'Не удалось подключиться', 'Не вдалося підключитися'),
    _t('My Networks', '我的网络', '我的網路', 'マイネットワーク', '내 네트워크', 'Mes réseaux', 'Meine Netzwerke',
       'Mis redes', 'Le mie reti', 'เครือข่ายของฉัน', 'Moje sieci', 'Мои сети', 'Мої мережі'),
    _t('Networks', '网络', '網路', 'ネットワーク', '네트워크', 'Réseaux', 'Netzwerke',
       'Redes', 'Reti', 'เครือข่าย', 'Sieci', 'Сети', 'Мережі'),
    _t('Other…', '其他…', '其他…', 'その他…', '기타…', 'Autre…', 'Andere…',
       'Otra…', 'Altra…', 'อื่น ๆ…', 'Inna…', 'Другая…', 'Інша…'),
    # The Wi-Fi info page (patch/wifipage.c, docs/modules/wifi.md): its rows, and the security's name (the standards' names stay as they are)
    _t('Forget This Network', '忘记此网络', '忘記此網路', 'このネットワーク設定を削除', '이 네트워크 지우기', 'Oublier ce réseau', 'Dieses Netzwerk ignorieren',
       'Olvidar esta red', 'Dimentica questa rete', 'ลืมเครือข่ายนี้', 'Zapomnij tę sieć', 'Забыть эту сеть', 'Забути цю мережу'),
    _t('Security', '安全性', '安全性', 'セキュリティ', '보안', 'Sécurité', 'Sicherheit',
       'Seguridad', 'Sicurezza', 'ความปลอดภัย', 'Zabezpieczenia', 'Защита', 'Захист'),
    _t('Router', '路由器', '路由器', 'ルーター', '라우터', 'Routeur', 'Router',
       'Router', 'Router', 'เราเตอร์', 'Router', 'Маршрутизатор', 'Маршрутизатор'),
    _t('Auto-Join', '自动加入', '自動加入', '自動接続', '자동 연결', 'Connexion auto', 'Automatisch verbinden',
       'Conexión automática', 'Connessione automatica', 'เชื่อมต่ออัตโนมัติ', 'Połącz automatycznie', 'Автоподключение', 'Автопідключення'),
    _t('Join', '加入', '加入', '接続', '연결', 'Rejoindre', 'Verbinden',
       'Conectar', 'Connetti', 'เชื่อมต่อ', 'Połącz', 'Войти', 'Увійти'),   # (short: it is also the keyboard's action key on the password page, 66 px)
    # The Wi-Fi password page (patch/wifipage.c, docs/modules/wifi.md "The password page"): the title, the field's label, the line under the title (%s is the network's name, put in by the payload) and the wrong-password line
    _t('Enter Password', '输入密码', '輸入密碼', 'パスワードを入力', '비밀번호 입력', 'Saisir le mot de passe', 'Passwort eingeben',
       'Introducir contraseña', 'Inserisci password', 'ป้อนรหัสผ่าน', 'Wpisz hasło', 'Введите пароль', 'Введіть пароль'),
    _t('Password', '密码', '密碼', 'パスワード', '비밀번호', 'Mot de passe', 'Passwort',
       'Contraseña', 'Password', 'รหัสผ่าน', 'Hasło', 'Пароль', 'Пароль'),
    _t('Enter the password for “%s”', '输入“%s”的密码', '輸入「%s」的密碼', '“%s”のパスワードを入力', '“%s”의 비밀번호를 입력하세요', 'Saisissez le mot de passe de « %s »', 'Passwort für „%s“ eingeben',
       'Introduce la contraseña de “%s”', 'Inserisci la password di “%s”', 'ป้อนรหัสผ่านสำหรับ “%s”', 'Wpisz hasło do sieci „%s”', 'Введите пароль для «%s»', 'Введіть пароль для «%s»'),
    _t('Incorrect password', '密码不正确', '密碼不正確', 'パスワードが正しくありません', '비밀번호가 올바르지 않습니다', 'Mot de passe incorrect', 'Falsches Passwort',
       'Contraseña incorrecta', 'Password errata', 'รหัสผ่านไม่ถูกต้อง', 'Nieprawidłowe hasło', 'Неверный пароль', 'Неправильний пароль'),
    # The Join Wi-Fi Network page (patch/wifipage.c wo_*, ws_*): its title, the Name row's placeholder, the action keys (Next, Join) and the Security picker (None; WPA2/WPA3 and WPA3 are the Wi-Fi page's)
    _t('Join Wi-Fi Network', '加入 Wi-Fi 网络', '加入 Wi-Fi 網路', 'Wi-Fiに接続', 'Wi-Fi 네트워크 연결', 'Rejoindre un réseau', 'Netzwerk beitreten',
       'Unirse a red Wi-Fi', 'Connetti a rete Wi-Fi', 'เข้าร่วมเครือข่าย Wi-Fi', 'Dołącz do sieci Wi-Fi', 'Подключение к Wi-Fi', 'Підключення до Wi-Fi'),
    _t('Network Name', '网络名称', '網路名稱', 'ネットワーク名', '네트워크 이름', 'Nom du réseau', 'Netzwerkname',
       'Nombre de red', 'Nome rete', 'ชื่อเครือข่าย', 'Nazwa sieci', 'Имя сети', 'Назва мережі'),
    _t('Next', '下一步', '下一步', '次へ', '다음', 'Suivant', 'Weiter',
       'Siguiente', 'Avanti', 'ถัดไป', 'Dalej', 'Далее', 'Далі'),
    _t('None', '无', '無', 'なし', '없음', 'Aucune', 'Keine',
       'Ninguna', 'Nessuna', 'ไม่มี', 'Brak', 'Нет', 'Немає'),
    _t('Open', '开放', '開放', 'オープン', '개방', 'Ouvert', 'Offen',
       'Abierta', 'Aperta', 'เปิด', 'Otwarta', 'Открытая', 'Відкрита'),
    _t('Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open',
       'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open', 'Enhanced Open'),
    _t('WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP', 'WEP'),
    _t('WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2', 'WPA/WPA2'),
    _t('WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3', 'WPA2/WPA3'),
    _t('WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3', 'WPA3'),
    _t('Enterprise', '企业级', '企業級', 'エンタープライズ', '엔터프라이즈', 'Entreprise', 'Enterprise',
       'Empresarial', 'Enterprise', 'องค์กร', 'Enterprise', 'Корпоративная', 'Корпоративна'),
    _t('Off: the device starts on Shanling Home', '关闭：设备启动后进入山灵主页', '關閉：裝置啟動後進入山靈主頁', 'オフ：Shanling ホームで起動', '끔: Shanling 홈으로 시작', "Désactivé : démarre sur l'accueil Shanling", 'Aus: Start im Shanling-Start',
       'Desactivado: inicia en Inicio Shanling', 'Disattivo: avvio da Home Shanling', 'ปิด: เริ่มที่หน้าหลัก Shanling', 'Wył.: start z ekranu Shanling', 'Выкл.: запуск с экрана Shanling', 'Вимк.: запуск з екрана Shanling'),
    _t('Show, hide and reorder the menu', '显示、隐藏和排序菜单项', '顯示、隱藏及排序選單項目', 'メニュー項目の表示・非表示・並べ替え', '메뉴 항목 표시, 숨기기, 순서 변경', 'Afficher, masquer, réordonner le menu', 'Menü ein-, ausblenden, anordnen',
       'Mostrar, ocultar y ordenar el menú', 'Mostra, nascondi e riordina il menu', 'แสดง ซ่อน และเรียงเมนู', 'Pokaż, ukryj i uporządkuj menu', 'Показать, скрыть и упорядочить меню', 'Показати, сховати й упорядкувати меню'),
    _t('Items the menu does not show', '菜单中未显示的项目', '選單中未顯示的項目', 'メニューに表示されない項目', '메뉴에 표시되지 않는 항목', 'Éléments absents du menu', 'Einträge, die das Menü nicht zeigt',
       'Elementos que el menú no muestra', 'Voci non mostrate nel menu', 'รายการที่เมนูไม่แสดง', 'Pozycje niewidoczne w menu', 'Пункты, которых нет в меню', 'Пункти, яких немає в меню'),
    _t('Favorites', '我的最爱', '我的最愛', 'お気に入り', '즐겨찾기', 'Favoris', 'Favoriten',
       'Favoritos', 'Preferiti', 'รายการโปรด', 'Ulubione', 'Избранное', 'Вибране'),
    _t('Recently Added', '最近添加', '最近新增', '最近追加した曲', '최근 추가됨', 'Ajoutés récemment', 'Kürzlich hinzugefügt',
       'Añadidos recientemente', 'Aggiunti di recente', 'เพิ่มล่าสุด', 'Ostatnio dodane', 'Недавно добавленные', 'Нещодавно додані'),
    _t('Recently Played', '最近播放', '最近播放', '最近再生した曲', '최근 재생', 'Lus récemment', 'Zuletzt gespielt',
       'Reproducido hace poco', 'Riprodotti di recente', 'เล่นล่าสุด', 'Ostatnio odtwarzane', 'Недавно слушали', 'Нещодавно відтворені'),
    # Settings > Home Screen > the Recently Played shelf's switch (patch/recent.c). Its own wording: the menu item's text above is too
    # wide for the switch row in Spanish and Ukrainian, and the shelf shows albums
    _t('Recent Albums', '最近专辑', '最近專輯', '最近のアルバム', '최근 앨범', 'Albums récents', 'Letzte Alben',
       'Álbumes recientes', 'Album recenti', 'อัลบั้มล่าสุด', 'Ostatnie albumy', 'Недавние альбомы', 'Недавні альбоми'),
    _t('Most Played','经常播放', '經常播放', 'よく再生する曲', '자주 듣는 음악', 'Les plus écoutés', 'Meistgespielt',
       'Más reproducidas', 'Più riprodotti', 'เล่นบ่อยที่สุด', 'Najczęściej odtwarzane', 'Часто слушаемые', 'Часто відтворювані'),
    _t('Composers', '作曲者', '作曲者', '作曲者', '작곡가', 'Compositeurs', 'Komponisten',
       'Compositores', 'Compositori', 'นักแต่งเพลง', 'Kompozytorzy', 'Композиторы', 'Композитори'),
    _t('Album Artists', '专辑表演者', '專輯表演者', 'アルバムアーティスト', '앨범 아티스트', "Artistes de l'album", 'Albumkünstler',
       'Artistas del álbum', "Artisti dell'album", 'ศิลปินอัลบั้ม', 'Wykonawcy albumu', 'Исполнители альбома', 'Виконавці альбому'),
    _t('Cancel', '取消', '取消', 'キャンセル', '취소', 'Annuler', 'Abbrechen',
       'Cancelar', 'Annulla', 'ยกเลิก', 'Anuluj', 'Отмена', 'Скасувати'),
    _t('Update Local Music first', '请先更新曲库', '請先更新曲庫', '先にライブラリを更新', '먼저 라이브러리를 업데이트하세요',
       'Mettez la bibliothèque à jour', 'Datenbank zuerst aktualisieren', 'Actualiza primero la librería',
       'Aggiorna prima la libreria', 'อัพเดทรายการเพลงก่อน', 'Najpierw zaktualizuj bibliotekę', 'Сначала обновите библиотеку', 'Спочатку оновіть медіатеку'),
    _t('Not enough memory', '内存不足', '記憶體不足', 'メモリ不足', '메모리 부족', 'Mémoire insuffisante', 'Nicht genug Speicher',
       'Memoria insuficiente', 'Memoria insufficiente', 'หน่วยความจำไม่พอ', 'Za mało pamięci', 'Недостаточно памяти', "Недостатньо пам'яті"),
    _t('Storage unavailable', '存储不可用', '儲存空間無法使用', 'ストレージを利用できません', '저장 장치를 사용할 수 없음', 'Stockage indisponible', 'Speicher nicht verfügbar',
       'Almacenamiento no disponible', 'Archivio non disponibile', 'ไม่พบที่เก็บข้อมูล', 'Pamięć niedostępna', 'Хранилище недоступно', 'Сховище недоступне'),
    _t('Too many songs to shuffle', '歌曲太多，无法随机播放', '歌曲太多，無法隨機播放', '曲が多すぎます', '노래가 너무 많음',
       'Trop de titres à mélanger', 'Zu viele Titel zum Mischen', 'Demasiadas canciones', 'Troppi brani da mescolare',
       'เพลงมากเกินไปสำหรับสุ่ม', 'Za dużo utworów do losowania', 'Слишком много песен', 'Забагато пісень'),
    _t('All albums', '所有专辑', '所有專輯', 'すべてのアルバム', '모든 앨범', 'Tous les albums', 'Alle Alben',
       'Todos los álbumes', 'Tutti gli album', 'อัลบั้มทั้งหมด', 'Wszystkie albumy', 'Все альбомы', 'Усі альбоми'),
    _t('Preparing covers...', '正在准备封面...', '正在準備封面...', 'カバーを準備中...', '커버 준비 중...', 'Création des pochettes...', 'Cover werden erstellt...',
       'Preparando carátulas...', 'Preparazione copertine...', 'กำลังเตรียมปก...', 'Przygotowanie okładek...', 'Подготовка обложек...', 'Готуємо обкладинки...'),
    _t('Preparing covers', '正在准备封面', '正在準備封面', 'カバーを準備中', '커버 준비 중', 'Création des pochettes', 'Cover werden erstellt',
       'Preparando carátulas', 'Preparazione copertine', 'กำลังเตรียมปก', 'Przygotowanie okładek', 'Подготовка обложек', 'Готуємо обкладинки'),
    _t('Rebuilding covers', '正在重建封面', '正在重建封面', 'カバーを再構築中', '커버 다시 만드는 중', 'Reconstruction des pochettes', 'Cover werden neu erstellt',
       'Reconstruyendo carátulas', 'Ricostruzione copertine', 'กำลังสร้างปกใหม่', 'Odbudowa okładek', 'Пересоздание обложек', 'Перестворення обкладинок'),
    _t('Preparing artist photos', '正在准备艺人照片', '正在準備藝人照片', 'アーティスト写真を準備中', '아티스트 사진 준비 중', "Préparation des photos d'artistes", 'Künstlerfotos werden erstellt',
       'Preparando fotos de artistas', 'Preparazione foto artisti', 'กำลังเตรียมรูปศิลปิน', 'Przygotowanie zdjęć wykonawców', 'Подготовка фото исполнителей', 'Готуємо фото виконавців'),
    _t('Rebuilding artist photos', '正在重建艺人照片', '正在重建藝人照片', 'アーティスト写真を再構築中', '아티스트 사진 다시 만드는 중', 'Reconstruction des photos', 'Künstlerfotos werden neu erstellt',
       'Reconstruyendo fotos de artistas', 'Ricostruzione foto artisti', 'กำลังสร้างรูปศิลปินใหม่', 'Odbudowa zdjęć wykonawców', 'Пересоздание фото исполнителей', 'Перестворення фото виконавців'),
    _t('Covers will rebuild on Home', '封面将在主屏幕重建', '封面將在主畫面重建', 'カバーはホームで再構築', '홈 화면에서 커버를 다시 만듭니다',
       "Pochettes refaites sur l'accueil", 'Cover auf Home neu erstellt', 'Carátulas se rehacen en Inicio',
       'Copertine rifatte in Home', 'จะสร้างปกใหม่ที่หน้าหลัก', 'Okładki odbudują się na Home', 'Обложки обновятся в Home',
       'Обкладинки оновимо в Home'),
    _t('Library too large', '曲库太大', '曲庫太大', 'ライブラリが大きすぎます', '라이브러리가 너무 큼', 'Bibliothèque trop volumineuse', 'Datenbank zu groß',
       'Librería demasiado grande', 'Libreria troppo grande', 'รายการเพลงมากเกินไป', 'Biblioteka jest za duża', 'Библиотека слишком велика', 'Медіатека завелика'),
    _t('Top Results', '热门结果', '熱門結果', '上位の結果', '상위 결과', 'Meilleurs résultats', 'Top-Ergebnisse',
       'Mejores resultados', 'Risultati migliori', 'ผลลัพธ์ยอดนิยม', 'Najlepsze wyniki', 'Лучшие результаты', 'Найкращі результати'),
    _t('Recently Searched', '最近搜索', '最近搜尋', '最近の検索', '최근 검색', 'Recherches récentes', 'Zuletzt gesucht',
       'Búsquedas recientes', 'Ricerche recenti', 'การค้นหาล่าสุด', 'Ostatnie wyszukiwania', 'Недавние запросы', 'Нещодавні пошуки'),
    _t('Song', '歌曲', '歌曲', '曲', '노래', 'Titre', 'Titel',
       'Canción', 'Brano', 'เพลง', 'Utwór', 'Песня', 'Пісня'),
    _t('Playlist', '歌单', '歌單', 'プレイリスト', '플레이리스트', 'Playlist', 'Playlist',
       'Lista', 'Playlist', 'เพลย์ลิสต์', 'Playlista', 'Плейлист', 'Плейлист'),
    _t('No Results', '无结果', '無結果', '結果なし', '결과 없음', 'Aucun résultat', 'Keine Ergebnisse',
       'Sin resultados', 'Nessun risultato', 'ไม่พบผลลัพธ์', 'Brak wyników', 'Нет результатов', 'Немає результатів'),
    _t('No albums', '没有专辑', '沒有專輯', 'アルバムがありません', '앨범 없음', 'Aucun album', 'Keine Alben',
       'Sin álbumes', 'Nessun album', 'ไม่มีอัลบั้ม', 'Brak albumów', 'Нет альбомов', 'Немає альбомів'),
    _t('No artists', '没有艺术家', '沒有藝術家', 'アーティストがありません', '아티스트 없음', 'Aucun artiste', 'Keine Künstler',
       'Sin artistas', 'Nessun artista', 'ไม่มีศิลปิน', 'Brak wykonawców', 'Нет исполнителей', 'Немає виконавців'),
    _t('Music', '音乐', '音樂', 'ミュージック', '음악', 'Musique', 'Musik',
       'Música', 'Musica', 'เพลง', 'Muzyka', 'Музыка', 'Музика'),
    # the Settings > Cover Flow sub-page (landscape switch; sort order, valued Artist or Album: "Album" is the stock key 'album')
    _t('Landscape', '横屏', '橫向', '横向き', '가로 모드', 'Paysage', 'Querformat',
       'Horizontal', 'Orizzontale', 'แนวนอน', 'Poziomo', 'Горизонтально', 'Горизонтально'),
    # Settings > Library > Cover Flow > Volume Buttons (patch/coverflow.c on_volkey) and its note
    _t('Volume Buttons', '音量键', '音量鍵', '音量ボタン', '볼륨 버튼', 'Boutons de volume', 'Lautstärketasten',
       'Teclas de volumen', 'Tasti volume', 'ปุ่มปรับเสียง', 'Przyciski głośności', 'Кнопки громкости', 'Кнопки гучності'),
    _t('In Cover Flow, the volume buttons move between albums.', '在封面流中，音量键用于切换专辑。', '在封面流中，音量鍵用於切換專輯。',
       'カバーフローでは、音量ボタンでアルバムを切り替えます。', '커버 플로우에서 볼륨 버튼으로 앨범을 넘깁니다.',
       "Dans Cover Flow, les boutons de volume changent d'album.", 'In Cover Flow wechseln die Lautstärketasten das Album.',
       'En Cover Flow, los botones de volumen cambian de álbum.', 'In Cover Flow, i tasti volume cambiano album.',
       'ใน Cover Flow ปุ่มปรับเสียงใช้เลื่อนระหว่างอัลบั้ม', 'W Cover Flow przyciski głośności przełączają albumy.',
       'В Cover Flow кнопки громкости переключают альбомы.', 'У Cover Flow кнопки гучності перемикають альбоми.'),
    _t('Artist', '歌手', '歌手', 'アーティスト', '아티스트', 'Artiste', 'Künstler',
       'Artista', 'Artista', 'ศิลปิน', 'Wykonawca', 'Исполнитель', 'Виконавець'),
    # Settings > Library > Rebuild Covers: the row, and the message of the stock confirm dialog (a centred white 20 px label
    # that wraps in 260 x 80 px: at most three lines, test/pod/i18n.py)
    _t('Rebuild Covers', '重建封面', '重建封面', 'カバーを再作成', '커버 다시 만들기', 'Recréer les pochettes', 'Cover neu erstellen',
       'Recrear carátulas', 'Ricrea copertine', 'สร้างปกใหม่', 'Odbuduj okładki', 'Пересоздать обложки', 'Оновити обкладинки'),
    _t('Clear Cover Cache', '清除封面缓存', '清除封面快取', 'カバーキャッシュを消去', '커버 캐시 지우기', 'Vider cache pochettes', 'Cover-Cache leeren',
       'Borrar caché de carátulas', 'Svuota cache copertine', 'ล้างแคชปก', 'Wyczyść pamięć okładek', 'Очистить кэш обложек', 'Очистити кеш обкладинок'),
    _t('Delete all cached covers? They will be made again on Home.', '删除所有已缓存的封面？它们将在主页重新生成。', '刪除所有已快取的封面？它們將在主畫面重新產生。',
       'キャッシュしたカバーをすべて削除しますか？ホームで再作成されます。', '캐시된 모든 커버를 삭제할까요? 홈에서 다시 만들어집니다.',
       'Supprimer les pochettes en cache ? Refaites sur l\'accueil.', 'Cover-Cache löschen? Auf Home neu erstellt.',
       '¿Borrar todas las carátulas en caché? Se rehacen en Inicio.', 'Eliminare tutte le copertine in cache? Verranno ricreate in Home.',
       'ลบปกที่แคชไว้ทั้งหมดหรือไม่ ระบบจะสร้างใหม่ที่หน้าหลัก', 'Usunąć okładki z pamięci? Powstaną na Home.',
       'Удалить кэш обложек? Он будет создан заново.', 'Видалити всі кешовані обкладинки? Їх буде створено знову в Home.'),
    _t('Cover cache cleared', '封面缓存已清除', '封面快取已清除', 'キャッシュを消去しました', '커버 캐시를 지웠습니다', 'Cache des pochettes vidé', 'Cover-Cache geleert',
       'Caché de carátulas borrada', 'Cache copertine svuotata', 'ล้างแคชปกแล้ว', 'Pamięć okładek wyczyszczona', 'Кэш обложек очищен', 'Кеш обкладинок очищено'),
    # Track durations (patch/durations.c, patch/homecover.c, patch/albumpage.c; docs/modules/album-page.md "Album length"): the Home line "Measuring tracks n/m", the album page's meta line
    # "N tracks, 49 minutes" / "1 hour, 12 minutes" (ru, pl, uk abbreviate the units: no plural forms, as their track counts are label forms), Settings > Developer > Clear Track Durations.
    # A native-speaker pass is wanted.
    _t('Measuring tracks', '正在测量曲目', '正在測量曲目', '曲の長さを測定中', '곡 길이 측정 중', 'Mesure des titres', 'Titeldauern werden gemessen', 'Midiendo pistas', 'Misura delle tracce',
       'กำลังวัดความยาวเพลง', 'Mierzenie utworów', 'Измерение треков', 'Вимірювання треків'),
    _t('Checking library…', '正在检查曲库…', '正在檢查曲庫…', 'ライブラリを確認中…', '라이브러리 확인 중…', 'Vérification de la bibliothèque…', 'Datenbank wird geprüft…',
       'Comprobando biblioteca…', 'Controllo libreria…', 'กำลังตรวจสอบคลัง…', 'Sprawdzanie biblioteki…', 'Проверка медиатеки…', 'Перевірка медіатеки…'),
    _t('Rebuilding covers…', '正在重建封面…', '正在重建封面…', 'カバーを再構築中…', '커버 다시 만드는 중…', 'Reconstruction des pochettes…', 'Cover werden neu erstellt…',
       'Reconstruyendo carátulas…', 'Ricostruzione copertine…', 'กำลังสร้างปกใหม่…', 'Odbudowa okładek…', 'Пересоздание обложек…', 'Перестворення обкладинок…'),
    _t('Rebuilding artist photos…', '正在重建艺人照片…', '正在重建藝人照片…', 'アーティスト写真を再構築中…', '아티스트 사진 다시 만드는 중…', 'Reconstruction des photos…', 'Künstlerfotos werden neu erstellt…',
       'Reconstruyendo fotos de artistas…', 'Ricostruzione foto artisti…', 'กำลังสร้างรูปศิลปินใหม่…', 'Odbudowa zdjęć wykonawców…', 'Пересоздание фото исполнителей…', 'Перестворення фото виконавців…'),
    _t('%d track, %s', '%d 首歌，%s', '%d 首歌，%s', '%d曲、%s', '%d곡, %s', '%d titre, %s', '%d Titel, %s', '%d canción, %s', '%d brano, %s', '%d เพลง, %s', 'Utwory: %d, %s', 'Песен: %d, %s', 'Пісень: %d, %s'),
    _t('%d tracks, %s', '%d 首歌，%s', '%d 首歌，%s', '%d曲、%s', '%d곡, %s', '%d titres, %s', '%d Titel, %s', '%d canciones, %s', '%d brani, %s', '%d เพลง, %s', 'Utwory: %d, %s', 'Песен: %d, %s', 'Пісень: %d, %s'),
    _t('%d minute', '%d 分钟', '%d 分鐘', '%d分', '%d분', '%d minute', '%d Minute', '%d minuto', '%d minuto', '%d นาที', '%d min', '%d мин', '%d хв'),
    _t('%d minutes', '%d 分钟', '%d 分鐘', '%d分', '%d분', '%d minutes', '%d Minuten', '%d minutos', '%d minuti', '%d นาที', '%d min', '%d мин', '%d хв'),
    _t('%d hour', '%d 小时', '%d 小時', '%d時間', '%d시간', '%d heure', '%d Stunde', '%d hora', '%d ora', '%d ชั่วโมง', '%d godz.', '%d ч', '%d год'),
    _t('%d hours', '%d 小时', '%d 小時', '%d時間', '%d시간', '%d heures', '%d Stunden', '%d horas', '%d ore', '%d ชั่วโมง', '%d godz.', '%d ч', '%d год'),
    # hours and minutes together (one key per singular / plural pair: each language controls its own join)
    _t('%d hour, %d minute', '%d 小时 %d 分钟', '%d 小時 %d 分鐘', '%d時間%d分', '%d시간 %d분', '%d heure, %d minute', '%d Stunde, %d Minute', '%d hora, %d minuto', '%d ora, %d minuto', '%d ชั่วโมง, %d นาที', '%d godz., %d min', '%d ч, %d мин', '%d год, %d хв'),
    _t('%d hour, %d minutes', '%d 小时 %d 分钟', '%d 小時 %d 分鐘', '%d時間%d分', '%d시간 %d분', '%d heure, %d minutes', '%d Stunde, %d Minuten', '%d hora, %d minutos', '%d ora, %d minuti', '%d ชั่วโมง, %d นาที', '%d godz., %d min', '%d ч, %d мин', '%d год, %d хв'),
    _t('%d hours, %d minute', '%d 小时 %d 分钟', '%d 小時 %d 分鐘', '%d時間%d分', '%d시간 %d분', '%d heures, %d minute', '%d Stunden, %d Minute', '%d horas, %d minuto', '%d ore, %d minuto', '%d ชั่วโมง, %d นาที', '%d godz., %d min', '%d ч, %d мин', '%d год, %d хв'),
    _t('%d hours, %d minutes', '%d 小时 %d 分钟', '%d 小時 %d 分鐘', '%d時間%d分', '%d시간 %d분', '%d heures, %d minutes', '%d Stunden, %d Minuten', '%d horas, %d minutos', '%d ore, %d minuti', '%d ชั่วโมง, %d นาที', '%d godz., %d min', '%d ч, %d мин', '%d год, %d хв'),
    _t('Clear Track Durations', '清除曲目时长', '清除曲目時長', '再生時間を消去', '트랙 길이 지우기', 'Vider les durées', 'Titeldauern leeren', 'Borrar duraciones', 'Elimina durate', 'ล้างความยาวเพลง', 'Wyczyść czasy', 'Сбросить длительности', 'Скинути тривалості'),
    _t('Delete all measured track durations? They will be measured again on Home.', '删除所有已测量的曲目时长？它们将在主页重新测量。', '刪除所有已測量的曲目時長？它們將在主畫面重新測量。',
       'すべての再生時間を削除しますか？ホームで再度測定されます。', '측정된 모든 트랙 길이를 삭제할까요? 홈에서 다시 측정됩니다.', 'Supprimer les durées mesurées ? Elles seront remesurées sur Home.',
       'Alle gemessenen Titeldauern löschen? Sie werden auf Home neu gemessen.', '¿Borrar todas las duraciones medidas? Se medirán de nuevo en Home.', 'Eliminare tutte le durate misurate? Verranno misurate di nuovo in Home.',
       'ลบความยาวเพลงที่วัดแล้วทั้งหมด? จะวัดใหม่ที่หน้าหลัก', 'Usunąć zmierzone czasy utworów? Zostaną zmierzone ponownie w Home.', 'Удалить все измеренные длительности? Они будут измерены заново в Home.',
       'Видалити всі виміряні тривалості? Їх буде виміряно знову в Home.'),
    _t('Track durations cleared', '曲目时长已清除', '曲目時長已清除', '再生時間を消去しました', '트랙 길이를 지웠습니다', 'Durées effacées', 'Titeldauern gelöscht', 'Duraciones borradas', 'Durate eliminate', 'ล้างความยาวเพลงแล้ว', 'Czasy wyczyszczone', 'Длительности сброшены', 'Тривалості скинуто'),
    _t('Delete this settings file?', '删除此设置文件？', '刪除此設定檔？',
       'この設定ファイルを削除しますか？', '이 설정 파일을 삭제할까요?', 'Supprimer ce fichier de réglage ?',
       'Diese Einstellungsdatei löschen?', '¿Borrar este archivo de ajustes?', 'Eliminare questo file di impostazioni?',
       'ลบไฟล์การตั้งค่านี้?', 'Usunąć ten plik ustawień?', 'Удалить этот файл настроек?',
       'Видалити цей файл налаштувань?'),
    _t('Settings file deleted', '设置文件已删除', '設定檔已刪除', '設定ファイルを削除しました', '설정 파일을 삭제했습니다', 'Fichier de réglage supprimé', 'Einstellungsdatei gelöscht', 'Archivo de ajustes borrado', 'File di impostazioni eliminato', 'ลบไฟล์การตั้งค่าแล้ว', 'Usunięto plik ustawień', 'Файл настроек удалён', 'Файл налаштувань видалено'),
    # Settings > Developer > Tools > Settings Files: Unsupported Files (the files older builds left behind; patch/setfiles.c, patch/covlist.c, patch/m1plus.c): the page's row and the list's title, the delete row, its confirm and toasts, the list's confirm and the empty list
    _t('Unsupported Files', '不受支持的文件', '不支援的檔案', '未対応のファイル', '지원되지 않는 파일', 'Fichiers obsolètes', 'Veraltete Dateien', 'Archivos antiguos', 'File non supportati', 'ไฟล์ที่ไม่รองรับ', 'Nieobsługiwane pliki', 'Старые файлы', 'Старі файли'),
    _t('Delete Unsupported Files', '删除不受支持的文件', '刪除不支援的檔案', '未対応のファイルを削除', '지원되지 않는 파일 삭제', 'Supprimer anciens fichiers', 'Veraltete Dateien löschen', 'Borrar archivos antiguos', 'Elimina file non supportati', 'ลบไฟล์ที่ไม่รองรับ', 'Usuń nieobsługiwane pliki', 'Удалить старые файлы', 'Видалити старі файли'),
    _t('Delete all unsupported files?', '删除所有不受支持的文件？', '刪除所有不支援的檔案？', 'サポートされていないファイルをすべて削除しますか？', '지원되지 않는 파일을 모두 삭제할까요?', 'Supprimer tous les fichiers non pris en charge ?', 'Alle nicht unterstützten Dateien löschen?', '¿Borrar todos los archivos no compatibles?', 'Eliminare tutti i file non supportati?', 'ลบไฟล์ที่ไม่รองรับทั้งหมด?', 'Usunąć wszystkie nieobsługiwane pliki?', 'Удалить все неподдерживаемые файлы?', 'Видалити всі непідтримувані файли?'),
    _t('Delete this unsupported file?', '删除此不受支持的文件？', '刪除此不支援的檔案？', 'このサポートされていないファイルを削除しますか？', '이 지원되지 않는 파일을 삭제할까요?', 'Supprimer ce fichier non pris en charge ?', 'Diese nicht unterstützte Datei löschen?', '¿Borrar este archivo no compatible?', 'Eliminare questo file non supportato?', 'ลบไฟล์ที่ไม่รองรับนี้?', 'Usunąć ten nieobsługiwany plik?', 'Удалить этот неподдерживаемый файл?', 'Видалити цей непідтримуваний файл?'),
    _t('Unsupported files deleted', '已删除不受支持的文件', '已刪除不支援的檔案', '未対応のファイルを削除しました', '지원되지 않는 파일을 삭제했습니다', 'Fichiers non pris en charge supprimés', 'Nicht unterstützte Dateien gelöscht', 'Archivos no compatibles borrados', 'File non supportati eliminati', 'ลบไฟล์ที่ไม่รองรับแล้ว', 'Usunięto nieobsługiwane pliki', 'Неподдерживаемые файлы удалены', 'Непідтримувані файли видалено'),
    _t('No unsupported files', '没有不受支持的文件', '沒有不支援的檔案', '未対応のファイルはありません', '지원되지 않는 파일이 없습니다', 'Aucun fichier non pris en charge', 'Keine nicht unterstützten Dateien', 'No hay archivos no compatibles', 'Nessun file non supportato', 'ไม่มีไฟล์ที่ไม่รองรับ', 'Brak nieobsługiwanych plików', 'Нет неподдерживаемых файлов', 'Немає непідтримуваних файлів'),
    # Settings > Developer > Tools > Reset All Settings (patch/m1plus.c reset_all_ask, patch/setfiles.c): the row, its confirm and the two toasts
    _t('Reset All Settings', '恢复所有设置', '重設所有設定', 'すべての設定をリセット', '모든 설정 초기화', 'Réinitialiser les réglages', 'Alles zurücksetzen',
       'Restablecer ajustes', 'Ripristina impostazioni', 'รีเซ็ตการตั้งค่าทั้งหมด', 'Zresetuj ustawienia', 'Сбросить все настройки', 'Скинути всі налаштування'),
    _t('Reset all settings to their defaults?', '将所有设置恢复为默认值？', '將所有設定恢復為預設值？',
       'すべての設定を初期値に戻しますか？', '모든 설정을 기본값으로 초기화할까요?',
       'Rétablir tous les réglages par défaut ?', 'Alle Einstellungen auf Standard zurücksetzen?',
       '¿Restablecer todos los ajustes predeterminados?', 'Ripristinare tutte le impostazioni predefinite?',
       'รีเซ็ตการตั้งค่าทั้งหมดเป็นค่าเริ่มต้นใช่ไหม?', 'Zresetować wszystkie ustawienia do domyślnych?',
       'Сбросить все настройки до значений по умолчанию?', 'Скинути всі налаштування до типових значень?'),
    _t('Settings reset. Restart to apply.', '设置已重置，重启后生效。', '設定已重設，重新啟動後生效。', '設定をリセットしました。再起動すると反映されます。', '설정을 초기화했습니다. 다시 시작하면 적용됩니다.',
       'Réglages réinitialisés. Redémarrez pour appliquer.', 'Einstellungen zurückgesetzt. Zum Übernehmen neu starten.', 'Ajustes restablecidos. Reinicia para aplicarlos.', 'Impostazioni ripristinate. Riavvia per applicarle.',
       'รีเซ็ตการตั้งค่าแล้ว รีสตาร์ทเพื่อใช้งาน', 'Ustawienia zresetowane. Uruchom ponownie, aby zastosować.', 'Настройки сброшены. Перезапустите, чтобы применить.', 'Налаштування скинуто. Перезапустіть, щоб застосувати.'),
    # Settings > Developer > Cache (patch/homecover.c): the row and page title, the seven labels, the Status values (a count "n/m" follows Preparing, Rebuilding and Building)
    _t('Settings Files', '设置文件', '設定檔案', '設定ファイル', '설정 파일', 'Fichiers de réglages', 'Einstellungsdateien', 'Archivos de ajustes', 'File delle impostazioni', 'ไฟล์การตั้งค่า', 'Pliki ustawień', 'Файлы настроек', 'Файли налаштувань'),
    _t('Cache', '缓存', '快取', 'キャッシュ', '캐시', 'Mémoire', 'Zwischenspeicher', 'Caché', 'Memoria', 'แคช', 'Pamięć podręczna', 'Кэш', 'Кеш'),
    # Settings > Developer > Cache > Track Durations (patch/durations.c): the section header and the table's count and size row
    _t('Track Durations', '曲目时长', '曲目時長', '再生時間', '트랙 길이', 'Durées des pistes', 'Titeldauern', 'Duraciones de pistas', 'Durate dei brani', 'ความยาวเพลง', 'Czasy utworów', 'Длительность треков', 'Тривалість треків'),
    _t('Measured Tracks', '已测量曲目', '已測量曲目', '計測済みの曲', '측정된 트랙', 'Pistes mesurées', 'Gemessene Titel', 'Pistas medidas', 'Brani misurati', 'เพลงที่วัดแล้ว', 'Zmierzone', 'Измерено', 'Виміряно треків'),
    _t('Covers', '封面', '封面', 'カバー', '커버', 'Pochettes', 'Cover', 'Carátulas', 'Copertine', 'ปก', 'Okładki', 'Обложки', 'Обкладинки'),
    _t('No art', '无封面', '無封面', 'カバーなし', '커버 없음', 'Sans pochette', 'Ohne Cover', 'Sin carátula', 'Senza copertina', 'ไม่มีปก', 'Brak okładki', 'Без обложки', 'Без обкладинки'),
    _t('No Art', '无封面', '無封面', 'カバーなし', '커버 없음', 'Sans pochette', 'Ohne Cover', 'Sin carátula', 'Senza copertina', 'ไม่มีปก', 'Brak okładki', 'Без обложки', 'Без обкладинки'),
    _t('Missing Covers', '缺失的封面', '缺少的封面', '未作成のカバー', '누락된 커버', 'Pochettes manquantes', 'Fehlende Cover', 'Carátulas que faltan', 'Copertine mancanti', 'ปกที่ขาดหาย', 'Brakujące okładki', 'Нет обложек', 'Немає обкладинок'),
    _t('Missing', '缺失', '缺少', '未作成', '누락', 'Manquantes', 'Fehlend', 'Faltan', 'Mancanti', 'ขาดหาย', 'Brakujące', 'Отсутствуют', 'Відсутні'),
    _t('Old files', '旧文件', '舊檔案', '古いファイル', '이전 파일', 'Anciens fichiers', 'Alte Dateien', 'Archivos viejos', 'File vecchi', 'ไฟล์เก่า', 'Stare pliki', 'Старые файлы', 'Старі файли'),
    _t('Size', '大小', '大小', 'サイズ', '크기', 'Taille', 'Größe', 'Tamaño', 'Dimensione', 'ขนาด', 'Rozmiar', 'Размер', 'Розмір'),
    _t('Status', '状态', '狀態', '状態', '상태', 'État', 'Status', 'Estado', 'Stato', 'สถานะ', 'Stan', 'Статус', 'Стан'),
    _t('Idle', '空闲', '閒置', '待機中', '대기 중', 'Inactif', 'Inaktiv', 'Inactivo', 'Inattivo', 'ว่าง', 'Bezczynny', 'Простой', 'Очікує'),
    _t('Preparing', '准备中', '準備中', '準備中', '준비 중', 'Création', 'Erstellen', 'Preparando', 'Preparazione', 'กำลังเตรียม', 'Tworzenie', 'Подготовка', 'Готуємо'),
    _t('Rebuilding', '重建中', '重建中', '再構築中', '재생성 중', 'Refonte', 'Neuaufbau', 'Rehaciendo', 'Ricostruzione', 'กำลังสร้างใหม่', 'Odbudowa', 'Пересоздаём', 'Перестворення'),
    _t('Rebuild requested', '已请求重建', '已要求重建', '再構築を予約済み', '재생성 예약됨', 'Refonte demandée', 'Neuaufbau angefordert', 'Rehacer pendiente', 'Ricostruzione richiesta', 'รอสร้างใหม่', 'Odbudowa zaplanowana', 'Запрошено', 'Перестворення заплановано'),
    _t('Clearing', '清除中', '清除中', '消去中', '지우는 중', 'Suppression', 'Löschen', 'Borrando', 'Eliminazione', 'กำลังล้าง', 'Czyszczenie', 'Очистка', 'Очищення'),
    _t('Building', '生成中', '產生中', '作成中', '생성 중', 'Création', 'Erstellung', 'Creando', 'Creazione', 'กำลังสร้าง', 'Tworzenie', 'Создание', 'Створення'),
    _t('Covers are being made, try later', '正在生成封面，请稍后再试', '正在產生封面，請稍後再試', 'カバー作成中。後で再試行', '커버 생성 중, 나중에 시도',
       'Pochettes en cours, plus tard', 'Cover werden erstellt, später', 'Creando carátulas, luego', 'Copertine in corso, dopo',
       'กำลังสร้างปก ลองใหม่ภายหลัง', 'Tworzenie okładek, później', 'Создаём обложки, позже', 'Створюємо обкладинки'),
    _t('Rebuild all covers? This may take a few minutes.', '重建所有封面？这可能需要几分钟。', '重建所有封面？這可能需要幾分鐘。',
       'すべてのカバーを再作成しますか？数分かかる場合があります。', '모든 커버를 다시 만들까요? 몇 분 걸릴 수 있습니다.',
       'Recréer toutes les pochettes ? Cela peut prendre quelques minutes.', 'Alle Cover neu erstellen? Das kann einige Minuten dauern.',
       '¿Recrear todas las carátulas? Puede tardar unos minutos.', 'Ricreare tutte le copertine? Potrebbe richiedere alcuni minuti.',
       'สร้างปกทั้งหมดใหม่หรือไม่ อาจใช้เวลาสองสามนาที', 'Odbudować wszystkie okładki? Może to potrwać kilka minut.',
       'Пересоздать все обложки? Это может занять несколько минут.', 'Оновити всі обкладинки? Це може тривати кілька хвилин.'),
    # Settings > Library > Rebuild Artist Photos (the row, the confirm of the stock dialog, the toast) and the Developer > Cache page's Artist Photos card (patch/m1plus.c arebuild_ask, patch/homecover.c)
    _t('Rebuild Artist Photos', '重建歌手照片', '重建歌手相片', 'アーティスト写真を再作成', '아티스트 사진 다시 만들기', 'Recréer photos artistes', 'Künstlerfotos neu erstellen',
       'Recrear fotos de artistas', 'Ricrea foto artisti', 'สร้างรูปศิลปินใหม่', 'Odbuduj zdjęcia', 'Обновить фото артистов', 'Оновити фото виконавців'),
    _t('Rebuild all artist photos? This may take a few minutes.', '重建所有歌手照片？这可能需要几分钟。', '重建所有歌手相片？這可能需要幾分鐘。',
       'すべてのアーティスト写真を再作成しますか？数分かかる場合があります。', '모든 아티스트 사진을 다시 만들까요? 몇 분 걸릴 수 있습니다.',
       'Recréer toutes les photos d\'artistes ? Cela peut prendre quelques minutes.', 'Alle Künstlerfotos neu erstellen? Das kann einige Minuten dauern.',
       '¿Recrear todas las fotos de artistas? Puede tardar unos minutos.', 'Ricreare tutte le foto degli artisti? Potrebbe richiedere alcuni minuti.',
       'สร้างรูปศิลปินทั้งหมดใหม่หรือไม่ อาจใช้เวลาสองสามนาที', 'Odbudować wszystkie zdjęcia wykonawców? Może to potrwać kilka minut.',
       'Пересоздать все фото исполнителей? Это может занять несколько минут.', 'Оновити всі фото виконавців? Це може тривати кілька хвилин.'),
    _t('Artist photos will rebuild on Home', '歌手照片将在主屏幕重建', '歌手相片將在主畫面重建', 'アーティスト写真はホームで再構築', '홈 화면에서 아티스트 사진을 다시 만듭니다',
       "Photos refaites sur l'accueil", 'Fotos auf Home neu erstellt', 'Fotos se rehacen en Inicio', 'Foto rifatte in Home',
       'จะสร้างรูปศิลปินใหม่ที่หน้าหลัก', 'Zdjęcia odbudują się na Home', 'Фото обновятся в Home', 'Фото оновимо в Home'),
    _t('Artist Photos', '歌手照片', '歌手相片', 'アーティスト写真', '아티스트 사진', "Photos d'artistes", 'Künstlerfotos',
       'Fotos de artistas', 'Foto artisti', 'รูปศิลปิน', 'Zdjęcia wykonawców', 'Фото исполнителей', 'Фото виконавців'),
    _t('Photos', '照片', '相片', '写真', '사진', 'Photos', 'Fotos',
       'Fotos', 'Foto', 'รูปภาพ', 'Zdjęcia', 'Фото', 'Фото'),
    # the Folders page's Delete confirm when a marked row is a folder (stock removes it with rm -rf; the dialog's wrapped label, at most three lines)
    _t('Delete folder and everything in it?', '删除文件夹及其中的所有内容？', '刪除資料夾及其中的所有內容？',
       'フォルダとその中身をすべて削除しますか？', '폴더와 그 안의 모든 항목을 삭제할까요?',
       'Supprimer le dossier et tout son contenu ?', 'Ordner und alles darin löschen?',
       '¿Eliminar la carpeta y todo su contenido?', 'Eliminare la cartella e tutto il suo contenuto?',
       'ลบโฟลเดอร์และทุกอย่างในโฟลเดอร์นี้หรือไม่', 'Usunąć folder i całą jego zawartość?',
       'Удалить папку и всё её содержимое?', 'Видалити папку та весь її вміст?'),
    # the track count of the album page's meta line: the payload chooses the key by n == 1 and puts the number where %d is;
    # languages with more than two plural forms (pl, ru, uk) use a label that needs none ("Tracks: 12")
    _t('%d track', '%d 首歌曲', '%d 首歌曲', '%d 曲', '%d곡', '%d titre', '%d Titel',
       '%d canción', '%d brano', '%d เพลง', 'Utwory: %d', 'Песен: %d', 'Пісень: %d'),
    _t('%d tracks', '%d 首歌曲', '%d 首歌曲', '%d 曲', '%d곡', '%d titres', '%d Titel',
       '%d canciones', '%d brani', '%d เพลง', 'Utwory: %d', 'Песен: %d', 'Пісень: %d'),
    # The Playlists page (patch/playlists.c): the menu row that opens the stock Playlists page to delete (its multi-select button), and the
    # empty page's line. New / Import / Export playlist are the stock keys (STOCK).
    _t('Delete Playlists', '删除歌单', '刪除歌單', 'プレイリストを削除', '재생 목록 삭제', 'Supprimer des playlists', 'Playlists löschen',
       'Eliminar listas', 'Elimina playlist', 'ลบเพลย์ลิสต์', 'Usuń playlisty', 'Удалить плейлисты', 'Видалити плейлисти'),
    _t('No playlists', '没有歌单', '沒有歌單', 'プレイリストがありません', '재생 목록 없음', 'Aucune playlist', 'Keine Playlists',
       'No hay listas', 'Nessuna playlist', 'ไม่มีเพลย์ลิสต์', 'Brak playlist', 'Нет плейлистов', 'Немає плейлистів'),
    # The song count under the last row of the Songs page and its lists (patch/songs.c sg_foot_text; chosen by n == 1 as the track count above;
    # pl, ru, uk the label form that needs no plural)
    _t('%d song', '%d 首歌曲', '%d 首歌曲', '%d 曲', '%d곡', '%d titre', '%d Titel',
       '%d canción', '%d brano', '%d เพลง', 'Utwory: %d', 'Песен: %d', 'Пісень: %d'),
    _t('%d songs', '%d 首歌曲', '%d 首歌曲', '%d 曲', '%d곡', '%d titres', '%d Titel',
       '%d canciones', '%d brani', '%d เพลง', 'Utwory: %d', 'Песен: %d', 'Пісень: %d'),
    # the grey line of a Most Played row, "12 plays · Artist" (patch/songs.c sg_prep; pl, ru, uk the label form)
    _t('%d play', '播放 %d 次', '播放 %d 次', '%d 回再生', '%d회 재생', '%d lecture', '%d Wiedergabe',
       '%d reproducción', '%d riproduzione', 'เล่น %d ครั้ง', 'Odtworzenia: %d', 'Прослушано: %d', 'Прослухано: %d'),
    _t('%d plays', '播放 %d 次', '播放 %d 次', '%d 回再生', '%d회 재생', '%d lectures', '%d Wiedergaben',
       '%d reproducciones', '%d riproduzioni', 'เล่น %d ครั้ง', 'Odtworzenia: %d', 'Прослушано: %d', 'Прослухано: %d'),
    # the Songs page's line for an empty list (Favourites, a playlist ...; the library's empty line is "Update Local Music first")
    _t('No songs', '没有歌曲', '沒有歌曲', '曲がありません', '노래 없음', 'Aucun titre', 'Keine Titel',
       'Sin canciones', 'Nessun brano', 'ไม่มีเพลง', 'Brak utworów', 'Нет песен', 'Немає пісень'),
    # the Folders page's line for a folder with nothing to show (patch/folders.c)
    _t('Empty folder', '空文件夹', '空資料夾', '空のフォルダ', '빈 폴더', 'Dossier vide', 'Leerer Ordner',
       'Carpeta vacía', 'Cartella vuota', 'โฟลเดอร์ว่าง', 'Pusty folder', 'Пустая папка', 'Порожня папка'),
    # the Folders page's toast for a folder (or storage) that folder_enter could not load: toolsLoadDirectory returned 0 (patch/folders.c fo_enter)
    _t('No music in this folder', '此文件夹中没有音乐', '此資料夾中沒有音樂', '音楽がありません', '이 폴더에 음악이 없습니다', 'Aucune musique ici', 'Keine Musik in diesem Ordner',
       'No hay música en esta carpeta', 'Nessuna musica qui', 'ไม่มีเพลงในโฟลเดอร์นี้', 'Brak muzyki w tym folderze', 'В этой папке нет музыки', 'У цій папці немає музики'),
    # the iPod page's Now Playing screen (patch/ipod.c): the line for an empty player (the track's place in the queue is the neutral "3 / 12": the table format allows one %d a text)
    _t('Not Playing', '未在播放', '未在播放', '再生していません', '재생 중이 아님', 'Aucune lecture', 'Keine Wiedergabe',
       'Sin reproducción', 'Nessuna riproduzione', 'ไม่ได้เล่น', 'Nie odtwarza', 'Не воспроизводится', 'Не відтворюється'),
    # the iPod page's Settings list (patch/ipod.c): the labels and the values that cycle (Shuffle: Off / Songs; Repeat: Off / One / All; its last row is the shared Settings key)
    _t('Repeat', '重复', '重複', 'リピート', '반복', 'Répéter', 'Wiederholen',
       'Repetir', 'Ripeti', 'เล่นซ้ำ', 'Powtarzaj', 'Повтор', 'Повтор'),
    _t('Off', '关', '關', 'オフ', '끔', 'Désactivé', 'Aus',
       'Desactivado', 'Disattivato', 'ปิด', 'Wył.', 'Выкл.', 'Вимк.'),
    _t('One', '单曲', '單曲', '1曲', '한 곡', 'Un titre', 'Einzeln',
       'Una', 'Uno', 'เพลงเดียว', 'Jeden', 'Один', 'Один'),
    _t('All', '全部', '全部', 'すべて', '전체', 'Tous', 'Alle',
       'Todo', 'Tutti', 'ทั้งหมด', 'Wszystkie', 'Все', 'Усі'),
    # Podcast search and Discover (patch/podcasts.c, docs/modules/podcasts.md "Search", "Discover", "Region"): the Settings row (Podcast Region, its Automatic choice) and its note, the search page's states, the preview's Subscribe pill,
    # the Discover line under the title (the storefront's name stays English in every language: no localised table of country names exists)
    _t('Podcast Discover', '播客发现', '播客探索', 'ポッドキャスト探索', '팟캐스트 탐색', 'Découvrir', 'Entdecken',
       'Descubrir', 'Scopri', 'ค้นพบพอดแคสต์', 'Odkrywaj', 'Обзор', 'Огляд'),   # (the switch: Discover and the search level; the short word under the Podcasts header, as Podcast Region)
    _t('Podcast Region', '播客地区', '播客地區', '地域', '지역', 'Région', 'Region',
       'Región', 'Regione', 'ภูมิภาค', 'Region', 'Регион', 'Регіон'),   # (the row has no glyph and its value needs the room: the short word under the Podcasts header)
    _t('Automatic', '自动', '自動', '自動', '자동', 'Automatique', 'Automatisch',
       'Automática', 'Automatica', 'อัตโนมัติ', 'Automatycznie', 'Автоматически', 'Автоматично'),
    _t('Top 25 Shows in %s', '%s 热门节目前 25', '%s 熱門節目前 25', '%sの人気番組トップ25', '%s 인기 프로그램 TOP 25', 'Top 25 des émissions : %s', 'Top 25 Sendungen in %s',
       'Top 25 programas en %s', 'Top 25 programmi in %s', 'รายการยอดนิยม 25 อันดับใน %s', 'Top 25 programów: %s', 'Топ-25 шоу: %s', 'Топ-25 шоу: %s'),
    _t('Top 25 Episodes in %s', '%s 热门单集前 25', '%s 熱門單集前 25', '%sの人気エピソードトップ25', '%s 인기 에피소드 TOP 25', 'Top 25 des épisodes : %s', 'Top 25 Folgen in %s',
       'Top 25 episodios en %s', 'Top 25 episodi in %s', 'ตอนยอดนิยม 25 อันดับใน %s', 'Top 25 odcinków: %s', 'Топ-25 выпусков: %s', 'Топ-25 випусків: %s'),
    _t('Search words are sent to Apple.', '搜索词会发送给 Apple。', '搜尋詞會傳送給 Apple。', '検索語は Apple に送信されます。', '검색어는 Apple로 전송됩니다.', 'Les mots recherchés sont envoyés à Apple.',
       'Suchbegriffe werden an Apple gesendet.', 'Los términos se envían a Apple.', 'Le parole cercate vanno ad Apple.', 'คำค้นหาจะถูกส่งไปยัง Apple', 'Szukane słowa trafiają do Apple.',
       'Слова запроса отправляются в Apple.', 'Слова запиту надсилаються до Apple.'),
    # Battery Percentage (patch/battery.c, docs/modules/battery.md): Settings > System > Battery
    _t('Battery Percentage', '电量百分比', '電量百分比', 'バッテリー残量', '배터리 잔량', 'Pourcentage', 'Akkustand',
       'Porcentaje', 'Percentuale', 'เปอร์เซ็นต์แบต', 'Poziom baterii', 'Процент заряда', 'Відсоток заряду'),
    _t('The exact charge beside the battery icon', '电池图标旁显示精确电量', '電池圖示旁顯示精確電量', 'バッテリーアイコンの横に正確な残量を表示', '배터리 아이콘 옆에 정확한 잔량 표시',
       'La charge exacte à côté de l’icône', 'Der genaue Ladestand neben dem Symbol', 'La carga exacta junto al icono', 'La carica esatta accanto all’icona',
       'ระดับแบตที่แน่นอนข้างไอคอน', 'Dokładny poziom obok ikony', 'Точный заряд рядом со значком', 'Точний заряд поруч зі значком'),
    # Continue with Next Album (patch/nextalbum.c, docs/modules/nextalbum.md): Settings > Playback
    _t('Continue Playing', '继续播放', '繼續播放', '続けて再生', '계속 재생', 'Enchaîner', 'Weiterspielen',
       'Continuar', 'Continua', 'เล่นต่อ', 'Kontynuuj', 'Продолжить', 'Продовжити'),
    _t('Next Albums', '下一张专辑', '下一張專輯', '次のアルバム', '다음 앨범', 'Albums suivants', 'Nächste Alben',
       'Álbumes siguientes', 'Album successivi', 'อัลบั้มถัดไป', 'Kolejne albumy', 'След. альбомы', 'Наст. альбоми'),
    _t('Plays the next album in the order of Albums, the artist or Cover Flow', '按专辑、艺人或封面流的顺序播放下一张专辑', '依專輯、藝人或封面流的順序播放下一張專輯',
       'アルバム、アーティスト、カバーフローの順で次のアルバムを再生', '앨범, 아티스트 또는 커버 플로우 순서로 다음 앨범 재생',
       'Lit l’album suivant dans l’ordre des Albums, de l’artiste ou de Cover Flow', 'Nächstes Album in der Reihenfolge von Alben, Künstler oder Cover Flow',
       'Reproduce el siguiente álbum en el orden de Álbumes, del artista o de Cover Flow', 'Riproduce l’album successivo nell’ordine di Album, artista o Cover Flow',
       'เล่นอัลบั้มถัดไปตามลำดับของอัลบั้ม ศิลปิน หรือ Cover Flow', 'Odtwarza następny album w kolejności Albumów, wykonawcy lub Cover Flow',
       'Играет следующий альбом в порядке списка, исполнителя или Cover Flow', 'Грає наступний альбом у порядку списку, виконавця або Cover Flow'),
    # Charge Limit (patch/charging.c, docs/modules/charging.md): Settings > System > Battery
    _t('Battery', '电池', '電池', 'バッテリー', '배터리', 'Batterie', 'Batterie',
       'Batería', 'Batteria', 'แบตเตอรี่', 'Bateria', 'Аккумулятор', 'Акумулятор'),
    _t('Charge Limit', '充电上限', '充電上限', '充電上限', '충전 한도', 'Limite de charge', 'Ladelimit',
       'Límite de carga', 'Limite di carica', 'ขีดจำกัดการชาร์จ', 'Limit ładowania', 'Лимит зарядки', 'Ліміт заряду'),
    _t('Applies while the player is on', '仅在开机时生效', '僅在開機時生效', '電源オン中のみ有効', '켜져 있는 동안 적용',
       'S’applique quand l’appareil est allumé', 'Gilt, solange das Gerät an ist', 'Se aplica con el equipo encendido',
       'Vale a dispositivo acceso', 'ใช้ขณะเปิดเครื่อง', 'Działa, gdy urządzenie jest włączone', 'Действует, пока плеер включён', 'Діє, поки плеєр увімкнено'),
    _t('Resumes a little below the limit', '略低于上限时恢复充电', '略低於上限時恢復充電', '上限を少し下回ると再開', '한도보다 조금 낮아지면 재개',
       'Reprend un peu sous la limite', 'Lädt knapp unter dem Limit weiter', 'Se reanuda algo por debajo del límite', 'Riprende poco sotto il limite',
       'ชาร์จต่อเมื่อต่ำกว่าขีดจำกัดเล็กน้อย', 'Wznawia nieco poniżej limitu', 'Возобновится чуть ниже предела', 'Відновиться трохи нижче межі'),
    # Settings > System > Display (patch/display.c, docs/modules/settings.md "Display"): our page's rows and the pickers' rows that are new. Our own short labels: stock's English for the backlight time is
    # "Screen Off" with the choice "Off", its LED row is "Atmosphere Lamp Settings", and its Follow Screen is English in every table but the Chinese ones. The other four backlight choices (15s .. 5min) are
    # stock's plain texts, the same in every language (BRANDS). (Lock Screen, Off and Orange are above.)
    _t('Follow Screen', '跟随屏幕', '跟隨螢幕', '画面に連動', '화면과 연동', 'Suivre l’écran', 'Bildschirm folgen',
       'Seguir pantalla', 'Segui schermo', 'ตามหน้าจอ', 'Jak ekran', 'Как экран', 'Як екран'),
    _t('Blue', '蓝色', '藍色', 'ブルー', '블루', 'Bleu', 'Blau',
       'Azul', 'Blu', 'น้ำเงิน', 'Niebieski', 'Синий', 'Синій'),
    _t('Screen Timeout', '背光时间', '背光時間', '画面消灯', '화면 꺼짐', 'Mise en veille', 'Bildschirm aus',
       'Apagar pantalla', 'Spegni schermo', 'ปิดหน้าจอ', 'Wygaszanie', 'Откл. экрана', 'Вимк. екрана'),
    _t('LED Light', '氛围灯', '氛圍燈', 'LEDライト', 'LED 조명', 'Voyant LED', 'LED-Licht',
       'Luz LED', 'Luce LED', 'ไฟ LED', 'Dioda LED', 'Светодиод', 'Світлодіод'),
    _t('Never', '常亮', '常亮', 'しない', '안 함', 'Jamais', 'Nie',
       'Nunca', 'Mai', 'ไม่เลย', 'Nigdy', 'Никогда', 'Ніколи'),
    # Settings > System > Buttons & Power (patch/keyspower.c, docs/modules/keyspower.md). Our own short labels, as Display's: stock's long texts do not fit the switch row, and some of its translations are wrong
    # (keylock_volume is "album" in Korean, powerm_saver the screen saver in Thai). The Tap to Wake row's room is the switch row's 173 px: test/pod/i18n.py measures every language. (Button Lock and Off are above.)
    _t('Buttons & Power', '按键与电源', '按鍵與電源', 'ボタンと電源', '버튼 및 전원', 'Touches et énergie', 'Tasten & Energie',
       'Botones y energía', 'Tasti e energia', 'ปุ่มและพลังงาน', 'Przyciski i zasilanie', 'Кнопки и питание', 'Кнопки й живлення'),
    _t('Tap to Wake', '点按唤醒', '點按喚醒', 'タップで復帰', '탭하여 깨우기', 'Réveil tactile', 'Antippen weckt',
       'Tocar para activar', 'Tocca per riattivare', 'แตะเพื่อปลุก', 'Dotyk wybudza', 'Касание будит', 'Дотик будить'),
    _t('Auto-Standby', '自动待机', '自動待機', '自動スタンバイ', '자동 대기', 'Veille auto', 'Auto-Standby',
       'Espera auto', 'Standby auto', 'สแตนด์บายอัตโนมัติ', 'Auto-gotowość', 'Автоожидание', 'Автоочікування'),
    _t('Auto-Shutdown', '自动关机', '自動關機', '自動電源オフ', '자동 종료', 'Arrêt auto', 'Auto-Abschaltung',
       'Autoapagado', 'Spegni auto', 'ปิดเครื่องอัตโนมัติ', 'Auto-wyłączanie', 'Автовыключение', 'Автовимкнення'),
    _t('Volume', '音量', '音量', '音量', '볼륨', 'Volume', 'Lautstärke',
       'Volumen', 'Volume', 'ระดับเสียง', 'Głośność', 'Громкость', 'Гучність'),
    _t('Buttons', '按键', '按鍵', 'ボタン', '버튼', 'Touches', 'Tasten',
       'Botones', 'Tasti', 'ปุ่ม', 'Przyciski', 'Кнопки', 'Кнопки'),
    _t('Both', '全部', '全部', '両方', '모두', 'Les deux', 'Beides',
       'Ambos', 'Entrambi', 'ทั้งคู่', 'Oba', 'Оба', 'Обидва'),
    _t('Lock Volume Only', '仅锁定音量', '僅鎖定音量', '音量のみロック', '볼륨만 잠금', 'Verrouiller le volume', 'Nur Lautstärke sperren',
       'Bloquear solo volumen', 'Blocca solo volume', 'ล็อกเฉพาะระดับเสียง', 'Blokuj tylko głośność', 'Только громкость', 'Лише гучність'),
    _t('Lock Buttons Only', '仅锁定按键', '僅鎖定按鍵', 'ボタンのみロック', '버튼만 잠금', 'Verrouiller les touches', 'Nur Tasten sperren',
       'Bloquear solo botones', 'Blocca solo tasti', 'ล็อกเฉพาะปุ่ม', 'Blokuj tylko przyciski', 'Только кнопки', 'Лише кнопки'),
    _t('Lock Volume & Buttons', '锁定音量和按键', '鎖定音量與按鍵', '音量とボタンをロック', '볼륨 및 버튼 잠금', 'Verrouiller vol. et touches', 'Lautstärke & Tasten sperren',
       'Bloquear volumen y botones', 'Blocca volume e tasti', 'ล็อกระดับเสียงและปุ่ม', 'Blokuj głośność i przyciski', 'Громкость и кнопки', 'Гучність і кнопки'),
    _t('Only effective when the screen is off', '仅在屏幕关闭时有效', '僅在螢幕關閉時有效', '画面がオフのときのみ有効', '화면이 꺼져 있을 때만 작동', 'Actif uniquement écran éteint', 'Nur bei ausgeschaltetem Bildschirm',
       'Solo con la pantalla apagada', 'Solo a schermo spento', 'ใช้ได้เฉพาะเมื่อปิดหน้าจอ', 'Tylko przy wyłączonym ekranie', 'Только при выключенном экране', 'Лише за вимкненого екрана'),
    _t('Only one of Auto-Standby and Auto-Shutdown is on at a time', '自动待机和自动关机只能开启其中一个', '自動待機和自動關機只能開啟其中一個', '自動スタンバイと自動電源オフは同時にオンにできません', '자동 대기와 자동 종료 중 하나만 켤 수 있습니다',
       'Veille auto et Arrêt auto ne peuvent pas être activés ensemble', 'Auto-Standby und Auto-Abschaltung sind nie gleichzeitig aktiv', 'Espera auto y Autoapagado no pueden estar activos a la vez',
       'Standby auto e Spegni auto non possono essere attivi insieme', 'เปิดได้ครั้งละหนึ่งอย่างระหว่างสแตนด์บายอัตโนมัติและปิดเครื่องอัตโนมัติ', 'Auto-gotowość i Auto-wyłączanie nie mogą działać jednocześnie',
       'Автоожидание и Автовыключение не работают одновременно', 'Автоочікування й Автовимкнення не працюють одночасно'),
    # A-Z lists (patch/azlist.c, docs/modules/settings.md): Settings > Library, the Index Rail and Section Headers switches
    _t('Index Rail', '索引栏', '索引欄', '索引バー', '색인 막대', 'Index latéral', 'Index-Leiste',
       'Índice lateral', 'Indice laterale', 'แถบดัชนี', 'Indeks boczny', 'Указатель', 'Покажчик'),
    _t('Section Headers', '分区标题', '分區標題', 'セクション見出し', '섹션 머리글', 'En-têtes', 'Abschnittstitel',
       'Encabezados', 'Intestazioni', 'หัวข้อส่วน', 'Nagłówki sekcji', 'Заголовки секций', 'Заголовки секцій'),
    _t('List Navigation', '列表导航', '列表導覽', 'リストのナビゲーション', '목록 탐색', 'Navigation des listes', 'Listennavigation',
       'Navegación de listas', 'Navigazione elenchi', 'การนำทางรายการ', 'Nawigacja list', 'Навигация по спискам', 'Навігація списками'),
    _t('Songs, Artists, Albums and Radio lists', '歌曲、艺人、专辑和电台列表', '歌曲、藝人、專輯和電台列表', '曲、アーティスト、アルバム、ラジオのリスト', '노래, 아티스트, 앨범, 라디오 목록',
       'Titres, artistes, albums et radios', 'Titel, Künstler, Alben und Radio', 'Canciones, artistas, álbumes y radio', 'Brani, artisti, album e radio',
       'เพลง ศิลปิน อัลบั้ม และวิทยุ', 'Utwory, wykonawcy, albumy i radio', 'Песни, исполнители, альбомы и радио', 'Пісні, виконавці, альбоми й радіо'),
    _t('Searching…','正在搜索…', '正在搜尋…', '検索中…', '검색 중…', 'Recherche…', 'Suche läuft…',
       'Buscando…', 'Ricerca in corso…', 'กำลังค้นหา…', 'Szukanie…', 'Поиск…', 'Пошук…'),
    _t('Loading…', '正在加载…', '正在載入…', '読み込み中…', '불러오는 중…', 'Chargement…', 'Wird geladen…',
       'Cargando…', 'Caricamento…', 'กำลังโหลด…', 'Wczytywanie…', 'Загрузка…', 'Завантаження…'),
    _t('No results', '无结果', '無結果', '結果なし', '결과 없음', 'Aucun résultat', 'Keine Ergebnisse',
       'Sin resultados', 'Nessun risultato', 'ไม่พบผลลัพธ์', 'Brak wyników', 'Нет результатов', 'Немає результатів'),
    _t('Not available', '不可用', '無法使用', '利用できません', '사용할 수 없음', 'Indisponible', 'Nicht verfügbar',
       'No disponible', 'Non disponibile', 'ไม่พร้อมใช้งาน', 'Niedostępny', 'Недоступно', 'Недоступно'),
    _t('Subscribe', '订阅', '訂閱', '登録', '구독', "S'abonner", 'Abonnieren',
       'Suscribirse', 'Iscriviti', 'ติดตาม', 'Subskrybuj', 'Подписаться', 'Підписатися'),
    _t("Can't subscribe", '无法订阅', '無法訂閱', '登録できません', '구독할 수 없음', 'Abonnement impossible', 'Abonnieren nicht möglich',
       'No se puede suscribir', 'Impossibile iscriversi', 'ติดตามไม่ได้', 'Nie można subskrybować', 'Не удалось подписаться', 'Не вдалося підписатися'),
    # The caption marker of a show that is only on the card (patch/podcasts.c, docs/modules/podcasts.md "The Shows page"; sentence case)
    _t('Local', '本地', '本地', 'ローカル', '로컬', 'Local', 'Lokal',
       'Local', 'Locale', 'ในเครื่อง', 'Lokalne', 'Локальные', 'Локальні'),
    # Podcasts (patch/podcasts.c, docs/modules/podcasts.md): the Extras item and the page's title, the two empty lines, the counts, the grey line of an episode
    _t('Podcasts', '播客', '播客', 'ポッドキャスト', '팟캐스트', 'Podcasts', 'Podcasts',
       'Pódcast', 'Podcast', 'พอดแคสต์', 'Podcasty', 'Подкасты', 'Подкасти'),
    _t('No podcasts. Copy a folder for each show into Podcasts on the card, or put subscriptions.txt there and choose Import from Card in the menu at the top right.',
       '没有播客。请在存储卡的 Podcasts 文件夹中为每个节目放一个文件夹，或把 subscriptions.txt 放在那里，然后在右上角的菜单中选择“从存储卡导入”。',
       '沒有播客。請在記憶卡的 Podcasts 資料夾中為每個節目放一個資料夾，或把 subscriptions.txt 放在那裡，然後在右上角的選單中選擇「從記憶卡匯入」。',
       'ポッドキャストがありません。カードの Podcasts フォルダに番組ごとのフォルダをコピーするか、subscriptions.txt を置いて、右上のメニューで「カードから読み込む」を選んでください。',
       '팟캐스트가 없습니다. 카드의 Podcasts 폴더에 프로그램마다 폴더를 복사하거나 subscriptions.txt를 넣고 오른쪽 위 메뉴에서 "카드에서 가져오기"를 선택하세요.',
       'Aucun podcast. Copiez un dossier par émission dans Podcasts sur la carte, ou placez-y subscriptions.txt et choisissez Importer depuis la carte dans le menu en haut à droite.',
       'Keine Podcasts. Kopiere für jede Sendung einen Ordner in Podcasts auf der Karte oder lege dort subscriptions.txt ab und wähle oben rechts im Menü Von Karte importieren.',
       'Sin pódcast. Copia una carpeta por programa en Podcasts de la tarjeta, o pon allí subscriptions.txt y elige Importar desde la tarjeta en el menú de arriba a la derecha.',
       'Nessun podcast. Copia una cartella per ogni programma in Podcasts sulla scheda, oppure mettici subscriptions.txt e scegli Importa dalla scheda nel menu in alto a destra.',
       'ไม่มีพอดแคสต์ คัดลอกโฟลเดอร์ของแต่ละรายการไปที่ Podcasts บนการ์ด หรือวาง subscriptions.txt ไว้ที่นั่น แล้วเลือกนำเข้าจากการ์ดในเมนูที่มุมขวาบน',
       'Brak podcastów. Skopiuj folder dla każdego programu do Podcasts na karcie albo połóż tam subscriptions.txt i wybierz Importuj z karty w menu w prawym górnym rogu.',
       'Нет подкастов. Скопируйте по папке на каждое шоу в Podcasts на карте или положите туда subscriptions.txt и выберите «Импорт с карты» в меню вверху справа.',
       'Немає подкастів. Скопіюйте по теці для кожного шоу в Podcasts на картці або покладіть туди subscriptions.txt і виберіть «Імпорт з картки» в меню вгорі праворуч.'),
    # The Shows page (patch/podcasts.c, docs/modules/podcasts.md "The Shows page"): the two section headers, the refresh line's word and its progress, the menu's row, the Show page's empty hint
    _t('Continue Listening', '继续收听', '繼續收聽', '続きを聴く', '이어 듣기', 'Reprendre la lecture', 'Weiterhören', 'Seguir escuchando', 'Continua ad ascoltare', 'ฟังต่อ', 'Kontynuuj słuchanie', 'Продолжить слушать', 'Продовжити слухати'),
    _t('Shows', '节目', '節目', '番組', '프로그램', 'Émissions', 'Sendungen', 'Programas', 'Programmi', 'รายการ', 'Programy', 'Шоу', 'Шоу'),
    _t('Refreshing %d/%d…', '正在刷新 %d/%d…', '正在更新 %d/%d…', '更新中 %d/%d…', '새로고침 중 %d/%d…', 'Actualisation %d/%d…', 'Aktualisiere %d/%d …', 'Actualizando %d/%d…', 'Aggiornamento %d/%d…', 'กำลังรีเฟรช %d/%d…',
       'Odświeżanie %d/%d…', 'Обновление %d/%d…', 'Оновлення %d/%d…'),
    _t('Import from Card', '从存储卡导入', '從記憶卡匯入', 'カードから読み込む', '카드에서 가져오기', 'Importer depuis la carte', 'Von Karte importieren', 'Importar desde la tarjeta', 'Importa dalla scheda', 'นำเข้าจากการ์ด',
       'Importuj z karty', 'Импорт с карты', 'Імпорт з картки'),
    _t('No episodes yet. Choose Refresh Feed in the menu at the top right.', '暂无节目。请在右上角的菜单中选择“刷新订阅源”。', '暫無節目。請在右上角的選單中選擇「更新訂閱源」。', 'エピソードはまだありません。右上のメニューで「フィードを更新」を選んでください。',
       '아직 에피소드가 없습니다. 오른쪽 위 메뉴에서 "피드 새로고침"을 선택하세요.', "Aucun épisode pour l'instant. Choisissez Actualiser dans le menu en haut à droite.", 'Noch keine Folgen. Wähle oben rechts im Menü Aktualisieren.',
       'Aún no hay episodios. Elige Actualizar en el menú de arriba a la derecha.', 'Ancora nessun episodio. Scegli Aggiorna nel menu in alto a destra.', 'ยังไม่มีตอน เลือกรีเฟรชฟีดในเมนูที่มุมขวาบน',
       'Brak odcinków. Wybierz Odśwież w menu w prawym górnym rogu.', 'Эпизодов пока нет. Выберите «Обновить» в меню вверху справа.', 'Епізодів поки немає. Виберіть «Оновити» в меню вгорі праворуч.'),
    # The refresh dialog of the Podcasts page (patch/podcasts.c pg_dlg_*; Cancel is the key above)
    _t('Refreshing Podcasts', '正在刷新播客', '正在更新 Podcast', 'ポッドキャストを更新中', '팟캐스트 새로고침 중', 'Actualisation des podcasts', 'Podcasts werden aktualisiert', 'Actualizando podcasts', 'Aggiornamento podcast',
       'กำลังรีเฟรชพอดแคสต์', 'Odświeżanie podcastów', 'Обновление подкастов', 'Оновлення подкастів'),
    _t('Cancelling…', '正在取消…', '正在取消…', 'キャンセル中…', '취소하는 중…', 'Annulation…', 'Wird abgebrochen …', 'Cancelando…', 'Annullamento…', 'กำลังยกเลิก…', 'Anulowanie…', 'Отмена…', 'Скасування…'),
    _t('%d of %d', '第 %d 个，共 %d 个', '第 %d 個，共 %d 個', '%d / %d', '%d / %d', '%d sur %d', '%d von %d', '%d de %d', '%d di %d', '%d จาก %d', '%d z %d', '%d из %d', '%d з %d'),
    _t('%d updated', '已更新 %d 个', '已更新 %d 個', '%d 件更新', '%d개 업데이트됨', '%d actualisés', '%d aktualisiert', '%d actualizados', '%d aggiornati', 'อัปเดต %d รายการ', 'Zaktualizowano: %d', 'Обновлено: %d', 'Оновлено: %d'),
    _t('%d updated, %d failed', '已更新 %d 个，%d 个失败', '已更新 %d 個，%d 個失敗', '%d 件更新、%d 件失敗', '%d개 업데이트됨, %d개 실패', '%d actualisés, %d échecs', '%d aktualisiert, %d fehlgeschlagen',
       '%d actualizados, %d con error', '%d aggiornati, %d non riusciti', 'อัปเดต %d รายการ ล้มเหลว %d', 'Zaktualizowano: %d, błędy: %d', 'Обновлено: %d, ошибок: %d', 'Оновлено: %d, помилок: %d'),
    _t('%d failed', '%d 个失败', '%d 個失敗', '%d 件失敗', '%d개 실패', '%d échecs', '%d fehlgeschlagen', '%d con error', '%d non riusciti', 'ล้มเหลว %d รายการ', 'Błędy: %d', 'Ошибок: %d', 'Помилок: %d'),
    _t('Cancelled', '已取消', '已取消', 'キャンセルしました', '취소됨', 'Annulé', 'Abgebrochen', 'Cancelado', 'Annullato', 'ยกเลิกแล้ว', 'Anulowano', 'Отменено', 'Скасовано'),
    _t('Cancelled, %d updated', '已取消，已更新 %d 个', '已取消，已更新 %d 個', 'キャンセル、%d 件更新', '취소됨, %d개 업데이트됨', 'Annulé, %d actualisés', 'Abgebrochen, %d aktualisiert', 'Cancelado, %d actualizados', 'Annullato, %d aggiornati',
       'ยกเลิกแล้ว อัปเดต %d รายการ', 'Anulowano, zaktualizowano: %d', 'Отменено, обновлено: %d', 'Скасовано, оновлено: %d'),
    # Podcasts, Feeds view and refresh (patch/podcasts.c, patch/pcnet.c; docs/modules/podcasts.md "Feeds")
    _t('Never refreshed', '从未刷新', '從未更新', '未更新', '새로고침 안 함', 'Jamais actualisé', 'Nie aktualisiert', 'Nunca actualizado', 'Mai aggiornato', 'ยังไม่เคยรีเฟรช', 'Nie odświeżano', 'Не обновлялось', 'Не оновлювалось'),
    _t('%d new', '%d 个新节目', '%d 個新節目', '新着 %d 件', '새 에피소드 %d개', '%d nouveaux', '%d neue', '%d nuevos', '%d nuovi', 'ใหม่ %d', '%d nowe', 'Новых: %d', 'Нових: %d'),
    _t('Too many shows', '节目过多', '節目過多', '番組が多すぎます', '프로그램이 너무 많습니다', 'Trop d’émissions', 'Zu viele Sendungen', 'Demasiados programas', 'Troppi programmi', 'รายการมากเกินไป', 'Zbyt wiele programów', 'Слишком много шоу', 'Забагато шоу'),   # (Subscribe and Import from Card with PC_MAX_SHOWS shows on the card; machine translations, unreviewed)
    _t('Nothing new to import', '没有可导入的新内容', '沒有可匯入的新內容', '読み込む新しい項目はありません', '가져올 새 항목이 없습니다', 'Rien de nouveau à importer', 'Nichts Neues zu importieren',
       'Nada nuevo que importar', 'Niente di nuovo da importare', 'ไม่มีรายการใหม่ให้นำเข้า', 'Brak nowych pozycji do zaimportowania', 'Нечего импортировать', 'Немає що імпортувати'),
    _t('%d added', '已添加 %d 个', '已新增 %d 個', '%d 件追加', '%d개 추가됨', '%d ajoutés', '%d hinzugefügt', '%d añadidos', '%d aggiunti', 'เพิ่ม %d รายการ', 'Dodano: %d', 'Добавлено: %d', 'Додано: %d'),
    # The Subscriptions page and OPML (patch/podcasts.c, docs/modules/podcasts.md "Subscriptions and OPML"; Unsubscribe is the Show page's key)
    _t('Subscriptions', '订阅', '訂閱', '登録番組', '구독', 'Abonnements', 'Abos', 'Suscripciones', 'Iscrizioni', 'การติดตาม', 'Subskrypcje', 'Подписки', 'Підписки'),
    _t('Export OPML', '导出 OPML', '匯出 OPML', 'OPML を書き出す', 'OPML 내보내기', 'Exporter en OPML', 'OPML exportieren', 'Exportar OPML', 'Esporta OPML', 'ส่งออก OPML', 'Eksportuj OPML', 'Экспорт OPML', 'Експорт OPML'),
    _t('Select Shows', '选择节目', '選擇節目', '番組を選択', '프로그램 선택', 'Sélectionner des émissions', 'Sendungen auswählen', 'Seleccionar programas', 'Seleziona programmi', 'เลือกรายการ', 'Wybierz programy', 'Выбрать шоу', 'Вибрати шоу'),
    _t('No subscriptions', '没有订阅', '沒有訂閱', '登録はありません', '구독이 없습니다', 'Aucun abonnement', 'Keine Abos', 'Sin suscripciones', 'Nessuna iscrizione', 'ไม่มีการติดตาม', 'Brak subskrypcji', 'Нет подписок', 'Немає підписок'),
    _t('Exported %d show', '已导出 %d 个节目', '已匯出 %d 個節目', '%d 件の番組を書き出しました', '프로그램 %d개 내보냄', '%d émission exportée', '%d Sendung exportiert', '%d programa exportado', '%d programma esportato', 'ส่งออก %d รายการ',
       'Wyeksportowano: %d', 'Экспортировано: %d', 'Експортовано: %d'),
    _t('Exported %d shows', '已导出 %d 个节目', '已匯出 %d 個節目', '%d 件の番組を書き出しました', '프로그램 %d개 내보냄', '%d émissions exportées', '%d Sendungen exportiert', '%d programas exportados', '%d programmi esportati', 'ส่งออก %d รายการ',
       'Wyeksportowano: %d', 'Экспортировано: %d', 'Експортовано: %d'),
    _t('Unsubscribe from these shows?', '取消订阅这些节目？', '取消訂閱這些節目？', 'これらの番組の登録を解除しますか？', '이 프로그램들의 구독을 취소할까요?', 'Se désabonner de ces émissions ?', 'Diese Sendungen nicht mehr abonnieren?',
       '¿Cancelar suscripción a estos programas?', "Annullare l'iscrizione a questi programmi?", 'เลิกติดตามรายการเหล่านี้หรือไม่?', 'Anulować subskrypcję tych programów?', 'Отписаться от этих шоу?', 'Скасувати підписку на ці шоу?'),
    _t('No Wi-Fi', '无 Wi-Fi', '沒有 Wi-Fi', 'Wi-Fi 未接続', 'Wi-Fi 연결 없음', 'Pas de Wi-Fi', 'Kein WLAN', 'Sin Wi-Fi', 'Nessun Wi-Fi', 'ไม่มี Wi-Fi', 'Brak Wi-Fi', 'Нет Wi-Fi', 'Немає Wi-Fi'),
    _t('Set the date first', '请先设置日期', '請先設定日期', '先に日付を設定してください', '먼저 날짜를 설정하세요', "Réglez d'abord la date", 'Zuerst das Datum einstellen', 'Ajusta antes la fecha',
       'Imposta prima la data', 'ตั้งวันที่ก่อน', 'Najpierw ustaw datę', 'Сначала установите дату', 'Спочатку встановіть дату'),
    _t('Certificates missing', '缺少证书', '缺少憑證', '証明書がありません', '인증서 없음', 'Certificats manquants', 'Zertifikate fehlen', 'Faltan certificados', 'Certificati mancanti', 'ไม่พบใบรับรอง', 'Brak certyfikatów', 'Нет сертификатов', 'Немає сертифікатів'),
    _t('Certificate problem', '证书有问题', '憑證有問題', '証明書に問題があります', '인증서 문제', 'Problème de certificat', 'Zertifikatsproblem', 'Problema de certificado', 'Problema di certificato', 'ใบรับรองมีปัญหา', 'Problem z certyfikatem', 'Проблема с сертификатом', 'Проблема із сертифікатом'),
    _t("Can't connect", '无法连接', '無法連線', '接続できません', '연결할 수 없음', 'Connexion impossible', 'Keine Verbindung', 'No se puede conectar', 'Impossibile connettersi', 'เชื่อมต่อไม่ได้', 'Nie można połączyć', 'Не удаётся подключиться', 'Не вдається підключитися'),
    _t('Feed not found', '找不到订阅源', '找不到訂閱源', 'フィードが見つかりません', '피드를 찾을 수 없음', 'Flux introuvable', 'Feed nicht gefunden', 'Fuente no encontrada', 'Feed non trovato', 'ไม่พบฟีด', 'Nie znaleziono kanału', 'Подписка не найдена', 'Підписку не знайдено'),
    _t('Server error', '服务器错误', '伺服器錯誤', 'サーバーエラー', '서버 오류', 'Erreur du serveur', 'Serverfehler', 'Error del servidor', 'Errore del server', 'เซิร์ฟเวอร์ผิดพลาด', 'Błąd serwera', 'Ошибка сервера', 'Помилка сервера'),
    _t('Not a podcast feed', '不是播客订阅源', '不是 Podcast 訂閱源', 'ポッドキャストのフィードではありません', '팟캐스트 피드가 아닙니다', "Ce n'est pas un flux de podcast", 'Kein Podcast-Feed', 'No es una fuente de podcast',
       'Non è un feed podcast', 'ไม่ใช่ฟีดพอดแคสต์', 'To nie jest kanał podcastu', 'Это не подписка на подкаст', 'Це не стрічка подкасту'),
    _t('%d MB', '%dMB', '%dMB', '%dMB', '%dMB', *(['%d MB'] * 8)),   # the size ending a remote episode's grey line (no space in the CJK languages)
    # Episode downloads (patch/podcasts.c, patch/pcnet.c; docs/modules/podcasts.md "Downloads"): the grey line of an episode that is not on the card, "Failed: <reason>" (the reasons above and these), and the Feeds row
    _t('Downloading', '正在下载', '正在下載', 'ダウンロード中', '다운로드 중', 'Téléchargement', 'Wird geladen', 'Descargando', 'Download in corso', 'กำลังดาวน์โหลด', 'Pobieranie', 'Загрузка', 'Завантаження'),
    _t('Waiting', '等待中', '等待中', '待機中', '대기 중', 'En attente', 'Wartet', 'En espera', 'In attesa', 'รอคิว', 'Oczekuje', 'Ожидание', 'Очікування'),
    _t('Paused', '已暂停', '已暫停', '一時停止中', '일시 중지됨', 'En pause', 'Pausiert', 'En pausa', 'In pausa', 'หยุดชั่วคราว', 'Wstrzymano', 'Приостановлено', 'Призупинено'),
    _t('Failed', '失败', '失敗', '失敗', '실패', 'Échec', 'Fehler', 'Error', 'Errore', 'ล้มเหลว', 'Błąd', 'Сбой', 'Збій'),
    _t('Not found', '未找到', '找不到', '見つかりません', '찾을 수 없음', 'Introuvable', 'Nicht gefunden', 'No encontrado', 'Non trovato', 'ไม่พบ', 'Nie znaleziono', 'Не найдено', 'Не знайдено'),
    _t('Not audio', '不是音频', '不是音訊', '音声ではありません', '오디오가 아님', "Pas de l'audio", 'Kein Audio', 'No es audio', 'Non è audio', 'ไม่ใช่เสียง', 'To nie audio', 'Не аудио', 'Не аудіо'),
    _t('Card is full', '存储卡已满', '記憶卡已滿', 'カードがいっぱいです', '카드가 가득 참', 'Carte pleine', 'Karte voll', 'Tarjeta llena', 'Scheda piena', 'การ์ดเต็ม', 'Karta pełna', 'Карта заполнена', 'Картка заповнена'),
    _t('Queue is full', '队列已满', '佇列已滿', 'キューがいっぱいです', '대기열이 가득 참', "File d'attente pleine", 'Warteschlange voll', 'Cola llena', 'Coda piena', 'คิวเต็ม', 'Kolejka pełna', 'Очередь заполнена', 'Черга заповнена'),
    _t('Download queue is full', '下载队列已满', '下載佇列已滿', 'ダウンロードキューがいっぱいです', '다운로드 대기열이 가득 참', 'File de téléchargement pleine', 'Download-Warteschlange voll', 'Cola de descargas llena', 'Coda di download piena', 'คิวดาวน์โหลดเต็ม', 'Kolejka pobierania pełna', 'Очередь загрузки заполнена', 'Черга завантаження заповнена'),
    # Download Album (the Subsonic album page's "..." card, patch/sbsrc.c nd_act LS_ACT_DOWNLOAD_ALL): the row and its one toast (1 song / n songs picked by n == 1; pl, ru, uk the label form)
    _t('Download Album', '下载专辑', '下載專輯', 'アルバムをダウンロード', '앨범 다운로드', "Télécharger l'album", 'Album laden', 'Descargar álbum', 'Scarica album', 'ดาวน์โหลดอัลบั้ม', 'Pobierz album', 'Загрузить альбом', 'Завантажити альбом'),
    _t('Downloading 1 song', '正在下载 1 首歌曲', '正在下載 1 首歌曲', '1 曲をダウンロード中', '1곡 다운로드 중', 'Téléchargement de 1 titre', '1 Titel wird geladen', 'Descargando 1 canción', 'Download di 1 brano', 'กำลังดาวน์โหลด 1 เพลง', 'Pobieranie utworu: 1', 'Загрузка песни: 1', 'Завантаження пісні: 1'),
    _t('Downloading %d songs', '正在下载 %d 首歌曲', '正在下載 %d 首歌曲', '%d 曲をダウンロード中', '%d곡 다운로드 중', 'Téléchargement de %d titres', '%d Titel werden geladen', 'Descargando %d canciones', 'Download di %d brani', 'กำลังดาวน์โหลด %d เพลง', 'Pobieranie utworów: %d', 'Загрузка песен: %d', 'Завантаження пісень: %d'),
    _t('Downloading %d, queue full', '正在下载 %d 首，队列已满', '正在下載 %d 首，佇列已滿', '%d 曲をダウンロード中、キューは満杯', '%d곡 다운로드 중, 대기열 가득 참', 'Téléchargement de %d, file pleine', '%d werden geladen, Warteschlange voll', 'Descargando %d, cola llena', 'Download di %d, coda piena', 'กำลังดาวน์โหลด %d เพลง คิวเต็ม', 'Pobieranie: %d, kolejka pełna', 'Загрузка: %d, очередь заполнена', 'Завантаження: %d, чергу заповнено'),
    _t('Already downloaded', '已下载', '已下載', 'ダウンロード済み', '이미 다운로드됨', 'Déjà téléchargé', 'Bereits geladen', 'Ya descargado', 'Già scaricato', 'ดาวน์โหลดแล้ว', 'Już pobrano', 'Уже загружено', 'Уже завантажено'),
    # The track rows' "..." menu (patch/rowmenu.c, docs/modules/rowmenu.md): its two rows (Add to Playlist is the Songs page's key), the two confirmations and the refusals of Play Next / Play After
    # (Adding Failed, Storage unavailable, Queue is full and Not enough memory are the stock key and the keys above)
    _t('Play Next', '下一首播放', '下一首播放', '次に再生', '다음에 재생', 'Lire ensuite', 'Als Nächstes spielen',
       'Reproducir a continuación', 'Riproduci come successivo', 'เล่นถัดไป', 'Odtwórz jako następny', 'Воспроизвести следующим', 'Відтворити наступним'),
    _t('Play After', '最后播放', '最後播放', '最後に再生', '마지막에 재생', 'Lire en dernier', 'Zuletzt spielen',
       'Reproducir al final', 'Riproduci per ultimo', 'เล่นเป็นเพลงสุดท้าย', 'Odtwórz na końcu', 'Воспроизвести последним', 'Відтворити останнім'),
    _t('Playing Next', '已设为下一首播放', '已設為下一首播放', '次に再生します', '다음에 재생됩니다', 'Lecture ensuite', 'Wird als Nächstes gespielt',
       'Se reproducirá a continuación', 'In riproduzione dopo', 'จะเล่นเพลงถัดไป', 'Odtworzone jako następne', 'Будет следующим', 'Буде наступним'),
    _t('Added to Queue', '已添加到队列', '已加入佇列', 'キューに追加しました', '대기열에 추가됨', "Ajouté à la file d'attente", 'Zur Warteschlange hinzugefügt',
       'Añadido a la cola', 'Aggiunto alla coda', 'เพิ่มในคิวแล้ว', 'Dodano do kolejki', 'Добавлено в очередь', 'Додано до черги'),
    # the track rows' "..." sheet's Favorite / Get Info rows and the Get Info page (patch/rowmenu.c, patch/songinfo.c; docs/modules/rowmenu.md, songinfo.md)
    _t('Favorite', '收藏', '收藏', 'お気に入り', '즐겨찾기', 'Favori', 'Favorit',
       'Favorito', 'Preferito', 'ชื่นชอบ', 'Ulubione', 'В избранное', 'В обране'),
    _t('Undo Favorite', '取消收藏', '取消收藏', 'お気に入りを解除', '즐겨찾기 해제', 'Retirer des favoris', 'Favorit entfernen',
       'Quitar de favoritos', 'Rimuovi dai preferiti', 'เลิกชื่นชอบ', 'Usuń z ulubionych', 'Убрать из избранного', 'Прибрати з обраного'),
    _t('Added to Favorites', '已添加到收藏', '已加入收藏', 'お気に入りに追加しました', '즐겨찾기에 추가됨', 'Ajouté aux favoris', 'Zu Favoriten hinzugefügt',
       'Añadido a favoritos', 'Aggiunto ai preferiti', 'เพิ่มในรายการโปรดแล้ว', 'Dodano do ulubionych', 'Добавлено в избранное', 'Додано до обраного'),
    _t('Removed from Favorites', '已取消收藏', '已取消收藏', 'お気に入りから削除しました', '즐겨찾기에서 삭제됨', 'Retiré des favoris', 'Aus Favoriten entfernt',
       'Quitado de favoritos', 'Rimosso dai preferiti', 'ลบออกจากรายการโปรดแล้ว', 'Usunięto z ulubionych', 'Удалено из избранного', 'Видалено з обраного'),
    _t('Get Info', '获取信息', '取得資訊', '情報を見る', '정보 가져오기', 'Informations', 'Informationen',
       'Obtener información', 'Ottieni informazioni', 'รับข้อมูล', 'Pobierz informacje', 'Сведения', 'Відомості'),
    _t('Format', '格式', '格式', 'フォーマット', '형식', 'Format', 'Format',
       'Formato', 'Formato', 'รูปแบบ', 'Format', 'Формат', 'Формат'),
    _t('Sample Rate', '采样率', '取樣率', 'サンプルレート', '샘플 레이트', "Fréquence d'échantillonnage", 'Abtastrate',
       'Frecuencia de muestreo', 'Frequenza di campionamento', 'อัตราการสุ่มตัวอย่าง', 'Częstotliwość próbkowania', 'Частота дискретизации', 'Частота дискретизації'),
    _t('Bit Depth', '位深度', '位元深度', 'ビット深度', '비트 심도', 'Profondeur de bits', 'Bittiefe',
       'Profundidad de bits', 'Profondità di bit', 'ความลึกบิต', 'Głębia bitowa', 'Разрядность', 'Бітова глибина'),
    _t('Duration', '时长', '時間長度', '再生時間', '재생 시간', 'Durée', 'Dauer',
       'Duración', 'Durata', 'ระยะเวลา', 'Czas trwania', 'Длительность', 'Тривалість'),
    _t('Path', '路径', '路徑', 'パス', '경로', 'Chemin', 'Pfad',
       'Ruta', 'Percorso', 'เส้นทาง', 'Ścieżka', 'Путь', 'Шлях'),
    _t('Not available while streaming', '流媒体播放时不可用', '串流播放時無法使用', 'ストリーミング中は使用できません', '스트리밍 중에는 사용할 수 없음', 'Indisponible pendant le streaming', 'Beim Streamen nicht verfügbar',
       'No disponible durante la transmisión', 'Non disponibile durante lo streaming', 'ใช้ไม่ได้ขณะสตรีม', 'Niedostępne podczas strumieniowania', 'Недоступно при потоковом воспроизведении', 'Недоступно під час потокового відтворення'),
    _t('Not available for folder playback', '文件夹播放时不可用', '資料夾播放時無法使用', 'フォルダ再生中は使用できません', '폴더 재생 중에는 사용할 수 없음', 'Indisponible en lecture de dossier', 'Bei Ordnerwiedergabe nicht verfügbar',
       'No disponible al reproducir una carpeta', 'Non disponibile con la riproduzione cartella', 'ใช้ไม่ได้ขณะเล่นจากโฟลเดอร์', 'Niedostępne przy odtwarzaniu folderu', 'Недоступно при воспроизведении папки', 'Недоступно під час відтворення папки'),
    _t('Not available for podcasts', '播客不可用', '播客無法使用', 'ポッドキャストでは使用できません', '팟캐스트에서는 사용할 수 없음', 'Indisponible pour les podcasts', 'Für Podcasts nicht verfügbar',
       'No disponible para podcasts', 'Non disponibile per i podcast', 'ใช้ไม่ได้กับพอดแคสต์', 'Niedostępne dla podcastów', 'Недоступно для подкастов', 'Недоступно для подкастів'),
    _t('Not available while DLNA is on', 'DLNA 开启时不可用', 'DLNA 開啟時無法使用', 'DLNAがオンの間は使用できません', 'DLNA가 켜져 있는 동안은 사용할 수 없음', 'Indisponible quand DLNA est activé', 'Bei aktivem DLNA nicht verfügbar',
       'No disponible con DLNA activado', 'Non disponibile con DLNA attivo', 'ใช้ไม่ได้เมื่อเปิด DLNA', 'Niedostępne przy włączonym DLNA', 'Недоступно при включённом DLNA', 'Недоступно, коли DLNA ввімкнено'),
    # The Queue page (patch/queuepage.c): the section line and the page's title, the line under it when nothing follows
    _t('Queue', '播放队列', '播放佇列', '再生キュー', '재생 대기열', "File d'attente", 'Warteschlange', 'Cola', 'Coda', 'คิว', 'Kolejka', 'Очередь', 'Черга'),
    _t('No upcoming songs', '没有待播歌曲', '沒有待播歌曲', '次の曲はありません', '다음 곡 없음', 'Aucun titre à suivre', 'Keine weiteren Titel', 'No hay más canciones', 'Nessun brano in coda', 'ไม่มีเพลงถัดไป', 'Brak kolejnych utworów', 'Нет следующих песен', 'Немає наступних пісень'),
    _t('Clear', '清除', '清除', '消去', '지우기', 'Effacer', 'Leeren', 'Borrar', 'Svuota', 'ล้าง', 'Wyczyść', 'Очистить', 'Очистити'),
    # The Downloads level and the select mode of the Show level (patch/podcasts.c; "N Selected", "Select All" and "Delete" are the Songs page's keys)
    _t('No downloads', '没有下载', '沒有下載', 'ダウンロードはありません', '다운로드 없음', 'Aucun téléchargement', 'Keine Downloads', 'Sin descargas', 'Nessun download', 'ไม่มีการดาวน์โหลด', 'Brak pobrań', 'Нет загрузок', 'Немає завантажень'),
    _t('Delete the selected episodes?', '删除所选节目？', '刪除所選節目？', '選択したエピソードを削除しますか？', '선택한 에피소드를 삭제할까요?', 'Supprimer les épisodes sélectionnés ?', 'Ausgewählte Folgen löschen?',
       '¿Eliminar los episodios seleccionados?', 'Eliminare gli episodi selezionati?', 'ลบตอนที่เลือกหรือไม่?', 'Usunąć wybrane odcinki?', 'Удалить выбранные выпуски?', 'Видалити вибрані випуски?'),
    _t('Remove the selected downloads?', '移除所选下载？', '移除所選下載？', '選択したダウンロードを削除しますか？', '선택한 다운로드를 제거할까요?', 'Retirer les téléchargements sélectionnés ?', 'Ausgewählte Downloads entfernen?',
       '¿Quitar las descargas seleccionadas?', 'Rimuovere i download selezionati?', 'ลบการดาวน์โหลดที่เลือกหรือไม่?', 'Usunąć wybrane pobrania?', 'Удалить выбранные загрузки?', 'Видалити вибрані завантаження?'),
    _t('The playing episode was kept', '正在播放的节目已保留', '正在播放的節目已保留', '再生中の項目は残しました', '재생 중인 에피소드는 유지되었습니다', 'L’épisode en lecture a été conservé', 'Die laufende Folge wurde behalten',
       'Se conservó el episodio en reproducción', 'Episodio in corso mantenuto', 'เก็บตอนที่กำลังเล่นไว้', 'Odtwarzany odcinek został zachowany', 'Воспроизводимый выпуск сохранён', 'Епізод, що відтворюється, збережено'),
    # Saved (patch/podcasts.c, docs/modules/podcasts.md "Saved"): the Shows page's row and page, and the episode sheet's row
    _t('Saved', '已保存', '已儲存', '保存済み', '저장됨', 'Enregistrés', 'Gesichert', 'Guardados', 'Salvati', 'บันทึกแล้ว', 'Zapisane', 'Сохранённые', 'Збережені'),
    _t('Save Episode', '保存单集', '儲存單集', 'エピソードを保存', '에피소드 저장', 'Enregistrer l’épisode', 'Episode sichern', 'Guardar episodio', 'Salva episodio', 'บันทึกตอน', 'Zapisz odcinek', 'Сохранить выпуск', 'Зберегти епізод'),
    _t('Unsave Episode', '取消保存单集', '取消儲存單集', 'エピソードの保存を解除', '에피소드 저장 해제', 'Retirer des enregistrés', 'Nicht mehr sichern', 'Quitar de guardados', 'Rimuovi dai salvati', 'เลิกบันทึกตอน', 'Usuń z zapisanych', 'Убрать из сохранённых', 'Прибрати зі збережених'),
    _t('No saved episodes', '没有已保存的单集', '沒有已儲存的單集', '保存したエピソードはありません', '저장된 에피소드가 없습니다', 'Aucun épisode enregistré', 'Keine gesicherten Episoden', 'Sin episodios guardados', 'Nessun episodio salvato', 'ไม่มีตอนที่บันทึกไว้', 'Brak zapisanych odcinków', 'Нет сохранённых выпусков', 'Немає збережених епізодів'),
    # The Pod's Podcasts pane on the main menu while no show has an episode (patch/ipod.c, docs/modules/ipod.md)
    _t('No Podcasts', '没有播客', '沒有播客', 'ポッドキャストなし', '팟캐스트 없음', 'Aucun podcast', 'Keine Podcasts', 'Sin pódcast', 'Nessun podcast', 'ไม่มีพอดแคสต์', 'Brak podcastów', 'Нет подкастов', 'Немає подкастів'),
    _t('No downloaded episodes', '没有已下载的节目', '沒有已下載的節目', 'ダウンロード済みのエピソードがありません', '다운로드한 에피소드가 없습니다', 'Aucun épisode téléchargé', 'Keine geladenen Folgen',
       'Sin episodios descargados', 'Nessun episodio scaricato', 'ไม่มีตอนที่ดาวน์โหลด', 'Brak pobranych odcinków', 'Нет загруженных выпусков', 'Немає завантажених випусків'),
    _t('%d episode', '%d 个节目', '%d 個節目', '%d エピソード', '에피소드 %d개', '%d épisode', '%d Folge',
       '%d episodio', '%d episodio', '%d ตอน', 'Odcinki: %d', 'Выпусков: %d', 'Випусків: %d'),
    _t('%d episodes', '%d 个节目', '%d 個節目', '%d エピソード', '에피소드 %d개', '%d épisodes', '%d Folgen',
       '%d episodios', '%d episodi', '%d ตอน', 'Odcinki: %d', 'Выпусков: %d', 'Випусків: %d'),
    # The Library rows of the Shows page and the Downloads page (patch/podcasts.c, docs/modules/podcasts.md "The Shows page", "The Downloaded page"): the rows' grey lines, the storage line, the two sections, the sheet and its toast
    _t('%d waiting', '%d 个等待中', '%d 個等待中', '%d 件待機中', '%d개 대기 중', '%d en attente', '%d wartend', '%d en espera', '%d in attesa', 'รอคิว %d', 'Oczekuje: %d', 'Ожидают: %d', 'Очікують: %d'),
    _t('%d paused', '%d 个已暂停', '%d 個已暫停', '%d 件一時停止中', '%d개 일시 중지됨', '%d en pause', '%d pausiert', '%d en pausa', '%d in pausa', 'หยุดชั่วคราว %d', 'Wstrzymano: %d', 'Приостановлено: %d', 'Призупинено: %d'),
    _t('%d show', '%d 个播客', '%d 個 Podcast', '%d 番組', '프로그램 %d개', '%d émission', '%d Sendung', '%d programa', '%d programma', '%d รายการ', 'Programy: %d', 'Шоу: %d', 'Шоу: %d'),
    _t('%d shows', '%d 个播客', '%d 個 Podcast', '%d 番組', '프로그램 %d개', '%d émissions', '%d Sendungen', '%d programas', '%d programmi', '%d รายการ', 'Programy: %d', 'Шоу: %d', 'Шоу: %d'),
    _t('%d.%d GB', '%d.%dGB', '%d.%dGB', '%d.%dGB', '%d.%dGB', '%d,%d GB', '%d,%d GB', '%d,%d GB', '%d,%d GB', '%d.%d GB', '%d,%d GB', '%d,%d GB', '%d,%d GB'),   # a size from a gigabyte on: one decimal, the language's mark (no space in the CJK languages, as %d MB)
    _t('%d GB', '%dGB', '%dGB', '%dGB', '%dGB', *(['%d GB'] * 8)),   # a size from 10 GB on, whole (no space in the CJK languages)
    _t('%s free', '剩余 %s', '剩餘 %s', '空き %s', '%s 사용 가능', '%s libres', '%s frei', '%s libres', '%s liberi', 'ว่าง %s', '%s wolnego', 'Свободно: %s', 'Вільно: %s'),
    _t('In Progress', '进行中', '進行中', '進行中', '진행 중', 'En cours', 'In Bearbeitung', 'En curso', 'In corso', 'กำลังดำเนินการ', 'W toku', 'В процессе', 'У процесі'),
    _t('Downloaded', '已下载', '已下載', 'ダウンロード済み', '다운로드됨', 'Téléchargés', 'Heruntergeladen', 'Descargados', 'Scaricati', 'ดาวน์โหลดแล้ว', 'Pobrane odcinki', 'Загружено', 'Завантажено'),
    _t('Select', '选择', '選擇', '選択', '선택', 'Sélectionner', 'Auswählen', 'Seleccionar', 'Seleziona', 'เลือก', 'Wybierz', 'Выбрать', 'Вибрати'),
    _t('Delete Played Episodes', '删除已播放的节目', '刪除已播放的節目', '再生済みのエピソードを削除', '재생한 에피소드 삭제', 'Supprimer les épisodes lus', 'Gehörte Folgen löschen', 'Eliminar episodios reproducidos', 'Elimina episodi riprodotti',
       'ลบตอนที่เล่นแล้ว', 'Usuń odtworzone odcinki', 'Удалить прослушанное', 'Видалити прослухані випуски'),
    _t('Delete all played episodes?', '删除所有已播放的节目？', '刪除所有已播放的節目？', '再生済みエピソードを削除しますか？', '재생한 에피소드를 모두 삭제할까요?', 'Supprimer tous les épisodes lus ?', 'Alle gehörten Folgen löschen?',
       '¿Eliminar los episodios reproducidos?', 'Eliminare tutti gli episodi riprodotti?', 'ลบตอนที่เล่นแล้วทั้งหมดหรือไม่?', 'Usunąć wszystkie odtworzone odcinki?', 'Удалить все прослушанные выпуски?', 'Видалити всі прослухані випуски?'),
    _t('%d deleted, %s freed', '已删除 %d 个，释放 %s', '已刪除 %d 個，釋放 %s', '%d 件削除、%s 解放', '%d개 삭제, %s 확보', 'Supprimés : %d, %s libérés', 'Gelöscht: %d, %s frei', 'Eliminados: %d, %s liberados', 'Eliminati: %d, %s liberati',
       'ลบ %d รายการ คืนพื้นที่ %s', 'Usunięto: %d, zwolniono %s', 'Удалено: %d, свободно %s', 'Видалено: %d, вільно %s'),
    _t('%d deleted', '已删除 %d 个', '已刪除 %d 個', '%d 件削除', '%d개 삭제', 'Supprimés : %d', 'Gelöscht: %d', 'Eliminados: %d', 'Eliminati: %d', 'ลบ %d รายการ', 'Usunięto: %d', 'Удалено: %d', 'Видалено: %d'),
    # The Show page (patch/podcasts.c, docs/modules/podcasts.md "The Show page"): the header's pill and list title, the two bottom sheets, the pills' labels
    _t('Latest Episode', '最新一集', '最新一集', '最新エピソード', '최신 에피소드', 'Dernier épisode', 'Neueste Folge', 'Último episodio', 'Ultimo episodio', 'ตอนล่าสุด', 'Najnowszy odcinek', 'Последний выпуск', 'Останній випуск'),
    _t('Episodes', '单集', '單集', 'エピソード', '에피소드', 'Épisodes', 'Folgen', 'Episodios', 'Episodi', 'ตอน', 'Odcinki', 'Выпуски', 'Випуски'),
    _t('Playback Speed', '播放速度', '播放速度', '再生速度', '재생 속도', 'Vitesse de lecture', 'Wiedergabetempo', 'Velocidad', 'Velocità di riproduzione', 'ความเร็วในการเล่น', 'Prędkość odtwarzania', 'Скорость', 'Швидкість відтворення'),
    _t('Episode Order', '节目顺序', '節目順序', 'エピソードの順序', '에피소드 순서', 'Ordre', 'Reihenfolge', 'Orden', 'Ordine', 'ลำดับตอน', 'Kolejność', 'Порядок', 'Порядок'),   # (the row shares its line with a value: the longer wordings of fr, de, es, it, pl, ru and uk are cut to one word, as the Region row's)
    _t('Newest First', '最新优先', '最新優先', '新しい順', '최신순', 'Plus récents', 'Neueste zuerst', 'Más recientes', 'Più recenti', 'ใหม่สุดก่อน', 'Najnowsze', 'Сначала новые', 'Спочатку нові'),
    _t('Oldest First', '最早优先', '最舊優先', '古い順', '오래된순', 'Plus anciens', 'Älteste zuerst', 'Más antiguos', 'Più vecchi', 'เก่าสุดก่อน', 'Najstarsze', 'Сначала старые', 'Спочатку старі'),
    _t('Search Episodes', '搜索节目', '搜尋節目', 'エピソードを検索', '에피소드 검색', 'Chercher des épisodes', 'Folgen durchsuchen', 'Buscar episodios', 'Cerca episodi', 'ค้นหาตอน', 'Szukaj odcinków', 'Поиск выпусков', 'Пошук випусків'),   # (the field of the Show page's search inside the show, patch/pcfind.c; machine translations, unreviewed)
    _t('Filter', '筛选', '篩選', 'フィルタ', '필터', 'Filtre', 'Filter', 'Filtro', 'Filtro', 'ตัวกรอง', 'Filtr', 'Фильтр', 'Фільтр'),   # (the Show page's sheet row; its values are All, Unplayed and Downloaded; machine translations, unreviewed)
    _t('Unplayed', '未播放', '未播放', '未再生', '재생 안 함', 'Non lus', 'Ungehört', 'No reproducidos', 'Non riprodotti', 'ยังไม่ได้เล่น', 'Nieodtworzone', 'Не прослушано', 'Не прослухано'),   # (the Filter's value; machine translations, unreviewed)
    _t('No unplayed episodes', '没有未播放的单集', '沒有未播放的單集', '未再生のエピソードはありません', '재생하지 않은 에피소드가 없습니다', 'Aucun épisode non lu', 'Keine ungehörten Folgen', 'Sin episodios sin reproducir', 'Nessun episodio non riprodotto', 'ไม่มีตอนที่ยังไม่ได้เล่น', 'Brak nieodtworzonych odcinków', 'Нет непрослушанных выпусков', 'Немає непрослуханих випусків'),   # (the Show page under the Filter Unplayed; machine translations, unreviewed)
    _t('Search All Episodes', '搜索所有节目', '搜尋所有節目', 'すべてのエピソードを検索', '모든 에피소드 검색', 'Chercher dans tous les épisodes', 'Alle Folgen durchsuchen', 'Buscar en todos los episodios', 'Cerca in tutti gli episodi', 'ค้นหาทุกตอน', 'Szukaj we wszystkich odcinkach', 'Поиск по всем выпускам', 'Пошук серед усіх випусків'),   # (the last row of the search inside a show with no archive yet, patch/pcfind.c; machine translations, unreviewed)
    _t('See All', '查看全部', '查看全部', 'すべてを表示', '모두 보기', 'Tout afficher', 'Alle ansehen', 'Ver todo', 'Mostra tutto', 'ดูทั้งหมด', 'Pokaż wszystko', 'Показать все', 'Показати все'),   # (the Show page's last row: opens the page with every episode, or for a subscription with no archive fetches the feed; Apple Podcasts' wording, machine translated, unreviewed)
    _t('See All (%d)', '查看全部 (%d)', '查看全部 (%d)', 'すべてを表示 (%d)', '모두 보기 (%d)', 'Tout afficher (%d)', 'Alle ansehen (%d)', 'Ver todo (%d)', 'Mostra tutto (%d)', 'ดูทั้งหมด (%d)', 'Pokaż wszystko (%d)', 'Показать все (%d)', 'Показати все (%d)'),   # (the same row once the show has an archive: the number of episodes; unreviewed)
    _t('Tap to Retry', '点按重试', '點一下重試', 'タップして再試行', '탭하여 다시 시도', 'Toucher pour réessayer', 'Tippen zum Wiederholen', 'Toca para reintentar', 'Tocca per riprovare', 'แตะเพื่อลองใหม่', 'Dotknij, aby ponowić', 'Нажмите, чтобы повторить', 'Натисніть, щоб повторити'),   # (the See All row after a failed job: "Can't connect \u00b7 Tap to Retry"; machine translations, unreviewed)
    _t('Refresh Feed', '刷新订阅源', '更新訂閱源', 'フィードを更新', '피드 새로고침', 'Actualiser', 'Aktualisieren', 'Actualizar', 'Aggiorna', 'รีเฟรชฟีด', 'Odśwież', 'Обновить', 'Оновити'),
    _t('Refresh All', '全部刷新', '全部更新', 'すべて更新', '모두 새로고침', 'Tout actualiser', 'Alle aktualisieren', 'Actualizar todo', 'Aggiorna tutto', 'รีเฟรชทั้งหมด', 'Odśwież wszystko', 'Обновить все', 'Оновити все'),
    _t('Select Episodes', '选择节目', '選擇節目', 'エピソードを選択', '에피소드 선택', 'Sélectionner des épisodes', 'Folgen auswählen', 'Seleccionar episodios', 'Seleziona episodi', 'เลือกตอน', 'Wybierz odcinki', 'Выбрать выпуски', 'Вибрати випуски'),
    _t('Mark All as Played', '全部标为已播放', '全部標為已播放', 'すべて再生済みにする', '모두 재생함으로 표시', 'Tout marquer comme lu', 'Alle als gehört markieren', 'Marcar todo como reproducido', 'Segna tutto come riprodotto',
       'ทำเครื่องหมายว่าเล่นแล้วทั้งหมด', 'Wszystkie jako odtworzone', 'Все как прослушанные', 'Усі як прослухані'),
    _t('Unsubscribe', '取消订阅', '取消訂閱', '登録解除', '구독 취소', 'Se désabonner', 'Abo beenden', 'Cancelar suscripción', 'Annulla iscrizione', 'เลิกติดตาม', 'Anuluj subskrypcję', 'Отписаться', 'Скасувати підписку'),
    _t('Unsubscribe from this show?', '取消订阅此节目？', '取消訂閱此節目？', 'この番組の登録を解除しますか？', '이 프로그램 구독을 취소할까요?', 'Se désabonner de ce podcast ?', 'Diesen Podcast nicht mehr abonnieren?',
       '¿Cancelar la suscripción a este podcast?', "Annullare l'iscrizione a questo podcast?", 'เลิกติดตามพอดแคสต์นี้หรือไม่?', 'Anulować subskrypcję tego podcastu?', 'Отписаться от этого подкаста?', 'Скасувати підписку на цей подкаст?'),
    _t('Download', '下载', '下載', 'ダウンロード', '다운로드', 'Télécharger', 'Laden', 'Descargar', 'Scarica', 'ดาวน์โหลด', 'Pobierz', 'Загрузить', 'Завантажити'),
    _t('Remove Download', '移除下载', '移除下載', 'ダウンロードを削除', '다운로드 제거', 'Supprimer le téléchargement', 'Download entfernen', 'Quitar descarga', 'Rimuovi download', 'ลบการดาวน์โหลด', 'Usuń pobrany plik', 'Удалить загрузку', 'Видалити завантаження'),
    # a Navidrome track's "..." sheet and the DSD confirm (patch/rowmenu.c, patch/sbsrc.c ls_dsd_confirm; docs/modules/subsonic.md "Row sheet"): the confirm's text is the title, a line break, then the body (%s the track, %s its size in MB)
    _t('Cancel Download', '取消下载', '取消下載', 'ダウンロードを中止', '다운로드 취소', 'Annuler le téléchargement', 'Download abbrechen', 'Cancelar descarga', 'Annulla download', 'ยกเลิกการดาวน์โหลด', 'Anuluj pobieranie', 'Отменить загрузку', 'Скасувати завантаження'),
    _t('Download to Play?', '下载后播放？', '下載後播放？', 'ダウンロードして再生？', '다운로드 후 재생할까요?', 'Télécharger pour lire ?', 'Zum Abspielen laden?', '¿Descargar para reproducir?', 'Scaricare per riprodurre?', 'ดาวน์โหลดเพื่อเล่นหรือไม่?', 'Pobrać, aby odtworzyć?', 'Загрузить и слушать?', 'Завантажити і слухати?'),
    _t('DSD tracks play from the card. %s, %s MB.', 'DSD 曲目需从存储卡播放。%s，%s MB。', 'DSD 曲目需從記憶卡播放。%s，%s MB。', 'DSD はカードで再生。%s、%s MB。', 'DSD 트랙은 카드에서 재생됩니다. %s, %s MB.', 'DSD : lecture depuis la carte. %s, %s Mo.', 'DSD wird von der Karte gespielt. %s, %s MB.',
       'DSD se reproduce desde la tarjeta. %s, %s MB.', 'Le tracce DSD si riproducono dalla scheda. %s, %s MB.', 'เพลง DSD เล่นจากการ์ด %s, %s MB', 'Utwory DSD odtwarzane są z karty. %s, %s MB.', 'DSD играет с карты. %s, %s МБ.', 'DSD грає з картки. %s, %s МБ.'),
    _t('Mark as Played', '标为已播放', '標為已播放', '再生済みにする', '재생함으로 표시', 'Marquer comme lu', 'Als gehört markieren', 'Marcar como reproducido', 'Segna come riprodotto', 'ทำเครื่องหมายว่าเล่นแล้ว', 'Oznacz jako odtworzone', 'Отметить как прослушанное', 'Позначити як прослухане'),
    _t('Mark as Unplayed', '标为未播放', '標為未播放', '未再生にする', '재생 안 함으로 표시', 'Marquer comme non lu', 'Als ungehört markieren', 'Marcar como no reproducido', 'Segna come non riprodotto', 'ทำเครื่องหมายว่ายังไม่เล่น', 'Oznacz jako nieodtworzone', 'Отметить как непрослушанное', 'Позначити як непрослухане'),
    _t('Retry', '重试', '重試', '再試行', '다시 시도', 'Réessayer', 'Erneut', 'Reintentar', 'Riprova', 'ลองใหม่', 'Ponów', 'Повторить', 'Повторити'),
    # the episode page (patch/pcdetail.c, docs/modules/podcasts.md "The episode page"): the hint of an episode with no description
    _t('No description', '没有简介', '沒有簡介', '説明はありません', '설명 없음', 'Aucune description', 'Keine Beschreibung', 'Sin descripción', 'Nessuna descrizione', 'ไม่มีคำอธิบาย', 'Brak opisu', 'Нет описания', 'Немає опису'),
    _t('%dm', '%d分钟', '%d分鐘', '%d分', '%d분', '%d min', '%d Min.', '%d min', '%d min', '%d นาที', '%d min', '%d мин', '%d хв'),   # the pill's length: short, no "left"
    _t('%dm left', '剩余%d分钟', '剩餘%d分鐘', '残り%d分', '%d분 남음', 'Reste %d min', 'Noch %d Min.', 'Quedan %d min', '%d min rimasti', 'เหลือ %d นาที', 'Zostało %d min', 'Ещё %d мин', 'Ще %d хв'),
    # Now Playing's info page labels (patch/nowplaying.c np_info): stock's "Genres" (the plural tab name) and "Era"
    # (a decade in several tables, "age" in Korean) become "Genre: ..." and "Year: ..."
    _t('Genre', '风格', '風格', 'ジャンル', '장르', 'Genre', 'Genre',
       'Género', 'Genere', 'ประเภท', 'Gatunek', 'Жанр', 'Жанр'),
    _t('Year', '年份', '年份', '年', '연도', 'Année', 'Jahr',
       'Año', 'Anno', 'ปี', 'Rok', 'Год', 'Рік'),
    # Now Playing's File Size / Location of a server stream when the server gave no size (np_stream_text)
    _t('Unknown', '未知', '未知', '不明', '알 수 없음', 'Inconnu', 'Unbekannt',
       'Desconocido', 'Sconosciuto', 'ไม่ทราบ', 'Nieznane', 'Неизвестно', 'Невідомо'),
    # the Albums "..." card (patch/viewsort.c, docs/modules/albums.md): the Title sort row, the View group (Grid, List) and the direction line under the ticked sort row
    _t('Title', '标题', '標題', 'タイトル', '제목', 'Titre', 'Titel',
       'Título', 'Titolo', 'ชื่อเรื่อง', 'Tytuł', 'Название', 'Назва'),
    # the Songs page's Sort card (the same shared card): File Name beside Title, Format and Recently Added
    _t('File Name', '文件名', '檔案名稱', 'ファイル名', '파일 이름', 'Nom du fichier', 'Dateiname',
       'Nombre de archivo', 'Nome file', 'ชื่อไฟล์', 'Nazwa pliku', 'Имя файла', 'Назва файлу'),
    # the Folders page's Sort card: Date Modified and Type beside Name
    _t('Date Modified', '修改日期', '修改日期', '更新日', '수정한 날짜', 'Date de modification', 'Änderungsdatum',
       'Fecha de modificación', 'Data di modifica', 'วันที่แก้ไข', 'Data modyfikacji', 'Дата изменения', 'Дата зміни'),
    _t('Type', '类型', '類型', '種類', '유형', 'Type', 'Typ',
       'Tipo', 'Tipo', 'ประเภท', 'Typ', 'Тип', 'Тип'),
    # the Playlists page's "..." card (the shared view-sort card): short row labels, so the longest languages fit the room after the glyph column
    _t('New Playlist', '新建歌单', '新增歌單', '新しいプレイリスト', '새 재생 목록', 'Nouvelle playlist', 'Neue Wiedergabeliste',
       'Nueva lista', 'Nuova playlist', 'เพลย์ลิสต์ใหม่', 'Nowa lista odtwarzania', 'Новый плейлист', 'Новий плейлист'),
    _t('Import', '导入', '匯入', 'インポート', '가져오기', 'Importer', 'Importieren',
       'Importar', 'Importa', 'นำเข้า', 'Importuj', 'Импорт', 'Імпорт'),
    _t('Export', '导出', '匯出', 'エクスポート', '내보내기', 'Exporter', 'Exportieren',
       'Exportar', 'Esporta', 'ส่งออก', 'Eksportuj', 'Экспорт', 'Експорт'),
    _t('Grid', '网格', '網格', 'グリッド', '격자', 'Grille', 'Raster',
       'Cuadrícula', 'Griglia', 'ตาราง', 'Siatka', 'Сетка', 'Сітка'),
    _t('List', '列表', '列表', 'リスト', '목록', 'Liste', 'Liste',
       'Lista', 'Elenco', 'รายการ', 'Lista', 'Список', 'Список'),
    _t('A–Z', 'A–Z', 'A–Z', 'A–Z', 'A–Z', 'A–Z', 'A–Z',
       'A–Z', 'A–Z', 'ก–ฮ', 'A–Z', 'А–Я', 'А–Я'),
    _t('Z–A', 'Z–A', 'Z–A', 'Z–A', 'Z–A', 'Z–A', 'Z–A',
       'Z–A', 'Z–A', 'ฮ–ก', 'Z–A', 'Я–А', 'Я–А'),
    _t('Newest First', '最新优先', '最新優先', '新しい順', '최신순', "Plus récent d'abord", 'Neueste zuerst',
       'Más recientes primero', 'Più recenti prima', 'ใหม่สุดก่อน', 'Najnowsze najpierw', 'Сначала новые', 'Спочатку нові'),
    _t('Oldest First', '最旧优先', '最舊優先', '古い順', '오래된 순', "Plus ancien d'abord", 'Älteste zuerst',
       'Más antiguos primero', 'Meno recenti prima', 'เก่าสุดก่อน', 'Najstarsze najpierw', 'Сначала старые', 'Спочатку старі'),
    # Screenshot (the Extras row; the toasts of patch/shot.c: the countdown is 5 s or 10 s, chosen on the confirm dialog's buttons)
    _t('Screenshot', '截图', '截圖', 'スクリーンショット', '스크린샷', "Capture d'écran", 'Screenshot',
       'Captura de pantalla', 'Screenshot', 'ภาพหน้าจอ', 'Zrzut ekranu', 'Скриншот', 'Знімок екрана'),
    _t('Take a screenshot?', '截图？', '截圖？', 'スクリーンショットを撮りますか？', '스크린샷을 찍을까요?',
       'Prendre une capture ?', 'Screenshot aufnehmen?', '¿Hacer una captura?', 'Fare uno screenshot?',
       'ถ่ายภาพหน้าจอไหม', 'Zrobić zrzut ekranu?', 'Сделать скриншот?', 'Зробити знімок?'),
    _t('Take a screenshot in:', '截图延时：', '截圖延遲：', 'スクリーンショットまで：', '스크린샷까지:',
       'Capture dans :', 'Screenshot in:', 'Captura en:', 'Screenshot tra:',
       'ถ่ายภาพหน้าจอใน:', 'Zrzut ekranu za:', 'Скриншот через:', 'Знімок через:'),
    # the two buttons of that dialog (patch/shot.c relabels the stock Yes / No)
    _t('5 s', '5 秒', '5 秒', '5秒', '5초', '5 s', '5 s', '5 s', '5 s', '5 วินาที', '5 s', '5 с', '5 с'),
    _t('10 s', '10 秒', '10 秒', '10秒', '10초', '10 s', '10 s', '10 s', '10 s', '10 วินาที', '10 s', '10 с', '10 с'),
    _t('Cancel the screenshot?', '取消截图？', '取消截圖？', 'スクリーンショットを取り消しますか？', '스크린샷을 취소할까요?',
       'Annuler la capture ?', 'Screenshot abbrechen?', '¿Cancelar la captura?', 'Annullare lo screenshot?',
       'ยกเลิกการถ่ายภาพหน้าจอไหม', 'Anulować zrzut ekranu?', 'Отменить скриншот?', 'Скасувати знімок?'),
    _t('Screenshot saved', '截图已保存', '截圖已儲存', 'スクリーンショットを保存', '스크린샷 저장됨', 'Capture enregistrée', 'Screenshot gespeichert',
       'Captura guardada', 'Screenshot salvato', 'บันทึกภาพหน้าจอแล้ว', 'Zrzut zapisany', 'Скриншот сохранён', 'Знімок збережено'),
    # Settings > Developer > Reset (the card holding Reset All Settings)
    _t('Reset', '重置', '重設', 'リセット', '초기화', 'Réinitialiser', 'Zurücksetzen',
       'Restablecer', 'Ripristina', 'รีเซ็ต', 'Resetuj', 'Сброс', 'Скидання'),
    _t('Screenshot failed','截图失败', '截圖失敗', 'スクリーンショット失敗', '스크린샷 실패', 'Échec de la capture', 'Screenshot fehlgeschlagen',
       'Error en la captura', 'Screenshot non riuscito', 'ถ่ายภาพหน้าจอไม่สำเร็จ', 'Zrzut nieudany', 'Не удалось снять экран', 'Не вдалося зробити знімок'),
    # Settings > Keyboards (iOS style: English always on, Chinese (Pinyin) a switch; patch/keyboard.c)
    _t('Keyboards', '键盘', '鍵盤', 'キーボード', '키보드', 'Claviers', 'Tastaturen',
       'Teclados', 'Tastiere', 'แป้นพิมพ์', 'Klawiatury', 'Клавиатуры', 'Клавіатури'),
    _t('English', '英语', '英語', '英語', '영어', 'Anglais', 'Englisch',
       'Inglés', 'Inglese', 'อังกฤษ', 'Angielski', 'Английский', 'Англійська'),
    _t('Chinese (Pinyin)', '中文拼音', '中文拼音', '中国語（ピンイン）', '중국어(병음)', 'Chinois (pinyin)', 'Chinesisch (Pinyin)',
       'Chino (pinyin)', 'Cinese (pinyin)', 'จีน (พินอิน)', 'Chiński (pinyin)', 'Пиньинь (кит.)', 'Китайська (піньїнь)'),
    # The on-screen keyboard (patch/keyboard.c; the Developer row, the page's title and the keys' labels)
    _t('Keyboard', '键盘', '鍵盤', 'キーボード', '키보드', 'Clavier', 'Tastatur',
       'Teclado', 'Tastiera', 'แป้นพิมพ์', 'Klawiatura', 'Клавиатура', 'Клавіатура'),
    _t('space', '空格', '空格', 'スペース', '스페이스', 'espace', 'Leertaste',
       'espacio', 'spazio', 'เว้นวรรค', 'spacja', 'пробел', 'пробіл'),
    _t('Search', '搜索', '搜尋', '検索', '검색', 'Chercher', 'Suchen',
       'Buscar', 'Cerca', 'ค้นหา', 'Szukaj', 'Поиск', 'Пошук'),
    _t('Apple Podcasts', *['Apple Podcasts'] * 12),
    _t('Discover', '发现', '探索', '見つける', '탐색', 'Découvrir', 'Entdecken',
       'Descubrir', 'Scopri', 'ค้นพบ', 'Odkrywaj', 'Обзор', 'Огляд'),   # the Podcasts page's row that opens the Discover charts, and the level's title
    _t('Search Apple Podcasts', '搜索 Apple Podcasts', '搜尋 Apple Podcasts', 'Apple Podcasts を検索', 'Apple Podcasts 검색', 'Chercher sur Apple Podcasts', 'Apple Podcasts durchsuchen',
       'Buscar en Apple Podcasts', 'Cerca su Apple Podcasts', 'ค้นหา Apple Podcasts', 'Szukaj w Apple Podcasts', 'Поиск в Apple Podcasts', 'Пошук в Apple Podcasts'),
    _t('Search Tidal', '搜索 Tidal', '搜尋 Tidal', 'Tidal を検索', 'Tidal 검색', 'Chercher sur Tidal', 'Tidal durchsuchen',
       'Buscar en Tidal', 'Cerca su Tidal', 'ค้นหา Tidal', 'Szukaj w Tidal', 'Поиск в Tidal', 'Пошук у Tidal'),   # the Tidal > Search bar's placeholder (patch/tidalkb.c; fits TK_TEXT_W, test/pod/tidalkb.py asset_tests)
    _t('Done', '完成', '完成', '完了', '완료', 'OK', 'Fertig',
       'Hecho', 'Fine', 'เสร็จ', 'Gotowe', 'Готово', 'Готово'),
    # Now Playing's More menu (patch/playmore.c): the row that opens the second page (and that page's back header), the short
    # Playback speed label (stock: "Multiple Speed", wider than the room before the four speed badges) and the 14 px note under it
    _t('More', '更多', '更多', 'その他', '더 보기', 'Plus', 'Mehr',
       'Más', 'Altro', 'เพิ่มเติม', 'Więcej', 'Ещё', 'Ще'),
    _t('Speed', '倍速', '倍速', '再生速度', '재생 속도', 'Vitesse', 'Tempo',
       'Velocidad', 'Velocità', 'ความเร็ว', 'Prędkość', 'Скорость', 'Швидкість'),
    # Now Playing's More sheet: the row that opens the landscape cassette page (patch/tape.c, docs/modules/tape.md); the page's own name is the same text
    _t('Cassette Mode', '磁带模式', '錄音帶模式', 'カセットモード', '카세트 모드', 'Mode cassette', 'Kassettenmodus',
       'Modo casete', 'Modalità cassetta', 'โหมดเทป', 'Tryb kasety', 'Режим кассеты', 'Режим касети'),
    # Now Playing's More sheet: the row that opens the turntable page (patch/vinyl.c, docs/modules/vinyl.md); the page's own name is the same text
    _t('Vinyl Mode', '黑胶模式', '黑膠模式', 'レコードモード', '바이닐 모드', 'Mode vinyle', 'Vinylmodus',
       'Modo vinilo', 'Modalità vinile', 'โหมดแผ่นเสียง', 'Tryb winylu', 'Режим винила', 'Режим вінілу'),
    # Now Playing's More sheet while an episode plays: the row that opens the Podcasts page (patch/podcasts.c podcasts_go)
    _t('Go to Podcasts', '前往播客', '前往 Podcast', 'ポッドキャストへ移動', '팟캐스트로 이동', 'Aller aux podcasts', 'Zu Podcasts',
       'Ir a pódcasts', 'Vai ai podcast', 'ไปที่พอดแคสต์', 'Przejdź do podcastów', 'К подкастам', 'До подкастів'),
    # Now Playing's More sheet (page 2): the row that opens Find Cover & Lyrics (patch/onlineart.c, docs/modules/onlineart.md); the page's own title is the same text
    _t('Cover & Lyrics', '封面和歌词', '封面和歌詞', 'ジャケットと歌詞', '커버 및 가사', 'Pochette et paroles', 'Cover & Songtext',
       'Portada y letra', 'Copertina e testo', 'ปกและเนื้อเพลง', 'Okładka i tekst', 'Обложка и текст', 'Обкладинка і текст'),
    _t('Covers', '封面', '封面', 'ジャケット', '커버', 'Pochettes', 'Cover', 'Portadas', 'Copertine', 'ปก', 'Okładki', 'Обложки', 'Обкладинки'),
    _t('Lyrics', '歌词', '歌詞', '歌詞', '가사', 'Paroles', 'Songtext', 'Letra', 'Testo', 'เนื้อเพลง', 'Tekst', 'Текст', 'Текст'),
    _t('Saving…', '正在保存…', '正在儲存…', '保存中…', '저장 중…', 'Enregistrement…', 'Wird gespeichert…', 'Guardando…', 'Salvataggio…', 'กำลังบันทึก…', 'Zapisywanie…', 'Сохранение…', 'Збереження…'),
    _t('Synced', '同步', '同步', '同期', '동기화', 'Synchro', 'Synchron', 'Sincr.', 'Sincr.', 'ซิงค์', 'Synchr.', 'Синхр.', 'Синхр.'),
    _t('Use This Cover', '使用此封面', '使用此封面', 'このジャケットを使用', '이 커버 사용', 'Utiliser cette pochette', 'Dieses Cover verwenden', 'Usar esta portada', 'Usa questa copertina', 'ใช้ปกนี้',
       'Użyj tej okładki', 'Выбрать обложку', 'Вибрати обкладинку'),
    _t('Replace Cover', '替换封面', '取代封面', 'ジャケットを置き換え', '커버 바꾸기', 'Remplacer la pochette', 'Cover ersetzen', 'Reemplazar portada', 'Sostituisci copertina', 'แทนที่ปก',
       'Zastąp okładkę', 'Заменить обложку', 'Замінити обкладинку'),
    # Software Update (patch/update.c, docs/modules/update.md): the Settings row and the page's title, the states' titles and explanations, the pills. %s is the version (put in by the payload, never a printf format).
    _t('Software Update', '软件更新', '軟體更新', 'ソフトウェア更新', '소프트웨어 업데이트', 'Mise à jour', 'Software-Update', 'Actualización', 'Aggiornamenti', 'อัปเดตซอฟต์แวร์',
       'Aktualizacja', 'Обновление ПО', 'Оновлення ПЗ'),
    _t('Check for Update', '检查更新', '檢查更新', 'アップデートを確認', '업데이트 확인', 'Rechercher', 'Nach Update suchen', 'Buscar actualización', 'Controlla aggiornamenti', 'ตรวจสอบอัปเดต',
       'Sprawdź aktualizację', 'Проверить обновление', 'Перевірити оновлення'),
    _t('Release Notes', '发行说明', '版本說明', 'リリースノート', '릴리스 노트', 'Notes de version', 'Versionshinweise', 'Notas de la versión', 'Note di rilascio', 'บันทึกประจำรุ่น', 'Informacje o wersji',
       'Список изменений', 'Список змін'),
    _t('Checking…', '正在检查…', '正在檢查…', '確認中…', '확인하는 중…', 'Vérification…', 'Prüfe …', 'Comprobando…', 'Controllo…', 'กำลังตรวจสอบ…', 'Sprawdzanie…', 'Проверка…', 'Перевірка…'),
    _t('Up to Date', '已是最新', '已是最新', '最新です', '최신 버전', 'À jour', 'Aktuell', 'Actualizado', 'Aggiornato', 'ล่าสุดแล้ว', 'Aktualne', 'Актуально', 'Оновлено'),
    _t('You have the latest version.', '你使用的已是最新版本。', '你使用的已是最新版本。', '最新バージョンをお使いです。', '최신 버전을 사용 중입니다.', 'Vous avez la dernière version.',
       'Sie haben die neueste Version.', 'Tienes la última versión.', 'Hai l\'ultima versione.', 'คุณใช้เวอร์ชันล่าสุดอยู่แล้ว', 'Masz najnowszą wersję.', 'У вас последняя версия.', 'У вас остання версія.'),
    _t('Version %s', '版本 %s', '版本 %s', 'バージョン %s', '버전 %s', 'Version %s', 'Version %s', 'Versión %s', 'Versione %s', 'เวอร์ชัน %s', 'Wersja %s', 'Версия %s', 'Версія %s'),
    _t('Version %s available', '版本 %s 可用', '版本 %s 可用', 'バージョン %s を利用可能', '버전 %s 사용 가능', 'Version %s disponible', 'Version %s verfügbar', 'Versión %s disponible',
       'Versione %s disponibile', 'มีเวอร์ชัน %s', 'Dostępna wersja %s', 'Доступна версия %s', 'Доступна версія %s'),
    _t('Current version: %s', '当前版本：%s', '目前版本：%s', '現在のバージョン：%s', '현재 버전: %s', 'Version actuelle : %s', 'Installiert: %s', 'Versión actual: %s', 'Versione attuale: %s',
       'เวอร์ชันปัจจุบัน: %s', 'Obecna wersja: %s', 'Текущая версия: %s', 'Поточна версія: %s'),
    _t('This may take a few minutes.', '这可能需要几分钟。', '這可能需要幾分鐘。', '数分かかることがあります。', '몇 분 걸릴 수 있습니다.', 'Quelques minutes environ.',
       'Das kann einige Minuten dauern.', 'Puede tardar unos minutos.', 'Può richiedere qualche minuto.', 'อาจใช้เวลาสักครู่', 'To może potrwać kilka minut.', 'Это займёт пару минут.',
       'Це займе кілька хвилин.'),
    _t('Update Downloaded', '更新已下载', '更新已下載', 'ダウンロード完了', '다운로드 완료', 'Mise à jour prête', 'Update geladen', 'Actualización lista', 'Aggiornamento scaricato', 'ดาวน์โหลดอัปเดตแล้ว',
       'Aktualizacja pobrana', 'Обновление загружено', 'Оновлення завантажено'),
    _t('Version %s is ready to install.', '版本 %s 可以安装。', '版本 %s 可以安裝。', 'バージョン %s をインストールできます。', '버전 %s을(를) 설치할 수 있습니다.', 'La version %s est prête à installer.',
       'Version %s ist installationsbereit.', 'La versión %s está lista para instalar.', 'La versione %s è pronta da installare.', 'เวอร์ชัน %s พร้อมติดตั้ง', 'Wersja %s jest gotowa do instalacji.',
       'Версия %s готова к установке.', 'Версія %s готова до встановлення.'),
    _t('Install', '安装', '安裝', 'インストール', '설치', 'Installer', 'Installieren', 'Instalar', 'Installa', 'ติดตั้ง', 'Zainstaluj', 'Установить', 'Встановити'),
    _t('Connect to Wi-Fi first', '请先连接 Wi-Fi', '請先連接 Wi-Fi', '先に Wi-Fi へ接続', '먼저 Wi-Fi에 연결', 'Connectez le Wi-Fi', 'Erst mit WLAN verbinden', 'Conéctate al Wi-Fi', 'Connettiti al Wi-Fi',
       'เชื่อมต่อ Wi-Fi ก่อน', 'Połącz z Wi-Fi', 'Подключите Wi-Fi', 'Підключіть Wi-Fi'),
    _t('Turn on Wi-Fi and try again.', '打开 Wi-Fi 后重试。', '開啟 Wi-Fi 後重試。', 'Wi-Fi をオンにして再試行してください。', 'Wi-Fi를 켜고 다시 시도하세요.', 'Activez le Wi-Fi et réessayez.',
       'WLAN einschalten und erneut versuchen.', 'Activa el Wi-Fi e inténtalo de nuevo.', 'Attiva il Wi-Fi e riprova.', 'เปิด Wi-Fi แล้วลองอีกครั้ง', 'Włącz Wi-Fi i spróbuj ponownie.',
       'Включите Wi-Fi и повторите.', 'Увімкніть Wi-Fi і повторіть.'),
    _t("Can't reach GitHub", '无法连接 GitHub', '無法連線 GitHub', 'GitHub に接続できません', 'GitHub에 연결할 수 없음', 'GitHub injoignable', 'GitHub nicht erreichbar', 'No se llega a GitHub',
       'GitHub non raggiungibile', 'เชื่อมต่อ GitHub ไม่ได้', 'Brak połączenia z GitHub', 'GitHub недоступен', 'GitHub недоступний'),
    _t("Can't check for updates", '无法检查更新', '無法檢查更新', '更新を確認できません', '업데이트를 확인할 수 없음', 'Vérification impossible', 'Prüfung nicht möglich', 'No se pudo comprobar',
       'Controllo non riuscito', 'ตรวจสอบอัปเดตไม่ได้', 'Nie można sprawdzić', 'Не удалось проверить', 'Не вдалося перевірити'),
    _t('GitHub did not name a release. Try again later.', 'GitHub 没有给出发布版本，请稍后再试。', 'GitHub 沒有提供發行版本，請稍後再試。', 'リリースを確認できません。後で再試行してください。',
       'GitHub에서 릴리스를 확인하지 못했습니다. 나중에 다시 시도하세요.', 'GitHub n\'a indiqué aucune version. Réessayez plus tard.', 'GitHub hat keine Version genannt. Später erneut versuchen.',
       'GitHub no indicó ninguna versión. Inténtalo más tarde.', 'GitHub non ha indicato una versione. Riprova più tardi.', 'GitHub ไม่ระบุรุ่น ลองใหม่ภายหลัง',
       'GitHub nie podał wersji. Spróbuj później.', 'GitHub не назвал версию. Повторите позже.', 'GitHub не назвав версію. Повторіть пізніше.'),
    _t('Card is full', '存储卡已满', '記憶卡已滿', 'カードがいっぱい', '카드가 가득 참', 'Carte pleine', 'Karte voll', 'Tarjeta llena', 'Scheda piena', 'การ์ดเต็ม', 'Karta jest pełna', 'Карта заполнена', 'Картка заповнена'),
    _t('Free at least 110 MB on the card.', '请在存储卡上腾出至少 110 MB。', '請在記憶卡上騰出至少 110 MB。', 'カードに 110 MB 以上の空きが必要です。', '카드에 110MB 이상의 여유 공간이 필요합니다.',
       'Libérez au moins 110 Mo sur la carte.', 'Mindestens 110 MB auf der Karte freigeben.', 'Libera al menos 110 MB en la tarjeta.', 'Libera almeno 110 MB sulla scheda.', 'ต้องมีที่ว่างในการ์ดอย่างน้อย 110 MB',
       'Zwolnij co najmniej 110 MB na karcie.', 'Освободите на карте не менее 110 МБ.', 'Звільніть на картці щонайменше 110 МБ.'),
    _t("Can't write to the card", '无法写入存储卡', '無法寫入記憶卡', 'カードに書き込めません', '카드에 쓸 수 없음', 'Écriture impossible', 'Schreiben nicht möglich', 'No se puede escribir', 'Scrittura non riuscita',
       'เขียนลงการ์ดไม่ได้', 'Nie można zapisać', 'Ошибка записи на карту', 'Помилка запису на картку'),
    _t('Check the TF card and try again.', '请检查存储卡后重试。', '請檢查記憶卡後重試。', 'TF カードを確認して再試行してください。', 'TF 카드를 확인하고 다시 시도하세요.', 'Vérifiez la carte TF et réessayez.',
       'TF-Karte prüfen und erneut versuchen.', 'Revisa la tarjeta TF e inténtalo de nuevo.', 'Controlla la scheda TF e riprova.', 'ตรวจสอบการ์ด TF แล้วลองอีกครั้ง', 'Sprawdź kartę TF i spróbuj ponownie.',
       'Проверьте карту TF и повторите.', 'Перевірте картку TF і повторіть.'),
    _t('Download cancelled', '下载已取消', '下載已取消', 'ダウンロードを中止', '다운로드 취소됨', 'Téléchargement annulé', 'Download abgebrochen', 'Descarga cancelada', 'Download annullato', 'ยกเลิกการดาวน์โหลดแล้ว',
       'Pobieranie anulowane', 'Загрузка отменена', 'Завантаження скасовано'),
    _t("Download doesn't match", '下载内容不符', '下載內容不符', 'ダウンロードが一致しません', '다운로드가 일치하지 않음', 'Fichier différent', 'Datei stimmt nicht', 'Archivo distinto', 'File diverso', 'ไฟล์ไม่ตรงกัน',
       'Niezgodny plik', 'Файл не совпадает', 'Файл не збігається'),
    _t('The file was not the version offered. Nothing was changed.', '文件不是所提供的版本，未做任何更改。', '檔案不是所提供的版本，未做任何變更。', 'ファイルが提示されたバージョンと異なります。何も変更されていません。',
       '파일이 제공된 버전과 다릅니다. 변경된 내용은 없습니다.', 'Le fichier n\'est pas la version proposée. Rien n\'a été modifié.', 'Die Datei ist nicht die angebotene Version. Nichts wurde geändert.',
       'El archivo no es la versión ofrecida. No se cambió nada.', 'Il file non è la versione offerta. Nulla è stato modificato.', 'ไฟล์ไม่ใช่เวอร์ชันที่เสนอ ไม่มีการเปลี่ยนแปลงใด ๆ',
       'Plik nie jest oferowaną wersją. Nic nie zmieniono.', 'Файл не является предложенной версией. Ничего не изменено.', 'Файл не є запропонованою версією. Нічого не змінено.'),
    # Software Update's download: the pill that asks, the confirm dialog (its buttons are Cancel and Download), the popup's title, and Check Again after a download
    _t('Download and Install', '下载并安装', '下載並安裝', 'ダウンロードして更新', '다운로드 및 설치', 'Télécharger et installer', 'Laden und installieren', 'Descargar e instalar', 'Scarica e installa',
       'ดาวน์โหลดและติดตั้ง', 'Pobierz i zainstaluj', 'Скачать и установить', 'Скачати й встановити'),
    _t('Check Again', '再次检查', '再次檢查', '再確認', '다시 확인', 'Revérifier', 'Erneut prüfen', 'Comprobar de nuevo', 'Ricontrolla', 'ตรวจสอบอีกครั้ง', 'Sprawdź ponownie', 'Проверить снова', 'Перевірити знову'),
    _t('Downloading %s', '正在下载 %s', '正在下載 %s', '%s を取得中', '%s 다운로드 중', 'Téléchargement %s', '%s wird geladen', 'Descargando %s', 'Download di %s', 'กำลังดาวน์โหลด %s',
       'Pobieranie %s', 'Загрузка %s', 'Завантаження %s'),
    _t('Download %s (55 MB)? It replaces update.bin on the card.', '下载 %s（55 MB）？这将替换存储卡上的 update.bin。', '下載 %s（55 MB）？這會取代記憶卡上的 update.bin。',
       '%s（55 MB）を取得しますか？update.bin を置換します。', '%s(55MB)을(를) 다운로드할까요? 카드의 update.bin을 대체합니다.',
       'Télécharger %s (55 Mo) ? Remplace update.bin sur la carte.', '%s laden (55 MB)? Ersetzt update.bin auf der Karte.', '¿Bajar %s (55 MB)? Reemplaza update.bin en la tarjeta.',
       'Scaricare %s (55 MB)? Sostituisce update.bin sulla scheda.', 'ดาวน์โหลด %s (55 MB) หรือไม่ จะแทนที่ update.bin บนการ์ด', 'Pobrać %s (55 MB)? Zastąpi plik update.bin na karcie.',
       'Скачать %s (55 МБ)? Заменит update.bin на карте.', 'Скачати %s (55 МБ)? Замінить update.bin на картці.'),
    # Find Cover & Lyrics' empty and failed states: a title, one or two lines under it, and the Try Again pill (docs/modules/onlineart.md). The failure titles are the Podcasts' words (No Wi-Fi ... Not enough memory).
    _t('No Lyrics Found', '未找到歌词', '未找到歌詞', '歌詞が見つかりません', '가사를 찾을 수 없음', 'Aucune parole trouvée', 'Kein Songtext gefunden', 'No se encontró la letra', 'Nessun testo trovato',
       'ไม่พบเนื้อเพลง', 'Nie znaleziono tekstu', 'Текст не найден', 'Текст не знайдено'),
    _t('No Covers Found', '未找到封面', '未找到封面', 'ジャケットが見つかりません', '커버를 찾을 수 없음', 'Aucune pochette trouvée', 'Keine Cover gefunden', 'No se encontraron portadas', 'Nessuna copertina trovata',
       'ไม่พบปก', 'Nie znaleziono okładek', 'Обложки не найдены', 'Обкладинки не знайдено'),
    _t('Lyrics Service Busy', '歌词服务繁忙', '歌詞服務繁忙', '歌詞サービスが混雑中', '가사 서비스 혼잡', 'Service de paroles occupé', 'Songtext-Dienst ausgelastet', 'Servicio de letras ocupado',
       'Servizio testi occupato', 'บริการเนื้อเพลงไม่ว่าง', 'Usługa tekstów zajęta', 'Сервис текстов занят', 'Сервіс текстів зайнятий'),
    _t('Cover Service Busy', '封面服务繁忙', '封面服務繁忙', 'ジャケットサービスが混雑中', '커버 서비스 혼잡', 'Service de pochettes occupé', 'Cover-Dienst ausgelastet', 'Servicio de portadas ocupado',
       'Servizio copertine occupato', 'บริการปกไม่ว่าง', 'Usługa okładek zajęta', 'Сервис обложек занят', 'Сервіс обкладинок зайнятий'),
    _t('LRCLIB is under heavy load. Try again in a moment.', 'LRCLIB 负载过高，请稍后再试。', 'LRCLIB 負載過高，請稍後再試。', 'LRCLIB は混み合っています。しばらくしてからお試しください。',
       'LRCLIB 부하가 높습니다. 잠시 후 다시 시도하세요.', 'LRCLIB est très sollicité. Réessayez dans un instant.', 'LRCLIB ist stark ausgelastet. Gleich noch einmal versuchen.',
       'LRCLIB tiene mucha carga. Inténtalo en un momento.', 'LRCLIB è sovraccarico. Riprova tra un momento.', 'LRCLIB มีผู้ใช้หนาแน่น ลองใหม่อีกสักครู่',
       'LRCLIB jest mocno obciążony. Spróbuj za chwilę.', 'LRCLIB перегружен. Повторите чуть позже.', 'LRCLIB перевантажений. Спробуйте за мить.'),
    _t('iTunes and Deezer are busy. Try again in a moment.', 'iTunes 和 Deezer 繁忙，请稍后再试。', 'iTunes 和 Deezer 繁忙，請稍後再試。', 'iTunes と Deezer が混み合っています。しばらくしてからお試しください。',
       'iTunes와 Deezer가 혼잡합니다. 잠시 후 다시 시도하세요.', 'iTunes et Deezer sont occupés. Réessayez dans un instant.', 'iTunes und Deezer sind ausgelastet. Gleich noch einmal versuchen.',
       'iTunes y Deezer están ocupados. Inténtalo en un momento.', 'iTunes e Deezer sono occupati. Riprova tra un momento.', 'iTunes และ Deezer ไม่ว่าง ลองใหม่อีกสักครู่',
       'iTunes i Deezer są zajęte. Spróbuj za chwilę.', 'iTunes и Deezer заняты. Повторите чуть позже.', 'iTunes і Deezer зайняті. Спробуйте за мить.'),
    _t('Turn on Wi-Fi to search online.', '打开 Wi-Fi 以在线搜索。', '開啟 Wi-Fi 以線上搜尋。', 'オンライン検索には Wi-Fi をオンにしてください。', 'Wi-Fi를 켜면 온라인으로 검색할 수 있습니다.',
       'Activez le Wi-Fi pour chercher en ligne.', 'WLAN einschalten, um online zu suchen.', 'Activa el Wi-Fi para buscar en línea.', 'Attiva il Wi-Fi per cercare online.', 'เปิด Wi-Fi เพื่อค้นหาออนไลน์',
       'Włącz Wi-Fi, aby szukać online.', 'Включите Wi-Fi для поиска.', 'Увімкніть Wi-Fi для пошуку.'),
    _t('Secure connections need the right date.', '安全连接需要正确的日期。', '安全連線需要正確的日期。', '安全な接続には正しい日付が必要です。', '보안 연결에는 올바른 날짜가 필요합니다.',
       'Une connexion sécurisée exige la bonne date.', 'Sichere Verbindungen brauchen das richtige Datum.', 'Las conexiones seguras necesitan la fecha correcta.', 'Le connessioni sicure richiedono la data corretta.',
       'การเชื่อมต่อที่ปลอดภัยต้องตั้งวันที่ให้ถูกต้อง', 'Bezpieczne połączenia wymagają poprawnej daty.', 'Для защищённого соединения нужна верная дата.', 'Для захищеного з’єднання потрібна правильна дата.'),
    _t('This device has no certificate bundle.', '此设备没有证书包。', '此裝置沒有憑證包。', 'この機器には証明書バンドルがありません。', '이 기기에 인증서 번들이 없습니다.',
       "Cet appareil n'a pas de lot de certificats.", 'Auf diesem Gerät fehlt das Zertifikatspaket.', 'Este dispositivo no tiene paquete de certificados.', 'Questo dispositivo non ha certificati.',
       'อุปกรณ์นี้ไม่มีชุดใบรับรอง', 'To urządzenie nie ma pakietu certyfikatów.', 'На устройстве нет набора сертификатов.', 'На пристрої немає набору сертифікатів.'),
    _t("The server's certificate was not accepted.", '服务器证书未被接受。', '伺服器憑證未被接受。', 'サーバーの証明書が受け入れられませんでした。', '서버 인증서가 거부되었습니다.',
       "Le certificat du serveur a été refusé.", 'Das Serverzertifikat wurde nicht akzeptiert.', 'No se aceptó el certificado del servidor.', 'Il certificato del server è stato rifiutato.',
       'ไม่ยอมรับใบรับรองของเซิร์ฟเวอร์', 'Certyfikat serwera nie został zaakceptowany.', 'Сертификат сервера не принят.', 'Сертифікат сервера не прийнято.'),
    _t('The server could not answer. Try again later.', '服务器无法响应，请稍后再试。', '伺服器無法回應，請稍後再試。', 'サーバーが応答できません。後でお試しください。', '서버가 응답하지 못했습니다. 나중에 다시 시도하세요.',
       "Le serveur n'a pas répondu. Réessayez plus tard.", 'Der Server antwortet nicht. Später erneut versuchen.', 'El servidor no respondió. Inténtalo más tarde.', 'Il server non ha risposto. Riprova più tardi.',
       'เซิร์ฟเวอร์ไม่ตอบสนอง ลองใหม่ภายหลัง', 'Serwer nie odpowiedział. Spróbuj później.', 'Сервер не ответил. Повторите позже.', 'Сервер не відповів. Спробуйте пізніше.'),
    _t('The SD card could not be used.', '无法使用 SD 卡。', '無法使用 SD 卡。', 'SD カードを使用できません。', 'SD 카드를 사용할 수 없습니다.', 'La carte SD est inutilisable.', 'Die SD-Karte ist nicht nutzbar.',
       'No se pudo usar la tarjeta SD.', 'Impossibile usare la scheda SD.', 'ไม่สามารถใช้การ์ด SD ได้', 'Nie można użyć karty SD.', 'Не удалось использовать SD-карту.', 'Не вдалося використати SD-карту.'),
    _t('There is not enough memory to search.', '内存不足，无法搜索。', '記憶體不足，無法搜尋。', 'メモリ不足のため検索できません。', '메모리가 부족해 검색할 수 없습니다.', 'Pas assez de mémoire pour chercher.',
       'Zu wenig Speicher für die Suche.', 'No hay memoria suficiente para buscar.', 'Memoria insufficiente per cercare.', 'หน่วยความจำไม่พอสำหรับค้นหา', 'Za mało pamięci, aby szukać.',
       'Недостаточно памяти для поиска.', 'Недостатньо пам’яті для пошуку.'),
    _t('Check your Wi-Fi connection.', '请检查 Wi-Fi 连接。', '請檢查 Wi-Fi 連線。', 'Wi-Fi 接続を確認してください。', 'Wi-Fi 연결을 확인하세요.', 'Vérifiez votre connexion Wi-Fi.', 'WLAN-Verbindung prüfen.',
       'Revisa tu conexión Wi-Fi.', 'Controlla la connessione Wi-Fi.', 'ตรวจสอบการเชื่อมต่อ Wi-Fi', 'Sprawdź połączenie Wi-Fi.', 'Проверьте подключение к Wi-Fi.', 'Перевірте підключення до Wi-Fi.'),
    _t('Nothing on iTunes or Deezer for this album.', 'iTunes 和 Deezer 上没有这张专辑。', 'iTunes 和 Deezer 上沒有這張專輯。', 'iTunes と Deezer にこのアルバムはありません。', 'iTunes와 Deezer에 이 앨범이 없습니다.',
       "Rien sur iTunes ni Deezer pour cet album.", 'Nichts bei iTunes oder Deezer zu diesem Album.', 'Nada en iTunes ni Deezer para este álbum.', 'Niente su iTunes o Deezer per questo album.',
       'ไม่พบอัลบั้มนี้บน iTunes หรือ Deezer', 'Brak tego albumu w iTunes i Deezer.', 'В iTunes и Deezer нет этого альбома.', 'В iTunes і Deezer немає цього альбому.'),
    _t('LRCLIB has no lyrics for this song.', 'LRCLIB 没有这首歌的歌词。', 'LRCLIB 沒有這首歌的歌詞。', 'LRCLIB にこの曲の歌詞はありません。', 'LRCLIB에 이 곡의 가사가 없습니다.',
       "LRCLIB n'a pas les paroles de ce titre.", 'LRCLIB hat keinen Songtext zu diesem Titel.', 'LRCLIB no tiene la letra de esta canción.', 'LRCLIB non ha il testo di questo brano.',
       'LRCLIB ไม่มีเนื้อเพลงของเพลงนี้', 'LRCLIB nie ma tekstu tego utworu.', 'В LRCLIB нет текста этой песни.', 'В LRCLIB немає тексту цієї пісні.'),
    _t('Try Again', '再试一次', '再試一次', 'もう一度試す', '다시 시도', 'Réessayer', 'Wiederholen', 'Reintentar', 'Riprova', 'ลองอีกครั้ง', 'Ponów próbę', 'Повторить', 'Повторити'),
    _t('Save Lyrics', '保存歌词', '儲存歌詞', '歌詞を保存', '가사 저장', 'Enregistrer les paroles', 'Songtext speichern', 'Guardar letra', 'Salva testo', 'บันทึกเนื้อเพลง', 'Zapisz tekst',
       'Сохранить текст', 'Зберегти текст'),
    _t('Replace Lyrics', '替换歌词', '取代歌詞', '歌詞を置き換え', '가사 바꾸기', 'Remplacer les paroles', 'Songtext ersetzen', 'Reemplazar letra', 'Sostituisci testo', 'แทนที่เนื้อเพลง', 'Zastąp tekst',
       'Заменить текст', 'Замінити текст'),
    # Settings > Now Playing > Theme: the picker's title and its three values
    _t('Cassette Theme', '磁带主题', '錄音帶主題', 'カセットテーマ', '카세트 테마', 'Thème cassette', 'Kassettendesign',
       'Tema del casete', 'Tema cassetta', 'ธีมเทป', 'Motyw kasety', 'Тема кассеты', 'Тема касети'),
    _t('Normal', '标准', '標準', '標準', '기본', 'Normal', 'Normal',
       'Normal', 'Normale', 'ปกติ', 'Normalny', 'Обычная', 'Звичайна'),
    _t('Chrome', '铬色', '鉻色', 'クローム', '크롬', 'Chrome', 'Chrom',
       'Cromo', 'Cromo', 'โครเมียม', 'Chrom', 'Хром', 'Хром'),
    _t('Metal', '金属', '金屬', 'メタル', '메탈', 'Métal', 'Metall',
       'Metal', 'Metallo', 'โลหะ', 'Metal', 'Металл', 'Метал'),
    # Settings > Now Playing > Record: Vinyl Mode's record colour, the picker's title and its values
    _t('Record', '唱片', '唱片', 'レコード', '레코드', 'Disque', 'Schallplatte',
       'Disco', 'Disco', 'แผ่นเสียง', 'Płyta', 'Пластинка', 'Платівка'),
    _t('Black', '黑色', '黑色', 'ブラック', '블랙', 'Noir', 'Schwarz',
       'Negro', 'Nero', 'ดำ', 'Czarny', 'Чёрный', 'Чорний'),
    _t('Cover', '封面', '封面', 'ジャケット', '커버', 'Pochette', 'Cover',
       'Portada', 'Copertina', 'ปก', 'Okładka', 'Обложка', 'Обкладинка'),
    _t('Base', '底座', '底座', 'ベース', '베이스', 'Socle', 'Sockel',
       'Soporte', 'Supporto', 'ฐาน', 'Podstawa', 'Основание', 'Основа'),
    _t('Graphite', '石墨', '石墨', 'グラファイト', '그래파이트', 'Graphite', 'Graphit',
       'Grafito', 'Grafite', 'กราไฟต์', 'Grafit', 'Графит', 'Графіт'),
    _t('Snow', '雪白', '雪白', 'スノー', '스노우', 'Neige', 'Schnee',
       'Nieve', 'Neve', 'หิมะ', 'Śnieg', 'Снег', 'Сніг'),
    _t('Applies the next time Vinyl Mode opens.', '下次打开黑胶模式时生效。', '下次開啟黑膠模式時生效。', '次回レコードモード起動時に反映', '다음에 바이닐 모드를 열 때 적용됩니다.', "S'applique à la prochaine ouverture.", 'Gilt beim nächsten Öffnen.',
       'Se aplica la próxima vez que se abre.', 'Si applica alla prossima apertura.', 'มีผลเมื่อเปิดครั้งถัดไป', 'Zastosowane przy następnym otwarciu.', 'Применится при следующем открытии.', 'Застосується при наступному відкритті.'),
    # Settings > System > Appearance > Background (patch/palette.c, docs/modules/accent.md): the row and its picker's title, and the Tinted value (Black is the key above)
    _t('Background', '背景', '背景', '背景', '배경', 'Arrière-plan', 'Hintergrund',
       'Fondo', 'Sfondo', 'พื้นหลัง', 'Tło', 'Фон', 'Тло'),
    _t('Tinted', '着色', '著色', 'ティント', '색조', 'Teinté', 'Getönt',
       'Teñido', 'Colorato', 'ปรับสี', 'Zabarwione', 'Тонированный', 'Тонований'),
    # Settings > System > Appearance > Lock Screen (patch/lockscreen.c, docs/modules/lockscreen.md): the row and its picker's title, the two layouts and the note
    _t('Lock Screen', '锁屏', '鎖定畫面', 'ロック画面', '잠금 화면', 'Écran de verrouillage', 'Sperrbildschirm',
       'Pantalla de bloqueo', 'Schermata di blocco', 'หน้าจอล็อก', 'Ekran blokady', 'Экран блокировки', 'Екран блокування'),
    _t('Enable', '启用', '啟用', '有効', '사용', 'Activer', 'Aktivieren',
       'Activar', 'Attiva', 'เปิดใช้งาน', 'Włącz', 'Включить', 'Увімкнути'),
    # (short in the languages whose full words do not fit beside the value of the row: the Lock Screen page's value row shows Large Cover / Mini Player at the right)
    _t('Player Style', '播放器样式', '播放器樣式', 'スタイル', '스타일', 'Style', 'Player-Stil',
       'Estilo', 'Stile', 'สไตล์เพลเยอร์', 'Styl', 'Стиль', 'Стиль'),
    _t('Large Cover', '大封面', '大封面', '大きなジャケット', '큰 커버', 'Grande pochette', 'Großes Cover',
       'Portada grande', 'Copertina grande', 'ปกใหญ่', 'Duża okładka', 'Крупная обложка', 'Велика обкладинка'),
    _t('Mini Player', '小播放栏', '小播放列', 'ミニプレーヤー', '미니 플레이어', 'Mini-lecteur', 'Mini-Player',
       'Minirreproductor', 'Mini player', 'มินิเพลเยอร์', 'Mini odtwarzacz', 'Мини-плеер', 'Міні-плеєр'),
    _t('Applies the next time the lock screen opens.', '下次打开锁屏时生效。', '下次開啟鎖定畫面時生效。', '次回ロック画面を開いたときに反映', '다음에 잠금 화면을 열 때 적용됩니다.', "S'applique à la prochaine ouverture.", 'Gilt beim nächsten Öffnen.',
       'Se aplica la próxima vez que se abre.', 'Si applica alla prossima apertura.', 'มีผลเมื่อเปิดครั้งถัดไป', 'Zastosowane przy następnym otwarciu.', 'Применится при следующем открытии.', 'Застосується при наступному відкритті.'),
    # Settings > Lock Screen > Wallpaper (patch/lockscreen.c lkwp_*, docs/modules/lockscreen.md "Wallpaper picker"): the row and its page's title (stock has no word for it)
    _t('Wallpaper', '壁纸', '桌布', '壁紙', '배경화면', "Fond d'écran", 'Hintergrundbild',
       'Fondo de pantalla', 'Carta da parati', 'วอลเปเปอร์', 'Tapeta', 'Обои', 'Шпалери'),
    # Settings > Lock Screen > Show Time: stock's clock switch with our own short label (stock's "Lockscreen Time Display" does not fit; the page already says Lock Screen)
    _t('Show Time', '显示时间', '顯示時間', '時刻を表示', '시간 표시', "Afficher l'heure", 'Uhrzeit anzeigen',
       'Mostrar hora', 'Mostra ora', 'แสดงเวลา', 'Pokaż godzinę', 'Показ времени', 'Показ часу'),
    # Settings > Lock Screen > Custom Wallpaper: the row and the title of our instructions page (how to add your own pictures); our own label (stock's "Custom lock screen" does not fit in 7 languages)
    _t('Custom Wallpaper', '自定义壁纸', '自訂桌布', 'カスタム壁紙', '맞춤 배경화면', 'Fond personnalisé', 'Eigener Hintergrund',
       'Fondo personalizado', 'Sfondi personali', 'วอลเปเปอร์ของคุณ', 'Własna tapeta', 'Свои обои', 'Власні шпалери'),
    # the page's three paragraphs (our wording of stock's screenlock_info1..3: the folder, the format, the count; the limits are stock's list builder's, docs/modules/lockscreen.md "List")
    _t('Copy pictures to a folder named lockscreenimage at the top level of the card.', '将图片复制到存储卡根目录下名为 lockscreenimage 的文件夹中。', '將圖片複製到記憶卡根目錄下名為 lockscreenimage 的資料夾中。',
       'カード直下の lockscreenimage フォルダに画像をコピーしてください。', '카드 최상위의 lockscreenimage 폴더에 사진을 복사하세요.',
       'Copiez les images dans un dossier nommé lockscreenimage, à la racine de la carte.', 'Bilder in einen Ordner namens lockscreenimage im Hauptverzeichnis der Karte kopieren.',
       'Copia las imágenes a una carpeta llamada lockscreenimage en la raíz de la tarjeta.', 'Copia le immagini in una cartella chiamata lockscreenimage nella radice della scheda.',
       'คัดลอกรูปภาพไปยังโฟลเดอร์ชื่อ lockscreenimage ที่ระดับบนสุดของการ์ด', 'Skopiuj obrazy do folderu lockscreenimage w katalogu głównym karty.',
       'Скопируйте изображения в папку lockscreenimage в корне карты.', 'Скопіюйте зображення до папки lockscreenimage у корені картки.'),
    _t('JPG or PNG, exactly 320 x 480 pixels, under 1 MB each.', 'JPG 或 PNG 格式，分辨率须为 320 x 480，每张小于 1 MB。', 'JPG 或 PNG 格式，解析度須為 320 x 480，每張小於 1 MB。',
       'JPG または PNG、320 x 480 ピクセルちょうど、1 枚 1 MB 未満。', 'JPG 또는 PNG, 정확히 320 x 480 픽셀, 장당 1MB 미만.',
       'JPG ou PNG, exactement 320 x 480 pixels, moins de 1 Mo chacune.', 'JPG oder PNG, genau 320 x 480 Pixel, je unter 1 MB.',
       'JPG o PNG, exactamente 320 x 480 píxeles, menos de 1 MB cada una.', 'JPG o PNG, esattamente 320 x 480 pixel, meno di 1 MB ciascuna.',
       'JPG หรือ PNG ขนาด 320 x 480 พิกเซลพอดี แต่ละรูปน้อยกว่า 1 MB', 'JPG lub PNG, dokładnie 320 x 480 pikseli, każdy poniżej 1 MB.',
       'JPG или PNG, ровно 320 x 480 пикселей, каждое меньше 1 МБ.', 'JPG або PNG, рівно 320 x 480 пікселів, кожне менше 1 МБ.'),
    _t('Up to 5 pictures. Choose one in Wallpaper.', '最多 5 张图片，可在“壁纸”中选择。', '最多 5 張圖片，可在「桌布」中選擇。',
       '画像は 5 枚まで。「壁紙」で選択してください。', '사진은 최대 5장입니다. 배경화면에서 선택하세요.',
       "Jusqu'à 5 images. Choisissez-en une dans Fond d'écran.", 'Bis zu 5 Bilder. Eines unter Hintergrundbild auswählen.',
       'Hasta 5 imágenes. Elige una en Fondo de pantalla.', 'Fino a 5 immagini. Scegline una in Carta da parati.',
       'สูงสุด 5 รูป เลือกได้ในวอลเปเปอร์', 'Do 5 obrazów. Wybierz jeden w ustawieniu Tapeta.',
       'До 5 изображений. Выберите одно в разделе «Обои».', 'До 5 зображень. Виберіть одне в розділі «Шпалери».'),
    # the heading above them (the Release Notes page's "Version x.y.z" style, 22 px in 288 px: the Russian and Ukrainian are the short "photos" wording to fit)
    _t('Add Your Own Pictures', '添加自己的图片', '加入自己的圖片', '自分の画像を追加', '내 사진 추가', 'Ajouter vos images', 'Eigene Bilder hinzufügen', 'Añadir tus imágenes',
       'Aggiungi le tue immagini', 'เพิ่มรูปภาพของคุณ', 'Dodaj własne obrazy', 'Добавьте свои фото', 'Додайте власні фото'),
    # Settings > System > Accent (patch/palette.c, docs/modules/accent.md): the row and its picker's title, then the seven accents (the picker's rows and the row's value)
    _t('Accent', '强调色', '強調色', 'アクセント', '강조 색상', 'Couleur', 'Akzentfarbe',
       'Color de énfasis', 'Accento', 'สีเน้น', 'Akcent', 'Акцент', 'Акцент'),
    _t('Neutral', '中性', '中性', 'ニュートラル', '중립', 'Neutre', 'Neutral',
       'Neutro', 'Neutro', 'เป็นกลาง', 'Neutralny', 'Нейтральный', 'Нейтральний'),
    _t('Red', '红色', '紅色', 'レッド', '레드', 'Rouge', 'Rot',
       'Rojo', 'Rosso', 'แดง', 'Czerwony', 'Красный', 'Червоний'),
    _t('Orange', '橙色', '橙色', 'オレンジ', '오렌지', 'Orange', 'Orange',
       'Naranja', 'Arancione', 'ส้ม', 'Pomarańczowy', 'Оранжевый', 'Помаранчевий'),
    _t('Green', '绿色', '綠色', 'グリーン', '그린', 'Vert', 'Grün',
       'Verde', 'Verde', 'เขียว', 'Zielony', 'Зелёный', 'Зелений'),
    _t('Teal', '青绿色', '青綠色', 'ティール', '틸', 'Sarcelle', 'Türkis',
       'Turquesa', 'Turchese', 'เขียวอมฟ้า', 'Morski', 'Бирюзовый', 'Бірюзовий'),
    _t('Purple', '紫色', '紫色', 'パープル', '퍼플', 'Violet', 'Violett',
       'Morado', 'Viola', 'ม่วง', 'Fioletowy', 'Фиолетовый', 'Фіолетовий'),
    _t('Champagne', '香槟色', '香檳色', 'シャンパン', '샴페인', 'Champagne', 'Champagner',
       'Champán', 'Champagne', 'แชมเปญ', 'Szampański', 'Шампань', 'Шампань'),
    # The Songs page (patch/songs.c): the select mode's navbar ("N Selected", the Select All text button) and its
    # Delete pill. The count goes where %d is (the payload puts the number there). Add to playlist is the stock key (STOCK). The Play pill's text, "Play", is below (the album, playlist and Daily Mix pages, and the Songs, Folders and artist pages' flat pills).
    _t('Select All', '全选', '全選', 'すべて選択', '모두 선택', 'Tout choisir', 'Alle wählen',
       'Todo', 'Tutti', 'เลือกทั้งหมด', 'Wszystko', 'Выбрать все', 'Вибрати все'),
    _t('Add to Playlist', '加入歌单', '加入歌單', 'リストに追加', '목록에 추가', 'Ajouter', 'Hinzufügen',
       'Añadir', 'Aggiungi', 'เพิ่ม', 'Dodaj', 'Добавить', 'Додати'),   # (the stock key's texts are longer than the select bar's 145 px pill holds beside its glyph: German 30 characters, Japanese 144 px)
    _t('Delete', '删除', '刪除', '削除', '삭제', 'Supprimer', 'Löschen',
       'Eliminar', 'Elimina', 'ลบ', 'Usuń', 'Удалить', 'Видалити'),
    _t('%d Selected', '已选 %d 项', '已選 %d 項', '%d 件選択', '%d개 선택', '%d choisis', '%d gewählt',
       '%d elegidas', '%d scelti', 'เลือก %d', 'Wybrano: %d', 'Выбрано: %d', 'Вибрано: %d'),
    _t('Files below 48 kHz only', '仅对 48kHz 以下有效', '僅對 48kHz 以下有效', '48kHz未満のみ', '48kHz 미만 파일만', 'Fichiers < 48 kHz seulement', 'Nur Dateien unter 48 kHz',
       'Solo archivos bajo 48 kHz', 'Solo file sotto 48 kHz', 'เฉพาะไฟล์ต่ำกว่า 48 kHz', 'Tylko pliki poniżej 48 kHz', 'Только файлы ниже 48 кГц', 'Лише файли нижче 48 кГц'),
    # The Daily Mix card of the Home menu (patch/dailymix.c, docs/modules/dailymix.md): the section header (the Recently Played shelf's style), the card title AND the
    # Settings > Home Screen switch row ("Daily Mix": the card breaks it at its first space into two lines, a word with no space is one line on the bottom one),
    # the action row, the card's artists line ("%s and more": a printf template of one %s) and the join of two names ("%s, %s": applied name by name). Not literal in every language
    # (fr "Mix du jour", de "Tagesmix", it "Mix del giorno", ru "Микс дня"); they want a native-speaker pass.
    _t('Made for You', '为你推荐', '為你推薦', 'あなたへのおすすめ', '맞춤 추천', 'Pour vous', 'Für dich',
       'Para ti', 'Per te', 'สำหรับคุณ', 'Dla Ciebie', 'Для вас', 'Для вас'),
    _t('Daily Mix', '每日精选', '每日精選', 'デイリー ミックス', '데일리 믹스', 'Mix du jour', 'Tagesmix',
       'Mix diario', 'Mix del giorno', 'มิกซ์ประจำวัน', 'Miks dnia', 'Микс дня', 'Мікс дня'),
    _t('Regenerate Daily Mix', '重新生成每日精选', '重新產生每日精選', 'デイリー ミックス再生成', '데일리 믹스 다시 만들기', 'Régénérer le Mix du jour', 'Tagesmix neu erstellen',
       'Regenerar Mix diario', 'Rigenera Mix del giorno', 'สร้างมิกซ์ประจำวันใหม่', 'Odśwież Miks dnia', 'Обновить Микс дня', 'Оновити Мікс дня'),
    _t('%s and more', '%s等', '%s等', '%s など', '%s 등', '%s et plus', '%s und mehr',
       '%s y más', '%s e altri', '%s และอื่นๆ', '%s i inni', '%s и другие', '%s та інші'),
    _t('%s, %s', *('%s、%s', '%s、%s', '%s、%s') + ('%s, %s',) * 9),
    # The Daily Mix page (patch/dailymix.c dp_*, docs/modules/dailymix.md "The page"): the Updated line under the subtitle (today, yesterday, else "Updated <ISO date>": the date is
    # YYYY-MM-DD in every language, so no month names), the white pill's text, and the description under the buttons (two lines of 288 px at 15 px in every language).
    # A native-speaker pass is wanted.
    _t('Updated today', '今天更新', '今天更新', '今日更新', '오늘 업데이트됨', 'Mis à jour aujourd\'hui', 'Heute aktualisiert',
       'Actualizado hoy', 'Aggiornato oggi', 'อัปเดตวันนี้', 'Zaktualizowano dzisiaj', 'Обновлено сегодня', 'Оновлено сьогодні'),
    _t('Updated yesterday', '昨天更新', '昨天更新', '昨日更新', '어제 업데이트됨', 'Mis à jour hier', 'Gestern aktualisiert',
       'Actualizado ayer', 'Aggiornato ieri', 'อัปเดตเมื่อวาน', 'Zaktualizowano wczoraj', 'Обновлено вчера', 'Оновлено вчора'),
    _t('Updated %s', '%s 更新', '%s 更新', '%s に更新', '%s 업데이트됨', 'Mis à jour le %s', 'Aktualisiert am %s',
       'Actualizado el %s', 'Aggiornato il %s', 'อัปเดต %s', 'Zaktualizowano %s', 'Обновлено %s', 'Оновлено %s'),
    _t('Play', '播放', '播放', '再生', '재생', 'Lecture', 'Wiedergabe',
       'Reproducir', 'Riproduci', 'เล่น', 'Odtwórz', 'Играть', 'Грати'),
    _t('Songs you love and some to rediscover, made fresh every day.', '你喜爱的歌曲，加上一些值得重新发现的好歌，每天为你更新。',
       '你喜愛的歌曲，加上一些值得重新發現的好歌，每天為你更新。', 'お気に入りの曲と、もう一度聴きたい曲を、毎日お届けします。',
       '좋아하는 노래와 다시 들어볼 노래를 매일 새롭게 만들어 드려요.', 'Les titres que vous aimez et des pépites à redécouvrir, renouvelés chaque jour.',
       'Songs, die du liebst, und einige zum Wiederentdecken – jeden Tag neu.', 'Canciones que te encantan y otras para redescubrir, renovadas cada día.',
       'Brani che ami e altri da riscoprire, rinnovati ogni giorno.', 'เพลงที่คุณรักและเพลงให้ค้นพบใหม่ สร้างสรรค์ใหม่ทุกวัน',
       'Utwory, które kochasz, i kilka do odkrycia na nowo, odświeżane codziennie.', 'Песни, которые вы любите, и несколько для нового открытия: каждый день заново.',
       'Пісні, які ви любите, і кілька для нового відкриття: щодня наново.'),
    # The section headers of the Extras page and Settings > Extras (pod_pages.EXTRAS_GROUPS): Play is the key above. The stock tables have no key for these
    # (their "Library" is part of longer texts). Library follows the terms of the stock tables (曲库, Datenbank, librería ...). A native-speaker pass is wanted.
    _t('Library', '曲库', '曲庫', 'ライブラリ', '라이브러리', 'Bibliothèque', 'Datenbank',
       'Librería', 'Libreria', 'คลังเพลง', 'Biblioteka', 'Библиотека', 'Медіатека'),
    _t('Collections', '合集', '合集', 'コレクション', '컬렉션', 'Collections', 'Sammlungen',
       'Colecciones', 'Raccolte', 'คอลเลกชัน', 'Kolekcje', 'Коллекции', 'Колекції'),
    _t('Streaming', '流媒体', '串流', 'ストリーミング', '스트리밍', 'Streaming', 'Streaming',
       'Streaming', 'Streaming', 'สตรีมมิง', 'Streaming', 'Стриминг', 'Стримінг'),
    _t('Tools', '工具', '工具', 'ツール', '도구', 'Outils', 'Werkzeuge',
       'Herramientas', 'Strumenti', 'เครื่องมือ', 'Narzędzia', 'Инструменты', 'Інструменти'),
    # Radio (patch/radiopage.c, patch/radionp.c; docs/modules/radio.md). A native-speaker pass is wanted.
    _t('Radio', '电台', '電台', 'ラジオ', '라디오', 'Radio', 'Radio',
       'Radio', 'Radio', 'วิทยุ', 'Radio', 'Радио', 'Радіо'),
    _t('Top Stations', '热门电台', '熱門電台', '人気の局', '인기 방송국', 'Stations populaires', 'Top-Sender',
       'Emisoras populares', 'Stazioni più ascoltate', 'สถานียอดนิยม', 'Najpopularniejsze stacje', 'Популярные станции', 'Популярні станції'),
    _t('By Country', '按国家', '按國家', '国別', '국가별', 'Par pays', 'Nach Land',
       'Por país', 'Per paese', 'ตามประเทศ', 'Według kraju', 'По странам', 'За країнами'),
    _t('By Genre', '按流派', '按流派', 'ジャンル別', '장르별', 'Par genre', 'Nach Genre',
       'Por género', 'Per genere', 'ตามแนวเพลง', 'Według gatunku', 'По жанрам', 'За жанрами'),
    _t('Countries', '国家和地区', '國家和地區', '国', '국가', 'Pays', 'Länder',
       'Países', 'Paesi', 'ประเทศ', 'Kraje', 'Страны', 'Країни'),
    _t('Search Albums', '搜索专辑', '搜尋專輯', 'アルバムを検索', '앨범 검색', 'Rechercher un album', 'Alben durchsuchen',
       'Buscar álbumes', 'Cerca album', 'ค้นหาอัลบั้ม', 'Szukaj albumów', 'Поиск альбомов', 'Пошук альбомів'),
    _t('Search Songs', '搜索歌曲', '搜尋歌曲', '曲を検索', '노래 검색', 'Rechercher un titre', 'Titel suchen',
       'Buscar canciones', 'Cerca brani', 'ค้นหาเพลง', 'Szukaj utworów', 'Поиск песен', 'Пошук пісень'),
    _t('Search Artists', '搜索歌手', '搜尋歌手', 'アーティストを検索', '아티스트 검색', 'Rechercher un artiste', 'Künstler durchsuchen',
       'Buscar artistas', 'Cerca artisti', 'ค้นหาศิลปิน', 'Szukaj wykonawców', 'Поиск исполнителей', 'Пошук виконавців'),
    _t('Name', '名称', '名稱', '名前', '이름', 'Nom', 'Name',
       'Nombre', 'Nome', 'ชื่อ', 'Nazwa', 'Имя', 'Назва'),
    _t('Search Stations', '搜索电台', '搜尋電台', '局を検索', '방송국 검색', 'Rechercher une station', 'Sender suchen',
       'Buscar emisoras', 'Cerca stazioni', 'ค้นหาสถานี', 'Szukaj stacji', 'Поиск станций', 'Пошук станцій'),
    _t('Radio Browser', '电台浏览', '電台瀏覽', 'ラジオブラウザ', '라디오 브라우저', 'Navigateur radio', 'Radiobrowser',
       'Explorar radio', 'Sfoglia radio', 'เบราว์เซอร์วิทยุ', 'Przeglądarka radia', 'Обзор радио', 'Огляд радіо'),
    _t('My Stations', '我的电台', '我的電台', 'マイ局', '내 방송국', 'Mes stations', 'Meine Sender',
       'Mis emisoras', 'Le mie stazioni', 'สถานีของฉัน', 'Moje stacje', 'Мои станции', 'Мої станції'),
    _t('Add to My Stations', '添加到我的电台', '加入我的電台', 'マイ局に追加', '내 방송국에 추가', 'Ajouter à Mes stations', 'Zu Meine Sender hinzufügen',
       'Añadir a Mis emisoras', 'Aggiungi a Le mie stazioni', 'เพิ่มในสถานีของฉัน', 'Dodaj do Moich stacji', 'Добавить в Мои станции', 'Додати до Моїх станцій'),
    _t('Remove from My Stations', '从我的电台中移除', '從我的電台移除', 'マイ局から削除', '내 방송국에서 제거', 'Retirer de Mes stations', 'Aus Meine Sender entfernen',
       'Quitar de Mis emisoras', 'Rimuovi da Le mie stazioni', 'ลบออกจากสถานีของฉัน', 'Usuń z Moich stacji', 'Удалить из Моих станций', 'Видалити з Моїх станцій'),
    _t('Added to My Stations', '已添加到我的电台', '已加入我的電台', 'マイ局に追加しました', '내 방송국에 추가됨', 'Ajouté à Mes stations', 'Zu Meine Sender hinzugefügt',
       'Añadido a Mis emisoras', 'Aggiunto a Le mie stazioni', 'เพิ่มในสถานีของฉันแล้ว', 'Dodano do Moich stacji', 'Добавлено в Мои станции', 'Додано до Моїх станцій'),
    _t('Removed from My Stations', '已从我的电台中移除', '已從我的電台移除', 'マイ局から削除しました', '내 방송국에서 제거됨', 'Retiré de Mes stations', 'Aus Meine Sender entfernt',
       'Quitado de Mis emisoras', 'Rimosso da Le mie stazioni', 'ลบออกจากสถานีของฉันแล้ว', 'Usunięto z Moich stacji', 'Удалено из Моих станций', 'Видалено з Моїх станцій'),
    _t('Could not save My Stations', '无法保存我的电台', '無法儲存我的電台', 'マイ局を保存できません', '내 방송국을 저장할 수 없음', "Impossible d'enregistrer Mes stations", 'Meine Sender nicht gespeichert',
       'No se guardaron Mis emisoras', 'Le mie stazioni non salvate', 'บันทึกสถานีของฉันไม่ได้', 'Nie zapisano Moich stacji', 'Не удалось сохранить Мои станции', 'Не вдалося зберегти Мої станції'),
    # (a plural-form-free label in pl, ru, uk: "Added: %d" as the track count's)
    _t('Added %d station', '已添加 %d 个电台', '已加入 %d 個電台', '%d 局を追加しました', '방송국 %d개 추가됨', '%d station ajoutée', '%d Sender hinzugefügt',
       '%d emisora añadida', '%d stazione aggiunta', 'เพิ่ม %d สถานีแล้ว', 'Dodano stacji: %d', 'Добавлено станций: %d', 'Додано станцій: %d'),
    _t('Added %d stations', '已添加 %d 个电台', '已加入 %d 個電台', '%d 局を追加しました', '방송국 %d개 추가됨', '%d stations ajoutées', '%d Sender hinzugefügt',
       '%d emisoras añadidas', '%d stazioni aggiunte', 'เพิ่ม %d สถานีแล้ว', 'Dodano stacji: %d', 'Добавлено станций: %d', 'Додано станцій: %d'),
    _t('No new stations', '没有新电台', '沒有新電台', '新しい局はありません', '새 방송국 없음', 'Aucune nouvelle station', 'Keine neuen Sender',
       'No hay emisoras nuevas', 'Nessuna nuova stazione', 'ไม่มีสถานีใหม่', 'Brak nowych stacji', 'Новых станций нет', 'Нових станцій немає'),
    _t('No playlists in the Radio folder', 'Radio 文件夹中没有播放列表', 'Radio 資料夾中沒有播放清單', 'Radio フォルダにプレイリストがありません', 'Radio 폴더에 재생목록 없음', 'Aucune liste de lecture dans le dossier Radio', 'Keine Playlists im Ordner Radio',
       'No hay listas en la carpeta Radio', 'Nessuna playlist nella cartella Radio', 'ไม่มีเพลย์ลิสต์ในโฟลเดอร์ Radio', 'Brak list odtwarzania w folderze Radio', 'В папке Radio нет плейлистов', 'У теці Radio немає плейлистів'),
    _t('My Stations is full', '我的电台已满', '我的電台已滿', 'マイ局がいっぱいです', '내 방송국이 가득 참', 'Mes stations sont pleines', 'Meine Sender ist voll',
       'Mis emisoras está llena', 'Le mie stazioni è pieno', 'สถานีของฉันเต็มแล้ว', 'Lista Moich stacji jest pełna', 'Список Моих станций заполнен', 'Список Моїх станцій заповнено'),
    _t('Add stations from Radio Browser or import .m3u files from the card.',
       '从电台浏览添加电台，或从存储卡导入 .m3u 文件。', '從電台瀏覽加入電台，或從記憶卡匯入 .m3u 檔案。',
       'ラジオブラウザから局を追加、またはカードから .m3u を読み込めます。',
       '라디오 브라우저에서 추가하거나 카드의 .m3u를 가져오세요.',
       'Ajoutez des stations via Navigateur radio ou importez des .m3u depuis la carte.',
       'Füge Sender im Radiobrowser hinzu oder importiere .m3u von der Karte.',
       'Añade emisoras desde Explorar radio o importa .m3u de la tarjeta.',
       'Aggiungi stazioni da Sfoglia radio o importa .m3u dalla scheda.',
       'เพิ่มสถานีจากเบราว์เซอร์วิทยุ หรือนำเข้าไฟล์ .m3u จากการ์ด',
       'Dodaj stacje z Przeglądarki radia lub zaimportuj .m3u z karty.',
       'Добавьте станции из Обзора радио или импортируйте .m3u с карты.',
       'Додайте станції з Огляду радіо або імпортуйте .m3u з картки.'),
    _t('No recently played stations', '没有最近播放的电台', '沒有最近播放的電台', '最近再生した局はありません', '최근 재생한 방송국 없음', 'Aucune station lue récemment', 'Keine zuletzt gespielten Sender',
       'No hay emisoras reproducidas recientemente', 'Nessuna stazione riprodotta di recente', 'ไม่มีสถานีที่เล่นล่าสุด', 'Brak ostatnio odtwarzanych stacji', 'Нет недавно воспроизведённых станций', 'Немає нещодавно відтворених станцій'),
    # Recently Played's "..." sheet (patch/radiopage.c) and Radio Now Playing's Station Info page (patch/radioinfo.c, patch/radionp.c; docs/modules/radio.md)
    _t('Clear Recently Played', '清除最近播放', '清除最近播放', '最近再生した局を消去', '최근 재생 지우기', 'Effacer les lus récemment', 'Zuletzt gespielte löschen',
       'Borrar recientes', 'Cancella riprodotte di recente', 'ล้างรายการที่เล่นล่าสุด', 'Wyczyść ostatnio odtwarzane', 'Очистить недавние', 'Очистити нещодавно відтворені'),
    _t('Cleared Recently Played', '已清除最近播放', '已清除最近播放', '最近再生した局を消去しました', '최근 재생을 지웠습니다', 'Lus récemment effacés', 'Zuletzt gespielte gelöscht',
       'Reproducidas recientemente borradas', 'Riprodotte di recente cancellate', 'ล้างรายการที่เล่นล่าสุดแล้ว', 'Wyczyszczono ostatnio odtwarzane', 'Недавно воспроизведённые очищены', 'Нещодавно відтворені очищено'),
    _t('Could not clear Recently Played', '无法清除最近播放', '無法清除最近播放', '最近再生した局を消去できません', '최근 재생을 지울 수 없음', 'Impossible d’effacer les lus récemment', 'Zuletzt gespielte nicht gelöscht',
       'No se pudo borrar lo reproducido recientemente', 'Impossibile cancellare le riprodotte di recente', 'ล้างรายการที่เล่นล่าสุดไม่ได้', 'Nie można wyczyścić ostatnio odtwarzanych', 'Не удалось очистить недавно воспроизведённые', 'Не вдалося очистити нещодавно відтворені'),
    _t('No radio is playing', '没有正在播放的电台', '沒有正在播放的電台', 'ラジオを再生していません', '재생 중인 라디오 없음', 'Aucune radio en cours de lecture', 'Kein Radio läuft',
       'No hay radio en reproducción', 'Nessuna radio in riproduzione', 'ไม่มีวิทยุที่กำลังเล่น', 'Radio nie jest odtwarzane', 'Радио не воспроизводится', 'Радіо не відтворюється'),
    _t('Station Info', '电台信息', '電台資訊', '局の情報', '방송국 정보', 'Infos sur la station', 'Senderinfo',
       'Info de la emisora', 'Info stazione', 'ข้อมูลสถานี', 'Informacje o stacji', 'О станции', 'Про станцію'),
    _t('Stream URL', '流媒体地址', '串流網址', 'ストリームURL', '스트림 URL', 'URL du flux', 'Stream-URL',
       'URL del flujo', 'URL dello stream', 'URL สตรีม', 'Adres strumienia', 'Адрес потока', 'Адреса потоку'),
    _t('Logo URL', '徽标地址', '標誌網址', 'ロゴURL', '로고 URL', 'URL du logo', 'Logo-URL',
       'URL del logotipo', 'URL del logo', 'URL โลโก้', 'Adres logo', 'Адрес логотипа', 'Адреса логотипу'),
    _t('Country', '国家/地区', '國家/地區', '国', '국가', 'Pays', 'Land',
       'País', 'Paese', 'ประเทศ', 'Kraj', 'Страна', 'Країна'),
    _t('Codec', '编码', '編碼', 'コーデック', '코덱', 'Codec', 'Codec',
       'Códec', 'Codec', 'โคเดก', 'Kodek', 'Кодек', 'Кодек'),
    _t('Bitrate', '比特率', '位元率', 'ビットレート', '비트 전송률', 'Débit', 'Bitrate',
       'Tasa de bits', 'Bitrate', 'บิตเรต', 'Przepływność', 'Битрейт', 'Бітрейт'),
    _t('Source', '来源', '來源', 'ソース', '출처', 'Source', 'Quelle',
       'Origen', 'Origine', 'แหล่งที่มา', 'Źródło', 'Источник', 'Джерело'),
    _t('Imported', '已导入', '已匯入', '読み込み済み', '가져옴', 'Importée', 'Importiert',
       'Importada', 'Importata', 'นำเข้าแล้ว', 'Zaimportowana', 'Импортирована', 'Імпортована'),
    _t('Playing', '正在播放', '正在播放', '再生中', '재생 중', 'Lecture en cours', 'Wiedergabe',
       'Reproduciendo', 'In riproduzione', 'กำลังเล่น', 'Odtwarzanie', 'Воспроизводится', 'Відтворюється'),
    _t('No stations', '没有电台', '沒有電台', '局がありません', '방송국 없음', 'Aucune station', 'Keine Sender',
       'No hay emisoras', 'Nessuna stazione', 'ไม่มีสถานี', 'Brak stacji', 'Станций нет', 'Станцій немає'),
    _t('Directory unavailable. Tap to try again.', '目录不可用。点按重试。', '目錄無法使用。點一下重試。', 'ディレクトリを利用できません。タップして再試行。', '디렉터리를 사용할 수 없습니다. 탭하여 다시 시도.', 'Annuaire indisponible. Touchez pour réessayer.', 'Verzeichnis nicht verfügbar. Tippen zum Wiederholen.',
       'Directorio no disponible. Toca para reintentar.', 'Elenco non disponibile. Tocca per riprovare.', 'ไม่สามารถใช้ไดเรกทอรีได้ แตะเพื่อลองอีกครั้ง', 'Katalog niedostępny. Dotknij, aby spróbować ponownie.', 'Каталог недоступен. Нажмите, чтобы повторить.', 'Каталог недоступний. Торкніться, щоб повторити.'),
    _t('Connecting…', '正在连接…', '正在連線…', '接続中…', '연결 중…', 'Connexion…', 'Verbindung wird hergestellt…',
       'Conectando…', 'Connessione…', 'กำลังเชื่อมต่อ…', 'Łączenie…', 'Подключение…', 'Підключення…'),
    _t("Can't play", '无法播放', '無法播放', '再生できません', '재생할 수 없음', 'Lecture impossible', 'Wiedergabe nicht möglich',
       'No se puede reproducir', 'Impossibile riprodurre', 'เล่นไม่ได้', 'Nie można odtworzyć', 'Не удаётся воспроизвести', 'Не вдається відтворити'),
    _t('Stopped', '已停止', '已停止', '停止中', '정지됨', 'Arrêté', 'Gestoppt',
       'Detenido', 'Fermato', 'หยุดแล้ว', 'Zatrzymano', 'Остановлено', 'Зупинено'),
    _t('LIVE', '直播', '直播', 'ライブ', '라이브', 'EN DIRECT', 'LIVE',
       'EN VIVO', 'LIVE', 'สด', 'NA ŻYWO', 'ЭФИР', 'ЕФІР'),
    _t('Live', '直播', '直播', 'ライブ', '라이브', 'En direct', 'Live',
       'En vivo', 'Live', 'สด', 'Na żywo', 'Эфир', 'Ефір'),
    _t('Stations from radio-browser.info', '电台来自 radio-browser.info', '電台來自 radio-browser.info', '局情報の提供元: radio-browser.info', '방송국 제공: radio-browser.info', 'Stations de radio-browser.info', 'Sender von radio-browser.info',
       'Emisoras de radio-browser.info', 'Stazioni da radio-browser.info', 'สถานีจาก radio-browser.info', 'Stacje z radio-browser.info', 'Станции с radio-browser.info', 'Станції з radio-browser.info'),
    _t('%d stations', '%d 个电台', '%d 個電台', '%d 局', '방송국 %d개', '%d stations', '%d Sender',
       '%d emisoras', '%d stazioni', '%d สถานี', 'Stacje: %d', 'Станций: %d', 'Станцій: %d'),
    # The Equalizer page (patch/peq_ui.c, docs/modules/peq.md): its title and switch row, the row of stock's own ten-band curve, the hint when the card has no
    # presets, the message box of a file the parser refuses and of a failed save.
    _t('Equalizer', '均衡器', '等化器', 'イコライザー', '이퀄라이저', 'Égaliseur', 'Equalizer',
       'Ecualizador', 'Equalizzatore', 'อีควอไลเซอร์', 'Korektor', 'Эквалайзер', 'Еквалайзер'),
    _t('10-Band EQ', '10 段均衡器', '10 段等化器', '10バンドEQ', '10밴드 EQ', 'EQ 10 bandes', '10-Band-EQ',
       'EQ 10 bandas', 'EQ a 10 bande', 'อีคิว 10 แบนด์', 'EQ 10 pasm.', 'EQ 10 полос', 'EQ 10 смуг'),
    _t('Edit 10-Band EQ', '编辑 10 段均衡器', '編輯 10 段等化器', '10バンドEQ編集', '10밴드 EQ 편집', 'Éditer 10 bandes', 'EQ bearbeiten',
       'Editar 10 bandas', 'Modifica EQ 10b.', 'แก้อีคิว 10 แบนด์', 'Edytuj 10 pasm.', 'Правка 10 полос', 'Змінити 10 смуг'),
    # The 10-Band EQ (docs/modules/peq.md "10-Band EQ"): the curve names (the Equalizer page's grey value, the Curve page, the Settings EQ value; the stock genre names are
    # poor in several languages, so these are our own; Metal is the Cassette theme's existing key), Curve, Custom, the preamp's value form (the payload puts a U+2212 minus before a cut) and the Reset confirm. Reset is the stock key eq_reset.
    # A native-speaker pass is wanted.
    _t('Curve', '曲线', '曲線', 'カーブ', '곡선', 'Courbe', 'Kurve',
       'Curva', 'Curva', 'เส้นโค้ง', 'Krzywa', 'Кривая', 'Крива'),
    _t('Custom', '自定义', '自訂', 'カスタム', '사용자 지정', 'Personnalisé', 'Eigene',
       'Personal', 'Personale', 'กำหนดเอง', 'Własna', 'Своя', 'Власна'),
    _t('Flat', '平直', '平坦', 'フラット', '플랫', 'Neutre', 'Flach',
       'Plano', 'Lineare', 'ราบเรียบ', 'Płaska', 'Плоская', 'Рівна'),
    _t('Pop', '流行', '流行', 'ポップ', '팝', 'Pop', 'Pop',
       'Pop', 'Pop', 'ป๊อป', 'Pop', 'Поп', 'Поп'),
    _t('Rock', '摇滚', '搖滾', 'ロック', '록', 'Rock', 'Rock',
       'Rock', 'Rock', 'ร็อก', 'Rock', 'Рок', 'Рок'),
    _t('Dance', '舞曲', '舞曲', 'ダンス', '댄스', 'Dance', 'Dance',
       'Dance', 'Dance', 'แดนซ์', 'Dance', 'Танцы', 'Танці'),
    _t('Blues', '蓝调', '藍調', 'ブルース', '블루스', 'Blues', 'Blues',
       'Blues', 'Blues', 'บลูส์', 'Blues', 'Блюз', 'Блюз'),
    _t('Vocal', '人声', '人聲', 'ボーカル', '보컬', 'Voix', 'Gesang',
       'Voz', 'Voce', 'เสียงร้อง', 'Wokal', 'Вокал', 'Вокал'),
    _t('Classical', '古典', '古典', 'クラシック', '클래식', 'Classique', 'Klassik',
       'Clásica', 'Classica', 'คลาสสิก', 'Klasyczna', 'Классика', 'Класика'),
    _t('Jazz', '爵士', '爵士', 'ジャズ', '재즈', 'Jazz', 'Jazz',
       'Jazz', 'Jazz', 'แจ๊ส', 'Jazz', 'Джаз', 'Джаз'),
    _t('%d dB', '%d dB', '%d dB', '%d dB', '%d dB', '%d dB', '%d dB',
       '%d dB', '%d dB', '%d dB', '%d dB', '%d dB', '%d dB'),
    _t('Auto reduces the level to help prevent distortion from EQ boosts.', '自动会降低音量，帮助防止 EQ 提升造成失真。', '自動會降低音量，幫助防止 EQ 提升造成失真。', '自動は音量を下げて、EQ のブーストによる歪みを防ぎます。', '자동은 EQ 부스트로 인한 왜곡을 막도록 음량을 줄입니다.',
       'Auto réduit le niveau pour éviter la distorsion due aux boosts EQ.', 'Auto senkt den Pegel, um Verzerrungen durch EQ-Anhebungen zu vermeiden.', 'Auto reduce el nivel para evitar la distorsión por los refuerzos del EQ.', 'Auto riduce il livello per evitare la distorsione dovuta ai boost dell\'EQ.',
       'อัตโนมัติจะลดระดับเสียงเพื่อช่วยป้องกันเสียงเพี้ยนจากการเพิ่มของอีคิว', 'Auto obniża poziom, aby zapobiegać zniekształceniom przy wzmocnieniach EQ.', 'Авто снижает уровень, чтобы избежать искажений при усилении EQ.', 'Авто знижує рівень, щоб уникнути спотворень при підсиленні EQ.'),
    _t('Reset 10-Band EQ?','重置 10 段均衡器？', '重置 10 段等化器？', '10バンドEQをリセットしますか？', '10밴드 EQ를 재설정할까요?', 'Réinitialiser l\'EQ 10 bandes ?', '10-Band-EQ zurücksetzen?',
       '¿Restablecer el EQ de 10 bandas?', 'Reimpostare l\'EQ a 10 bande?', 'รีเซ็ตอีคิว 10 แบนด์ไหม?', 'Zresetować korektor 10-pasmowy?', 'Сбросить 10-полосный эквалайзер?', 'Скинути 10-смуговий еквалайзер?'),
    # the 10-Band editor's Save as Preset row (its name entry is the Save As entry) and the message box after the file is written
    _t('Save as Preset', '存为预设', '存為預設', 'プリセットとして保存', '프리셋으로 저장', 'Enregistrer comme préréglage', 'Als Preset speichern',
       'Guardar como preajuste', 'Salva come preset', 'บันทึกเป็นพรีเซ็ต', 'Zapisz jako preset', 'Сохранить как пресет', 'Зберегти як пресет'),
    _t('Saved as Preset', '已存为预设', '已存為預設', 'プリセットとして保存しました', '프리셋으로 저장됨', 'Enregistré comme préréglage', 'Als Preset gespeichert',
       'Guardado como preajuste', 'Salvato come preset', 'บันทึกเป็นพรีเซ็ตแล้ว', 'Zapisano jako preset', 'Сохранено как пресет', 'Збережено як пресет'),
    # the 10-Band editor's region line under the graph (the dragged band's range; each fits 272 px at 18 px, widths_tests) and the message box when a slider move replaces a preset file
    _t('Sub bass · rumble', '超低频 · 隆隆声', '超低頻 · 隆隆聲', 'サブベース · 轟き', '서브 베이스 · 울림', 'Sous-grave · grondement', 'Subbass · Grollen',
       'Subgrave · retumbo', 'Sub bassi · rimbombo', 'ซับเบส · เสียงก้อง', 'Subbas · dudnienie', 'Суббас · гул', 'Суббас · гул'),
    _t('Mid bass · punch and warmth', '中低频 · 力度与温暖', '中低頻 · 力度與溫暖', 'ミッドベース · パンチと温かみ', '미드 베이스 · 펀치와 따뜻함', 'Médiums graves · punch et chaleur', 'Tiefmitten · Punch und Wärme',
       'Medios graves · pegada y calidez', 'Medio-bassi · impatto e calore', 'เบสกลาง · พลังและความอบอุ่น', 'Średni bas · moc i ciepło', 'Средние низы · напор и тепло', 'Середні низи · напір і тепло'),
    _t('Lower mids · body and fullness', '中低音 · 厚度与丰满', '中低音 · 厚度與豐滿', '中低域 · 厚みと豊かさ', '중저음 · 두께감과 풍성함', 'Bas médiums · corps et plénitude', 'Untere Mitten · Körper und Fülle',
       'Medios bajos · cuerpo y plenitud', 'Medi bassi · corpo e pienezza', 'กลางต่ำ · เนื้อเสียงและความอิ่ม', 'Dolna średnica · ciało i pełnia', 'Низ. середина · плотность, полнота', 'Низ. середина · щільність, повнота'),
    _t('Upper mids · shouty if too much', '中高音 · 过多会刺耳', '中高音 · 過多會刺耳', '中高域 · 多すぎると耳障り', '중고음 · 과하면 날카로움', 'Haut médiums · criard si excessif', 'Obere Mitten · schrill bei zu viel',
       'Medios altos · estridente en exceso', 'Medi alti · stridulo se eccessivo', 'กลางสูง · มากไปจะแสบหู', 'Górny środek · ostry, gdy za dużo', 'Верх. середина · резко при избытке', 'Верх. середина · різко, як забагато'),
    _t('Treble · detail and sparkle', '高音 · 细节与明亮', '高音 · 細節與明亮', '高域 · 細部ときらめき', '고음 · 디테일과 반짝임', 'Aigus · détail et brillance', 'Höhen · Detail und Glanz',
       'Agudos · detalle y brillo', 'Alti · dettaglio e brillantezza', 'เสียงแหลม · รายละเอียดและประกาย', 'Wysokie tony · szczegół i blask', 'Высокие · детали и блеск', 'Високі · деталі й блиск'),
    _t('Air · openness', '空气感 · 开阔', '空氣感 · 開闊', 'エア · 開放感', '공기감 · 개방감', 'Air · ouverture', 'Luft · Offenheit',
       'Aire · amplitud', 'Aria · apertura', 'อากาศ · ความโปร่ง', 'Powietrze · otwartość', 'Воздух · открытость', 'Повітря · відкритість'),
    _t('Switched to 10-Band EQ', '已切换到 10 段均衡器', '已切換到 10 段等化器', '10バンドEQに切り替えました', '10밴드 EQ로 전환됨', 'Passé à EQ 10 bandes', 'Zu 10-Band-EQ gewechselt',
       'Cambiado a EQ 10 bandas', 'Passato a EQ a 10 bande', 'สลับเป็นอีคิว 10 แบนด์แล้ว', 'Przełączono na EQ 10 pasm.', 'Переключено на EQ 10 полос', 'Перемкнено на EQ 10 смуг'),
    _t('Download headphone presets in Presets, or copy APO .txt files into EQ on the card.',
       '在“预设”中下载耳机预设，或将 APO 的 .txt 文件复制到存储卡的 EQ 文件夹。', '在「預設」中下載耳機預設，或將 APO 的 .txt 檔案複製到記憶卡的 EQ 資料夾。',
       '「プリセット」でヘッドホン用プリセットをダウンロードするか、APO の .txt ファイルをカードの EQ フォルダにコピーしてください。', '프리셋에서 헤드폰 프리셋을 다운로드하거나 APO .txt 파일을 카드의 EQ 폴더에 복사하세요.',
       'Téléchargez des préréglages de casque dans Préréglages, ou copiez des fichiers .txt APO dans EQ sur la carte.', 'Lade Kopfhörer-Presets unter Voreinstellungen herunter oder kopiere APO-.txt-Dateien in EQ auf der Karte.',
       'Descarga preajustes de auriculares en Preajustes o copia archivos .txt de APO en EQ de la tarjeta.', 'Scarica i preset per cuffie in Preset oppure copia file .txt APO in EQ sulla scheda.',
       'ดาวน์โหลดพรีเซ็ตหูฟังใน พรีเซ็ต หรือคัดลอกไฟล์ .txt ของ APO ไปที่ EQ บนการ์ด', 'Pobierz presety słuchawek w Presety lub skopiuj pliki .txt APO do EQ na karcie.',
       'Скачайте пресеты для наушников в разделе Пресеты или скопируйте файлы .txt APO в EQ на карте.', 'Завантажте пресети для навушників у розділі Пресети або скопіюйте файли .txt APO в EQ на картці.'),
    _t('EQ is not applied to DSD.', 'EQ 不作用于 DSD。', 'EQ 不會套用於 DSD。', 'EQ は DSD には適用されません。', 'EQ는 DSD에 적용되지 않습니다.',
       'L\'EQ ne s\'applique pas au DSD.', 'Der EQ wird nicht auf DSD angewendet.', 'El EQ no se aplica a DSD.', 'L\'EQ non viene applicato al DSD.',
       'อีคิวไม่ทำงานกับ DSD', 'EQ nie działa z DSD.', 'EQ не применяется к DSD.', 'EQ не застосовується до DSD.'),
    # the Equalizer page's grey line under the switch: the output whose EQ the page edits (patch/peqout.c)
    _t('For Headphones', '用于耳机', '用於耳機', 'ヘッドホン用', '헤드폰용', 'Pour le casque', 'Für Kopfhörer',
       'Para auriculares', 'Per le cuffie', 'สำหรับหูฟัง', 'Dla słuchawek', 'Для наушников', 'Для навушників'),
    _t('For Line Out', '用于线路输出', '用於線路輸出', 'ライン出力用', '라인 아웃용', 'Pour la sortie ligne', 'Für Line-Out',
       'Para salida de línea', 'Per l\'uscita linea', 'สำหรับไลน์เอาต์', 'Dla wyjścia liniowego', 'Для линейного выхода', 'Для лінійного виходу'),
    _t('For USB DAC', '用于 USB DAC', '用於 USB DAC', 'USB DAC用', 'USB DAC용', 'Pour le DAC USB', 'Für USB-DAC',
       'Para DAC USB', 'Per il DAC USB', 'สำหรับ USB DAC', 'Dla USB DAC', 'Для USB-ЦАП', 'Для USB-ЦАП'),
    _t('Cannot read this preset', '无法读取此预设', '無法讀取此預設', 'このプリセットを読み込めません', '이 프리셋을 읽을 수 없습니다', 'Préréglage illisible', 'Preset nicht lesbar',
       'No se puede leer el preajuste', 'Impossibile leggere il preset', 'อ่านพรีเซ็ตนี้ไม่ได้', 'Nie można odczytać ustawienia', 'Не удалось прочитать пресет', 'Не вдалося прочитати пресет'),
    _t('Not saved', '未保存', '未儲存', '保存できませんでした', '저장하지 못했습니다', 'Non enregistré', 'Nicht gespeichert',
       'No se guardó', 'Non salvato', 'บันทึกไม่สำเร็จ', 'Nie zapisano', 'Не сохранено', 'Не збережено'),
    # The preset page (patch/peqpage.c, docs/modules/peq.md "Preset page"): the Preamp row ("Auto" in its value), the Bands header, a band's type, the note about skipped lines. Short, the Preamp row's label has 116 px.
    # A native-speaker pass is wanted.
    _t('Preamp', '前级增益', '前級增益', 'プリアンプ', '프리앰프', 'Préampli', 'Vorstufe',
       'Previo', 'Preampli', 'พรีแอมป์', 'Przedwzm.', 'Предусил.', 'Передпідс.'),
    _t('Bands', '频段', '頻段', 'バンド', '밴드', 'Bandes', 'Bänder',
       'Bandas', 'Bande', 'แบนด์', 'Pasma', 'Полосы', 'Смуги'),
    _t('Auto', '自动', '自動', '自動', '자동', 'Auto', 'Auto',
       'Auto', 'Auto', 'อัตโนมัติ', 'Auto', 'Авто', 'Авто'),
    _t('Low shelf', '低架滤波', '低架濾波', 'ローシェルフ', '로우 셸프', 'Plateau grave', 'Tiefen-Shelf',
       'Shelf grave', 'Shelf bassi', 'โลว์เชลฟ์', 'Półka niskich', 'НЧ-шельф', 'НЧ-шельф'),
    _t('High shelf', '高架滤波', '高架濾波', 'ハイシェルフ', '하이 셸프', 'Plateau aigu', 'Höhen-Shelf',
       'Shelf agudo', 'Shelf alti', 'ไฮเชลฟ์', 'Półka wysokich', 'ВЧ-шельф', 'ВЧ-шельф'),
    _t('Peak', '峰值', '峰值', 'ピーク', '피크', 'Cloche', 'Glocke',
       'Pico', 'Picco', 'พีค', 'Pik', 'Пик', 'Пік'),
    _t('%d line not supported was skipped.', '已跳过 %d 行不支持的内容。', '已略過 %d 行不支援的內容。', '未対応の %d 行をスキップしました。', '지원되지 않는 %d줄을 건너뛰었습니다.',
       '%d ligne non prise en charge ignorée.', '%d nicht unterstützte Zeile übersprungen.', 'Se omitió %d línea no admitida.', '%d riga non supportata ignorata.',
       'ข้าม %d บรรทัดที่ไม่รองรับ', 'Pominięto %d nieobsługiwany wiersz.', 'Пропущена %d неподдерживаемая строка.', 'Пропущено %d непідтримуваний рядок.'),
    _t('%d lines not supported were skipped.', '已跳过 %d 行不支持的内容。', '已略過 %d 行不支援的內容。', '未対応の %d 行をスキップしました。', '지원되지 않는 %d줄을 건너뛰었습니다.',
       '%d lignes non prises en charge ignorées.', '%d nicht unterstützte Zeilen übersprungen.', 'Se omitieron %d líneas no admitidas.', '%d righe non supportate ignorate.',
       'ข้าม %d บรรทัดที่ไม่รองรับ', 'Pominięto nieobsługiwane wiersze: %d.', 'Пропущено неподдерживаемых строк: %d.', 'Пропущено непідтримуваних рядків: %d.'),
    # The AutoEq download (patch/autoeq.c, docs/modules/peq.md "AutoEq download"): the Presets page's card, the list's progress, a result's progress and its states, the kind of headphone.
    # A native-speaker pass is wanted.
    # The Presets page (patch/peqlib.c, patch/peqpage.c, docs/modules/peq.md "Presets page"): its title and section headers, the grey line of a file on the card, the Preset page's delete row and its confirm, and the failed delete.
    _t('Presets', '预设', '預設', 'プリセット', '프리셋', 'Préréglages', 'Voreinstellungen', 'Preajustes', 'Preset', 'พรีเซ็ต', 'Presety', 'Пресеты', 'Пресети'),
    _t('AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq', 'AutoEq'),
    _t('On Card', '在存储卡上', '在記憶卡上', 'カード内', '카드 내', 'Sur la carte', 'Auf Karte', 'En la tarjeta', 'Sulla scheda', 'ในการ์ด', 'Na karcie', 'На карте', 'На карті'),
    _t('On card', '在存储卡上', '在記憶卡上', 'カード内', '카드 내', 'Sur la carte', 'Auf Karte', 'En la tarjeta', 'Sulla scheda', 'ในการ์ด', 'Na karcie', 'На карте', 'На карті'),
    _t('Delete Preset', '删除预设', '刪除預設', 'プリセットを削除', '프리셋 삭제', 'Supprimer le préréglage', 'Preset löschen', 'Eliminar preajuste', 'Elimina preset', 'ลบพรีเซ็ต', 'Usuń ustawienie', 'Удалить пресет', 'Видалити пресет'),
    _t('Delete Preset?', '删除预设？', '刪除預設？', 'プリセットを削除しますか？', '프리셋을 삭제할까요?', 'Supprimer le préréglage ?', 'Preset löschen?', '¿Eliminar preajuste?', 'Eliminare il preset?', 'ลบพรีเซ็ตนี้ไหม?', 'Usunąć ustawienie?', 'Удалить пресет?', 'Видалити пресет?'),
    _t('Failed To Delete Preset', '无法删除预设', '無法刪除預設', 'プリセットを削除できませんでした', '프리셋을 삭제하지 못했습니다', 'Impossible de supprimer le préréglage', 'Preset konnte nicht gelöscht werden', 'No se pudo eliminar el preajuste', 'Impossibile eliminare il preset', 'ไม่สามารถลบพรีเซ็ตได้', 'Nie udało się usunąć ustawienia', 'Не удалось удалить пресет', 'Не вдалося видалити пресет'),
    _t('Download from AutoEq', '从 AutoEq 下载', '從 AutoEq 下載', 'AutoEq からダウンロード', 'AutoEq에서 다운로드', 'Obtenir depuis AutoEq', 'Von AutoEq laden',
       'Descargar de AutoEq', 'Scarica da AutoEq', 'ดาวน์โหลดจาก AutoEq', 'Pobierz z AutoEq', 'Скачать из AutoEq', 'Завантажити з AutoEq'),
    _t('Downloading List…', '正在下载列表…', '正在下載清單…', 'リストをダウンロード中…', '목록 다운로드 중…', 'Téléchargement de la liste…', 'Liste wird geladen…',
       'Descargando lista…', 'Download elenco…', 'กำลังดาวน์โหลดรายการ…', 'Pobieranie listy…', 'Загрузка списка…', 'Завантаження списку…'),
    _t('Downloading…', '正在下载…', '正在下載…', 'ダウンロード中…', '다운로드 중…', 'Téléchargement…', 'Wird geladen…',
       'Descargando…', 'Download…', 'กำลังดาวน์โหลด…', 'Pobieranie…', 'Загрузка…', 'Завантаження…'),
    _t('Saved to EQ \u00b7 Tap to use', '已存入 EQ \u00b7 点按使用', '已存入 EQ \u00b7 點按使用', 'EQ に保存済み \u00b7 タップで使用', 'EQ에 저장됨 \u00b7 탭하여 사용',
       'Dans EQ \u00b7 Touchez pour utiliser', 'In EQ \u00b7 Tippen zum Nutzen', 'En EQ \u00b7 Toca para usar', 'In EQ \u00b7 Tocca per usare', 'อยู่ใน EQ \u00b7 แตะเพื่อใช้',
       'W EQ \u00b7 Dotknij, by użyć', 'В EQ \u00b7 Нажмите, чтобы выбрать', 'В EQ \u00b7 Торкніться, щоб вибрати'),
    _t('In use','使用中', '使用中', '使用中', '사용 중', 'Utilisé', 'In Gebrauch', 'En uso', 'In uso', 'กำลังใช้', 'W użyciu', 'Используется', 'Використовується'),
    _t('Over-ear', '头戴式', '頭戴式', 'オーバーイヤー', '오버이어', 'Circum-aural', 'Over-Ear', 'Circumaurales', 'Circumaurali', 'ครอบหู', 'Nauszne', 'Мониторные', 'Повнорозмірні'),
    _t('In-ear', '入耳式', '入耳式', 'カナル型', '인이어', 'Intra-auriculaire', 'In-Ear', 'Intraurales', 'Intrauricolari', 'อินเอียร์', 'Douszne', 'Вставные', 'Вставні'),
    _t('Earbud', '耳塞式', '耳塞式', 'イヤホン', '이어버드', 'Écouteurs', 'Earbuds', 'Earbuds', 'Auricolari', 'เอียร์บัด', 'Earbuds', 'Вкладыши', 'Вкладиші'),
    # Preset editing (patch/peqpage.c, patch/peqband.c, docs/modules/peq.md "Preset editing"): the unsaved-changes dialog, the band page, the name entries and their refusals. A native-speaker pass is wanted.
    _t('Edited', '已编辑', '已編輯', '編集済み', '편집됨', 'Modifié', 'Geändert', 'Editado', 'Modificato', 'แก้ไขแล้ว', 'Zmieniono', 'Изменено', 'Змінено'),
    _t('Save', '保存', '儲存', '保存', '저장', 'Enregistrer', 'Speichern', 'Guardar', 'Salva', 'บันทึก', 'Zapisz', 'Сохранить', 'Зберегти'),
    _t('Save Changes?', '要保存更改吗？', '要儲存更改嗎？', '変更を保存しますか？', '변경 사항을 저장할까요?', 'Enregistrer les modifications ?', 'Änderungen speichern?', '¿Guardar los cambios?', 'Salvare le modifiche?', 'บันทึกการเปลี่ยนแปลงไหม',
       'Zapisać zmiany?', 'Сохранить изменения?', 'Зберегти зміни?'),
    _t('Save As New…', '另存为新预设…', '另存為新預設…', '新規として保存…', '새 프리셋으로 저장…', 'Enregistrer comme nouveau…', 'Als neu speichern…', 'Guardar como nuevo…', 'Salva come nuovo…', 'บันทึกเป็นรายการใหม่…',
       'Zapisz jako nowe…', 'Сохранить как новый…', 'Зберегти як новий…'),
    _t("Don't Save", '不保存', '不儲存', '保存しない', '저장 안 함', 'Ne pas enregistrer', 'Nicht speichern', 'No guardar', 'Non salvare', 'ไม่บันทึก', 'Nie zapisuj', 'Не сохранять', 'Не зберігати'),
    _t('Rename Preset', '重命名预设', '重新命名預設', 'プリセット名を変更', '프리셋 이름 변경', 'Renommer le préréglage', 'Preset umbenennen', 'Renombrar preajuste', 'Rinomina preset', 'เปลี่ยนชื่อพรีเซ็ต',
       'Zmień nazwę ustawienia', 'Переименовать пресет', 'Перейменувати пресет'),
    _t('Save As', '另存为', '另存為', '別名で保存', '다른 이름으로 저장', 'Enregistrer sous', 'Speichern unter', 'Guardar como', 'Salva come', 'บันทึกเป็น', 'Zapisz jako', 'Сохранить как', 'Зберегти як'),
    _t('Band %d', '频段 %d', '頻段 %d', 'バンド %d', '밴드 %d', 'Bande %d', 'Band %d', 'Banda %d', 'Banda %d', 'แบนด์ %d', 'Pasmo %d', 'Полоса %d', 'Смуга %d'),
    _t('Frequency', '频率', '頻率', '周波数', '주파수', 'Fréquence', 'Frequenz', 'Frecuencia', 'Frequenza', 'ความถี่', 'Częstotliwość', 'Частота', 'Частота'),
    _t('Gain', '增益', '增益', 'ゲイン', '게인', 'Gain', 'Verstärkung', 'Ganancia', 'Guadagno', 'เกน', 'Wzmocnienie', 'Усиление', 'Підсилення'),
    _t('Range', '范围', '範圍', '範囲', '범위', 'Plage', 'Bereich', 'Rango', 'Intervallo', 'ช่วง', 'Zakres', 'Диапазон', 'Діапазон'),   # the number keypad's "Range 20 Hz – 20 kHz" line (patch/peqband.c)
    _t('Tap a value to type it exactly.', '点按数值可精确输入。', '點按數值以精確輸入。', '値をタップして正確に入力できます。', '값을 탭하여 정확히 입력하세요.', 'Touchez une valeur pour la saisir.', 'Wert antippen, um ihn einzugeben.',
       'Toca un valor para escribirlo.', 'Tocca un valore per digitarlo.', 'แตะค่าเพื่อพิมพ์ค่าที่ต้องการ', 'Dotknij wartości, aby ją wpisać.', 'Нажмите на значение, чтобы ввести его.', 'Торкніться значення, щоб ввести його.'),
    _t('Name already in use', '名称已被使用', '名稱已被使用', '名前は既に使われています', '이미 사용 중인 이름입니다', 'Nom déjà utilisé', 'Name bereits vergeben', 'Nombre ya en uso', 'Nome già in uso', 'ชื่อนี้ถูกใช้แล้ว',
       'Nazwa jest już używana', 'Имя уже занято', 'Ім\'я вже використовується'),
    _t('Preset limit reached', '已达预设数量上限', '已達預設數量上限', 'プリセット数の上限です', '프리셋 수 한도에 도달했습니다', 'Limite de préréglages atteinte', 'Preset-Limit erreicht', 'Límite de preajustes alcanzado',
       'Limite di preset raggiunto', 'ถึงขีดจำกัดจำนวนพรีเซ็ตแล้ว', 'Osiągnięto limit ustawień', 'Достигнут лимит пресетов', 'Досягнуто ліміту пресетів'),
])
# The Podcasts page's dates (patch/pcmodel.c pc_when, docs/modules/podcasts.md "The date"): Apple Podcasts' "Just now", "4m ago", "4h ago", "4d ago", "Oct 23", "Oct 23, 2025". A month
# text has its one %d (the day) where the language puts it; the year follows as ", %d". These keys do not start with %d, so DATE_KEYS lets the %d test of the tables know them.
_MONTH_KEYS = ('Jan %d', 'Feb %d', 'Mar %d', 'Apr %d', 'May %d', 'Jun %d', 'Jul %d', 'Aug %d', 'Sep %d', 'Oct %d', 'Nov %d', 'Dec %d')
_MONTHS = {   # locale -> the twelve month texts
    'zh_CN': [f'{m}月%d日' for m in range(1, 13)], 'zh_HK': [f'{m}月%d日' for m in range(1, 13)], 'ja_JP': [f'{m}月%d日' for m in range(1, 13)],
    'ko_KR': [f'{m}월 %d일' for m in range(1, 13)],
    'fr_FR': [f'{x} %d' for x in ('janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.')],
    'ge_DE': [f'%d. {x}' for x in ('Jan.', 'Feb.', 'März', 'Apr.', 'Mai', 'Juni', 'Juli', 'Aug.', 'Sept.', 'Okt.', 'Nov.', 'Dez.')],
    'sp_ES': [f'%d {x}' for x in ('ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic')],
    'it_IT': [f'%d {x}' for x in ('gen', 'feb', 'mar', 'apr', 'mag', 'giu', 'lug', 'ago', 'set', 'ott', 'nov', 'dic')],
    'th_TH': [f'%d {x}' for x in ('ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.')],
    'po_PL': [f'%d {x}' for x in ('sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru')],
    'ru_RU': [f'%d {x}' for x in ('янв.', 'февр.', 'мар.', 'апр.', 'мая', 'июн.', 'июл.', 'авг.', 'сент.', 'окт.', 'нояб.', 'дек.')],
    'uk_UK': [f'%d {x}' for x in ('січ.', 'лют.', 'бер.', 'квіт.', 'трав.', 'черв.', 'лип.', 'серп.', 'вер.', 'жовт.', 'лист.', 'груд.')],
}
TEXT.update(_t(k, *[_MONTHS[loc][i] for loc in _L]) for i, k in enumerate(_MONTH_KEYS))
# The lock screen's date (docs/modules/lockscreen.md "The date"): the short date of each language, e.g. "Wed, Nov 11", "11月11日 周三", "Mi., 11. Nov.". Three kinds of key:
# the digit_clock format (LOCK_DATE_KEY, the asset's own format; the payload sets its translation at the page's init: M / D numbers, MMM and W the names below, the rest copied),
# and the weekday and month names, which demo's formatter itself looks up (wstr_format_date_time; tools/mod_lockscreen.py patch_date_names). A format's own letters must not be
# among the formatter's tokens (Y M D h H m s T w W). The CJK formats write the month as a number; their month names only show with the kill switch (the asset's format).
LOCK_DATE_KEY = 'W, MMM D'
WEEKDAY_KEYS = ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')
MONTH_NAME_KEYS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
DEMO_KEYS = WEEKDAY_KEYS + MONTH_NAME_KEYS     # looked up by demo, not by an asset or the payload (the orphan test, test/pod/i18n.py)
_LOCK_DATE = {   # locale -> (format, the seven weekdays from Sunday, the twelve months)
    'zh_CN': ('M月D日 W', ['周' + c for c in '日一二三四五六'], [f'{m}月' for m in range(1, 13)]),
    'zh_HK': ('M月D日 W', ['週' + c for c in '日一二三四五六'], [f'{m}月' for m in range(1, 13)]),
    'ja_JP': ('M月D日(W)', list('日月火水木金土'), [f'{m}月' for m in range(1, 13)]),
    'ko_KR': ('M월 D일 (W)', list('일월화수목금토'), [f'{m}월' for m in range(1, 13)]),
    'fr_FR': ('W D MMM', 'dim. lun. mar. mer. jeu. ven. sam.'.split(), 'janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.'.split()),
    'ge_DE': ('W, D. MMM', 'So. Mo. Di. Mi. Do. Fr. Sa.'.split(), 'Jan. Feb. März Apr. Mai Juni Juli Aug. Sept. Okt. Nov. Dez.'.split()),
    'sp_ES': ('W, D MMM', 'dom lun mar mié jue vie sáb'.split(), 'ene feb mar abr may jun jul ago sept oct nov dic'.split()),
    'it_IT': ('W D MMM', 'dom lun mar mer gio ven sab'.split(), 'gen feb mar apr mag giu lug ago set ott nov dic'.split()),
    'th_TH': ('W D MMM', 'อา. จ. อ. พ. พฤ. ศ. ส.'.split(), 'ม.ค. ก.พ. มี.ค. เม.ย. พ.ค. มิ.ย. ก.ค. ส.ค. ก.ย. ต.ค. พ.ย. ธ.ค.'.split()),
    'po_PL': ('W, D MMM', 'niedz. pon. wt. śr. czw. pt. sob.'.split(), 'sty lut mar kwi maj cze lip sie wrz paź lis gru'.split()),
    'ru_RU': ('W, D MMM', 'вс пн вт ср чт пт сб'.split(), 'янв. февр. мар. апр. мая июн. июл. авг. сент. окт. нояб. дек.'.split()),
    'uk_UK': ('W, D MMM', 'нд пн вт ср чт пт сб'.split(), 'січ. лют. бер. квіт. трав. черв. лип. серп. вер. жовт. лист. груд.'.split()),
}
assert all(len(w) == 7 and len(m) == 12 for _, w, m in _LOCK_DATE.values())
TEXT.update([_t(LOCK_DATE_KEY, *[_LOCK_DATE[loc][0] for loc in _L])])
TEXT.update(_t(k, *[_LOCK_DATE[loc][1][i] for loc in _L]) for i, k in enumerate(WEEKDAY_KEYS))
TEXT.update(_t(k, *[_LOCK_DATE[loc][2][i] for loc in _L]) for i, k in enumerate(MONTH_NAME_KEYS))


def lock_date(loc):
    """(format, weekdays, months) of the lock screen's date in the language loc."""
    return TEXT[LOCK_DATE_KEY][loc], [TEXT[k][loc] for k in WEEKDAY_KEYS], [TEXT[k][loc] for k in MONTH_NAME_KEYS]


TEXT['Subsonic'] = {loc: 'Subsonic' for loc in LOCALES}   # the product name, the same in every language (the menu row and the pages' title)
TEXT.update([
    _t(', %d', '，%d年', '，%d年', ', %d年', ', %d년', ', %d', ', %d', ', %d', ', %d', ', %d', ', %d', ', %d', ', %d'),
    _t('Just now', '刚刚', '剛剛', 'たった今', '방금', 'À l’instant', 'Gerade eben', 'Ahora mismo', 'Adesso', 'เมื่อสักครู่', 'Przed chwilą', 'Только что', 'Щойно'),
    _t('%dm ago', '%d分钟前', '%d分鐘前', '%d分前', '%d분 전', 'il y a %d min', 'vor %d Min.', 'hace %d min', '%d min fa', '%d นาทีที่แล้ว', '%d min temu', '%d мин назад', '%d хв тому'),
    _t('%dh ago', '%d小时前', '%d小時前', '%d時間前', '%d시간 전', 'il y a %d h', 'vor %d Std.', 'hace %d h', '%d h fa', '%d ชั่วโมงที่แล้ว', '%d godz. temu', '%d ч назад', '%d год тому'),
    _t('%dd ago', '%d天前', '%d天前', '%d日前', '%d일 전', 'il y a %d j', 'vor %d T.', 'hace %d d', '%d g fa', '%d วันที่แล้ว', '%d dn. temu', '%d дн. назад', '%d дн. тому'),
])
DATE_KEYS = _MONTH_KEYS + (', %d', '%dm ago', '%dh ago', '%dd ago', 'Refreshing %d/%d…', 'Exported %d show', 'Exported %d shows', 'Band %d', 'Updating library… %d/%d', 'Loading covers… %d/%d', 'Loading artist images… %d/%d')   # keys with a %d that do not start with it (the tables test, test/pod/i18n.py)
# The Navidrome Server page (patch/ndserver.c, tools/pod_ndserver.py): the row labels (the keyboard's titles and placeholders too), the two confirmations and the toasts. "Navidrome" stays as it is.
TEXT.update([
    _t('Server', '服务器', '伺服器', 'サーバー', '서버', 'Serveur', 'Server', 'Servidor', 'Server', 'เซิร์ฟเวอร์', 'Serwer', 'Сервер', 'Сервер'),
    _t('URL', '地址', '位址', 'URL', 'URL', 'URL', 'URL', 'URL', 'URL', 'URL', 'Adres', 'Адрес', 'Адреса'),   # the Server page's row and the Sign In placeholder: the page says Server already
    _t('Username', '用户名', '使用者名稱', 'ユーザー名', '사용자 이름', 'Nom d’utilisateur', 'Benutzername', 'Usuario', 'Nome utente', 'ชื่อผู้ใช้', 'Nazwa użytkownika', 'Имя пользователя', 'Ім’я користувача'),
    _t('Sync Now', '立即同步', '立即同步', '今すぐ同期', '지금 동기화', 'Synchroniser', 'Jetzt synchronisieren', 'Sincronizar', 'Sincronizza', 'ซิงค์ทันที', 'Synchronizuj', 'Синхронизация', 'Синхронізація'),
    _t('Sign Out', '退出登录', '登出', 'サインアウト', '로그아웃', 'Se déconnecter', 'Abmelden', 'Cerrar sesión', 'Esci', 'ออกจากระบบ', 'Wyloguj się', 'Выйти', 'Вийти'),
    _t('Leave empty to keep', '留空则不修改', '留空則不更改', '空欄なら変更なし', '비워 두면 유지', 'Vide pour conserver', 'Leer lassen: behalten', 'Vacío para mantener', 'Vuoto per mantenere',
       'เว้นว่างเพื่อคงเดิม', 'Puste: bez zmian', 'Пусто: без изменений', 'Порожньо: без змін'),
    _t('1 download waiting', '1 项下载等待中', '1 項下載等待中', '1 件のダウンロードが待機中', '다운로드 1개 대기 중', '1 téléchargement en attente', '1 Download wartet', '1 descarga en espera', '1 download in attesa',
       'รอดาวน์โหลด 1 รายการ', '1 pobieranie czeka', '1 загрузка ожидает', '1 завантаження очікує'),
    _t('%d downloads waiting', '%d 项下载等待中', '%d 項下載等待中', '%d 件のダウンロードが待機中', '다운로드 %d개 대기 중', '%d téléchargements en attente', '%d Downloads warten', '%d descargas en espera', '%d download in attesa',
       'รอดาวน์โหลด %d รายการ', 'Oczekujące pobierania: %d', 'Загрузок в ожидании: %d', 'Завантажень в очікуванні: %d'),
    _t('Sign out of Subsonic? Downloaded songs stay on the card.', '退出 Subsonic 登录？已下载的歌曲会保留在存储卡上。', '登出 Subsonic？已下載的歌曲會保留在記憶卡上。', 'Subsonic からサインアウトしますか？ダウンロード済みの曲はカードに残ります。',
       'Subsonic에서 로그아웃할까요? 다운로드한 곡은 카드에 남습니다.', 'Se déconnecter de Subsonic ? Les titres téléchargés restent sur la carte.', 'Von Subsonic abmelden? Heruntergeladene Titel bleiben auf der Karte.',
       '¿Cerrar sesión en Subsonic? Las canciones descargadas se quedan en la tarjeta.', 'Uscire da Subsonic? I brani scaricati restano sulla scheda.', 'ออกจาก Subsonic หรือไม่ เพลงที่ดาวน์โหลดไว้จะยังอยู่ในการ์ด',
       'Wylogować się z Subsonic? Pobrane utwory zostają na karcie.', 'Выйти из Subsonic? Загруженные песни останутся на карте.', 'Вийти з Subsonic? Завантажені пісні залишаться на картці.'),
    _t('Enter a valid server address', '请输入有效的服务器地址', '請輸入有效的伺服器位址', '有効なサーバーアドレスを入力', '올바른 서버 주소를 입력하세요', 'Saisissez une adresse de serveur valide', 'Gültige Serveradresse eingeben',
       'Introduce una dirección de servidor válida', 'Inserisci un indirizzo server valido', 'ป้อนที่อยู่เซิร์ฟเวอร์ที่ถูกต้อง', 'Wpisz prawidłowy adres serwera', 'Введите правильный адрес сервера', 'Введіть правильну адресу сервера'),
    _t('Enter a valid username', '请输入有效的用户名', '請輸入有效的使用者名稱', '有効なユーザー名を入力', '올바른 사용자 이름을 입력하세요', 'Saisissez un nom d’utilisateur valide', 'Gültigen Benutzernamen eingeben',
       'Introduce un usuario válido', 'Inserisci un nome utente valido', 'ป้อนชื่อผู้ใช้ที่ถูกต้อง', 'Wpisz prawidłową nazwę użytkownika', 'Введите правильное имя пользователя', 'Введіть правильне ім’я користувача'),
    _t('Enter a valid password', '请输入有效的密码', '請輸入有效的密碼', '有効なパスワードを入力', '올바른 비밀번호를 입력하세요', 'Saisissez un mot de passe valide', 'Gültiges Passwort eingeben',
       'Introduce una contraseña válida', 'Inserisci una password valida', 'ป้อนรหัสผ่านที่ถูกต้อง', 'Wpisz prawidłowe hasło', 'Введите правильный пароль', 'Введіть правильний пароль'),
    _t('Could not save settings', '无法保存设置', '無法儲存設定', '設定を保存できません', '설정을 저장할 수 없습니다', 'Impossible d’enregistrer les réglages', 'Speichern fehlgeschlagen',
       'No se pudieron guardar los ajustes', 'Impossibile salvare le impostazioni', 'บันทึกการตั้งค่าไม่ได้', 'Nie można zapisać ustawień', 'Не удалось сохранить настройки', 'Не вдалося зберегти налаштування'),
    _t('Add a server first', '请先添加服务器', '請先新增伺服器', '先にサーバーを追加', '먼저 서버를 추가하세요', 'Ajoutez d’abord un serveur', 'Zuerst Server hinzufügen',
       'Añade primero un servidor', 'Aggiungi prima un server', 'เพิ่มเซิร์ฟเวอร์ก่อน', 'Najpierw dodaj serwer', 'Сначала добавьте сервер', 'Спочатку додайте сервер'),
    # The Sign In page (patch/ndserver.c nl_*): the title and action key, and the error line under the card.
    _t('Sign In', '登录', '登入', 'サインイン', '로그인', 'Entrer', 'Anmelden', 'Entrar', 'Accedi', 'เข้าสู่ระบบ', 'Zaloguj się', 'Войти', 'Увійти'),
    _t('Incorrect username or password', '用户名或密码不正确', '使用者名稱或密碼不正確', 'ユーザー名かパスワードが違います', '사용자 이름 또는 비밀번호가 틀립니다', 'Identifiant ou mot de passe incorrect', 'Benutzername oder Passwort falsch',
       'Usuario o contraseña incorrectos', 'Nome utente o password errati', 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'Zła nazwa użytkownika lub hasło', 'Неверный логин или пароль', 'Хибний логін або пароль'),
    _t("Can't connect to the server", '无法连接到服务器', '無法連線到伺服器', 'サーバーに接続できません', '서버에 연결할 수 없습니다', 'Connexion au serveur impossible', 'Server nicht erreichbar',
       'No se puede conectar al servidor', 'Impossibile connettersi al server', 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้', 'Brak połączenia z serwerem', 'Не удаётся подключиться к серверу', 'Не вдається підключитися до сервера'),
    _t('Server certificate not trusted', '服务器证书不受信任', '伺服器憑證不受信任', 'サーバー証明書が信頼できません', '서버 인증서를 신뢰할 수 없습니다', 'Certificat du serveur non fiable', 'Serverzertifikat nicht vertrauenswürdig',
       'Certificado del servidor no confiable', 'Certificato del server non attendibile', 'ไม่เชื่อถือใบรับรองเซิร์ฟเวอร์', 'Certyfikat serwera niezaufany', 'Сертификат сервера не доверенный', 'Сертифікат сервера не довірений'),
    _t('Set the date and time first', '请先设置日期和时间', '請先設定日期和時間', '先に日付と時刻を設定', '먼저 날짜와 시간을 설정하세요', "Réglez d'abord la date et l'heure", 'Zuerst Datum und Uhrzeit einstellen',
       'Ajusta primero la fecha y la hora', "Imposta prima data e ora", 'ตั้งวันที่และเวลาก่อน', 'Najpierw ustaw datę i godzinę', 'Сначала задайте дату и время', 'Спочатку задайте дату й час'),
    # The Navidrome download and sync failures (patch/sbsrc.c sbs_message); the rest of its words are the Sign In page's, "Card is full", "Server error" and "Not enough memory".
    _t('Write failed', '写入失败', '寫入失敗', '書き込みに失敗しました', '쓰기 실패', "Échec de l'écriture", 'Schreiben fehlgeschlagen', 'Error de escritura', 'Scrittura non riuscita', 'เขียนไม่สำเร็จ', 'Zapis nie powiódł się', 'Ошибка записи', 'Помилка запису'),
    _t('Song not found on the server', '服务器上找不到该歌曲', '伺服器上找不到該歌曲', 'サーバーに曲が見つかりません', '서버에서 곡을 찾을 수 없습니다', 'Titre introuvable sur le serveur', 'Titel nicht auf dem Server gefunden', 'Canción no encontrada en el servidor', 'Brano non trovato sul server', 'ไม่พบเพลงบนเซิร์ฟเวอร์', 'Nie znaleziono utworu na serwerze', 'Песня не найдена на сервере', 'Пісню не знайдено на сервері'),
    _t('Unexpected server response', '服务器响应异常', '伺服器回應異常', 'サーバーから予期しない応答がありました', '서버 응답이 올바르지 않습니다', 'Réponse inattendue du serveur', 'Unerwartete Serverantwort', 'Respuesta inesperada del servidor', 'Risposta imprevista dal server', 'เซิร์ฟเวอร์ตอบกลับผิดปกติ', 'Nieoczekiwana odpowiedź serwera', 'Неожиданный ответ сервера', 'Несподівана відповідь сервера'),
    _t('Download interrupted', '下载已中断', '下載已中斷', 'ダウンロードが中断されました', '다운로드가 중단되었습니다', 'Téléchargement interrompu', 'Download unterbrochen', 'Descarga interrumpida', 'Download interrotto', 'การดาวน์โหลดถูกขัดจังหวะ', 'Pobieranie przerwane', 'Загрузка прервана', 'Завантаження перервано'),
])
# The Navidrome root page (patch/ndroot.c, tools/pod_nd.py): the Server row's state words, the footer and the empty state. "Navidrome" stays as it is.
TEXT.update([
    _t('Not Connected', '未连接', '未連線', '未接続', '연결 안 됨', 'Non connecté', 'Nicht verbunden', 'No conectado', 'Non connesso', 'ไม่ได้เชื่อมต่อ', 'Brak połączenia', 'Не подключено', 'Не підключено'),
    _t('Syncing…', '正在同步…', '正在同步…', '同期中…', '동기화 중…', 'Synchro…', 'Sync läuft…', 'Sincronizando…', 'Sincronizzo…', 'กำลังซิงค์…', 'Synchronizacja…', 'Синхронизация…', 'Синхронізація…'),
    # the status line while the background fill runs (patch/sbapi.c phase 2): songs, then covers; done/total, short because the line is narrow
    _t('Updating library… %d/%d', '正在更新曲库… %d/%d', '正在更新曲庫… %d/%d', 'ライブラリを更新中… %d/%d', '라이브러리 업데이트 중… %d/%d', 'Mise à jour… %d/%d', 'Aktualisiere… %d/%d', 'Actualizando librería… %d/%d', 'Aggiorno libreria… %d/%d', 'กำลังอัปเดตคลัง… %d/%d', 'Aktualizacja biblioteki… %d/%d', 'Обновление медиатеки… %d/%d', 'Оновлення медіатеки… %d/%d'),
    _t('Loading covers… %d/%d', '正在加载封面… %d/%d', '正在載入封面… %d/%d', 'カバーを読み込み中… %d/%d', '커버 불러오는 중… %d/%d', 'Pochettes… %d/%d', 'Cover laden… %d/%d', 'Cargando carátulas… %d/%d', 'Copertine… %d/%d', 'กำลังโหลดปก… %d/%d', 'Okładki… %d/%d', 'Загрузка обложек… %d/%d', 'Завантаження обкладинок… %d/%d'),
    _t('Loading artist images… %d/%d', '正在加载歌手图片… %d/%d', '正在載入歌手圖片… %d/%d', 'アーティスト画像… %d/%d', '아티스트 이미지… %d/%d', "Images d'artistes… %d/%d", 'Künstlerbilder… %d/%d', 'Imágenes de artistas… %d/%d', 'Immagini artisti… %d/%d', 'กำลังโหลดรูปศิลปิน… %d/%d', 'Zdjęcia wykonawców… %d/%d', 'Фото исполнителей… %d/%d', 'Фото виконавців… %d/%d'),
    _t('Synced %s', '%s同步', '%s同步', '%sに同期', '%s 동기화됨', 'Synchronisé %s', 'Synchronisiert %s', 'Sincronizado %s', 'Sincronizzato %s', 'ซิงค์ %s', 'Zsynchronizowano %s', 'Синхронизировано %s', 'Синхронізовано %s'),
    _t('Synced just now', '刚刚同步', '剛剛同步', 'たった今同期', '방금 동기화됨', 'Synchronisé à l’instant', 'Gerade synchronisiert', 'Sincronizado ahora mismo', 'Sincronizzato adesso', 'เพิ่งซิงค์', 'Zsynchronizowano przed chwilą', 'Только что синхронизировано', 'Щойно синхронізовано'),
    _t('Server Settings', '服务器设置', '伺服器設定', 'サーバー設定', '서버 설정', 'Réglages du serveur', 'Servereinstellungen', 'Ajustes del servidor', 'Impostazioni server', 'การตั้งค่าเซิร์ฟเวอร์', 'Ustawienia serwera', 'Настройки сервера', 'Налаштування сервера'),
    _t('Not synced yet', '尚未同步', '尚未同步', '未同期', '아직 동기화되지 않음', 'Pas encore synchronisé', 'Noch nicht synchronisiert', 'Aún sin sincronizar', 'Non ancora sincronizzato', 'ยังไม่ได้ซิงค์', 'Jeszcze nie zsynchronizowano', 'Ещё не синхронизировано', 'Ще не синхронізовано'),
    _t('Navidrome, Gonic, Airsonic and other Subsonic servers', 'Navidrome、Gonic、Airsonic 及其他 Subsonic 服务器', 'Navidrome、Gonic、Airsonic 及其他 Subsonic 伺服器', 'Navidrome、Gonic、Airsonic などの Subsonic サーバー', 'Navidrome, Gonic, Airsonic 및 기타 Subsonic 서버',
       'Navidrome, Gonic, Airsonic et autres serveurs Subsonic', 'Navidrome, Gonic, Airsonic und andere Subsonic-Server', 'Navidrome, Gonic, Airsonic y otros servidores Subsonic', 'Navidrome, Gonic, Airsonic e altri server Subsonic',
       'Navidrome, Gonic, Airsonic และเซิร์ฟเวอร์ Subsonic อื่นๆ', 'Navidrome, Gonic, Airsonic i inne serwery Subsonic', 'Navidrome, Gonic, Airsonic и другие серверы Subsonic', 'Navidrome, Gonic, Airsonic та інші сервери Subsonic'),
    _t('Add Server', '添加服务器', '新增伺服器', 'サーバーを追加', '서버 추가', 'Ajouter un serveur', 'Server hinzufügen', 'Añadir servidor', 'Aggiungi server', 'เพิ่มเซิร์ฟเวอร์', 'Dodaj serwer', 'Добавить сервер', 'Додати сервер'),
])
DPAGE_KEYS = ('Updated today', 'Updated yesterday', 'Updated %s', 'Play', 'Songs you love and some to rediscover, made fresh every day.')   # the Daily Mix page's keys
DAILY_KEYS =('Made for You', 'Daily Mix', 'Regenerate Daily Mix', '%s and more', '%s, %s')     # the card's keys (tools/pod_dailymix.py TEXT)

# Keys a built asset or payload text does not use yet (test/pod/i18n.py exempts them from the orphan check). None: the 10-Band editor's strings are all used (phase 2).
PENDING_KEYS = ()

KEYS = sorted(TEXT)


def english(key):
    """The English text a key stands for (our keys are their own English; stock keys come from STOCK)."""
    return TEXT[key]['en_US'] if key in TEXT else STOCK[key]


import pod_pages
BRANDS = ('M1+ Music', 'Tidal', 'Pod') + pod_pages.GUARD_FILES + (pod_pages.FOLDER_LABEL,) + pod_pages.SETTING_FILES + pod_pages.pcregion.NAMES + pod_pages.GRAPH_TEXTS + pod_pages.SLIDER_TEXTS + ('Q',) + tuple(f'{p}%' for p in pod_pages.CHGLIMIT_VALUES) + pod_pages.LIGHTTIME_VALUES[1:] + pod_pages.SHUTDOWN_VALUES[1:]   # shown as they are, no key (the Settings Files labels are file names)

for _rgb_label in ('Sample Rate', 'Sample Rate Theme', 'Reference', 'Gentle Breathe', 'Candle', 'Ocean Wave',
                   'Forest', 'Nebula', 'Heartbeat', 'Focus', 'Lighthouse', 'Ember Fade', 'Lighting Reminders',
                   'Volume-based Brightness', 'Off keeps the lamp at maximum brightness.',
                   'Yellow above 75; amber at battery 20/10/5.'):
    TEXT.setdefault(_rgb_label, {locale: _rgb_label for locale in LOCALES})
KEYS = sorted(TEXT)


def key_for(english):
    """The tr_text key of an English text we show: itself (our keys), the stock key whose en_US text it is, or None
    for a brand name, which stays a plain text."""
    if english in TEXT: return english
    for k, v in STOCK.items():
        if v == english: return k
    assert english in BRANDS, f'no translation key for {english!r}'
    return None


def text_prop(english):
    """The (property, value) pair an asset widget shows `english` with: tr_text with its key, or text for a brand."""
    key = key_for(english)
    return ('tr_text', key) if key else ('text', english)


def shown_english(w):
    """The English text of an asset widget (tr_text or text)."""
    k = w.get('tr_text')
    return english(k) if k is not None else w.get('text')


def table_for(locale):
    """The language a table file holds: a stub table holds its twin's."""
    return TWINS.get(locale, locale)


# Wi-Fi and Bluetooth together (tools/coex.py, docs/modules/overlays.md "Wi-Fi and Bluetooth together"): stock's two switch-on questions (msg_wifi_open, msg_bt_open: "turn the other radio off first?") become one warning,
# the same text under both keys, shown before the requested radio is switched on with the other left on. Replaces the stock value in the 13 tables the language menu reaches.
COEX_KEYS = ('msg_wifi_open', 'msg_bt_open')
COEX_TEXT = {
    'en_US': 'Bluetooth audio may stutter while Wi-Fi is on.',
    'zh_CN': '同时使用 Wi-Fi 和蓝牙时，蓝牙音频可能断续。',
    'zh_HK': '同時使用 Wi-Fi 和藍牙時，藍牙音訊可能斷續。',
    'ja_JP': 'Wi-Fi がオンの間、Bluetooth の音声が途切れることがあります。',
    'ko_KR': 'Wi-Fi가 켜져 있으면 Bluetooth 오디오가 끊길 수 있습니다.',
    'fr_FR': "L'audio Bluetooth peut saccader lorsque le Wi-Fi est activé.",
    'ge_DE': 'Die Bluetooth-Wiedergabe kann bei aktivem Wi-Fi stottern.',
    'sp_ES': 'El audio Bluetooth puede entrecortarse con el Wi-Fi activado.',
    'it_IT': "L'audio Bluetooth può interrompersi mentre il Wi-Fi è attivo.",
    'th_TH': 'เสียง Bluetooth อาจสะดุดขณะเปิด Wi-Fi',
    'po_PL': 'Dźwięk Bluetooth może się zacinać, gdy Wi-Fi jest włączone.',
    'ru_RU': 'Звук Bluetooth может прерываться, пока включён Wi-Fi.',
    'uk_UK': 'Звук Bluetooth може уривчастися, поки ввімкнено Wi-Fi.',
}


def coex_tables(tables):
    """tables: {locale: [(key, value), ...]} -> the same with the shared warning under both stock keys (a stub table has neither key and is unchanged)."""
    return {loc: [(k, COEX_TEXT[table_for(loc)] if k in COEX_KEYS else v) for k, v in items] for loc, items in tables.items()}



# Stock texts the stock tables leave in English (or in another language, or out). A block of keys that came with later firmware has the English text in the ten tables
# besides en_US, zh_CN and zh_HK (Now Playing's Look up Album / Look up Artist, the digital filters, the format-card and New playlist messages, the sort orders ...);
# a few more are English, misspelt or another language's in single tables, and it_IT lacks `fav` and `songer`. Each (key, table) below replaces the stock value
# (or adds the missing entry); en_US, zh_CN and zh_HK are never touched. Found by comparing every table with en_US; tools/mod_strings.py applies them.
_FL = ('ja_JP', 'ko_KR', 'fr_FR', 'ge_DE', 'sp_ES', 'it_IT', 'th_TH', 'po_PL', 'ru_RU', 'uk_UK')


def _f(key, *texts, **by):
    """key -> {locale: text}: `texts` are the ten _FL tables in order (None: that table keeps the stock text; none at all for a key fixed in single tables), `by` names single tables."""
    assert len(texts) in (0, len(_FL)) and set(by) <= set(_FL), key
    d = {loc: t for loc, t in zip(_FL, texts) if t is not None}; d.update(by)
    return key, d


def _own(key, text, *locs):
    """A stock key that takes the translations of one of our own texts (all ten tables, or the ones named)."""
    return key, {loc: TEXT[text][loc] for loc in (locs or _FL)}


#       ja_JP    ko_KR    fr_FR    ge_DE    sp_ES    it_IT    th_TH    po_PL    ru_RU    uk_UK
STOCK_FIX = dict([
    # Now Playing's More sheet (patch/playmore.c: the stock rows listitem4 and listitem5) and the stock messages of a track without the tag
    _f('player_albuminfo', 'アルバムを表示', '앨범 보기', "Voir l'album", 'Album anzeigen', 'Ver álbum', "Vai all'album", 'ดูอัลบั้ม', 'Pokaż album', 'Показать альбом', 'Показати альбом'),
    _f('player_songerinfo', 'アーティストを表示', '아티스트 보기', "Voir l'artiste", 'Künstler anzeigen', 'Ver artista', "Vai all'artista", 'ดูศิลปิน', 'Pokaż wykonawcę', 'Показать исполнителя', 'Показати виконавця'),
    _f('msg_notalbuminfo', 'この曲にはアルバム情報がありません', '이 곡에는 앨범 정보가 없습니다', "Ce fichier n'a pas d'info d'album", 'Diese Datei enthält keine Albumdaten', 'Este archivo no tiene datos de álbum',
       "Questo file non ha dati sull'album", 'ไฟล์นี้ไม่มีข้อมูลอัลบั้ม', 'Ten plik nie ma danych albumu', 'В файле нет данных об альбоме', 'У файлі немає даних про альбом'),
    _f('msg_notsongerinfo', 'この曲にはアーティスト情報がありません', '이 곡에는 아티스트 정보가 없습니다', "Ce fichier n'a pas d'info d'artiste", 'Diese Datei enthält keine Künstlerdaten', 'Este archivo no tiene datos de artista',
       "Questo file non ha dati sull'artista", 'ไฟล์นี้ไม่มีข้อมูลศิลปิน', 'Ten plik nie ma danych wykonawcy', 'В файле нет данных об исполнителе', 'У файлі немає даних про виконавця'),
    # playlists (the New playlist keyboard's placeholder and its message box: STOCK above), the keyboards' placeholders, Search's hint
    _f('msg_newplaylists', 'プレイリスト名を入力', '플레이리스트 이름 입력', 'Nom de la playlist', 'Name der Playlist eingeben', 'Nombre de la lista', 'Nome della playlist', 'ป้อนชื่อเพลย์ลิสต์', 'Wpisz nazwę playlisty',
       'Введите название плейлиста', 'Введіть назву плейлиста'),
    _f('msg_playlistexist', 'プレイリストはすでに存在します', '이미 있는 플레이리스트입니다', 'La playlist existe déjà', 'Playlist existiert bereits', 'La lista ya existe', 'La playlist esiste già', 'มีเพลย์ลิสต์นี้อยู่แล้ว',
       'Playlista już istnieje', 'Плейлист уже существует', 'Плейлист уже існує'),
    _f('keyboard_keyword', 'キーワードを入力', '키워드 입력', 'Saisir un mot-clé', 'Suchbegriff eingeben', 'Introduce una palabra clave', 'Inserisci una parola chiave', 'ป้อนคำค้นหา', 'Wpisz słowo kluczowe',
       'Введите ключевое слово', 'Введіть ключове слово'),
    _f('keyboard_netname', 'ネットワーク名を入力', '네트워크 이름 입력', 'Saisir le nom du réseau', 'Netzwerknamen eingeben', 'Introduce el nombre de la red', 'Inserisci il nome della rete', 'ป้อนชื่อเครือข่าย', 'Wpisz nazwę sieci',
       'Введите имя сети', 'Введіть назву мережі'),
    _f('keyboard_password', 'パスワードを入力', '비밀번호 입력', 'Saisir le mot de passe', 'Passwort eingeben', 'Introduce la contraseña', 'Inserisci la password', 'ป้อนรหัสผ่าน', 'Wpisz hasło', 'Введите пароль', 'Введіть пароль'),
    _f('search_tips1', '曲、アーティスト、アルバムを検索', '노래, 아티스트, 앨범 검색', 'Titres, artistes, albums', 'Titel, Künstler, Alben suchen', 'Buscar canciones, artistas, álbumes', 'Cerca brani, artisti, album',
       'ค้นหาเพลง ศิลปิน อัลบั้ม', 'Szukaj utworów, wykonawców, albumów', 'Поиск песен, исполнителей, альбомов', 'Пошук пісень, виконавців, альбомів'),
    # the sort orders
    _f('title_sort', '並び順', '정렬 순서', 'Ordre de tri', 'Sortierung', 'Orden de la lista', 'Ordinamento', 'การเรียงลำดับ', 'Sortowanie', 'Сортировка', 'Сортування'),
    _f('sort_alphabet', 'アルファベット順', '알파벳순', 'Alphabétique', 'Alphabetisch', 'Alfabético', 'Alfabetico', 'ตามตัวอักษร', 'Alfabetycznie', 'По алфавиту', 'За алфавітом'),
    _own('sort_filename', 'File Name'),
    _f('sort_format', 'ファイル形式', '파일 형식', 'Format de fichier', 'Dateiformat', 'Formato de archivo', 'Formato file', 'รูปแบบไฟล์', 'Format pliku', 'Формат файла', 'Формат файлу'),
    _f('sort_time_asc', '追加日時 (昇順)', '추가한 시간 (오름차순)', "Date d'ajout (croissant)", 'Hinzugefügt (aufsteigend)', 'Fecha de adición (ascendente)', 'Data di aggiunta (crescente)', 'เวลาที่เพิ่ม (น้อยไปมาก)',
       'Data dodania (rosnąco)', 'Дата добавления (по возрастанию)', 'Дата додавання (за зростанням)'),
    _f('sort_time_desc', '追加日時 (降順)', '추가한 시간 (내림차순)', "Date d'ajout (décroissant)", 'Hinzugefügt (absteigend)', 'Fecha de adición (descendente)', 'Data di aggiunta (decrescente)', 'เวลาที่เพิ่ม (มากไปน้อย)',
       'Data dodania (malejąco)', 'Дата добавления (по убыванию)', 'Дата додавання (за спаданням)'),
    # formatting the card
    _f('system_formatcard', 'カードをフォーマット', '카드 포맷', 'Formater la carte', 'Karte formatieren', 'Formatear tarjeta', 'Formatta scheda', 'ฟอร์แมตการ์ด', 'Formatuj kartę', 'Форматировать карту', 'Форматувати картку'),
    _f('msg_checkformat', 'カードをフォーマットしますか?', '카드를 포맷할까요?', 'Formater la carte ?', 'Karte formatieren?', '¿Formatear la tarjeta?', 'Formattare la scheda?', 'ฟอร์แมตการ์ดหรือไม่', 'Sformatować kartę?',
       'Форматировать карту?', 'Форматувати картку?'),
    _f('msg_warnformt', 'すべてのデータが削除されます!', '모든 데이터가 삭제됩니다!', 'Toutes les données seront effacées !', 'Alle Daten werden gelöscht!', '¡Se borrarán todos los datos!', 'Tutti i dati verranno eliminati!',
       'ข้อมูลทั้งหมดจะถูกลบ!', 'Wszystkie dane zostaną usunięte!', 'Все данные будут удалены!', 'Усі дані буде видалено!'),
    _f('msg_formating', 'フォーマット中', '포맷 중', 'Formatage en cours', 'Formatierung läuft', 'Formateando', 'Formattazione in corso', 'กำลังฟอร์แมต', 'Formatowanie', 'Форматирование', 'Форматування'),
    _f('msg_formatsuccess', 'フォーマットが完了しました', '포맷 완료', 'Formatage terminé', 'Formatierung abgeschlossen', 'Formateo completado', 'Formattazione completata', 'ฟอร์แมตสำเร็จ', 'Formatowanie zakończone',
       'Форматирование завершено', 'Форматування завершено'),
    _f('msg_formaterr', 'フォーマットに失敗しました', '포맷 실패', 'Échec du formatage', 'Formatierung fehlgeschlagen', 'Error al formatear', 'Formattazione non riuscita', 'ฟอร์แมตไม่สำเร็จ', 'Formatowanie nie powiodło się',
       'Ошибка форматирования', 'Помилка форматування'),
    # Bluetooth
    _f('msg_btinit_run', 'Bluetoothを起動中', 'Bluetooth 시작 중', 'Démarrage du Bluetooth', 'Bluetooth wird gestartet', 'Iniciando Bluetooth', 'Avvio del Bluetooth', 'กำลังเริ่ม Bluetooth', 'Uruchamianie Bluetooth',
       'Запуск Bluetooth', 'Запуск Bluetooth'),
    _f('msg_unpairing', 'ペアリングを解除しますか?', '페어링을 해제할까요?', 'Dissocier ?', 'Kopplung aufheben?', '¿Desemparejar?', "Annullare l'abbinamento?", 'ยกเลิกการจับคู่หรือไม่', 'Anulować sparowanie?', 'Отменить сопряжение?', 'Скасувати спарення?'),
    _f('msg_disonnectbt', 'Bluetoothデバイスを切断してください', 'Bluetooth 기기 연결을 해제하세요', "Veuillez déconnecter l'appareil Bluetooth", 'Bitte Bluetooth-Gerät trennen', 'Desconecta el dispositivo Bluetooth',
       'Disconnetti il dispositivo Bluetooth', 'โปรดยกเลิกการเชื่อมต่ออุปกรณ์ Bluetooth', 'Odłącz urządzenie Bluetooth', 'Отключите устройство Bluetooth', "Від'єднайте пристрій Bluetooth"),
    # system settings
    _own('about_ipaddr', 'IP Address'),
    _f('rotate_0', '0度', '0도', '0 degré', '0 Grad', '0 grados', '0 gradi', '0 องศา', '0 stopni', '0 градусов', '0 градусів'),
    _f('rotate_180', '180度', '180도', '180 degrés', '180 Grad', '180 grados', '180 gradi', '180 องศา', '180 stopni', '180 градусов', '180 градусів'),
    _f('screenlock_timeshow', 'ロック画面の時刻表示', '잠금 화면 시간 표시', "Heure sur l'écran verrouillé", 'Uhrzeit auf Sperrbildschirm', 'Hora en pantalla de bloqueo', 'Ora sulla schermata di blocco', 'แสดงเวลาบนหน้าจอล็อก',
       'Godzina na ekranie blokady', 'Время на экране блокировки', 'Час на екрані блокування'),
    _f('sset_atmosphereled', 'アンビエントライト設定', '무드등 설정', "Éclairage d'ambiance", 'Ambientelicht', 'Luz ambiental', 'Luce ambiente', 'ไฟบรรยากาศ', 'Podświetlenie nastrojowe', 'Декоративная подсветка', 'Декоративне підсвічування'),
    _f('ledfollowscreen', '画面に連動', '화면과 연동', "Suivre l'écran", 'Dem Bildschirm folgen', 'Seguir la pantalla', 'Segui lo schermo', 'ตามหน้าจอ', 'Jak ekran', 'Как экран', 'Як екран'),
    # the digital filters (Thai keeps the English names: no Thai manual or review was found that translates them)
    _f('filter_linearfast', 'リニアフェーズ高速ロールオフ', '선형 위상 고속 롤오프', 'Phase linéaire, atténuation rapide', 'Linearphasig, steiler Roll-off', 'Fase lineal, caída rápida', 'Fase lineare, roll-off rapido', None,
       'Faza liniowa, szybki spadek', 'Линейная фаза, быстрый спад', 'Лінійна фаза, швидкий спад'),
    _f('filter_linearslow', 'リニアフェーズ低速ロールオフ', '선형 위상 저속 롤오프', 'Phase linéaire, atténuation lente', 'Linearphasig, flacher Roll-off', 'Fase lineal, caída lenta', 'Fase lineare, roll-off lento', None,
       'Faza liniowa, wolny spadek', 'Линейная фаза, медленный спад', 'Лінійна фаза, повільний спад'),
    _f('filter_minifast', 'ミニマムフェーズ高速ロールオフ', '최소 위상 고속 롤오프', 'Phase minimale, atténuation rapide', 'Minimalphasig, steiler Roll-off', 'Fase mínima, caída rápida', 'Fase minima, roll-off rapido', None,
       'Faza minimalna, szybki spadek', 'Минимальная фаза, быстрый спад', 'Мінімальна фаза, швидкий спад'),
    _f('filter_minislow', 'ミニマムフェーズ低速ロールオフ', '최소 위상 저속 롤오프', 'Phase minimale, atténuation lente', 'Minimalphasig, flacher Roll-off', 'Fase mínima, caída lenta', 'Fase minima, roll-off lento', None,
       'Faza minimalna, wolny spadek', 'Минимальная фаза, медленный спад', 'Мінімальна фаза, повільний спад'),
    _f('filter_minimum', 'ミニマムフェーズ', '최소 위상', 'Phase minimale', 'Minimalphasig', 'Fase mínima', 'Fase minima', None, 'Faza minimalna', 'Минимальная фаза', 'Мінімальна фаза'),
    _f('filter_apodizing', 'アポダイジング高速ロールオフ', '아포다이징 고속 롤오프', 'Apodisant, atténuation rapide', 'Apodisierend, steiler Roll-off', 'Apodizante, caída rápida', 'Apodizzante, roll-off rapido', None,
       'Apodyzujący, szybki spadek', 'Аподизирующий, быстрый спад', 'Аподизуючий, швидкий спад'),
    _f('filter_brickwall', 'ブリックウォール', '브릭월 필터', 'Filtre brickwall', 'Brickwall-Filter', 'Filtro brickwall', 'Filtro brickwall', None, 'Filtr brickwall', 'Фильтр brickwall', 'Фільтр brickwall'),
    _f('filter_corrminifast', 'ミニマムフェーズ高速ロールオフ (補正)', '보정 최소 위상 고속 롤오프', 'Phase minimale corrigée, atténuation rapide', 'Minimalphasig korrigiert, steiler Roll-off', 'Fase mínima corregida, caída rápida',
       'Fase minima corretta, roll-off rapido', None, 'Faza minimalna skorygowana, szybki spadek', 'Скорректированная минимальная фаза, быстрый спад', 'Скоригована мінімальна фаза, швидкий спад'),
    _f('filter_linearsfastapodizing', 'リニアフェーズ高速ロールオフ (アポダイジング)', '선형 위상 고속 롤오프 아포다이징', 'Phase linéaire, atténuation rapide, apodisant', 'Linearphasig, steiler Roll-off, apodisierend',
       'Fase lineal, caída rápida, apodizante', 'Fase lineare, roll-off rapido, apodizzante', None, 'Faza liniowa, szybki spadek, apodyzujący', 'Линейная фаза, быстрый спад, аподизирующий',
       'Лінійна фаза, швидкий спад, аподизуючий'),
    _f('filter_linearsfastripple', 'リニアフェーズ高速ロールオフ (低リップル)', '선형 위상 고속 롤오프 저리플', 'Phase linéaire, atténuation rapide, faible ondulation', 'Linearphasig, steiler Roll-off, geringe Welligkeit',
       'Fase lineal, caída rápida, bajo rizado', 'Fase lineare, roll-off rapido, basso ripple', None, 'Faza liniowa, szybki spadek, niskie tętnienia', 'Линейная фаза, быстрый спад, низкие пульсации',
       'Лінійна фаза, швидкий спад, низькі пульсації'),
    _f('filter_minimumdispersion', 'ミニマムフェーズ低速ロールオフ (低分散)', '최소 위상 저속 롤오프 저분산', 'Phase minimale, atténuation lente, faible dispersion', 'Minimalphasig, flacher Roll-off, geringe Dispersion',
       'Fase mínima, caída lenta, baja dispersión', 'Fase minima, roll-off lento, bassa dispersione', None, 'Faza minimalna, wolny spadek, niska dyspersja', 'Минимальная фаза, медленный спад, низкая дисперсия',
       'Мінімальна фаза, повільний спад, низька дисперсія'),
    # single tables: English left in place
    _f('gain_high', ja_JP='高ゲイン', ko_KR='높음', it_IT='Alto'),
    _f('gain_low', ja_JP='低ゲイン', ko_KR='낮음', it_IT='Basso'),
    _own('powerm_saver', 'Auto-Shutdown', 'ja_JP'),
    _f('pset_gapless', ja_JP='ギャップレス再生'),
    _f('sset_carmode', ja_JP='車載モード'),
    _f('memplay_off', ko_KR='끄기'),
    _own('recentadd', 'Recently Added', 'ko_KR'),
    _f('msg_btabnormal', th_TH='Bluetooth ผิดปกติ'),
    _own('msg_notmemory', 'Not enough memory', 'ge_DE', 'sp_ES', 'th_TH', 'po_PL', 'uk_UK'),
    _f('player_multiple', sp_ES='Velocidad de reproducción', it_IT='Velocità di riproduzione'),
    _f('player_onlinesearch', ge_DE='Cover und Songtext laden'),
    _f('playmode_listplay', it_IT='Riproduzione in ordine'),
    _f('powerm_standby', it_IT='Standby automatico'),
    _f('sset_display', it_IT='Impostazioni schermo'),
    _f('system_scrotate', it_IT='Rotazione schermo'),
    _f('sset_doublewake', it_IT='Doppio tocco per accendere lo schermo', uk_UK='Подвійний дотик для ввімкнення екрана'),
    _f('usb_disconnect', it_IT='USB disconnesso'),
    _f('scover_lyric', po_PL='Tekst'),
    # single tables: another language's text (ru_RU and uk_UK hold each other's; Thai has the Spanish word; ru_RU's Artist is Ukrainian), a misspelling (po_PL "Astysta"), and the two keys it_IT lacks
    _f('msg_actionnotsupport', ge_DE='Nicht lokale Titel werden derzeit nicht unterstützt', it_IT='Brani non locali, attualmente non supportati', ru_RU='Не локальные файлы временно не поддерживаются',
       uk_UK='Не локальні файли тимчасово не підтримуються'),
    _f('dsdmode_native', th_TH='Native'),
    _own('songer', 'Artist', 'it_IT', 'po_PL', 'ru_RU'),
    _own('fav', 'Favorites', 'it_IT'),
])


def fix_tables(tables):
    """tables: {locale: [(key, value), ...]} -> the same with STOCK_FIX's texts in place of the stock values; a key a reachable table lacks is added in sorted
    position (a stub table keeps its eleven entries: only a key it has is replaced, with its twin's text)."""
    out = {}
    for loc, items in tables.items():
        fix = {k: by[table_for(loc)] for k, by in STOCK_FIX.items() if table_for(loc) in by}
        have = {k for k, _ in items}
        new = [(k, fix.get(k, v)) for k, v in items] + ([(k, v) for k, v in fix.items() if k not in have] if loc in LOCALES else [])
        out[loc] = sorted(new, key=lambda kv: kv[0].encode())
    return out


def built_tables(tables):
    """The shipped tables of the stock ones: our keys added, the untranslated stock texts translated, the Wi-Fi + Bluetooth warning."""
    return coex_tables(fix_tables(add_to_tables(tables)))


def tr(locale, key, stock=None):
    """What a widget with tr_text `key` shows in `locale`. Our keys: the TEXT entry. A stock key: the entry of `stock`
    (a {locale: {key: text}} read from the shipped tables), else the key itself, as locale_info_tr returns it."""
    if key in TEXT: return TEXT[key][table_for(locale)]
    if stock is not None: return stock.get(locale, {}).get(key, key)
    return key


def add_to_tables(tables):
    """tables: {locale: [(key, value), ...]} (awtk_strings.items) -> the same with our keys added, sorted for the
    binary search. Refuses a table that already has one of our keys."""
    out = {}
    for loc, items in tables.items():
        have = {k for k, _ in items}
        assert not have & set(TEXT), f'{loc}: already has {sorted(have & set(TEXT))}'
        out[loc] = sorted(items + [(k, TEXT[k][table_for(loc)]) for k in TEXT], key=lambda kv: kv[0].encode())
    return out
