# Développement de l'interface web — Beetter

Ce guide explique comment modifier et étendre le site web Flask qui tourne sur le Raspberry Pi. Il explique non seulement **comment** faire les choses, mais surtout **pourquoi** elles fonctionnent ainsi.

---

## Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| Backend | Python 3, Flask 3 | Logique serveur, routes, accès BDD |
| BDD relationnelle | PostgreSQL + SQLAlchemy | Utilisateurs, ruches, serveurs distants |
| BDD time-series | InfluxDB 2 | Relevés des capteurs |
| Templates | Jinja2 (HTML) | Rendu des pages côté serveur |
| CSS | Bootstrap 5 + `custom.css` | Mise en page et style |
| JS | Vanilla JS + Chart.js | Graphes et appels API |
| Conteneurisation | Docker Compose | Orchestration des services |

### Pourquoi Flask et pas Django ou FastAPI ?

Flask est un micro-framework : il ne force aucune structure, ne génère pas de code automatiquement, et ne fait que ce qu'on lui demande. C'est un bon choix ici car le projet est de taille maîtrisée, l'équipe apprend le framework, et on a besoin de la flexibilité pour mélanger du rendu HTML côté serveur (les pages) et une API JSON (pour les graphes et le mobile).

Django aurait imposé beaucoup plus de conventions. FastAPI est excellent pour des API pures mais moins adapté au rendu HTML.

### Pourquoi deux bases de données (PostgreSQL + InfluxDB) ?

Ce sont deux problèmes fondamentalement différents :

**PostgreSQL** stocke des données *structurelles* qui changent rarement : qui est l'apiculteur, comment s'appelle la ruche, quel est son emplacement. Ce sont des entités avec des relations entre elles (une ruche appartient à un apiculteur). SQL est conçu pour ça.

**InfluxDB** stocke des données *temporelles* qui arrivent en continu : température toutes les 5 minutes, humidité, audio. Ce type de données a des contraintes très différentes — on n'y fait presque jamais de mise à jour, on y fait beaucoup de requêtes "donne-moi la moyenne sur les 24 dernières heures". InfluxDB est optimisé pour ces lectures temporelles et est 10 à 100x plus rapide que PostgreSQL pour ce cas d'usage.

Essayer de tout mettre dans PostgreSQL fonctionnerait au début, mais deviendrait lent dès qu'on accumule quelques semaines de données sur plusieurs ruches.

### Pourquoi Docker Compose ?

Sur le Raspberry Pi, faire tourner Flask, PostgreSQL et InfluxDB séparément implique d'installer et configurer chaque service manuellement, de gérer les conflits de versions, et de s'assurer que tout redémarre correctement après un reboot.

Docker Compose résout ça en décrivant tous les services dans un seul fichier `compose.yml`. Un seul `docker compose up -d` démarre tout, dans le bon ordre, avec les bonnes variables d'environnement. Si le Pi redémarre, Docker redémarre les conteneurs automatiquement (`restart: unless-stopped` dans le compose).

---

## Structure du dossier `app/`

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

### Pourquoi cette séparation en dossiers ?

Sans organisation, une app Flask peut tenir dans un seul fichier de 50 lignes. Mais à mesure qu'elle grandit, un seul fichier devient ingérable. Le découpage en blueprints permet à plusieurs personnes de travailler en parallèle sur des sections différentes sans se marcher dessus. Un développeur peut travailler sur `beehives/` pendant qu'un autre travaille sur `auth/` — les deux sections sont complètement indépendantes.

---

## Comment Flask traite une requête — le cycle complet

Comprendre ce cycle est essentiel avant de modifier quoi que ce soit.

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

C'est ce qu'on appelle le rendu **côté serveur** (SSR — Server Side Rendering) : le serveur fait tout le travail, le navigateur reçoit un HTML déjà prêt à afficher. C'est différent des frameworks JS modernes (React, Vue) où le navigateur reçoit du JavaScript et construit le HTML lui-même.

Le choix du SSR ici est délibéré : la page se charge même sans JavaScript activé, et la complexité est moindre pour un projet d'école.

---

## Le pattern Blueprint — pourquoi et comment

Un Blueprint est un "sous-app" Flask qui regroupe tout ce qui concerne une section du site : ses routes, ses formulaires, ses templates. Il est ensuite enregistré dans l'app principale.

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

### Pourquoi un `__init__.py` dans chaque blueprint ?

Le `__init__.py` est ce qui fait d'un dossier un **module Python importable**. Sans lui, Python ne saurait pas que le dossier `beehives/` est un module — `from .blueprints.beehives import beehives_bp` ne fonctionnerait pas.

C'est dans ce fichier qu'on crée l'objet Blueprint et qu'on importe les routes pour qu'elles s'enregistrent :

```python
# blueprints/beehives/__init__.py
from flask import Blueprint

# url_prefix="/beehives" : toutes les routes de ce blueprint
# commenceront par /beehives — on n'a pas à le répéter dans chaque route
beehives_bp = Blueprint("beehives", __name__, url_prefix="/beehives")

# Cet import doit être en bas pour éviter les imports circulaires :
# routes.py importe beehives_bp, donc il faut que beehives_bp existe avant
from . import routes
```

---

## Comment ajouter une nouvelle page — étape par étape

### Exemple : ajouter une page "Alertes" à `/alertes`

**Étape 1 — Créer le blueprint**

```
blueprints/
└── alertes/
    ├── __init__.py
    └── routes.py
```

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
@login_required  # redirige vers /login si l'utilisateur n'est pas connecté
def index():
    # SQLAlchemy traduit ça en : SELECT * FROM alerte ORDER BY created_at DESC
    alertes = Alerte.query.order_by(Alerte.created_at.desc()).all()
    # render_template cherche le fichier dans templates/alertes/index.html
    # et injecte la variable alertes (accessible via {{ alertes }} en Jinja2)
    return render_template("alertes/index.html", alertes=alertes)

@alertes_bp.route("/<int:id>/acquitter", methods=["POST"])
@login_required
def acquitter(id):
    alerte = Alerte.query.get_or_404(id)  # renvoie 404 si l'ID n'existe pas
    alerte.lue = True
    db.session.commit()  # sauvegarde en base
    # url_for génère l'URL correcte même si on change le prefix plus tard
    return redirect(url_for("alertes.index"))
```

**Étape 3 — Enregistrer le blueprint dans `__init__.py`**

```python
# app/__init__.py
from .blueprints.alertes import alertes_bp
app.register_blueprint(alertes_bp)
# Sans cette ligne, Flask ne connaît pas ce blueprint
# et toutes ses routes retournent 404
```

**Étape 4 — Créer le template**

```html
<!-- templates/alertes/index.html -->
{% extends "base.html" %}
<!-- "extends" signifie : utilise base.html comme layout,
     et remplace le bloc "content" par ce qui suit.
     Tout ce qui est dans base.html (navbar, CSS, JS) est
     automatiquement inclus sans le réécrire. -->

{% block title %}Alertes{% endblock %}

{% block content %}
<h1 class="mb-4">Alertes</h1>

{% for alerte in alertes %}
<div class="alert alert-{{ 'danger' if alerte.severite == 'critique' else 'warning' }}">
  <strong>{{ alerte.ruche.name }}</strong> — {{ alerte.message }}
  <small class="text-muted ms-2">{{ alerte.created_at.strftime('%d/%m %H:%M') }}</small>

  {% if not alerte.lue %}
  <!-- On utilise un <form method="POST"> et non un <a href>
       car acquitter une alerte est une action qui modifie des données.
       Par convention HTTP, GET = lecture, POST = modification.
       Un lien GET pour modifier des données causerait des problèmes
       si le navigateur recharge la page ou si un robot la crawle. -->
  <form method="POST" action="{{ url_for('alertes.acquitter', id=alerte.id) }}"
        class="d-inline">
    <button type="submit" class="btn btn-sm btn-outline-secondary ms-2">
      Acquitter
    </button>
  </form>
  {% endif %}
</div>
{% endfor %}

{% if not alertes %}
<p class="text-muted">Aucune alerte.</p>
{% endif %}
{% endblock %}
```

**Étape 5 — Ajouter le lien dans la navbar**

```html
<!-- templates/base.html — dans la navbar -->
<li class="nav-item">
  <!-- url_for génère l'URL correcte même si on change le prefix plus tard.
       Ne jamais écrire href="/alertes" en dur. -->
  <a class="nav-link" href="{{ url_for('alertes.index') }}">Alertes</a>
</li>
```

---

## Les templates Jinja2 — syntaxe et pourquoi ça marche

Jinja2 est le moteur de templates intégré à Flask. Il fonctionne comme du HTML avec des "trous" que Flask remplit avant d'envoyer la page au navigateur.

### Pourquoi des templates et pas du HTML statique ?

Un fichier HTML statique est toujours identique. Avec Jinja2, le même template peut afficher la ruche n°1 ou la ruche n°42 selon les données passées par Flask — c'est le principe du rendu dynamique.

```html
<!-- Variables — {{ }} : injecte la valeur d'une variable Python -->
{{ beehive.name }}
{{ latest.temperature | round(1) }} °C
<!-- le filtre | round(1) est l'équivalent de round(x, 1) en Python -->

<!-- Conditions -->
{% if beehive.active %}
  <span class="badge bg-success">Active</span>
{% else %}
  <span class="badge bg-secondary">Inactive</span>
{% endif %}

<!-- Boucles — génère autant de <li> qu'il y a de ruches -->
{% for beehive in beehives %}
  <li>{{ beehive.name }}</li>
{% endfor %}

<!-- URL d'une route Flask — toujours utiliser url_for, jamais une URL en dur -->
<a href="{{ url_for('beehives.detail', id=beehive.id) }}">Voir</a>
<!-- url_for('beehives.detail', id=3) génère → /beehives/3 -->

<!-- Héritage de layout -->
{% extends "base.html" %}
{% block title %}Ma page{% endblock %}
{% block content %}
  <!-- contenu spécifique ici -->
{% endblock %}

<!-- Inclusion d'un sous-template réutilisable -->
{% include "components/chart_card.html" %}
```

### Pourquoi `url_for` plutôt que des liens en dur ?

Si on écrit `href="/beehives/3"` en dur et qu'on change plus tard le prefix du blueprint de `/beehives` à `/ruches`, tous les liens cassent. Avec `url_for('beehives.detail', id=3)`, Flask calcule toujours l'URL correcte automatiquement quelle que soit la configuration des routes.

---

## Ajouter un graphe Chart.js — comment ça s'articule

Le graphe fonctionne en deux temps :
1. Flask rend la page HTML avec juste un `<canvas>` vide
2. JavaScript fait un appel AJAX vers une route Flask qui retourne du JSON, puis dessine le graphe

Ce découpage existe pour une raison précise : si Flask essayait d'inclure toutes les données historiques dans le HTML initial, la page mettrait plusieurs secondes à charger. En séparant le chargement de la page et le chargement des données, la page s'affiche immédiatement et le graphe apparaît une fraction de seconde plus tard.

```html
<!-- templates/beehives/detail.html -->
{% extends "base.html" %}
{% block content %}

<!-- Le canvas est vide au chargement — JS le remplira après -->
<canvas id="tempChart" height="80"></canvas>

<script>
// fetch() envoie une requête GET asynchrone.
// La page n'est pas bloquée pendant l'attente de la réponse.
fetch("{{ url_for('api.beehive_data', id=beehive.id) }}?range=24h")
  .then(r => r.json())    // parse la réponse JSON
  .then(data => {
    // data est un tableau d'objets {time, temperature, humidity, ...}
    new Chart(document.getElementById("tempChart"), {
      type: "line",
      data: {
        labels: data.map(d => new Date(d.time).toLocaleTimeString()),
        datasets: [{
          label: "Température (°C)",
          data: data.map(d => d.temperature),
          borderColor: "#1D9E75",
          tension: 0.3,   // 0 = angulaire, 1 = très courbé
          fill: false
        }]
      },
      options: {
        responsive: true,  // s'adapte à la taille de l'écran
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: false } }
      }
    });
  });
</script>
{% endblock %}
```

La route Flask qui répond à cet appel :

```python
# blueprints/api/routes.py
@api_bp.route("/beehives/<int:id>/data")
@login_required
def beehive_data(id):
    # request.args.get : lit le paramètre d'URL ?range=24h
    # "24h" est la valeur par défaut si le paramètre est absent
    range_ = request.args.get("range", "24h")
    beehive = Beehive.query.get_or_404(id)
    data = get_history(beehive.id, range_)   # lit InfluxDB
    # jsonify convertit le dict/liste Python en JSON
    # et positionne le Content-Type: application/json dans les headers HTTP
    return jsonify(data)
```

---

## Accéder à InfluxDB depuis une route

```python
# blueprints/utils/influxdb.py
from influxdb_client import InfluxDBClient
from flask import current_app

def get_latest(beehive_id: int) -> dict:
    """Retourne le dernier relevé d'une ruche."""

    # current_app : proxy vers l'app Flask active.
    # On ne peut pas importer l'app directement (import circulaire),
    # Flask fournit ce proxy pour y accéder depuis n'importe où.
    client = InfluxDBClient(
        url=current_app.config["INFLUXDB_URL"],
        token=current_app.config["INFLUXDB_TOKEN"],
        org=current_app.config["INFLUXDB_ORG"],
    )

    # Flux (le langage de requête d'InfluxDB) se lit de haut en bas comme un pipe :
    # 1. from(bucket:...)  → sélectionne la base de données
    # 2. range(start:-1h)  → filtre les données de la dernière heure
    # 3. filter(...)       → filtre par measurement et par ruche
    # 4. last()            → garde uniquement la valeur la plus récente
    # 5. pivot(...)        → transforme les lignes en colonnes
    #    (sans pivot, chaque field est une ligne séparée ;
    #     avec pivot, tous les fields d'un même timestamp
    #     sont dans la même ligne — bien plus facile à utiliser)
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
    client = InfluxDBClient(...)
    query = f'''
        from(bucket: "{current_app.config["INFLUXDB_BUCKET"]}")
          |> range(start: -{range_})
          |> filter(fn: (r) => r._measurement == "releve")
          |> filter(fn: (r) => r.ruche_id == "{beehive_id}")
          |> aggregateWindow(every: 5m, fn: mean)
          |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    # aggregateWindow(every: 5m, fn: mean) :
    # regroupe les points par fenêtres de 5 minutes et calcule la moyenne.
    # Indispensable pour les longues périodes (7j, 30j) : sans ça,
    # on retournerait des milliers de points au navigateur inutilement.
    tables = client.query_api().query(query)
    return [r.values for t in tables for r in t.records]
```

---

## Modifier le style

**Bootstrap 5** est déjà inclus via `base.html`. Pour des styles personnalisés, édite `static/css/custom.css` — ce fichier est chargé après Bootstrap, donc ses règles ont priorité :

```css
/* static/css/custom.css */

.beehive-card {
  border-left: 4px solid var(--bs-success);
  transition: box-shadow 0.2s;
}
.beehive-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.health-score {
  font-size: 2.5rem;
  font-weight: 700;
}
```

---

## Les modèles SQLAlchemy — comment PostgreSQL est abstrait

SQLAlchemy permet d'écrire les interactions avec la base de données en Python pur, sans écrire de SQL à la main. Chaque classe Python = une table PostgreSQL.

```python
# models.py
class Beehive(db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    name     = db.Column(db.String(100), nullable=False)   # NOT NULL
    location = db.Column(db.String(200))                   # nullable
    lora_id  = db.Column(db.Integer, unique=True)          # UNIQUE
    active   = db.Column(db.Boolean, default=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    # relationship : permet beehive.owner directement en Python, sans JOIN SQL
    owner    = db.relationship("User", back_populates="beehives")
```

Utilisé dans une route :

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

---

## Commandes utiles au quotidien

```bash
# ── Développement local (rechargement automatique) ─────────
cd app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
flask run --debug              # rechargement auto à chaque modif .py

# ── Sur le Raspberry Pi (production) ───────────────────────
./deploy.sh                    # pull GitHub + rebuild + redémarrage
./deploy.sh --no-build         # redémarrage rapide (templates/CSS seulement)
./deploy.sh --branch develop   # déployer une branche spécifique

docker compose logs -f         # logs en temps réel (tous services)
docker compose logs -f web     # logs Flask uniquement
docker compose ps              # état des conteneurs
docker compose exec web bash   # shell dans le conteneur Flask
docker compose down            # stopper tout
docker compose up -d --build   # rebuild et redémarrer

# ── Base de données ─────────────────────────────────────────
# Après ajout d'un modèle dans models.py :
docker compose exec web flask shell
>>> from app import db; db.create_all()

# ── Git ─────────────────────────────────────────────────────
git checkout -b feature/ma-feature    # nouvelle branche
git add blueprints/ templates/        # fichiers modifiés
git commit -m "feat: description"
git push origin feature/ma-feature
# → Pull Request sur GitHub → merge sur main → ./deploy.sh
```

---

## Convention de commits

```
feat:      nouvelle fonctionnalité
fix:       correction de bug
refactor:  restructuration sans changement visible
style:     CSS, mise en forme uniquement
docs:      documentation
chore:     maintenance (dépendances, Docker, config)
```

Exemples :
```
feat: ajout graphe spectral audio sur page détail ruche
fix: correction calcul score santé quand poids manquant
style: ajout animation sur les cartes ruche au survol
chore: mise à jour Flask 3.0.3 → 3.1.0
```

---

## Règles de travail en équipe

**Les secrets ne vont jamais dans Git.** Le fichier `.env` est dans `.gitignore`. Si un token apparaît dans un commit, il faut le révoquer immédiatement — les tokens visibles dans l'historique Git sont compromis même après suppression.