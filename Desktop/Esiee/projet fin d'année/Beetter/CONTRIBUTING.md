# Guide de développement — Beetter

Ce guide explique comment modifier et étendre chaque composant du projet Beetter. Il couvre l'application web Flask, l'application Android, la base de données InfluxDB et les interactions entre les services.

---

## Sommaire

1. [Stack technique et choix d'architecture](#1-stack-technique-et-choix-darchitecture)
2. [Démarrer l'environnement de développement](#2-démarrer-lenvironnement-de-développement)
   - [Installer Docker](#installer-docker)
   - [Premier démarrage](#premier-démarrage)
   - [Workflow quotidien](#workflow-quotidien)
   - [Alimenter la base avec de fausses données](#alimenter-la-base-avec-de-fausses-données)
3. [Application web Flask (Raspberry Pi)](#3-application-web-flask-raspberry-pi)
   - [Structure du dossier `app/`](#structure-du-dossier-app)
   - [Comment Flask traite une requête](#comment-flask-traite-une-requête--le-cycle-complet)
   - [Le pattern Blueprint](#le-pattern-blueprint--pourquoi-et-comment)
   - [Ajouter une nouvelle page](#comment-ajouter-une-nouvelle-page--étape-par-étape)
   - [Templates Jinja2](#les-templates-jinja2--syntaxe-et-pourquoi-ça-marche)
   - [Graphes Chart.js](#ajouter-un-graphe-chartjs--comment-ça-sarticule)
   - [Modèles SQLAlchemy](#les-modèles-sqlalchemy--comment-postgresql-est-abstrait)
   - [Modifier le style](#modifier-le-style)
4. [InfluxDB — base de données time-series](#4-influxdb--base-de-données-time-series)
   - [Concepts fondamentaux](#concepts-fondamentaux)
   - [Accéder à InfluxDB depuis Flask](#accéder-à-influxdb-depuis-flask)
   - [Interface web InfluxDB](#interface-web-influxdb)
   - [Requêtes Flux utiles](#requêtes-flux-utiles)
   - [Commandes de maintenance](#commandes-de-maintenance-influxdb)
5. [Application Android](#5-application-android)
   - [Prérequis et setup](#prérequis-et-setup)
   - [Structure du projet Android](#structure-du-projet-android)
   - [Architecture MVVM](#architecture-mvvm--pourquoi-et-comment)
   - [Ajouter un écran](#ajouter-un-écran--étape-par-étape)
   - [Appels API avec Retrofit](#appels-api-avec-retrofit)
   - [Commandes Gradle](#commandes-gradle-utiles)
6. [Interactions entre les services](#6-interactions-entre-les-services)
7. [Commandes utiles au quotidien](#7-commandes-utiles-au-quotidien)
8. [Convention de commits et règles d'équipe](#8-convention-de-commits-et-règles-déquipe)

---

## 1. Stack technique et choix d'architecture

| Couche | Technologie | Rôle |
|---|---|---|
| Backend web | Python 3, Flask 3 | Logique serveur, routes, accès BDD |
| BDD relationnelle | PostgreSQL + SQLAlchemy | Utilisateurs, ruches, serveurs distants |
| BDD time-series | InfluxDB 2 | Relevés des capteurs |
| Templates | Jinja2 (HTML) | Rendu des pages côté serveur |
| CSS | Bootstrap 5 + `custom.css` | Mise en page et style |
| JS | Vanilla JS + Chart.js | Graphes et appels API |
| Conteneurisation | Docker Compose | Orchestration des services |
| Application mobile | Kotlin + Jetpack Compose | App Android native |
| Réseau mobile | Retrofit 2 + OkHttp | Appels HTTP vers le serveur distant |

### Pourquoi Flask et pas Django ou FastAPI ?

Flask est un micro-framework : il ne force aucune structure, ne génère pas de code automatiquement, et ne fait que ce qu'on lui demande. C'est un bon choix ici car le projet est de taille maîtrisée, l'équipe apprend le framework, et on a besoin de la flexibilité pour mélanger du rendu HTML côté serveur (les pages) et une API JSON (pour les graphes et le mobile).

Django aurait imposé beaucoup plus de conventions. FastAPI est excellent pour des API pures mais moins adapté au rendu HTML.

### Pourquoi deux bases de données (PostgreSQL + InfluxDB) ?

Ce sont deux problèmes fondamentalement différents :

**PostgreSQL** stocke des données *structurelles* qui changent rarement : qui est l'apiculteur, comment s'appelle la ruche, quel est son emplacement. Ce sont des entités avec des relations entre elles (une ruche appartient à un apiculteur). SQL est conçu pour ça.

**InfluxDB** stocke des données *temporelles* qui arrivent en continu : température toutes les 5 minutes, humidité, CO2, audio. Ce type de données a des contraintes très différentes — on n'y fait presque jamais de mise à jour, on y fait beaucoup de requêtes "donne-moi la moyenne sur les 24 dernières heures". InfluxDB est optimisé pour ces lectures temporelles et est 10 à 100x plus rapide que PostgreSQL pour ce cas d'usage.

### Pourquoi Docker Compose ?

Sur le Raspberry Pi, faire tourner Flask, PostgreSQL et InfluxDB séparément implique d'installer et configurer chaque service manuellement, de gérer les conflits de versions, et de s'assurer que tout redémarre correctement après un reboot.

Docker Compose résout ça en décrivant tous les services dans un seul fichier `compose.yml`. Un seul `docker compose up -d` démarre tout, dans le bon ordre, avec les bonnes variables d'environnement. Si le Pi redémarre, Docker redémarre les conteneurs automatiquement (`restart: unless-stopped` dans le compose).

---

## 2. Démarrer l'environnement de développement

Tout l'environnement (Flask, PostgreSQL, InfluxDB) tourne via Docker Compose. Tu n'as rien à installer manuellement sauf Docker lui-même.

### Installer Docker

**Windows / macOS :**

Télécharge et installe **Docker Desktop** depuis le site officiel :
→ https://www.docker.com/products/docker-desktop/

Docker Desktop installe automatiquement Docker et Docker Compose en une seule fois. Lance l'application après l'installation — elle doit tourner en arrière-plan (icône dans la barre des tâches) pour que les commandes `docker` fonctionnent dans le terminal.

**Linux (Ubuntu / Debian) :**

```bash
# Installation via le script officiel Docker
curl -fsSL https://get.docker.com | sh

# Ajouter ton utilisateur au groupe docker
# (pour ne pas avoir à taper sudo à chaque commande)
sudo usermod -aG docker $USER

# Recharge les groupes sans se déconnecter
newgrp docker

# Vérifier que ça fonctionne
docker --version
docker compose version
```

### Premier démarrage

**1. Cloner le repo et aller dans le dossier app**

```bash
git clone https://github.com/Charlox29/Beetter.git
cd Beetter/app
```

**2. Créer le fichier de configuration**

```bash
cp .env.example .env
```

Le fichier `.env.example` contient des valeurs par défaut qui fonctionnent directement pour le développement local. Tu n'as pas besoin de les modifier pour démarrer.

**3. Configurer le compose.yml pour le développement**

Pour que les modifications de CSS et de templates soient visibles immédiatement sans rebuild, le `compose.yml` doit monter les dossiers en volume et activer le mode debug Flask. Vérifie que le service `app` contient bien ces lignes :

```yaml
services:
  app:
    build: .
    ports:
      - "5000:5000"
    env_file:
      - .env
    environment:
      FLASK_DEBUG: "1"          # rechargement automatique des .py
    volumes:
      - ./templates:/app/templates   # templates rechargés à chaque requête
      - ./static:/app/static         # CSS/JS servis depuis le disque
    depends_on:
      db:
        condition: service_healthy
      influxdb:
        condition: service_healthy
    restart: unless-stopped
```

**4. Construire et démarrer**

```bash
docker compose up -d --build
```

- `up` : démarre tous les services définis dans `compose.yml`
- `-d` : en arrière-plan (detached) — le terminal reste libre
- `--build` : reconstruit l'image Docker avant de démarrer

La première fois, Docker télécharge les images PostgreSQL et InfluxDB — ça peut prendre 1 à 2 minutes selon ta connexion. Les démarrages suivants sont instantanés.

**5. Vérifier que tout tourne**

```bash
docker compose ps
```

Tu dois voir trois conteneurs avec le statut `running` :

```
NAME              STATUS
beetter-app-1     running
beetter-db-1      running (healthy)
beetter-influxdb-1  running (healthy)
```

**6. Ouvrir l'application**

→ Dashboard Flask : http://localhost:5000
→ Interface InfluxDB : http://localhost:8086

Inscris un compte sur http://localhost:5000/register — le premier compte créé reçoit automatiquement le rôle admin.

### Workflow quotidien

**Démarrer le projet (matin)**

```bash
cd Beetter/app
docker compose up -d
# Pas besoin de --build sauf si tu as modifié requirements.txt ou le Dockerfile
```

**Pendant le développement**

| Tu modifies | Ce qu'il faut faire | Délai |
|---|---|---|
| `static/css/custom.css` | Ctrl+Shift+R dans le navigateur | Immédiat |
| `templates/*.html` | F5 dans le navigateur | Immédiat |
| `blueprints/*/routes.py` | Attendre 1-2 secondes | Auto (Flask debug) |
| `models.py` | `docker compose restart app` | ~5 secondes |
| `requirements.txt` | `docker compose up -d --build` | ~30 secondes |

> **Astuce navigateur** : si le CSS ne se met pas à jour malgré F5, utilise **Ctrl+Shift+R** (ou Cmd+Shift+R sur Mac) pour vider le cache. Ou ouvre les DevTools (F12) → onglet Network → coche **"Disable cache"** pendant que tu développes.

**Voir les logs en temps réel**

```bash
docker compose logs -f          # tous les services
docker compose logs -f app      # Flask uniquement
docker compose logs -f db       # PostgreSQL uniquement
docker compose logs -f influxdb # InfluxDB uniquement
```

Les logs Flask affichent chaque requête HTTP reçue et toutes les erreurs Python avec leur traceback complet — indispensable pour déboguer.

**Arrêter le projet (soir)**

```bash
docker compose down
```

`down` arrête et supprime les conteneurs, mais **conserve les données** (volumes PostgreSQL et InfluxDB). La prochaine fois que tu fais `docker compose up -d`, tu retrouves exactement l'état où tu en étais.

> **Attention** : `docker compose down -v` supprime aussi les volumes, donc toutes les données. À n'utiliser que pour repartir d'une base vierge.

**Cas particuliers**

```bash
# Reconstruire l'image après modification de requirements.txt ou Dockerfile
docker compose up -d --build

# Redémarrer uniquement Flask (après modif de models.py)
docker compose restart app

# Ouvrir un shell dans le conteneur Flask (pour déboguer)
docker compose exec app bash

# Accéder à Python Flask shell (pour tester des requêtes BDD)
docker compose exec app flask shell
>>> from app import db
>>> from app.models import Beehive
>>> Beehive.query.all()

# Repartir d'une base de données vierge
docker compose down -v
docker compose up -d --build
```

### Alimenter la base avec de fausses données

Sans module ESP32 sous la main, le simulateur permet de remplir les graphes instantanément :

```bash
# Depuis la racine du projet
cd tools
pip install requests

# Créer d'abord une ruche dans l'interface web (http://localhost:5000)
# puis lancer le simulateur avec l'ID de la ruche créée

# Remplir 200 points historiques sur les 24 dernières heures (remplit les graphes)
python simulate.py --burst 200

# Mode live — un relevé toutes les 10 secondes (pour tester le temps réel)
python simulate.py --ids 1 --interval 10

# Plusieurs ruches simultanément
python simulate.py --ids 1 2 3 --interval 5
```

---

## 3. Application web Flask (Raspberry Pi)

### Structure du dossier `app/`

```
app/
├── __init__.py          ← Point d'entrée : crée l'app Flask, connecte les blueprints
├── models.py            ← Définition des tables PostgreSQL
├── scheduler.py         ← Tâche périodique de push vers le serveur distant
├── requirements.txt     ← Liste des dépendances Python
├── compose.yml          ← Description des services Docker
├── Dockerfile           ← Recette pour construire l'image Docker de l'app
├── .env                 ← Secrets et config locale (jamais dans Git)
├── .env.example         ← Modèle de .env à copier au premier setup
│
├── blueprints/          ← Un dossier par section du site
│   ├── api/             ← Endpoint POST /api/data (ingest des données LoRa)
│   ├── auth/            ← Pages login, register, logout
│   ├── beehives/        ← Pages liste et détail des ruches, formulaires
│   ├── dashboard/       ← Page d'accueil avec vue d'ensemble
│   ├── settings/        ← Configuration des serveurs distants
│   └── utils/
│       ├── influxdb.py  ← Fonctions de lecture/écriture InfluxDB
│       └── push.py      ← Logique d'envoi des données au serveur distant
│
├── templates/           ← Fichiers HTML avec syntaxe Jinja2
│   ├── base.html        ← Layout commun à toutes les pages (navbar, CSS, JS)
│   └── ...              ← Un sous-dossier par blueprint
│
└── static/
    ├── css/custom.css   ← Styles qui complètent Bootstrap
    └── js/              ← Scripts JavaScript spécifiques au projet
```

### Comment Flask traite une requête — le cycle complet

```
Navigateur                    Raspberry Pi
────────                      ────────────
GET /beehives/3  ─────────►   1. Flask reçoit la requête
                              2. Il cherche quelle route correspond à /beehives/3
                              3. Il appelle la fonction Python associée (le "view")
                              4. La fonction lit PostgreSQL → récupère la ruche n°3
                              5. La fonction lit InfluxDB → récupère le dernier relevé
                              6. La fonction passe ces données à un template HTML
                              7. Jinja2 génère le HTML final en injectant les données
◄─────────────  HTML complet  8. Flask envoie le HTML au navigateur
```

C'est ce qu'on appelle le rendu **côté serveur** (SSR — Server Side Rendering) : le serveur fait tout le travail, le navigateur reçoit un HTML déjà prêt à afficher.

### Le pattern Blueprint — pourquoi et comment

Un Blueprint est un "sous-app" Flask qui regroupe tout ce qui concerne une section du site : ses routes, ses formulaires, ses templates.

```
URL                      Blueprint         Fichier
──────────────────────────────────────────────────────────
/                        dashboard         blueprints/dashboard/routes.py
/login                   auth              blueprints/auth/routes.py
/beehives                beehives          blueprints/beehives/routes.py
/beehives/<id>           beehives          blueprints/beehives/routes.py
/settings                settings          blueprints/settings/routes.py
POST /api/data           api               blueprints/api/routes.py
```

Le `__init__.py` de chaque blueprint crée l'objet Blueprint et importe les routes :

```python
# blueprints/beehives/__init__.py
from flask import Blueprint

# url_prefix="/beehives" : toutes les routes commenceront par /beehives
beehives_bp = Blueprint("beehives", __name__, url_prefix="/beehives")

# Import en bas pour éviter les imports circulaires
from . import routes
```

### Comment ajouter une nouvelle page — étape par étape

**Exemple : ajouter une page "Alertes" à `/alertes`**

**Étape 1 — Créer le blueprint**

```python
# blueprints/alertes/__init__.py
from flask import Blueprint
alertes_bp = Blueprint("alertes", __name__, url_prefix="/alertes")
from . import routes
```

**Étape 2 — Écrire les routes**

```python
# blueprints/alertes/routes.py
from flask import render_template, redirect, url_for
from flask_login import login_required
from . import alertes_bp
from ...models import Alerte, db

@alertes_bp.route("/")
@login_required
def index():
    alertes = Alerte.query.order_by(Alerte.created_at.desc()).all()
    return render_template("alertes/index.html", alertes=alertes)

@alertes_bp.route("/<int:id>/acquitter", methods=["POST"])
@login_required
def acquitter(id):
    alerte = Alerte.query.get_or_404(id)
    alerte.lue = True
    db.session.commit()
    return redirect(url_for("alertes.index"))
```

**Étape 3 — Enregistrer le blueprint dans `app/__init__.py`**

```python
from .blueprints.alertes import alertes_bp
app.register_blueprint(alertes_bp)
```

**Étape 4 — Créer le template**

```html
<!-- templates/alertes/index.html -->
{% extends "base.html" %}

{% block content %}
<h1>Alertes</h1>
{% for alerte in alertes %}
<div class="alert alert-{{ 'danger' if alerte.severite == 'critique' else 'warning' }}">
  <strong>{{ alerte.ruche.name }}</strong> — {{ alerte.message }}
  {% if not alerte.lue %}
  <form method="POST" action="{{ url_for('alertes.acquitter', id=alerte.id) }}"
        class="d-inline">
    <button type="submit" class="btn btn-sm btn-outline-secondary">Acquitter</button>
  </form>
  {% endif %}
</div>
{% endfor %}
{% endblock %}
```

**Étape 5 — Ajouter le lien dans la navbar de `base.html`**

```html
<a class="nav-link" href="{{ url_for('alertes.index') }}">Alertes</a>
```

### Les templates Jinja2 — syntaxe et pourquoi ça marche

```html
<!-- Variables -->
{{ beehive.name }}
{{ latest.temperature | round(1) }} °C

<!-- Conditions -->
{% if beehive.active %}
  <span class="badge bg-success">Active</span>
{% else %}
  <span class="badge bg-secondary">Inactive</span>
{% endif %}

<!-- Boucles -->
{% for beehive in beehives %}
  <li>{{ beehive.name }}</li>
{% endfor %}

<!-- URL — toujours url_for, jamais une URL en dur -->
<a href="{{ url_for('beehives.detail', id=beehive.id) }}">Voir</a>

<!-- Héritage de layout -->
{% extends "base.html" %}
{% block content %}
  <!-- contenu spécifique ici -->
{% endblock %}
```

### Ajouter un graphe Chart.js — comment ça s'articule

Le graphe fonctionne en deux temps : Flask rend la page avec un `<canvas>` vide, puis JavaScript charge les données via une API et dessine le graphe. Ce découpage évite de bloquer le chargement de la page.

```html
<canvas id="tempChart" height="80"></canvas>
<script>
fetch("{{ url_for('api.beehive_data', id=beehive.id) }}?range=24h")
  .then(r => r.json())
  .then(data => {
    new Chart(document.getElementById("tempChart"), {
      type: "line",
      data: {
        labels: data.map(d => new Date(d.time).toLocaleTimeString()),
        datasets: [{
          label: "Température (°C)",
          data: data.map(d => d.temperature),
          borderColor: "#1D9E75",
          tension: 0.3,
          fill: false
        }]
      },
      options: { responsive: true, scales: { y: { beginAtZero: false } } }
    });
  });
</script>
```

Route Flask correspondante :

```python
@api_bp.route("/beehives/<int:id>/data")
@login_required
def beehive_data(id):
    range_ = request.args.get("range", "24h")
    beehive = Beehive.query.get_or_404(id)
    data = get_history(beehive.id, range_)
    return jsonify(data)
```

### Les modèles SQLAlchemy — comment PostgreSQL est abstrait

```python
# models.py
class Beehive(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(200))
    lora_id  = db.Column(db.Integer, unique=True)
    active   = db.Column(db.Boolean, default=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    owner    = db.relationship("User", back_populates="beehives")
```

```python
# Lecture
ruche  = Beehive.query.get(3)
ruches = Beehive.query.filter_by(active=True).all()

# Écriture
nouvelle = Beehive(name="Ruche nord", lora_id=42, owner_id=1)
db.session.add(nouvelle)
db.session.commit()

# Mise à jour
ruche.name = "Nouveau nom"
db.session.commit()

# Suppression
db.session.delete(ruche)
db.session.commit()
```

### Modifier le style

Bootstrap 5 est déjà inclus via `base.html`. Pour des styles personnalisés, édite `static/css/custom.css` — ce fichier est chargé après Bootstrap, donc ses règles ont priorité :

```css
.beehive-card {
  border-left: 4px solid var(--bs-success);
  transition: box-shadow 0.2s;
}
.beehive-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
```

---

## 4. InfluxDB — base de données time-series

### Concepts fondamentaux

InfluxDB organise les données différemment d'une base SQL classique. Il faut comprendre quatre concepts :

**Bucket** — l'équivalent d'une base de données. Dans Beetter il y en a un : `ruche`.

**Measurement** — l'équivalent d'une table. Dans Beetter : `releve`.

**Tags** — des champs indexés utilisés pour filtrer. Exemple : `ruche_id`. Ce sont des strings, ils ne stockent pas de valeurs numériques. Toujours utiliser des tags pour ce sur quoi on va filtrer souvent.

**Fields** — les valeurs numériques réelles. Exemple : `temperature`, `humidite`, `co2`, `poids`. Non indexés, lus séquentiellement.

**Timestamp** — chaque point a un horodatage nanoseconde.

```
measurement : "releve"
    tag     : ruche_id = "ruche_01"
    fields  : temperature=34.2, humidite=68.4, co2=1240.0, poids=42.35
    time    : 2026-05-19T14:32:00Z
```

### Accéder à InfluxDB depuis Flask

```python
# blueprints/utils/influxdb.py
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from flask import current_app

def get_client():
    """Retourne un client InfluxDB configuré depuis les variables Flask."""
    return InfluxDBClient(
        url=current_app.config["INFLUXDB_URL"],
        token=current_app.config["INFLUXDB_TOKEN"],
        org=current_app.config["INFLUXDB_ORG"],
    )

def write_releve(decoded: dict):
    """Écrit un relevé complet (une trame LoRa) dans InfluxDB."""
    client = get_client()
    write_api = client.write_api(write_options=SYNCHRONOUS)

    p = (
        Point("releve")
        .tag("ruche_id", str(decoded["ruche_id"]))
        .time(decoded["timestamp"])
        .field("temperature",   decoded["temperature"])
        .field("humidite",      decoded["humidite"])
        .field("co2",           decoded["co2"])
        .field("poids",         decoded["poids"])
        .field("audio_peak_hz", decoded["audio_peak_hz"])
        .field("audio_rms",     decoded["audio_rms"])
        .field("rssi",          decoded["rssi"])
        .field("batterie_mv",   decoded["batterie_mv"])
    )
    write_api.write(bucket=current_app.config["INFLUXDB_BUCKET"], record=p)

def get_latest(beehive_id: int) -> dict:
    """Retourne le dernier relevé d'une ruche."""
    client = get_client()
    query = f'''
        from(bucket: "{current_app.config["INFLUXDB_BUCKET"]}")
          |> range(start: -1h)
          |> filter(fn: (r) => r._measurement == "releve")
          |> filter(fn: (r) => r.ruche_id == "{beehive_id}")
          |> last()
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    tables = client.query_api().query(query)
    if tables and tables[0].records:
        return tables[0].records[0].values
    return {}

def get_history(beehive_id: int, range_: str = "24h") -> list:
    """Retourne l'historique des relevés sur une période donnée."""
    client = get_client()
    query = f'''
        from(bucket: "{current_app.config["INFLUXDB_BUCKET"]}")
          |> range(start: -{range_})
          |> filter(fn: (r) => r._measurement == "releve")
          |> filter(fn: (r) => r.ruche_id == "{beehive_id}")
          |> aggregateWindow(every: 5m, fn: mean)
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    # aggregateWindow regroupe par fenêtres de 5 min et calcule la moyenne.
    # Indispensable pour les longues périodes (7j, 30j) sinon on retourne
    # des milliers de points inutilement.
    tables = client.query_api().query(query)
    return [r.values for t in tables for r in t.records]
```

### Interface web InfluxDB

InfluxDB expose une interface web sur le port **8086**. Sur le Raspberry Pi :

```
http://<ip-du-raspberry-pi>:8086
```

Depuis cette interface tu peux :
- Écrire et tester des requêtes Flux en temps réel dans l'onglet **Data Explorer**
- Visualiser les données sous forme de graphes sans passer par le dashboard Flask
- Gérer les buckets, les tokens et les organisations
- Voir les statistiques d'utilisation

Le login/mot de passe sont ceux définis dans le `.env` (`INFLUXDB_TOKEN` pour l'API, et les credentials admin définis au premier démarrage).

### Requêtes Flux utiles

**Dernier relevé de toutes les ruches :**
```flux
from(bucket: "ruche")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "releve")
  |> last()
  |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
```

**Historique température d'une ruche sur 24h :**
```flux
from(bucket: "ruche")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "releve")
  |> filter(fn: (r) => r.ruche_id == "1")
  |> filter(fn: (r) => r._field == "temperature")
  |> aggregateWindow(every: 30m, fn: mean)
```

**Détecter les pics audio anormaux (pic > 450 Hz) :**
```flux
from(bucket: "ruche")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "releve")
  |> filter(fn: (r) => r._field == "audio_peak_hz")
  |> filter(fn: (r) => r._value > 450.0)
```

**Moyenne de toutes les ruches sur une plage :**
```flux
from(bucket: "ruche")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "releve")
  |> filter(fn: (r) => r._field == "temperature")
  |> group(columns: ["ruche_id"])
  |> mean()
```

### Commandes de maintenance InfluxDB

```bash
# Ouvrir un shell dans le conteneur InfluxDB
docker compose exec influxdb bash

# Lister les buckets
influx bucket list

# Supprimer des données anciennes (ex: garder seulement 30j)
influx bucket update --name ruche --retention 720h

# Exporter des données en CSV
influx query 'from(bucket:"ruche") |> range(start:-24h)' --raw > export.csv

# Voir l'état du service depuis le Pi
docker compose logs -f influxdb
```

---

## 5. Application Android

### Prérequis et setup

- **Android Studio** Hedgehog (2023.1) ou plus récent
- **JDK 17** ou supérieur
- Un appareil Android 8.0+ (API 26+) ou un émulateur
- Le serveur distant (`server/`) en cours d'exécution et accessible sur le réseau

**Ouvrir le projet :**
1. Lance Android Studio
2. **File → Open** → sélectionne le dossier `android/` (pas la racine du projet)
3. Attends la synchronisation Gradle (peut prendre 2-3 minutes à la première ouverture)
4. Android Studio télécharge automatiquement les dépendances

**Configurer l'URL du serveur pour le développement :**

L'app demande l'URL au login, mais pour éviter de la retaper à chaque lancement en dev, tu peux hardcoder une valeur par défaut temporairement dans l'écran de login.

### Structure du projet Android

```
android/app/src/main/java/fr/esiee/beetter/
│
├── data/
│   ├── api/
│   │   ├── ApiService.kt        ← Interface Retrofit (définit tous les endpoints)
│   │   └── ApiClient.kt         ← Configuration OkHttp + Retrofit
│   ├── model/
│   │   ├── Beehive.kt           ← Data class ruche (JSON ↔ Kotlin)
│   │   ├── SensorData.kt        ← Data class relevé capteurs
│   │   └── AuthResponse.kt      ← Data class réponse login
│   ├── repository/
│   │   ├── BeehiveRepository.kt ← Logique d'accès aux données (API + cache)
│   │   └── AuthRepository.kt    ← Gestion login/logout/token
│   └── datastore/
│       └── PreferencesDataStore.kt ← Stockage local (token, URL serveur)
│
├── ui/
│   ├── login/
│   │   ├── LoginScreen.kt       ← Écran de connexion (Compose)
│   │   └── LoginViewModel.kt    ← Logique métier de l'écran login
│   ├── dashboard/
│   │   ├── DashboardScreen.kt   ← Liste des ruches
│   │   └── DashboardViewModel.kt
│   ├── detail/
│   │   ├── DetailScreen.kt      ← Détail d'une ruche + graphes
│   │   └── DetailViewModel.kt
│   └── settings/
│       ├── SettingsScreen.kt    ← Seuils d'alerte, déconnexion
│       └── SettingsViewModel.kt
│
└── worker/
    └── AlertWorker.kt           ← Vérification des seuils en arrière-plan
```

### Architecture MVVM — pourquoi et comment

L'app suit le pattern **MVVM** (Model — View — ViewModel), le standard recommandé par Google pour Android.

```
UI (Screen / Composable)
    │  observe les StateFlow
    ▼
ViewModel
    │  appelle le repository
    ▼
Repository
    │  appelle l'API ou le cache local
    ▼
ApiService (Retrofit) → Serveur distant
```

**Pourquoi cette séparation ?**

- Le **Screen** (Composable) ne fait qu'afficher ce que le ViewModel lui donne. Il ne contient aucune logique métier — seulement du code d'affichage.
- Le **ViewModel** survit aux rotations d'écran. Si tu retournes le téléphone, le ViewModel garde son état alors que le Screen est recréé de zéro.
- Le **Repository** isole l'accès aux données. Si on veut ajouter un cache local plus tard, on le fait dans le Repository sans toucher au ViewModel ni au Screen.

**Exemple concret — DashboardViewModel :**

```kotlin
// ui/dashboard/DashboardViewModel.kt
class DashboardViewModel(
    private val repository: BeehiveRepository
) : ViewModel() {

    // StateFlow : flux de données observé par le Screen
    // "_" prefix = version privée modifiable
    private val _beehives = MutableStateFlow<List<Beehive>>(emptyList())
    val beehives: StateFlow<List<Beehive>> = _beehives.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    init {
        loadBeehives()
    }

    fun loadBeehives() {
        viewModelScope.launch {
            // viewModelScope : coroutine liée au cycle de vie du ViewModel
            // Si le ViewModel est détruit, la coroutine est annulée automatiquement
            _isLoading.value = true
            try {
                _beehives.value = repository.getBeehives()
            } catch (e: Exception) {
                // gestion d'erreur
            } finally {
                _isLoading.value = false
            }
        }
    }
}
```

**Screen correspondant :**

```kotlin
// ui/dashboard/DashboardScreen.kt
@Composable
fun DashboardScreen(
    viewModel: DashboardViewModel = viewModel(),
    onBeehiveClick: (Int) -> Unit
) {
    // collectAsState : observe le StateFlow et recompose l'UI à chaque changement
    val beehives by viewModel.beehives.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()

    if (isLoading) {
        CircularProgressIndicator()
    } else {
        LazyColumn {
            items(beehives) { beehive ->
                BeehiveCard(
                    beehive = beehive,
                    onClick = { onBeehiveClick(beehive.id) }
                )
            }
        }
    }
}
```

### Ajouter un écran — étape par étape

**Exemple : ajouter un écran "Alertes"**

**Étape 1 — Créer la data class (model)**

```kotlin
// data/model/Alert.kt
data class Alert(
    val id: Int,
    val beehiveId: Int,
    val message: String,
    val severity: String,   // "critique" | "avertissement"
    val isRead: Boolean,
    val createdAt: String   // ISO 8601
)
```

**Étape 2 — Ajouter l'endpoint dans ApiService**

```kotlin
// data/api/ApiService.kt
interface ApiService {
    // ... endpoints existants ...

    @GET("api/beehives/{id}/alerts")
    suspend fun getAlerts(
        @Header("Authorization") token: String,
        @Path("id") beehiveId: Int
    ): List<Alert>

    @POST("api/alerts/{id}/acknowledge")
    suspend fun acknowledgeAlert(
        @Header("Authorization") token: String,
        @Path("id") alertId: Int
    ): Response<Unit>
}
```

**Étape 3 — Créer le ViewModel**

```kotlin
// ui/alerts/AlertsViewModel.kt
class AlertsViewModel(
    private val repository: BeehiveRepository,
    private val beehiveId: Int
) : ViewModel() {

    private val _alerts = MutableStateFlow<List<Alert>>(emptyList())
    val alerts: StateFlow<List<Alert>> = _alerts.asStateFlow()

    init { loadAlerts() }

    fun loadAlerts() {
        viewModelScope.launch {
            _alerts.value = repository.getAlerts(beehiveId)
        }
    }

    fun acknowledge(alertId: Int) {
        viewModelScope.launch {
            repository.acknowledgeAlert(alertId)
            loadAlerts()  // recharge la liste après acquittement
        }
    }
}
```

**Étape 4 — Créer le Screen**

```kotlin
// ui/alerts/AlertsScreen.kt
@Composable
fun AlertsScreen(
    beehiveId: Int,
    viewModel: AlertsViewModel = viewModel(
        factory = AlertsViewModelFactory(beehiveId)
    )
) {
    val alerts by viewModel.alerts.collectAsState()

    LazyColumn(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        items(alerts) { alert ->
            Card(
                modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                colors = CardDefaults.cardColors(
                    containerColor = if (alert.severity == "critique")
                        MaterialTheme.colorScheme.errorContainer
                    else
                        MaterialTheme.colorScheme.secondaryContainer
                )
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(alert.message, modifier = Modifier.weight(1f))
                    if (!alert.isRead) {
                        TextButton(onClick = { viewModel.acknowledge(alert.id) }) {
                            Text("Acquitter")
                        }
                    }
                }
            }
        }
    }
}
```

**Étape 5 — Ajouter la route dans la navigation**

```kotlin
// MainActivity.kt ou NavGraph.kt
composable("alerts/{beehiveId}") { backStackEntry ->
    val beehiveId = backStackEntry.arguments?.getString("beehiveId")?.toInt() ?: return@composable
    AlertsScreen(beehiveId = beehiveId)
}

// Naviguer vers cet écran depuis le détail d'une ruche :
navController.navigate("alerts/$beehiveId")
```

### Appels API avec Retrofit

Retrofit génère automatiquement le code d'appel HTTP depuis une interface Kotlin.

```kotlin
// data/api/ApiClient.kt
object ApiClient {
    fun create(baseUrl: String): ApiService {
        val okHttpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(10, TimeUnit.SECONDS)
            .build()

        return Retrofit.Builder()
            .baseUrl(baseUrl)           // ex: "http://192.168.1.10:5001/"
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create())
            // Gson convertit automatiquement JSON ↔ data classes Kotlin
            .build()
            .create(ApiService::class.java)
    }
}
```

```kotlin
// Exemple d'appel dans le repository
class BeehiveRepository(private val api: ApiService, private val token: String) {
    suspend fun getBeehives(): List<Beehive> {
        // "Bearer $token" : format standard d'authentification HTTP
        return api.getBeehives("Bearer $token")
    }
}
```

### Commandes Gradle utiles

```bash
cd android

# Compiler et installer l'APK debug sur un appareil connecté
./gradlew installDebug

# Compiler l'APK debug sans l'installer
./gradlew assembleDebug
# Résultat : android/app/build/outputs/apk/debug/app-debug.apk

# Nettoyer le cache de build (utile en cas d'erreur bizarre)
./gradlew clean

# Vérifier les dépendances obsolètes
./gradlew dependencyUpdates

# Lancer les tests unitaires
./gradlew test

# Voir toutes les tâches disponibles
./gradlew tasks
```

**Installer l'APK sans cable (via réseau local) :**

```bash
# Activer le débogage sans fil sur Android 11+ :
# Paramètres → Options développeur → Débogage sans fil

# Connecter via adb
adb connect <ip-du-telephone>:5555
adb install app/build/outputs/apk/debug/app-debug.apk
```

---

## 6. Interactions entre les services

Voici comment les différents services communiquent, et comment les tester manuellement.

### ESP32 → Raspberry Pi (LoRa)

Le `lora/receiver.py` reçoit les paquets radio et les forward à Flask :

```bash
# Tester la réception manuellement (sans ESP32) avec simulate.py
cd tools
python simulate.py --ids 1 --interval 5

# Voir les logs du receiver LoRa
sudo journalctl -u beetter-lora -f
```

### Receiver → Flask (HTTP local)

```bash
# Tester l'endpoint d'ingest manuellement avec curl
curl -X POST http://localhost:5000/api/data \
  -H "Content-Type: application/json" \
  -d '{"id": 1, "t": 34.7, "h": 62.1}'

# Réponse attendue : {"status": "ok"}
```

### Flask → InfluxDB (interne Docker)

```bash
# Vérifier que les données arrivent bien dans InfluxDB
# Via l'interface web : http://<ip-pi>:8086
# Ou via curl :
curl -X POST http://localhost:8086/api/v2/query \
  -H "Authorization: Token <ton-token>" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket:"ruche") |> range(start:-1h) |> last()'
```

### Raspberry Pi → Serveur distant (HTTP)

```bash
# Forcer un push immédiat (normalement géré par le scheduler)
curl -X POST http://<ip-serveur>:5001/api/push \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{"beehive_id": 1, "readings": [{"t": 34.7, "h": 62.1, "timestamp": "2026-05-19T14:00:00Z"}]}'
```

### Serveur distant → App Android (HTTP)

```bash
# Tester le login
curl -X POST http://<ip-serveur>:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "charles", "password": "monmotdepasse"}'
# Réponse : {"token": "eyJ..."}

# Tester la liste des ruches avec le token
curl http://<ip-serveur>:5001/api/beehives \
  -H "Authorization: Bearer eyJ..."
```

---

## 7. Commandes utiles au quotidien

```bash
# ── Développement Flask local (rechargement automatique) ───
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask run --debug

# ── Sur le Raspberry Pi (production) ──────────────────────
./deploy.sh                    # pull GitHub + rebuild + redémarrage
./deploy.sh --no-build         # redémarrage rapide (templates/CSS seulement)
./deploy.sh --branch develop   # déployer une branche spécifique

docker compose logs -f         # logs temps réel (tous services)
docker compose logs -f web     # logs Flask uniquement
docker compose logs -f influxdb # logs InfluxDB
docker compose ps              # état des conteneurs
docker compose exec web bash   # shell dans le conteneur Flask
docker compose exec influxdb bash # shell dans le conteneur InfluxDB
docker compose down            # stopper tout
docker compose up -d --build   # rebuild et redémarrer

# ── Base de données PostgreSQL ─────────────────────────────
# Créer les tables après ajout d'un modèle :
docker compose exec web flask shell
>>> from app import db; db.create_all()

# Accéder à psql directement :
docker compose exec db psql -U beetter -d beetter

# ── InfluxDB ───────────────────────────────────────────────
# Interface web :
http://<ip-raspberry>:8086

# Shell InfluxDB :
docker compose exec influxdb influx

# ── Android ───────────────────────────────────────────────
cd android
./gradlew installDebug         # compiler et installer sur appareil
./gradlew assembleDebug        # compiler uniquement (APK dans build/outputs/)
./gradlew clean                # nettoyer le cache

# ── Git ───────────────────────────────────────────────────
git checkout -b feature/ma-feature
git add .
git commit -m "feat: description"
git push origin feature/ma-feature
# → Pull Request sur GitHub → merge sur main → ./deploy.sh
```

---

## 8. Convention de commits et règles d'équipe

### Convention de commits

```
feat:      nouvelle fonctionnalité
fix:       correction de bug
refactor:  restructuration sans changement visible
style:     CSS, mise en forme uniquement
docs:      documentation
chore:     maintenance (dépendances, Docker, config)
test:      ajout ou modification de tests
```

Exemples :
```
feat: ajout écran alertes dans l'app Android
fix: correction calcul score santé quand poids manquant
style: ajout animation sur les cartes ruche au survol
chore: mise à jour Flask 3.0.3 → 3.1.0
docs: ajout section InfluxDB dans CONTRIBUTING
```

### Règles de travail en équipe

**Le Pi ne pull que `main`.**

**Les secrets ne vont jamais dans Git.** Le fichier `.env` est dans `.gitignore`. Si un token apparaît dans un commit, il faut le révoquer immédiatement — les tokens visibles dans l'historique Git sont compromis même après suppression.

**Un composant par branche.** Ne mélange pas des modifications Flask et Android dans le même commit — ça rend les revues difficiles et les rollbacks impossibles.