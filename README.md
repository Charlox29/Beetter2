# Beetter — Système de surveillance de ruches

Beetter est une plateforme IoT de bout en bout pour la surveillance de ruches. Chaque ruche est équipée de **nœuds capteurs** (un module intérieur et un module extérieur) qui relèvent température, humidité, niveau sonore et luminosité, puis transmettent ces mesures par radio **LoRa**. Un **Raspberry Pi** reçoit les paquets, stocke les relevés en local et expose un dashboard. Il pousse périodiquement les données vers un **serveur distant** qui agrège plusieurs Raspberry Pi. Enfin, une **application Android** interroge ce serveur pour offrir un accès mobile aux ruches.

```
Nœud intérieur            Nœud extérieur
(temp/hum + micro)        (temp/hum + micro + photorésistance)
        └──────────┬───────────────┘
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

## Capteurs

C'est le cœur du système : chaque ruche surveillée porte **deux nœuds capteurs**, un à l'intérieur et un à l'extérieur. Voici l'inventaire exact du matériel et les grandeurs relevées.

| Emplacement | Capteur | Grandeur mesurée | Unité |
|---|---|---|---|
| Intérieur de la ruche | Capteur température/humidité | Température intérieure | °C |
| Intérieur de la ruche | Capteur température/humidité | Humidité intérieure | % |
| Intérieur de la ruche | Microphone | Son intérieur — fréquence du pic d'amplitude | Hz |
| Intérieur de la ruche | Microphone | Son intérieur — amplitude de ce pic | (relative) |
| Extérieur | Capteur température/humidité | Température extérieure | °C |
| Extérieur | Capteur température/humidité | Humidité extérieure | % |
| Extérieur | Microphone | Son extérieur — fréquence du pic d'amplitude | Hz |
| Extérieur | Microphone | Son extérieur — amplitude de ce pic | (relative) |
| Extérieur | Photorésistance | Luminosité | (lux / relative) |

Chaque **microphone** remonte donc **deux valeurs** : la fréquence du pic d'amplitude et l'amplitude de ce pic. Soit, par ruche, **9 mesures** au total.

> **Pourquoi ces capteurs ?** La température et l'humidité du nid à couvain renseignent sur la santé de la colonie (le nid est régulé autour de ~35 °C). Le son reflète l'activité de la colonie : la fréquence dominante et son intensité changent selon l'état (bourdonnement normal, essaimage, détresse). La luminosité extérieure sert de contexte (cycle jour/nuit, météo). Les mesures extérieures servent de référence pour interpréter les mesures intérieures.

> **Note** : le projet ne gère **ni CO₂ ni poids**. Ces grandeurs ne font pas partie du matériel et ne doivent apparaître ni dans le code ni dans la documentation.

---

## Modèle de données et formats d'échange

Cette section documente précisément ce qui circule entre les composants. Elle est la référence pour tout développeur qui touche au pipeline de données.

Les **9 mesures** ont des noms canoniques, identiques de bout en bout (clé de paquet LoRa courte ↔ champ d'API ↔ mesure InfluxDB ↔ champ mobile) :

| Grandeur | Clé LoRa | Champ API / mesure InfluxDB |
|---|---|---|
| Température intérieure | `t_int` | `temperature_int` |
| Humidité intérieure | `h_int` | `humidity_int` |
| Température extérieure | `t_ext` | `temperature_ext` |
| Humidité extérieure | `h_ext` | `humidity_ext` |
| Son intérieur — fréquence | `sf_int` | `sound_freq_int` |
| Son intérieur — amplitude | `sa_int` | `sound_amp_int` |
| Son extérieur — fréquence | `sf_ext` | `sound_freq_ext` |
| Son extérieur — amplitude | `sa_ext` | `sound_amp_ext` |
| Luminosité extérieure | `l_ext` | `light_ext` |

Tous les champs capteurs sont **optionnels** : seuls ceux présents dans un message sont écrits. Une ruche qui n'enverrait que la température fonctionne sans erreur. La liste canonique des mesures vit dans `app/blueprints/utils/influxdb.py` (`MEASUREMENTS`) et est répliquée à l'identique côté serveur (`server/blueprints/utils/influxdb.py`).

### 1. Paquet LoRa (nœud capteur → récepteur)

JSON, 255 octets max, clés courtes pour économiser le temps d'antenne :

```json
{
  "id": 1,
  "t_int": 34.7, "h_int": 62.1,
  "t_ext": 18.3, "h_ext": 55.0,
  "sf_int": 245.0, "sa_int": 0.42,
  "sf_ext": 120.0, "sa_ext": 0.11,
  "l_ext": 760.0
}
```

### 2. Ingest local (récepteur → application web, `POST /api/data`)

Le récepteur traduit les clés courtes en noms canoniques pour l'API Flask :

```json
{
  "beehive_id": 1,
  "temperature_int": 34.7, "humidity_int": 62.1,
  "temperature_ext": 18.3, "humidity_ext": 55.0,
  "sound_freq_int": 245.0, "sound_amp_int": 0.42,
  "sound_freq_ext": 120.0, "sound_amp_ext": 0.11,
  "light_ext": 760.0,
  "timestamp": "2026-05-19T14:32:00Z"
}
```

`timestamp` est optionnel (par défaut : heure de réception). Réponse : `201 {"status": "ok"}`.

### 3. Stockage InfluxDB

Une **mesure** (`measurement`) par grandeur, taggée par `beehive_id`, avec un unique champ `value` :

```
measurement : sound_freq_int   tag: beehive_id="1"   field: value=245.0   time: ...
measurement : light_ext        tag: beehive_id="1"   field: value=760.0   time: ...
```

Le nom du bucket vient de `INFLUXDB_BUCKET` (par défaut `sensors`).

### 4. Push vers le serveur distant (`POST /api/push`)

L'application web envoie un lot regroupant toutes les ruches actives. Chaque relevé porte les mesures disponibles :

```json
{
  "source": "beetter",
  "pushed_at": "2026-05-19T14:35:00Z",
  "beehives": [
    {
      "id": 1,
      "name": "Ruche du verger",
      "location": "12 rue des Tilleuls, Noisy-le-Grand",
      "data": [
        {
          "timestamp": "2026-05-19T14:30:00Z",
          "temperature_int": 34.7, "humidity_int": 62.1,
          "sound_freq_int": 245.0, "light_ext": 760.0
        }
      ]
    }
  ]
}
```

Le serveur distant écrit ces mesures sous les **mêmes noms** que l'application web : la distinction intérieur/extérieur ainsi que le son et la luminosité sont propagés jusqu'à l'agrégation et au mobile (pipeline harmonisé).

### 5. Réponses de l'API mobile (serveur → Android)

`GET /api/beehives` — dernières valeurs par mesure :

```json
{ "beehives": [ { "id": "1", "latest": {
  "temperature_int": {"value": 34.7, "time": "..."},
  "humidity_int":    {"value": 62.1, "time": "..."},
  "sound_freq_int":  {"value": 245.0, "time": "..."},
  "light_ext":       {"value": 760.0, "time": "..."}
} } ] }
```

`GET /api/beehives/<id>/data?range=24h` retourne une série (`labels` + `data`) par mesure.

---

## Composants

### 1. Application web (`app/`)

L'application qui tourne sur le Raspberry Pi. Elle reçoit les relevés depuis le récepteur LoRa via son API REST, les stocke dans une instance InfluxDB locale (séries temporelles) et dans PostgreSQL (entités : utilisateurs, ruches, alertes, configurations de push), et fournit un dashboard web. Un scheduler en arrière-plan pousse périodiquement les nouvelles données vers le ou les serveurs distants configurés.

**Stack** : Flask 3, PostgreSQL (utilisateurs/ruches/alertes), InfluxDB 2 (données time-series), APScheduler, Gunicorn.

**Organisation interne (blueprints)** — chaque blueprint est un module Flask autonome (routes + formulaires + templates) :

| Blueprint | Rôle |
|---|---|
| `api/` | Ingest des relevés LoRa (`POST /api/data`) et données de graphe (`/api/beehives/<id>/chart-data`) |
| `auth/` | Inscription, connexion, déconnexion |
| `account/` | Gestion du compte (email, mot de passe, suppression) et administration des utilisateurs |
| `beehives/` | CRUD des ruches (nom, localisation, configuration LoRa) |
| `dashboard/` | Page d'accueil et vue d'ensemble |
| `alerts/` | Journal des alertes (changements de statut d'une ruche) |
| `settings/` | Configuration des serveurs distants vers lesquels pousser |
| `utils/` | Helpers transverses : InfluxDB, push, statut, géocodage, décorateurs |

**Fichiers clés** : `models.py` (modèles SQLAlchemy), `scheduler.py` (job de push toutes les minutes), `migrate.py` (création/mise à jour des tables), `compose.yml` + `Dockerfile` (déploiement).

**Comment ça s'articule** : un relevé arrive sur `POST /api/data` → la route vérifie que la ruche existe et est active (PostgreSQL) → écrit les points dans InfluxDB → le dashboard lit InfluxDB pour tracer les graphes (température, humidité, son et lumière, intérieur/extérieur) → toutes les minutes, le scheduler vérifie chaque configuration de serveur distant et, si son intervalle est écoulé, déclenche un push des données récentes.

**Variables d'environnement** (voir `app/.env.example`) :

| Variable | Description |
|---|---|
| `SECRET_KEY` | Clé secrète de session Flask (mettre une longue chaîne aléatoire) |
| `DATABASE_URL` | Chaîne de connexion PostgreSQL |
| `INFLUXDB_URL` | URL de base InfluxDB |
| `INFLUXDB_TOKEN` | Token d'authentification InfluxDB |
| `INFLUXDB_ORG` | Nom de l'organisation InfluxDB |
| `INFLUXDB_BUCKET` | Nom du bucket InfluxDB (par défaut `sensors`) |

---

### 2. Serveur distant (`server/`)

Le serveur d'agrégation centralisé. Les applications Raspberry Pi lui poussent des lots de données ; l'application Android l'interroge pour afficher les dashboards. Il ne reçoit jamais de LoRa directement : il ne voit que les données déjà collectées et transmises par les Raspberry Pi, et les stocke sous les mêmes noms de mesures.

**Stack** : Flask 3, PostgreSQL (utilisateurs/API keys/sessions), InfluxDB 2, Gunicorn.

**Fonctionnalités principales** :
- Dashboard web affichant toutes les ruches de tous les Raspberry Pi connectés
- Gestion des API keys (génération / révocation des clés utilisées par les apps Raspberry Pi)
- API REST mobile avec authentification par token de session (expiration 30 jours)
- Réception des données poussées via `POST /api/push` (Bearer API key)

**Comment ça s'articule** : deux types d'authentification cohabitent sur la même API. Les Raspberry Pi s'authentifient avec une **API key** (header `Authorization: Bearer <clé>`) pour pousser des données. L'application Android s'authentifie d'abord via `POST /api/auth/login` (identifiants) pour obtenir un **token de session**, qu'elle réutilise ensuite sur les endpoints de lecture.

**Endpoints REST** :

| Méthode | Chemin | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | Connexion mobile, retourne un token de session |
| `POST` | `/api/auth/logout` | Bearer token | Invalide la session |
| `GET` | `/api/beehives` | Bearer token / API key | Liste les ruches avec les dernières valeurs |
| `GET` | `/api/beehives/<id>/data` | Bearer token / API key | Données graphe (`?range=24h`) |
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

Un script Python qui tourne sur le Raspberry Pi aux côtés de l'application web. Il écoute les paquets des nœuds capteurs LoRa, les décode (température, humidité, son, lumière) et transmet les relevés à l'API REST locale (`POST /api/data`). C'est le pont entre le monde radio et le monde HTTP.

Le script est livré sous forme de **stub** — l'initialisation matérielle (`init_lora`) et l'appel de réception (`receive_packet`) sont des placeholders. Remplace-les par ta vraie bibliothèque LoRa. Le décodage (`parse_packet`, qui gère déjà les 9 grandeurs) et l'envoi à l'API (`push_to_api`) sont fonctionnels.

**Bibliothèques compatibles** (remplace le bloc stub dans `receiver.py`) :
- `adafruit-circuitpython-rfm9x` — SX127x via CircuitPython / Blinka
- `pyLoRa` / `SX127x` — SX127x brut via GPIO + SPI du Raspberry Pi
- `pyserial` + RAK811 / Dragino — module LoRaWAN à commandes AT via UART

**Format de paquet attendu** : voir [Modèle de données § 1](#1-paquet-lora-nœud-capteur--récepteur).

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

Une application Android native qui se connecte au serveur distant et affiche les données des ruches en direct. Architecture MVVM : `data/` (Retrofit, modèles, DataStore, repository), `ui/` (écrans Compose + ViewModels), `worker/` (alertes en arrière-plan).

**Stack** : Kotlin, Jetpack Compose, Retrofit 2 + OkHttp, Gson, DataStore, WorkManager.

**Fonctionnalités** :
- Connexion avec l'URL du serveur, le nom d'utilisateur et le mot de passe (token stocké via DataStore)
- Dashboard listant toutes les ruches avec la dernière température et humidité intérieures
- Écran de détail d'une ruche avec un graphe par grandeur (temp/hum intérieur et extérieur, son fréquence + amplitude des deux micros, luminosité), plage de temps sélectionnable
- Alertes en arrière-plan via WorkManager (seuils min/max sur la température et l'humidité intérieures)
- Paramètres : seuils de notification, déconnexion

**Comment ça s'articule** : `LoginViewModel` appelle `BeehiveRepository.login()` → Retrofit envoie les identifiants à `/api/auth/login` → le token reçu est stocké et réinjecté en header sur tous les appels suivants (`/api/beehives`, `/api/beehives/<id>/data`). Le `AlertWorker` interroge périodiquement le serveur en tâche de fond et compare les valeurs intérieures aux seuils définis dans les paramètres.

**Prérequis** :
- Android 8.0 (API 26) ou supérieur
- Un serveur distant en cours d'exécution, accessible sur le réseau

---

### 5. Simulateur (`tools/simulate.py`)

Un outil de développement qui envoie de faux relevés réalistes (dérive sinusoïdale + bruit) pour les 9 grandeurs à l'application web, en remplacement du matériel LoRa réel. Il cible le même endpoint que le récepteur (`POST /api/data`).

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
│   │   ├── api/          # POST /api/data — ingest LoRa + données de graphe
│   │   ├── auth/         # Connexion / inscription / déconnexion
│   │   ├── account/      # Gestion du compte + administration des utilisateurs
│   │   ├── beehives/     # CRUD des ruches
│   │   ├── dashboard/    # Page d'accueil
│   │   ├── alerts/       # Journal des alertes (changements de statut)
│   │   ├── settings/     # Configuration des serveurs distants
│   │   └── utils/        # Helpers InfluxDB, push, statut, géocodage, décorateurs
│   ├── templates/
│   ├── static/
│   ├── models.py         # Modèles SQLAlchemy (User, Beehive, Alert, RemoteServerConfig)
│   ├── scheduler.py      # Job APScheduler de push vers les serveurs distants
│   ├── migrate.py        # Création / mise à jour des tables
│   ├── compose.yml
│   └── Dockerfile
├── server/               # Serveur d'agrégation distant (Flask :5001)
│   ├── blueprints/
│   │   ├── api/          # API REST mobile & push
│   │   ├── auth/
│   │   ├── dashboard/
│   │   └── utils/        # Helpers InfluxDB
│   ├── templates/
│   ├── static/
│   ├── models.py         # Modèles (User, ApiKey, UserSession)
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
