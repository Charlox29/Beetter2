# Beetter — Système de surveillance de ruches

Beetter est une plateforme IoT de bout en bout pour la surveillance de ruches. Des nœuds capteurs transmettent température et humidité via LoRa ; un Raspberry Pi reçoit les données et expose un dashboard local ; un serveur distant agrège les données de plusieurs Raspberry Pi ; une application Android donne un accès mobile au serveur distant.

## Architecture

```
  Nœuds capteurs LoRa
        │  (paquets radio LoRa)
        ▼
  ┌──────────────────────────┐
  │  Raspberry Pi — Web App  │  Flask :5000
  │  • Récepteur LoRa        │──────────────── InfluxDB (local)
  │  • Dashboard local       │                 PostgreSQL (local)
  │  • Scheduler (push data) │
  └──────────┬───────────────┘
             │  POST /api/push  (Bearer API key)
             ▼
  ┌──────────────────────────┐
  │  Serveur distant         │  Flask :5001
  │  • Dashboard agrégé      │──────────────── InfluxDB (distant)
  │  • Gestion des API keys  │                 PostgreSQL (distant)
  │  • API REST mobile       │
  └──────────┬───────────────┘
             │  API REST  (Bearer session token)
             ▼
       Application Android
```

---

## Composants

### 1. Application web (`app/`)

L'application qui tourne sur le Raspberry Pi. Elle reçoit les relevés des capteurs depuis le récepteur LoRa, les stocke dans une instance InfluxDB locale, et fournit un dashboard web pour la gestion locale. Elle pousse également périodiquement les données agrégées vers le serveur distant.

**Stack** : Flask 3, PostgreSQL (utilisateurs/ruches), InfluxDB 2 (données time-series), APScheduler, Gunicorn.

**Fonctionnalités principales** :
- Inscription/connexion avec accès basé sur les rôles (admin / viewer)
- Création et gestion des ruches (nom, localisation, configuration LoRa)
- Graphes en temps réel (1 h / 6 h / 24 h / 7 j / 30 j)
- Configuration d'un ou plusieurs serveurs distants vers lesquels pousser les données
- Endpoint REST (`POST /api/data`) pour le récepteur LoRa

**Variables d'environnement** (voir `app/.env.example`) :

| Variable | Description |
|---|---|
| `SECRET_KEY` | Clé secrète de session Flask (mettre une longue chaîne aléatoire) |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL |
| `INFLUXDB_URL` | URL de base InfluxDB |
| `INFLUXDB_TOKEN` | Token d'authentification InfluxDB |
| `INFLUXDB_ORG` | Nom de l'organisation InfluxDB |
| `INFLUXDB_BUCKET` | Nom du bucket InfluxDB |

---

### 2. Serveur distant (`server/`)

Le serveur d'agrégation centralisé. Les applications Raspberry Pi lui poussent des lots de données capteurs ; l'application Android l'interroge pour afficher les dashboards.

**Stack** : Flask 3, PostgreSQL (utilisateurs/API keys/sessions), InfluxDB 2, Gunicorn.

**Fonctionnalités principales** :
- Dashboard web affichant toutes les ruches de tous les Raspberry Pi connectés
- Gestion des API keys (génération / révocation des clés utilisées par les apps Raspberry Pi)
- API REST mobile avec authentification par token de session (expiration 30 jours)
- Réception des données poussées via `POST /api/push` (Bearer API key)

**Endpoints REST** :

| Méthode | Chemin | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | Connexion mobile, retourne un token de session |
| `POST` | `/api/auth/logout` | Bearer token | Invalide la session |
| `GET` | `/api/beehives` | Bearer token | Liste les ruches avec les dernières valeurs |
| `GET` | `/api/beehives/<id>/data` | Bearer token | Données graphe (`?range=24h`) |
| `POST` | `/api/push` | Bearer API key | Réception d'un lot depuis le Raspberry Pi |

**Variables d'environnement** (voir `server/.env.example`) :

| Variable | Description |
|---|---|
| `SECRET_KEY` | Clé secrète de session Flask (longue chaîne aléatoire, **différente** de celle de l'app web) |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL |
| `INFLUXDB_URL` | URL de base InfluxDB |
| `INFLUXDB_TOKEN` | Token d'authentification InfluxDB |
| `INFLUXDB_ORG` | Nom de l'organisation InfluxDB |
| `INFLUXDB_BUCKET` | Nom du bucket InfluxDB |

---

### 3. Récepteur LoRa (`lora/`)

Un script Python qui tourne sur le Raspberry Pi aux côtés de l'application web. Il écoute les paquets des nœuds capteurs LoRa et transmet les relevés à l'API REST de l'application web locale.

Le script est livré sous forme de **stub** — l'initialisation matérielle (`init_lora`) et l'appel de réception (`receive_packet`) sont des placeholders. Remplace-les par ta vraie bibliothèque LoRa.

**Bibliothèques compatibles** (remplace le bloc stub dans `receiver.py`) :
- `adafruit-circuitpython-rfm9x` — SX127x via CircuitPython / Blinka
- `pyLoRa` / `SX127x` — SX127x brut via GPIO + SPI du Raspberry Pi
- `pyserial` + RAK811 / Dragino — module LoRaWAN à commandes AT via UART

**Format de paquet attendu des nœuds capteurs** (JSON, 255 octets max) :
```json
{"id": 1, "t": 34.7, "h": 62.1}
```

**Variables d'environnement** :

| Variable | Défaut | Description |
|---|---|---|
| `BEETTER_URL` | `http://localhost:5000` | URL de base de l'application web |
| `LORA_FREQUENCY` | `868.0` | Fréquence radio en MHz |
| `LORA_SF` | `7` | Spreading factor (7–12) |
| `LORA_BW` | `125000` | Largeur de bande en Hz |

**Lancement** :
```bash
cd lora
pip install -r requirements.txt
python receiver.py
# ou avec des valeurs personnalisées
BEETTER_URL=http://localhost:5000 LORA_FREQUENCY=868.0 python receiver.py
```

---

### 4. Application Android (`android/`)

Une application Android native qui se connecte au serveur distant et affiche les données des ruches en direct.

**Stack** : Kotlin, Jetpack Compose, Retrofit 2 + OkHttp, Gson, DataStore, WorkManager.

**Fonctionnalités** :
- Connexion avec l'URL du serveur, le nom d'utilisateur et le mot de passe
- Dashboard listant toutes les ruches avec la dernière température et humidité
- Écran de détail d'une ruche avec graphes interactifs (plage de temps sélectionnable)
- Alertes en arrière-plan via WorkManager (seuils min/max configurables)
- Paramètres : seuils de notification, déconnexion

**Prérequis** :
- Android 8.0 (API 26) ou supérieur
- Un serveur distant en cours d'exécution, accessible sur le réseau

---

### 5. Simulateur (`tools/simulate.py`)

Un outil de développement qui envoie de faux relevés de capteurs réalistes à l'application web, en remplacement du matériel LoRa réel.

> **Note** : la ruche doit déjà exister dans la base de données de l'application web (crée-la via l'interface d'abord). Le simulateur cible les ruches par leur ID en base.

```bash
cd tools
pip install requests

# Mode live — un relevé toutes les 10 secondes, ruche ID 1
python simulate.py

# Plusieurs ruches
python simulate.py --ids 1 2 3

# Intervalle et URL personnalisés
python simulate.py --url http://raspberrypi.local:5000 --interval 5

# Mode burst — remplit 200 points historiques répartis sur les 24 dernières heures
python simulate.py --burst 200
```

---

## Déploiement

### Application web — Raspberry Pi

**Prérequis** : Docker et Docker Compose installés sur le Raspberry Pi.

1. Copie et configure le fichier d'environnement :
   ```bash
   cd app
   cp .env.example .env
   nano .env   # au minimum, renseigne SECRET_KEY et INFLUXDB_TOKEN
   ```

2. Build et démarrage :
   ```bash
   docker compose up -d --build
   ```

3. Ouvre `http://<ip-du-raspberry-pi>:5000` dans un navigateur.  
   Le premier compte inscrit reçoit automatiquement le rôle **admin**.

4. Démarre le récepteur LoRa (tourne directement sur le Pi, hors Docker) :
   ```bash
   cd lora
   pip install -r requirements.txt
   BEETTER_URL=http://localhost:5000 python receiver.py
   ```

**Lancer le récepteur LoRa en tant que service systemd** :

Crée `/etc/systemd/system/beetter-lora.service` :
```ini
[Unit]
Description=Beetter LoRa Receiver
After=network.target

[Service]
WorkingDirectory=/home/pi/beetter/lora
ExecStart=/usr/bin/python3 /home/pi/beetter/lora/receiver.py
Environment=BEETTER_URL=http://localhost:5000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now beetter-lora
```

---

### Serveur distant

**Prérequis** : un serveur Linux avec Docker et Docker Compose.

1. Copie et configure le fichier d'environnement :
   ```bash
   cd server
   cp .env.example .env
   nano .env   # renseigne SECRET_KEY (différent de celui de l'app web) et les identifiants InfluxDB
   ```

2. Build et démarrage :
   ```bash
   docker compose up -d --build
   ```

3. Ouvre `http://<ip-du-serveur>:5001`. Inscris un compte (le premier est admin).

4. Génère une API key : **Dashboard → API Keys → New key**.  
   Copie cette clé — tu en auras besoin lors de la configuration de l'application web.

---

### Connexion de l'application web au serveur distant

1. Ouvre l'application web sur `http://<ip-du-raspberry-pi>:5000` et connecte-toi.
2. Va dans **Paramètres → Ajouter un serveur**.
3. Renseigne :
   - **URL** : `http://<ip-du-serveur>:5001`
   - **API key** : la clé générée sur le serveur
   - **Intervalle de push** : fréquence d'envoi (en minutes)
4. Sauvegarde. L'application web commence à pousser les données automatiquement au prochain tick du scheduler.  
   Le badge de statut passe au **vert** dès que le premier push réussit.

---

### Application Android

#### Build

**Prérequis** : Android Studio Hedgehog (2023.1) ou ultérieur, ou un environnement en ligne de commande avec JDK 17+.

**Depuis Android Studio** :
1. Ouvre le dossier `android/` comme projet.
2. Attends la synchronisation Gradle.
3. **Build → Build Bundle(s) / APK(s) → Build APK(s)**.  
   Résultat : `android/app/build/outputs/apk/debug/app-debug.apk`

**Depuis la ligne de commande** :
```bash
cd android

# APK de debug
./gradlew assembleDebug          # Linux / macOS
gradlew.bat assembleDebug        # Windows

# APK de release (nécessite un keystore de signature)
./gradlew assembleRelease
```

#### Installation

```bash
# Via adb (débogage USB activé sur l'appareil)
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

Ou installe l'APK directement sur l'appareil (active *Installer des applications inconnues* dans les Paramètres).

#### Premier lancement

1. Entre l'URL du serveur distant — ex. `http://192.168.1.10:5001`.
2. Entre le nom d'utilisateur et le mot de passe inscrits sur le serveur distant.
3. Appuie sur **Se connecter**.

---

## Développement — démarrage rapide (sans Docker)

```bash
# Application web
cd app
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # édite DATABASE_URL / INFLUXDB_* selon tes besoins
flask run --debug

# Remplir les graphes avec de fausses données (après avoir créé une ruche dans l'interface)
cd tools
python simulate.py --burst 200

# Serveur distant
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask run --debug --port 5001
```

---

## Structure du projet

```
beetter/
├── app/                  # Application web Raspberry Pi (Flask :5000)
│   ├── blueprints/
│   │   ├── api/          # POST /api/data  — ingest LoRa
│   │   ├── auth/         # Connexion / inscription / déconnexion
│   │   ├── beehives/     # CRUD des ruches
│   │   ├── dashboard/    # Page d'accueil
│   │   ├── settings/     # Configuration des serveurs distants
│   │   └── utils/        # Helpers InfluxDB, scheduler de push
│   ├── templates/
│   ├── compose.yml
│   └── Dockerfile
├── server/               # Serveur d'agrégation distant (Flask :5001)
│   ├── blueprints/
│   │   ├── api/          # API REST mobile & push
│   │   ├── auth/
│   │   ├── dashboard/
│   │   └── utils/        # Helpers InfluxDB
│   ├── templates/
│   ├── compose.yml
│   └── Dockerfile
├── android/              # Application Android (Kotlin + Jetpack Compose)
│   └── app/src/main/java/fr/esiee/beetter/
│       ├── data/         # Retrofit, modèles, DataStore, repository
│       ├── ui/           # Écrans et ViewModels
│       └── worker/       # Worker d'alertes en arrière-plan (WorkManager)
├── lora/                 # Récepteur LoRa (stub + guide d'intégration matérielle)
│   ├── receiver.py
│   └── requirements.txt
└── tools/
    └── simulate.py       # Simulateur de données capteurs pour le développement
```